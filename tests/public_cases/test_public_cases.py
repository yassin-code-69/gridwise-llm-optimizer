"""Regression tests verifying all 10 official public sample cases."""

import pytest
from app.schemas.request import OptimizationRequest
from app.services.optimization_service import optimization_service


@pytest.mark.asyncio
async def test_all_ten_public_cases(sample_public_cases):
    """Verifies that all 10 public cases pass end-to-end interpretation, optimization, and replay."""
    assert len(sample_public_cases) == 10

    for case in sample_public_cases:
        sc_id = case["scenario_id"]
        req = OptimizationRequest(
            scenario_id=sc_id,
            operator_notes=case["operator_notes"],
            hours=case["hours"],
            battery=case["battery"],
        )
        res = await optimization_service.optimize(req)

        # 1. Invariant verification
        assert res.scenario_id == sc_id
        assert len(res.directive_interpretation) == len(case["operator_notes"])
        assert len(res.hourly_plan) == 24
        assert res.total_grid_kwh > 0
        assert res.total_cost_bdt > 0
        assert res.peak_grid_kwh > 0
        assert len(res.plan_summary) > 0

        # 2. Semantic matching against expected directive types
        expected = case.get("expected_interpretations", [])
        for exp_item, act_item in zip(expected, res.directive_interpretation):
            assert act_item.directive_type == exp_item["directive_type"], (
                f"{sc_id}: expected directive {exp_item['directive_type']}, got {act_item.directive_type}"
            )
            assert act_item.applies == exp_item["applies"]
