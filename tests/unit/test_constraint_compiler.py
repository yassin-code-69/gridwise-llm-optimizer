"""Unit tests for constraint compiler."""

from app.core.constraint_compiler import compile_constraints
from app.schemas.directives import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
)
from app.schemas.request import OptimizationRequest


def test_compile_no_directives(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="TEST-01",
        operator_notes=["No-op note"],
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

    assert len(constraints.effective_solar) == 24
    assert constraints.effective_solar[12] == sample_hours[12].solar_kwh
    assert all(r == 40.0 for r in constraints.minimum_energy)
    assert all(constraints.charge_allowed)
    assert all(constraints.discharge_allowed)
    assert all(g == float("inf") for g in constraints.max_grid)


def test_compile_solar_and_reserve(sample_battery, sample_hours):
    req = OptimizationRequest(
        scenario_id="TEST-02",
        operator_notes=["Solar reduction", "Battery reserve"],
        hours=sample_hours,
        battery=sample_battery,
    )
    directives = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment=SolarReductionAdjustment(hours=[12, 13], factor=0.25),
            explanation="75% cut",
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

    assert constraints.effective_solar[12] == sample_hours[12].solar_kwh * 0.25
    assert constraints.effective_solar[13] == sample_hours[13].solar_kwh * 0.25
    assert constraints.effective_solar[11] == sample_hours[11].solar_kwh

    assert constraints.minimum_energy[18] == 100.0
    assert constraints.minimum_energy[19] == 100.0
    assert constraints.minimum_energy[20] == 100.0
    assert constraints.minimum_energy[17] == 40.0
