"""Unit tests for Pydantic v2 request and directive schemas."""

import math
import pytest
from pydantic import ValidationError

from app.schemas.request import BatteryInput, HourInput, OptimizationRequest
from app.schemas.directives import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
)


def test_valid_battery_input():
    batt = BatteryInput(
        capacity_kwh=200.0,
        initial_energy_kwh=100.0,
        minimum_energy_kwh=40.0,
        max_charge_kwh_per_hour=50.0,
        max_discharge_kwh_per_hour=50.0,
    )
    assert batt.capacity_kwh == 200.0


def test_battery_initial_exceeds_capacity():
    with pytest.raises(ValidationError, match="cannot exceed capacity_kwh"):
        BatteryInput(
            capacity_kwh=200.0,
            initial_energy_kwh=250.0,
            minimum_energy_kwh=40.0,
            max_charge_kwh_per_hour=50.0,
            max_discharge_kwh_per_hour=50.0,
        )


def test_battery_minimum_exceeds_capacity():
    with pytest.raises(ValidationError, match="cannot exceed capacity_kwh"):
        BatteryInput(
            capacity_kwh=200.0,
            initial_energy_kwh=100.0,
            minimum_energy_kwh=220.0,
            max_charge_kwh_per_hour=50.0,
            max_discharge_kwh_per_hour=50.0,
        )


def test_battery_initial_less_than_minimum():
    with pytest.raises(ValidationError, match="cannot be less than minimum_energy_kwh"):
        BatteryInput(
            capacity_kwh=200.0,
            initial_energy_kwh=30.0,
            minimum_energy_kwh=50.0,
            max_charge_kwh_per_hour=50.0,
            max_discharge_kwh_per_hour=50.0,
        )


def test_battery_nan_rejected():
    with pytest.raises(ValidationError):
        BatteryInput(
            capacity_kwh=float("nan"),
            initial_energy_kwh=100.0,
            minimum_energy_kwh=40.0,
            max_charge_kwh_per_hour=50.0,
            max_discharge_kwh_per_hour=50.0,
        )



def test_hour_input_negative_demand():
    with pytest.raises(ValidationError):
        HourInput(hour=0, demand_kwh=-5.0, solar_kwh=0.0, tariff_bdt_per_kwh=6.0)


def test_hour_input_out_of_range():
    with pytest.raises(ValidationError):
        HourInput(hour=24, demand_kwh=10.0, solar_kwh=0.0, tariff_bdt_per_kwh=6.0)


def test_optimization_request_missing_hour(sample_battery, sample_hours):
    # Only 23 hours
    short_hours = sample_hours[:23]
    with pytest.raises(ValidationError):
        OptimizationRequest(
            scenario_id="TEST-01",
            operator_notes=["Valid note"],
            hours=short_hours,
            battery=sample_battery,
        )


def test_optimization_request_duplicate_hour(sample_battery, sample_hours):
    dup_hours = list(sample_hours)
    dup_hours[23] = HourInput(hour=0, demand_kwh=50.0, solar_kwh=0.0, tariff_bdt_per_kwh=5.0)
    with pytest.raises(ValidationError, match="Duplicate hour"):
        OptimizationRequest(
            scenario_id="TEST-02",
            operator_notes=["Valid note"],
            hours=dup_hours,
            battery=sample_battery,
        )


def test_optimization_request_empty_notes(sample_battery, sample_hours):
    with pytest.raises(ValidationError):
        OptimizationRequest(
            scenario_id="TEST-03",
            operator_notes=[],
            hours=sample_hours,
            battery=sample_battery,
        )


def test_optimization_request_too_many_notes(sample_battery, sample_hours):
    with pytest.raises(ValidationError):
        OptimizationRequest(
            scenario_id="TEST-04",
            operator_notes=["Note 1", "Note 2", "Note 3", "Note 4"],
            hours=sample_hours,
            battery=sample_battery,
        )


def test_directive_no_op_with_applies_true():
    with pytest.raises(ValidationError, match="must have applies=false"):
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="Irrelevant note",
        )


def test_directive_solar_reduction_valid():
    d = DirectiveInterpretation(
        note_index=0,
        applies=True,
        directive_type="solar_reduction",
        structured_adjustment=SolarReductionAdjustment(hours=[11, 12, 13], factor=0.2),
        explanation="Solar cut 80%",
    )
    assert d.applies is True
    assert d.directive_type == "solar_reduction"
    assert d.structured_adjustment.factor == 0.2
