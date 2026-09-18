"""Integration tests for FastAPI HTTP endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_optimize_energy_endpoint(sample_public_cases):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        case = sample_public_cases[0]
        payload = {
            "scenario_id": case["scenario_id"],
            "operator_notes": case["operator_notes"],
            "hours": case["hours"],
            "battery": case["battery"],
        }
        resp = await client.post("/optimize-energy", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_id"] == case["scenario_id"]
        assert len(data["directive_interpretation"]) == len(case["operator_notes"])
        assert len(data["hourly_plan"]) == 24
        assert data["total_grid_kwh"] > 0
        assert data["total_cost_bdt"] > 0
        assert data["peak_grid_kwh"] > 0
