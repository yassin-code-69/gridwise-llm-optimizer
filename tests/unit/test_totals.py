"""Unit tests for totals recalculation."""

from app.core.totals import recalculate_totals
from app.schemas.response import HourlyPlanEntry


def test_recalculate_totals_exactness(sample_hours):
    plan = [
        HourlyPlanEntry(
            hour=h,
            grid_kwh=10.0,
            solar_used_kwh=0.0,
            battery_action="idle",
            battery_kwh=0.0,
            battery_energy_after_kwh=100.0,
        )
        for h in range(24)
    ]

    total_grid, total_cost, peak_grid = recalculate_totals(plan, sample_hours)

    assert total_grid == 240.0
    expected_cost = sum(10.0 * sample_hours[h].tariff_bdt_per_kwh for h in range(24))
    assert abs(total_cost - expected_cost) < 1e-4
    assert peak_grid == 10.0
