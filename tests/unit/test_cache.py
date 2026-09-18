"""Unit tests for bounded LRU InterpretationCache."""

import pytest
from app.llm.interpreter import InterpretationCache, LLMInterpreter
from app.llm.providers.mock_provider import MockDirectiveInterpreter
from app.schemas.directives import DirectiveInterpretation
from app.schemas.request import BatteryInput


def test_cache_key_differentiation():
    cache = InterpretationCache(maxsize=10)
    b1 = BatteryInput(
        capacity_kwh=100.0,
        initial_energy_kwh=50.0,
        minimum_energy_kwh=20.0,
        max_charge_kwh_per_hour=25.0,
        max_discharge_kwh_per_hour=25.0,
    )
    b2 = BatteryInput(
        capacity_kwh=200.0,
        initial_energy_kwh=50.0,
        minimum_energy_kwh=20.0,
        max_charge_kwh_per_hour=25.0,
        max_discharge_kwh_per_hour=25.0,
    )
    notes = ["Maintain 50% capacity in reserve"]

    k1 = cache.make_key(notes, b1, "mock", "test-model")
    k2 = cache.make_key(notes, b2, "mock", "test-model")

    # Keys must be distinct because battery capacity differs
    assert k1 != k2


def test_cache_hit_and_eviction():
    cache = InterpretationCache(maxsize=2)
    b = BatteryInput(
        capacity_kwh=100.0,
        initial_energy_kwh=50.0,
        minimum_energy_kwh=20.0,
        max_charge_kwh_per_hour=25.0,
        max_discharge_kwh_per_hour=25.0,
    )
    k1 = cache.make_key(["note 1"], b, "mock", "m1")
    k2 = cache.make_key(["note 2"], b, "mock", "m1")
    k3 = cache.make_key(["note 3"], b, "mock", "m1")

    val1 = [DirectiveInterpretation(note_index=0, applies=False, directive_type="no_op", structured_adjustment=None, explanation="no-op 1")]
    val2 = [DirectiveInterpretation(note_index=0, applies=False, directive_type="no_op", structured_adjustment=None, explanation="no-op 2")]
    val3 = [DirectiveInterpretation(note_index=0, applies=False, directive_type="no_op", structured_adjustment=None, explanation="no-op 3")]

    cache.set(k1, val1)
    cache.set(k2, val2)
    assert cache.size == 2
    assert cache.get(k1) is not None
    assert cache.hits == 1

    # Adding 3rd item should evict k2 (since k1 was accessed most recently)
    cache.set(k3, val3)
    assert cache.size == 2
    assert cache.get(k2) is None  # Evicted
    assert cache.get(k1) is not None  # Retained
    assert cache.get(k3) is not None  # Present


@pytest.mark.asyncio
async def test_llm_interpreter_caching():
    cache = InterpretationCache(maxsize=10)
    interpreter = LLMInterpreter(provider=MockDirectiveInterpreter(), cache=cache)

    battery = BatteryInput(
        capacity_kwh=100.0,
        initial_energy_kwh=50.0,
        minimum_energy_kwh=20.0,
        max_charge_kwh_per_hour=25.0,
        max_discharge_kwh_per_hour=25.0,
    )
    notes = ["Do not charge between 14:00 and 17:00."]

    # First call: cache miss
    res1 = await interpreter.interpret_and_validate(notes, battery)
    assert cache.misses == 1
    assert cache.hits == 0

    # Second call: cache hit
    res2 = await interpreter.interpret_and_validate(notes, battery)
    assert cache.hits == 1
    assert len(res1) == len(res2) == 1
    assert res1[0].directive_type == res2[0].directive_type == "no_charge_window"
