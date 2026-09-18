"""Gemini primary and backup credential manager with health tracking and circuit breaking."""

import logging
import threading
import time
from enum import Enum
from typing import Any, Optional
from pydantic import SecretStr
from app.config import settings
from app.errors import ConfigurationError

logger = logging.getLogger(__name__)


class CredentialStatus(str, Enum):
    HEALTHY = "HEALTHY"
    TEMPORARILY_DISABLED = "TEMPORARILY_DISABLED"
    INVALID = "INVALID"


class GeminiCredential:
    """Encapsulates a single Gemini API credential with safe masking and health tracking."""

    def __init__(self, label: str, secret: SecretStr):
        self.label = label
        self._secret = secret
        self.status = CredentialStatus.HEALTHY
        self.consecutive_failures: int = 0
        self.disabled_until: float = 0.0
        self.last_error_type: Optional[str] = None
        self.total_attempts: int = 0
        self.total_successes: int = 0

    def get_secret_value(self) -> str:
        """Returns the raw secret string strictly for HTTP authorization headers."""
        return self._secret.get_secret_value()

    def is_available(self, current_time: float) -> bool:
        """Checks if the credential is currently eligible for request dispatch."""
        if self.status == CredentialStatus.INVALID:
            return False
        if self.status == CredentialStatus.TEMPORARILY_DISABLED:
            if current_time >= self.disabled_until:
                # Cooldown elapsed: reset consecutive failures and restore to healthy
                self.status = CredentialStatus.HEALTHY
                self.consecutive_failures = 0
                return True
            return False
        return True

    def __repr__(self) -> str:
        return f"<GeminiCredential label={self.label} status={self.status.value}>"

    def __str__(self) -> str:
        return self.__repr__()


class GeminiKeyManager:
    """Manages ordered Gemini credentials, primary-first selection, health state, and circuit breakers.

    Thread-safe for concurrent async requests: locks are held only briefly during in-memory state
    transitions and never across external network calls.
    """

    def __init__(
        self,
        credentials: Optional[list[GeminiCredential]] = None,
        failure_threshold: Optional[int] = None,
        cooldown_seconds: Optional[float] = None,
    ):
        self._lock = threading.Lock()
        self.failure_threshold = failure_threshold or settings.GEMINI_CIRCUIT_FAILURE_THRESHOLD
        self.cooldown_seconds = cooldown_seconds or settings.GEMINI_CIRCUIT_COOLDOWN_SECONDS

        if credentials is not None:
            self.credentials = credentials
        else:
            self.credentials = self._load_configured_credentials()

        # Aggregate observability metrics
        self.metrics = {
            "total_requests": 0,
            "primary_successes": 0,
            "fallback_successes": 0,
            "auth_failures": 0,
            "rate_limit_429s": 0,
            "service_error_5xxs": 0,
            "timeouts": 0,
            "invalid_outputs": 0,
        }

    def _load_configured_credentials(self) -> list[GeminiCredential]:
        """Builds the ordered credential list: PRIMARY -> BACKUP_1 -> ... -> BACKUP_4."""
        creds: list[GeminiCredential] = []

        raw_pairs = [
            ("primary", settings.GEMINI_API_KEY_PRIMARY),
            ("backup_1", settings.GEMINI_API_KEY_BACKUP_1),
            ("backup_2", settings.GEMINI_API_KEY_BACKUP_2),
            ("backup_3", settings.GEMINI_API_KEY_BACKUP_3),
            ("backup_4", settings.GEMINI_API_KEY_BACKUP_4),
        ]

        for label, secret in raw_pairs:
            if secret and secret.get_secret_value().strip():
                creds.append(GeminiCredential(label=label, secret=secret))

        return creds

    def has_credentials(self) -> bool:
        """Returns True if at least one credential is configured."""
        with self._lock:
            return len(self.credentials) > 0

    def select_next_healthy(self, excluded_labels: Optional[set[str]] = None) -> Optional[GeminiCredential]:
        """Selects the highest-priority healthy credential (strictly PRIMARY-first).

        Args:
            excluded_labels: Labels already attempted in the current request to avoid retrying the same key.
        """
        excluded = excluded_labels or set()
        now = time.time()

        with self._lock:
            for cred in self.credentials:
                if cred.label in excluded:
                    continue
                if cred.is_available(now):
                    cred.total_attempts += 1
                    return cred
            return None

    def record_success(self, label: str) -> None:
        """Marks a credential as healthy and resets consecutive failure counters."""
        with self._lock:
            for cred in self.credentials:
                if cred.label == label:
                    cred.status = CredentialStatus.HEALTHY
                    cred.consecutive_failures = 0
                    cred.total_successes += 1
                    break

            if label == "primary":
                self.metrics["primary_successes"] += 1
            else:
                self.metrics["fallback_successes"] += 1

    def record_failure(self, label: str, error_category: str, is_permanent: bool = False) -> None:
        """Records a failure and triggers the circuit breaker if the threshold is met.

        Args:
            label: The credential label (e.g. 'primary', 'backup_1').
            error_category: One of ('auth_failure', 'rate_limit_429', 'service_error_5xx', 'transport_timeout', 'invalid_model_output').
            is_permanent: If True (e.g. 401/403 invalid API key), permanently marks INVALID for current process.
        """
        now = time.time()

        with self._lock:
            # Update metrics
            if error_category == "auth_failure":
                self.metrics["auth_failures"] += 1
            elif error_category == "rate_limit_429":
                self.metrics["rate_limit_429s"] += 1
            elif error_category == "service_error_5xx":
                self.metrics["service_error_5xxs"] += 1
            elif error_category == "transport_timeout":
                self.metrics["timeouts"] += 1
            elif error_category == "invalid_model_output":
                self.metrics["invalid_outputs"] += 1

            for cred in self.credentials:
                if cred.label == label:
                    cred.last_error_type = error_category
                    if is_permanent:
                        cred.status = CredentialStatus.INVALID
                        logger.error(
                            f"Gemini credential '{label}' permanently marked INVALID due to authentication/revocation failure."
                        )
                    else:
                        cred.consecutive_failures += 1
                        if cred.consecutive_failures >= self.failure_threshold:
                            cred.status = CredentialStatus.TEMPORARILY_DISABLED
                            cred.disabled_until = now + self.cooldown_seconds
                            logger.warning(
                                f"Gemini credential '{label}' circuit opened: TEMPORARILY_DISABLED for {self.cooldown_seconds}s "
                                f"(failures={cred.consecutive_failures}, threshold={self.failure_threshold})."
                            )
                    break

    def get_stats(self) -> dict[str, Any]:
        """Returns safe, non-sensitive credential health status and aggregate metrics."""
        now = time.time()
        with self._lock:
            cred_status = []
            for c in self.credentials:
                cred_status.append(
                    {
                        "label": c.label,
                        "status": c.status.value,
                        "consecutive_failures": c.consecutive_failures,
                        "is_available": c.is_available(now),
                        "total_attempts": c.total_attempts,
                        "total_successes": c.total_successes,
                        "last_error": c.last_error_type,
                    }
                )
            return {
                "credentials": cred_status,
                "metrics": dict(self.metrics),
            }

    def reset(self) -> None:
        """Resets state for testing and clean test isolation."""
        with self._lock:
            for c in self.credentials:
                c.status = CredentialStatus.HEALTHY
                c.consecutive_failures = 0
                c.disabled_until = 0.0
                c.last_error_type = None
                c.total_attempts = 0
                c.total_successes = 0
            for k in self.metrics:
                self.metrics[k] = 0


# Global singleton instance for runtime application use
gemini_key_manager = GeminiKeyManager()
