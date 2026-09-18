"""Unit tests for GeminiKeyManager, credential health tracking, and circuit breaker."""

import threading
import time
from pydantic import SecretStr
from app.llm.gemini_key_manager import CredentialStatus, GeminiCredential, GeminiKeyManager


def test_gemini_credential_masking():
    secret = SecretStr("SUPER_SECRET_KEY_12345")
    cred = GeminiCredential(label="primary", secret=secret)

    # Verify secret is accessible via method strictly for headers
    assert cred.get_secret_value() == "SUPER_SECRET_KEY_12345"

    # Verify str and repr NEVER contain the secret
    assert "SUPER_SECRET_KEY" not in str(cred)
    assert "SUPER_SECRET_KEY" not in repr(cred)
    assert cred.label == "primary"
    assert cred.status == CredentialStatus.HEALTHY


def test_primary_first_selection_priority():
    c1 = GeminiCredential("primary", SecretStr("key1"))
    c2 = GeminiCredential("backup_1", SecretStr("key2"))
    c3 = GeminiCredential("backup_2", SecretStr("key3"))

    mgr = GeminiKeyManager(credentials=[c1, c2, c3])

    # Default selection must always be primary when healthy
    selected = mgr.select_next_healthy()
    assert selected is not None
    assert selected.label == "primary"

    # Repeated calls must continue preferring primary (no round-robin)
    for _ in range(5):
        s = mgr.select_next_healthy()
        assert s.label == "primary"


def test_excluded_labels_failover():
    c1 = GeminiCredential("primary", SecretStr("key1"))
    c2 = GeminiCredential("backup_1", SecretStr("key2"))
    c3 = GeminiCredential("backup_2", SecretStr("key3"))

    mgr = GeminiKeyManager(credentials=[c1, c2, c3])

    # When primary is excluded (e.g. attempted in current request), select backup_1
    s1 = mgr.select_next_healthy(excluded_labels={"primary"})
    assert s1.label == "backup_1"

    # When primary and backup_1 are excluded, select backup_2
    s2 = mgr.select_next_healthy(excluded_labels={"primary", "backup_1"})
    assert s2.label == "backup_2"

    # When all are excluded, returns None
    s3 = mgr.select_next_healthy(excluded_labels={"primary", "backup_1", "backup_2"})
    assert s3 is None


def test_auth_failure_permanently_disables_credential():
    c1 = GeminiCredential("primary", SecretStr("bad_key"))
    c2 = GeminiCredential("backup_1", SecretStr("good_key"))

    mgr = GeminiKeyManager(credentials=[c1, c2])

    # Record permanent auth failure on primary
    mgr.record_failure("primary", error_category="auth_failure", is_permanent=True)

    assert c1.status == CredentialStatus.INVALID
    assert not c1.is_available(time.time())

    # Next request must automatically pick backup_1 without needing excluded_labels
    next_cred = mgr.select_next_healthy()
    assert next_cred.label == "backup_1"


def test_circuit_breaker_transient_failures_and_recovery():
    c1 = GeminiCredential("primary", SecretStr("key1"))
    c2 = GeminiCredential("backup_1", SecretStr("key2"))

    mgr = GeminiKeyManager(credentials=[c1, c2], failure_threshold=2, cooldown_seconds=0.2)

    # 1st transient failure
    mgr.record_failure("primary", error_category="transport_timeout", is_permanent=False)
    assert c1.status == CredentialStatus.HEALTHY
    assert mgr.select_next_healthy().label == "primary"

    # 2nd transient failure -> trips circuit breaker
    mgr.record_failure("primary", error_category="transport_timeout", is_permanent=False)
    assert c1.status == CredentialStatus.TEMPORARILY_DISABLED

    # Primary is temporarily disabled, so backup_1 is chosen
    assert mgr.select_next_healthy().label == "backup_1"

    # Wait for cooldown to expire (0.2s)
    time.sleep(0.25)

    # Primary should automatically recover to HEALTHY upon next check
    recovered = mgr.select_next_healthy()
    assert recovered.label == "primary"
    assert c1.status == CredentialStatus.HEALTHY


def test_concurrency_thread_safety():
    c1 = GeminiCredential("primary", SecretStr("key1"))
    c2 = GeminiCredential("backup_1", SecretStr("key2"))
    mgr = GeminiKeyManager(credentials=[c1, c2], failure_threshold=10, cooldown_seconds=1.0)

    errors = []

    def worker(worker_id: int):
        try:
            for _ in range(50):
                cred = mgr.select_next_healthy()
                if cred:
                    if worker_id % 2 == 0:
                        mgr.record_success(cred.label)
                    else:
                        mgr.record_failure(cred.label, error_category="transport_timeout", is_permanent=False)
                else:
                    time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    stats = mgr.get_stats()
    assert "credentials" in stats
    assert "metrics" in stats
