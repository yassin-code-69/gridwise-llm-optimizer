"""Unit tests for plan reconstruction."""

from app.core.optimizer import RawOptimizationResult
from app.core.reconstruction import reconstruct_hourly_plan
from app.schemas.request import OptimizationRequest


def test_reconstruction_action_mapping(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="RECON-01",
        operator_notes=["Note 1"],
        hours=sample_hours,
        battery=sample_battery,
    )

    # Synthetic raw result: hour 0 charges, hour 1 discharges, hour 2 idle
    raw = RawOptimizationResult(
        grid=[50.0] * 24,
        solar_used=[0.0] * 24,
        battery_flow=[20.0, -15.0, 1e-9] + [0.0] * 21,
        battery_energy=[120.0, 105.0, 105.0] + [100.0] * 21,
        objective_cost=1000.0,
    )

    plan = reconstruct_hourly_plan(req, raw)

    assert plan[0].battery_action == "charge"
    assert plan[0].battery_kwh == 20.0

    assert plan[1].battery_action == "discharge"
    assert plan[1].battery_kwh == 15.0

    assert plan[2].battery_action == "idle"
    assert plan[2].battery_kwh == 0.0
