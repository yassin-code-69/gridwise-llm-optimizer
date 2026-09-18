"""Replay corruption tests ensuring the independent validator catches all invariant violations."""

import copy
import pytest
from app.core.constraint_compiler import compile_constraints
from app.core.optimizer import solve_energy_schedule
from app.core.reconstruction import reconstruct_hourly_plan
from app.core.replay_validator import validate_hourly_plan_replay
from app.errors import ReplayValidationError
from app.schemas.directives import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
)
from app.schemas.request import OptimizationRequest


@pytest.fixture
def valid_plan_and_context(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="CORRUPT-TEST",
        operator_notes=["Solar 50% cut", "Reserve 100 kWh"],
        hours=sample_hours,
        battery=sample_battery,
    )
    directives = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment=SolarReductionAdjustment(hours=[11, 12, 13], factor=0.5),
            explanation="50% cut",
        ),
        DirectiveInterpretation(
            note_index=1,
            applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment=MinimumBatteryReserveAdjustment(hours=[18, 19, 20], minimum_energy_kwh=100.0),
            explanation="100 kWh reserve",
        ),
    ]
    constraints = compile_constraints(req, directives)
    raw = solve_energy_schedule(req, constraints)
    plan = reconstruct_hourly_plan(req, raw)
    # Sanity check: valid plan passes
    validate_hourly_plan_replay(req, constraints, plan)
    return req, constraints, plan


def test_corrupt_solar_exceeded(valid_plan_and_context):
    req, constraints, plan = valid_plan_and_context
    corrupt_plan = copy.deepcopy(plan)
    # Exceed solar at hour 12
    corrupt_plan[12].solar_used_kwh += 50.0
    with pytest.raises(ReplayValidationError, match="Solar used|Energy balance"):
        validate_hourly_plan_replay(req, constraints, corrupt_plan)


def test_corrupt_battery_energy_after(valid_plan_and_context):
    req, constraints, plan = valid_plan_and_context
    corrupt_plan = copy.deepcopy(plan)
    # Alter battery_energy_after_kwh
    corrupt_plan[5].battery_energy_after_kwh += 15.0
    with pytest.raises(ReplayValidationError, match="Battery transition mismatch"):
        validate_hourly_plan_replay(req, constraints, corrupt_plan)


def test_corrupt_energy_balance(valid_plan_and_context):
    req, constraints, plan = valid_plan_and_context
    corrupt_plan = copy.deepcopy(plan)
    # Increase grid by 20 without changing demand or battery flow
    corrupt_plan[10].grid_kwh += 20.0
    with pytest.raises(ReplayValidationError, match="Energy balance violation"):
        validate_hourly_plan_replay(req, constraints, corrupt_plan)


def test_corrupt_reserve_violated(valid_plan_and_context):
    req, constraints, plan = valid_plan_and_context
    corrupt_plan = copy.deepcopy(plan)
    # Force battery below reserve at hour 18
    corrupt_plan[18].battery_energy_after_kwh = 30.0  # Required is 100.0
    with pytest.raises(ReplayValidationError, match="Battery energy .* below required reserve|Battery transition mismatch"):
        validate_hourly_plan_replay(req, constraints, corrupt_plan)
