"""Unit tests for deterministic guardrail validation."""

import pytest
from app.core.guardrails import validate_llm_interpretations
from app.errors import LLMOutputValidationError
from app.schemas.directives import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
)
from app.schemas.request import BatteryInput


def test_guardrail_valid(sample_battery):
    notes = ["Solar down 50% from 11 AM to 2 PM", "Cleaning scheduled"]
    interps = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment=SolarReductionAdjustment(hours=[11, 12, 13], factor=0.5),
            explanation="50% drop in solar",
        ),
        DirectiveInterpretation(
            note_index=1,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="Cleaning unrelated to scheduling",
        ),
    ]
    res = validate_llm_interpretations(interps, notes, sample_battery)
    assert len(res) == 2


def test_guardrail_count_mismatch(sample_battery):
    notes = ["Note 1", "Note 2"]
    interps = [
        DirectiveInterpretation(
            note_index=0,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="no-op",
        )
    ]
    with pytest.raises(LLMOutputValidationError, match="Expected exactly 2"):
        validate_llm_interpretations(interps, notes, sample_battery)


def test_guardrail_index_mismatch(sample_battery):
    notes = ["Note 1", "Note 2"]
    interps = [
        DirectiveInterpretation(
            note_index=0,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="no-op",
        ),
        DirectiveInterpretation(
            note_index=2,  # Should be 1!
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="no-op",
        ),
    ]
    with pytest.raises(LLMOutputValidationError, match="Note indices do not match"):
        validate_llm_interpretations(interps, notes, sample_battery)


def test_guardrail_reserve_exceeds_capacity(sample_battery):
    notes = ["Keep 300 kWh in reserve"]
    # sample_battery capacity is 200.0 kWh
    interps = [
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment=MinimumBatteryReserveAdjustment(hours=[18, 19], minimum_energy_kwh=300.0),
            explanation="Huge reserve",
        )
    ]
    with pytest.raises(LLMOutputValidationError, match="exceeds battery capacity"):
        validate_llm_interpretations(interps, notes, sample_battery)
