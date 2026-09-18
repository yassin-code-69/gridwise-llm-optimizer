"""Tests semantic generalization against paraphrased operator note expressions."""

import pytest
from app.llm.providers.mock_provider import MockDirectiveInterpreter


@pytest.mark.asyncio
async def test_paraphrased_solar_reduction():
    interpreter = MockDirectiveInterpreter()
    notes = [
        "PV production will drop by 80% from 11 AM to 2 PM.",
        "Only one-fifth of rooftop solar will remain from 11 AM to 2 PM.",
    ]
    interps = await interpreter.interpret(notes, {"capacity_kwh": 200.0})
    
    assert interps[0].directive_type == "solar_reduction"
    assert interps[0].structured_adjustment.factor == 0.2
    assert interps[0].structured_adjustment.hours == [11, 12, 13]

    assert interps[1].directive_type == "solar_reduction"
    assert interps[1].structured_adjustment.factor == 0.2
    assert interps[1].structured_adjustment.hours == [11, 12, 13]


@pytest.mark.asyncio
async def test_paraphrased_reserve():
    interpreter = MockDirectiveInterpreter()
    notes = [
        "Retain half the battery capacity from 6 PM to 9 PM.",
        "Do not let stored energy fall below 50% from 6 PM until 9 PM.",
    ]
    interps = await interpreter.interpret(notes, {"capacity_kwh": 200.0})
    
    for item in interps:
        assert item.directive_type == "minimum_battery_reserve"
        assert item.structured_adjustment.minimum_energy_kwh == 100.0
        assert item.structured_adjustment.hours == [18, 19, 20]
