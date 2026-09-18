"""Comprehensive failover tests for Gemini provider under simulated network & credential faults."""

import json
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from pydantic import SecretStr
from app.errors import GeminiCredentialError, LLMOutputValidationError, LLMProviderError
from app.llm.gemini_key_manager import CredentialStatus, GeminiCredential, GeminiKeyManager
from app.llm.providers.gemini_provider import GeminiDirectiveInterpreter

SAMPLE_VALID_GEMINI_PAYLOAD = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": json.dumps(
                            [
                                {
                                    "note_index": 0,
                                    "applies": True,
                                    "directive_type": "no_charge_window",
                                    "structured_adjustment": {"hours": [14, 15]},
                                    "explanation": "No charging between 2 PM and 4 PM",
                                }
                            ]
                        )
                    }
                ]
            }
        }
    ]
}


def make_test_key_manager():
    return GeminiKeyManager(
        credentials=[
            GeminiCredential("primary", SecretStr("test-key-primary")),
            GeminiCredential("backup_1", SecretStr("test-key-backup-1")),
            GeminiCredential("backup_2", SecretStr("test-key-backup-2")),
            GeminiCredential("backup_3", SecretStr("test-key-backup-3")),
            GeminiCredential("backup_4", SecretStr("test-key-backup-4")),
        ],
        failure_threshold=2,
        cooldown_seconds=10.0,
    )


@pytest.mark.asyncio
async def test_primary_success_uses_no_backup():
    km = make_test_key_manager()
    interpreter = GeminiDirectiveInterpreter(key_manager=km)

    mock_resp = httpx.Response(200, json=SAMPLE_VALID_GEMINI_PAYLOAD, request=httpx.Request("POST", "http://test"))

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        results = await interpreter.interpret(["Do not charge between 2 PM and 4 PM"], {"capacity_kwh": 200.0})

        assert len(results) == 1
        assert results[0].directive_type == "no_charge_window"

        # Exactly 1 request made, using primary key
        assert mock_post.call_count == 1
        call_headers = mock_post.call_args[1]["headers"]
        assert call_headers["X-goog-api-key"] == "test-key-primary"

        # Key manager metrics
        assert km.metrics["primary_successes"] == 1
        assert km.metrics["fallback_successes"] == 0


@pytest.mark.asyncio
async def test_primary_invalid_credential_fails_over_to_backup():
    km = make_test_key_manager()
    interpreter = GeminiDirectiveInterpreter(key_manager=km)

    auth_err_resp = httpx.Response(403, text='{"error": {"code": 403, "message": "API key not valid"}}', request=httpx.Request("POST", "http://test"))
    valid_resp = httpx.Response(200, json=SAMPLE_VALID_GEMINI_PAYLOAD, request=httpx.Request("POST", "http://test"))

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        # First call fails auth on primary, second call succeeds on backup_1
        mock_post.side_effect = [auth_err_resp, valid_resp]

        results = await interpreter.interpret(["Do not charge between 2 PM and 4 PM"], {"capacity_kwh": 200.0})

        assert len(results) == 1
        assert results[0].directive_type == "no_charge_window"
        assert mock_post.call_count == 2

        # Verify call 1 used primary, call 2 used backup_1
        c1_headers = mock_post.call_args_list[0][1]["headers"]
        c2_headers = mock_post.call_args_list[1][1]["headers"]
        assert c1_headers["X-goog-api-key"] == "test-key-primary"
        assert c2_headers["X-goog-api-key"] == "test-key-backup-1"

        # Primary must now be permanently INVALID
        primary_cred = next(c for c in km.credentials if c.label == "primary")
        assert primary_cred.status == CredentialStatus.INVALID

        # Backup_1 is healthy and recorded success
        assert km.metrics["auth_failures"] == 1
        assert km.metrics["fallback_successes"] == 1


@pytest.mark.asyncio
async def test_primary_timeout_fails_over_to_backup():
    km = make_test_key_manager()
    interpreter = GeminiDirectiveInterpreter(key_manager=km)

    valid_resp = httpx.Response(200, json=SAMPLE_VALID_GEMINI_PAYLOAD, request=httpx.Request("POST", "http://test"))

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        # First call times out on primary, second succeeds on backup_1
        mock_post.side_effect = [httpx.TimeoutException("Timeout"), valid_resp]

        results = await interpreter.interpret(["Do not charge between 2 PM and 4 PM"], {"capacity_kwh": 200.0})

        assert len(results) == 1
        assert results[0].directive_type == "no_charge_window"
        assert mock_post.call_count == 2

        assert km.metrics["timeouts"] == 1
        assert km.metrics["fallback_successes"] == 1


@pytest.mark.asyncio
async def test_multiple_failed_credentials_respects_max_attempts():
    km = make_test_key_manager()
    # Limit max attempts to 2
    interpreter = GeminiDirectiveInterpreter(key_manager=km, max_attempts=2)

    err_resp = httpx.Response(500, text="Internal Server Error", request=httpx.Request("POST", "http://test"))
    valid_resp = httpx.Response(200, json=SAMPLE_VALID_GEMINI_PAYLOAD, request=httpx.Request("POST", "http://test"))

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        # Primary fails (500), Backup_1 fails (500), Backup_2 would succeed but shouldn't be called
        mock_post.side_effect = [err_resp, err_resp, valid_resp]

        with pytest.raises(LLMProviderError, match="Gemini service error"):
            await interpreter.interpret(["Do not charge between 2 PM and 4 PM"], {"capacity_kwh": 200.0})

        # Exactly 2 attempts made because max_attempts=2
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_all_credentials_fail_controlled_error():
    km = make_test_key_manager()
    interpreter = GeminiDirectiveInterpreter(key_manager=km, max_attempts=3)

    err_resp = httpx.Response(503, text="Service Unavailable", request=httpx.Request("POST", "http://test"))

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [err_resp, err_resp, err_resp]

        with pytest.raises(LLMProviderError):
            await interpreter.interpret(["Do not charge between 2 PM and 4 PM"], {"capacity_kwh": 200.0})

        # Bounded 5xx failure stops after 2 attempts to prevent burning all keys on outage
        assert mock_post.call_count == 2


@pytest.mark.asyncio
async def test_quota_429_bounded_failover():
    km = make_test_key_manager()
    interpreter = GeminiDirectiveInterpreter(key_manager=km, max_attempts=5)

    rate_err = httpx.Response(429, text="Resource Exhausted", request=httpx.Request("POST", "http://test"))

    with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = [rate_err, rate_err, rate_err, rate_err, rate_err]

        with pytest.raises(LLMProviderError, match="HTTP 429"):
            await interpreter.interpret(["Do not charge"], {"capacity_kwh": 200.0})

        # Must NOT burn through all 5 keys on 429 quota exhaustion (bounded at 2)
        assert mock_post.call_count == 2
        assert km.metrics["rate_limit_429s"] == 2


@pytest.mark.asyncio
async def test_deadline_expired_halts_failover():
    km = make_test_key_manager()
    # Set tight total deadline of 0.2 seconds (less than min_safe_attempt_time 0.3s)
    interpreter = GeminiDirectiveInterpreter(key_manager=km, total_deadline=0.2)

    with pytest.raises(LLMProviderError, match="deadline"):
        await interpreter.interpret(["Do not charge"], {"capacity_kwh": 200.0})
