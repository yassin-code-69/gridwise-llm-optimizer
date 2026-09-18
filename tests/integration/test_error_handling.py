"""Integration tests for controlled error handling and status codes."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_malformed_json_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/optimize-energy",
            content="{ invalid json syntax ...",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data


@pytest.mark.asyncio
async def test_missing_required_field_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/optimize-energy",
            json={"scenario_id": "MISSING-BATTERY"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "RequestValidationError"
