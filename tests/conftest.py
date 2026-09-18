"""Pytest configuration and shared fixtures."""

import json
import pytest
from app.schemas.request import BatteryInput, HourInput, OptimizationRequest


@pytest.fixture
def sample_battery() -> BatteryInput:
    return BatteryInput(
        capacity_kwh=200.0,
        initial_energy_kwh=100.0,
        minimum_energy_kwh=40.0,
        max_charge_kwh_per_hour=50.0,
        max_discharge_kwh_per_hour=50.0,
    )


@pytest.fixture
def sample_hours() -> list[HourInput]:
    with open("samples/public_cases.json", "r") as f:
        cases = json.load(f)
    return [HourInput.model_validate(h) for h in cases[0]["hours"]]


@pytest.fixture
def sample_public_cases() -> list[dict]:
    with open("samples/public_cases.json", "r") as f:
        return json.load(f)
