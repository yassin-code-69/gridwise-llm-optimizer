"""Google Gemini directive interpreter with primary-first credential management and bounded failover."""

import json
import logging
import re
import time
from typing import Any, Optional
import httpx
from pydantic import SecretStr
from app.config import settings
from app.errors import GeminiCredentialError, LLMOutputValidationError, LLMProviderError
from app.llm.base import DirectiveInterpreter
from app.llm.gemini_key_manager import GeminiCredential, GeminiKeyManager, gemini_key_manager
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas.directives import DirectiveInterpretation

logger = logging.getLogger(__name__)


class GeminiDirectiveInterpreter(DirectiveInterpreter):
    """Interprets operator notes using Google Gemini generative API with primary-first credential failover."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        key_manager: Optional[GeminiKeyManager] = None,
        request_timeout: Optional[float] = None,
        total_deadline: Optional[float] = None,
        max_attempts: Optional[int] = None,
    ):
        self.model = model or settings.GEMINI_MODEL or "gemini-flash-lite-latest"
        self.request_timeout = request_timeout or settings.GEMINI_REQUEST_TIMEOUT_SECONDS
        self.total_deadline = total_deadline or settings.GEMINI_TOTAL_DEADLINE_SECONDS
        self.max_attempts = max_attempts or settings.GEMINI_MAX_ATTEMPTS

        if key_manager:
            self.key_manager = key_manager
        elif api_key:
            # Backwards compatibility: Wrap explicit key as primary credential
            self.key_manager = GeminiKeyManager(
                credentials=[GeminiCredential(label="primary", secret=SecretStr(api_key))]
            )
        else:
            self.key_manager = gemini_key_manager

    def _clean_markdown_fence(self, text: str) -> str:
        """Strips markdown code fences (```json ... ```) from model text output."""
        clean = text.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean)
        return clean.strip()

    async def interpret(
        self,
        operator_notes: list[str],
        battery_context: dict[str, Any],
    ) -> list[DirectiveInterpretation]:
        """Interprets operator notes into typed directives using primary-first, deadline-aware failover.

        Raises:
            LLMProviderError / GeminiCredentialError: When all eligible attempts fail or deadline expires.
            LLMOutputValidationError: When model responses fail schema or guardrail validation.
        """
        if not self.key_manager.has_credentials():
            raise GeminiCredentialError(
                credential_label="none",
                reason="no_credentials_configured",
                details={"message": "No Gemini credentials configured. Set GEMINI_API_KEY_PRIMARY."},
            )

        user_prompt = build_user_prompt(operator_notes, battery_context)
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.0,
            },
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        t_start = time.perf_counter()
        attempt = 0
        excluded_labels: set[str] = set()
        last_error: Optional[Exception] = None

        rate_limit_count = 0
        server_error_count = 0
        model_output_error_count = 0

        while attempt < self.max_attempts:
            now = time.perf_counter()
            elapsed = now - t_start
            remaining_deadline = self.total_deadline - elapsed

            # Deadline-aware check: enforce minimum safe attempt window (0.3s)
            min_safe_attempt_time = 0.3
            if remaining_deadline <= min_safe_attempt_time:
                logger.warning(
                    f"Gemini failover deadline reached: elapsed={elapsed:.2f}s, deadline={self.total_deadline:.2f}s. "
                    f"Halting failover to preserve service responsiveness."
                )
                break

            credential = self.key_manager.select_next_healthy(excluded_labels=excluded_labels)
            if not credential:
                logger.warning("No healthy Gemini credentials available in key manager.")
                break

            attempt += 1
            label = credential.label
            excluded_labels.add(label)

            attempt_timeout = min(self.request_timeout, remaining_deadline)
            headers = {
                "Content-Type": "application/json",
                "X-goog-api-key": credential.get_secret_value(),
            }

            attempt_t0 = time.perf_counter()

            try:
                async with httpx.AsyncClient(timeout=attempt_timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    attempt_latency_ms = (time.perf_counter() - attempt_t0) * 1000.0

                    # 1. Successful HTTP 200 response
                    if response.status_code == 200:
                        data = response.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        clean_json = self._clean_markdown_fence(raw_text)
                        parsed = json.loads(clean_json)

                        if isinstance(parsed, list):
                            raw_list = parsed
                        elif isinstance(parsed, dict) and "interpretations" in parsed:
                            raw_list = parsed["interpretations"]
                        else:
                            raw_list = next((v for v in parsed.values() if isinstance(v, list)), [parsed])

                        interpretations = [DirectiveInterpretation.model_validate(item) for item in raw_list]

                        self.key_manager.record_success(label)
                        logger.info(
                            f"Gemini attempt={attempt} credential={label} result=success latency_ms={attempt_latency_ms:.1f}"
                        )
                        return interpretations

                    # 2. Authentication / Authorization Failure (401, 403 API_KEY_INVALID)
                    elif response.status_code in (401, 403):
                        err_text = response.text[:200]
                        self.key_manager.record_failure(label, "auth_failure", is_permanent=True)
                        last_error = GeminiCredentialError(
                            credential_label=label,
                            reason="authentication_failed",
                            details={"status": response.status_code, "err": err_text},
                        )
                        logger.error(
                            f"Gemini attempt={attempt} credential={label} result=auth_failure status={response.status_code} "
                            f"latency_ms={attempt_latency_ms:.1f}. Credential permanently disabled for this process."
                        )
                        continue  # Immediately try next healthy backup credential

                    # 3. Quota Exhaustion / Rate Limit (429)
                    elif response.status_code == 429:
                        err_text = response.text[:200]
                        rate_limit_count += 1
                        self.key_manager.record_failure(label, "rate_limit_429", is_permanent=False)
                        last_error = LLMProviderError(
                            f"Gemini API quota exceeded (HTTP 429) on credential '{label}': {err_text}"
                        )
                        logger.warning(
                            f"Gemini attempt={attempt} credential={label} result=rate_limit_429 latency_ms={attempt_latency_ms:.1f}"
                        )
                        # Do not blindly cycle all credentials on quota exhaustion (Context Rule 10)
                        if rate_limit_count >= 2:
                            logger.warning("Multiple credentials encountered 429 quota exhaustion. Halting failover.")
                            break
                        continue

                    # 4. Service-side Errors (5xx)
                    elif response.status_code >= 500:
                        err_text = response.text[:200]
                        server_error_count += 1
                        self.key_manager.record_failure(label, "service_error_5xx", is_permanent=False)
                        last_error = LLMProviderError(
                            f"Gemini service error (HTTP {response.status_code}) on credential '{label}': {err_text}"
                        )
                        logger.warning(
                            f"Gemini attempt={attempt} credential={label} result=service_error_5xx status={response.status_code} "
                            f"latency_ms={attempt_latency_ms:.1f}"
                        )
                        # Bounded 5xx failover (Context Rule 9)
                        if server_error_count >= 2:
                            logger.warning("Gemini service outage detected across multiple attempts. Halting failover.")
                            break
                        continue

                    else:
                        err_text = response.text[:200]
                        self.key_manager.record_failure(label, "http_error", is_permanent=False)
                        last_error = LLMProviderError(
                            f"Gemini HTTP {response.status_code} on credential '{label}': {err_text}"
                        )
                        logger.warning(
                            f"Gemini attempt={attempt} credential={label} result=http_error status={response.status_code}"
                        )
                        continue

            except httpx.TimeoutException as exc:
                attempt_latency_ms = (time.perf_counter() - attempt_t0) * 1000.0
                self.key_manager.record_failure(label, "transport_timeout", is_permanent=False)
                last_error = LLMProviderError(
                    f"Gemini request timed out after {attempt_timeout:.2f}s on credential '{label}'"
                )
                logger.warning(
                    f"Gemini attempt={attempt} credential={label} result=timeout timeout_s={attempt_timeout:.2f} "
                    f"latency_ms={attempt_latency_ms:.1f}"
                )
                continue

            except (json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
                attempt_latency_ms = (time.perf_counter() - attempt_t0) * 1000.0
                model_output_error_count += 1
                self.key_manager.record_failure(label, "invalid_model_output", is_permanent=False)
                last_error = LLMOutputValidationError(
                    f"Gemini returned malformed or unparseable structured output on credential '{label}': {exc}"
                )
                logger.warning(
                    f"Gemini attempt={attempt} credential={label} result=invalid_model_output latency_ms={attempt_latency_ms:.1f}"
                )
                # Bounded retry for model outputs (Context Rule 11)
                if model_output_error_count >= 2:
                    break
                continue

            except Exception as exc:
                attempt_latency_ms = (time.perf_counter() - attempt_t0) * 1000.0
                self.key_manager.record_failure(label, "transport_network_error", is_permanent=False)
                last_error = LLMProviderError(
                    f"Gemini transport error on credential '{label}': {exc}"
                )
                logger.warning(
                    f"Gemini attempt={attempt} credential={label} result=network_error latency_ms={attempt_latency_ms:.1f}"
                )
                continue

        if last_error:
            raise last_error
        raise LLMProviderError("All eligible Gemini credentials failed within the request deadline.")
