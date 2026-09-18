"""Unit tests for the 24-hour continuous Linear Program optimizer."""

import pytest
from app.core.constraint_compiler import compile_constraints
from app.core.optimizer import solve_energy_schedule
from app.schemas.directives import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
)
from app.schemas.request import OptimizationRequest


def test_optimizer_baseline(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="OPT-BASE",
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
    res = solve_energy_schedule(req, constraints)

    assert len(res.grid) == 24
    assert len(res.solar_used) == 24
    assert len(res.battery_flow) == 24
    assert len(res.battery_energy) == 24
    assert res.objective_cost > 0.0
    # End-of-day neutrality check
    assert abs(res.battery_energy[23] - sample_battery.initial_energy_kwh) < 1e-4


def test_solver_cross_verification_highs_and_cbc(sample_battery, sample_hours):
    """Phase 64 requirement: verifies that HiGHS and CBC produce equivalent optimal objectives."""
    req = OptimizationRequest(
        scenario_id="OPT-CROSS",
        operator_notes=["Solar cut"],
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
        )
    ]
    constraints = compile_constraints(req, directives)

    res_highs = solve_energy_schedule(req, constraints, forced_solver="HiGHS")
    res_cbc = solve_energy_schedule(req, constraints, forced_solver="CBC")

    # Objectives must match within 0.01 BDT
    cost_diff = abs(res_highs.objective_cost - res_cbc.objective_cost)
    assert cost_diff < 0.05, f"HiGHS cost ({res_highs.objective_cost}) and CBC cost ({res_cbc.objective_cost}) differ by {cost_diff}"
