"""Unit tests for independent replay validator."""

import pytest
from app.core.constraint_compiler import compile_constraints
from app.core.replay_validator import validate_hourly_plan_replay
from app.errors import ReplayValidationError
from app.schemas.directives import DirectiveInterpretation, SolarReductionAdjustment
from app.schemas.request import OptimizationRequest
from app.schemas.response import HourlyPlanEntry


def test_replay_valid_plan(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="REPLAY-OK",
        operator_notes=["No notes"],
        hours=sample_hours,
        battery=sample_battery,
    )
    directives = [
        DirectiveInterpretation(
            note_index=0,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="no-op",
        )
    ]
    constraints = compile_constraints(req, directives)

    # Valid plan with zero battery movement
    plan = [
        HourlyPlanEntry(
            hour=h,
            grid_kwh=sample_hours[h].demand_kwh - sample_hours[h].solar_kwh,
            solar_used_kwh=sample_hours[h].solar_kwh,
            battery_action="idle",
            battery_kwh=0.0,
            battery_energy_after_kwh=sample_battery.initial_energy_kwh,
        )
        for h in range(24)
    ]

    # Should pass without error
    validate_hourly_plan_replay(req, constraints, plan, directives=directives)


def test_replay_detects_broken_end_neutrality(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="REPLAY-FAIL-NEUTRAL",
        operator_notes=["No notes"],
        hours=sample_hours,
        battery=sample_battery,
    )
    constraints = compile_constraints(req, [])
    plan = [
        HourlyPlanEntry(
            hour=h,
            grid_kwh=sample_hours[h].demand_kwh - sample_hours[h].solar_kwh,
            solar_used_kwh=sample_hours[h].solar_kwh,
            battery_action="idle",
            battery_kwh=0.0,
            battery_energy_after_kwh=sample_battery.initial_energy_kwh + (10.0 if h == 23 else 0.0),
        )
        for h in range(24)
    ]

    with pytest.raises(ReplayValidationError, match="Battery transition mismatch|End-of-day battery neutrality broken"):
        validate_hourly_plan_replay(req, constraints, plan)


def test_replay_compiler_audit_tampering(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="REPLAY-COMPILER-AUDIT",
        operator_notes=["Reduce solar by 50% between 10 and 12"],
        hours=sample_hours,
        battery=sample_battery,
    )
    directives = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment=SolarReductionAdjustment(hours=[10, 11, 12], factor=0.5),
            explanation="Reduce solar by 50%",
        )
    ]
    constraints = compile_constraints(req, directives)

    # Intentionally tamper with constraints object to simulate compiler bug/drift
    constraints.effective_solar[10] = 999.0

    plan = [
        HourlyPlanEntry(
            hour=h,
            grid_kwh=sample_hours[h].demand_kwh,
            solar_used_kwh=0.0,
            battery_action="idle",
            battery_kwh=0.0,
            battery_energy_after_kwh=sample_battery.initial_energy_kwh,
        )
        for h in range(24)
    ]

    with pytest.raises(ReplayValidationError, match="Replay compiler audit failed"):
        validate_hourly_plan_replay(req, constraints, plan, directives=directives)


def test_replay_simultaneous_no_charge_and_no_discharge(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="REPLAY-DUAL-OUTAGE",
        operator_notes=["Outage"],
        hours=sample_hours,
        battery=sample_battery,
    )
    constraints = compile_constraints(req, [])
    # Both prohibited at hour 5
    constraints.charge_allowed[5] = False
    constraints.discharge_allowed[5] = False

    plan = [
        HourlyPlanEntry(
            hour=h,
            grid_kwh=sample_hours[h].demand_kwh,
            solar_used_kwh=0.0,
            battery_action="charge" if h == 5 else "idle",
            battery_kwh=5.0 if h == 5 else 0.0,
            battery_energy_after_kwh=sample_battery.initial_energy_kwh + (5.0 if h >= 5 else 0.0),
        )
        for h in range(24)
    ]

    with pytest.raises(ReplayValidationError, match="Both charge and discharge prohibited"):
        validate_hourly_plan_replay(req, constraints, plan)
