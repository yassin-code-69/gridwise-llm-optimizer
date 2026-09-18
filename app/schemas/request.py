"""Request schemas with strict Pydantic v2 validation."""

import math
from typing import Annotated
from pydantic import BaseModel, Field, field_validator, model_validator


def check_finite(val: float, field_name: str) -> float:
    if not math.isfinite(val):
        raise ValueError(f"Field '{field_name}' must be finite; received {val}")
    return val


class HourInput(BaseModel):
    model_config = {"extra": "forbid"}

    hour: int = Field(..., ge=0, le=23, description="Hour of the day (0-23)")
    demand_kwh: float = Field(..., ge=0.0, description="Demand in kWh, must be non-negative")
    solar_kwh: float = Field(..., ge=0.0, description="Forecast rooftop solar in kWh, must be non-negative")
    tariff_bdt_per_kwh: float = Field(..., description="Grid electricity tariff in BDT per kWh")

    @field_validator("demand_kwh", "solar_kwh", "tariff_bdt_per_kwh")
    @classmethod
    def validate_finite_numbers(cls, v: float, info) -> float:
        return check_finite(v, info.field_name)


class BatteryInput(BaseModel):
    model_config = {"extra": "forbid"}

    capacity_kwh: float = Field(..., ge=0.0, description="Total storage capacity in kWh")
    initial_energy_kwh: float = Field(..., ge=0.0, description="Energy in battery at start of hour 0 in kWh")
    minimum_energy_kwh: float = Field(..., ge=0.0, description="Base minimum allowable battery energy in kWh")
    max_charge_kwh_per_hour: float = Field(..., ge=0.0, description="Maximum charge rate in kWh/h")
    max_discharge_kwh_per_hour: float = Field(..., ge=0.0, description="Maximum discharge rate in kWh/h")

    @field_validator(
        "capacity_kwh",
        "initial_energy_kwh",
        "minimum_energy_kwh",
        "max_charge_kwh_per_hour",
        "max_discharge_kwh_per_hour",
    )
    @classmethod
    def validate_finite_battery_numbers(cls, v: float, info) -> float:
        return check_finite(v, info.field_name)

    @model_validator(mode="after")
    def validate_battery_invariants(self) -> "BatteryInput":
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError(
                f"initial_energy_kwh ({self.initial_energy_kwh}) cannot exceed capacity_kwh ({self.capacity_kwh})"
            )
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError(
                f"minimum_energy_kwh ({self.minimum_energy_kwh}) cannot exceed capacity_kwh ({self.capacity_kwh})"
            )
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError(
                f"initial_energy_kwh ({self.initial_energy_kwh}) cannot be less than minimum_energy_kwh ({self.minimum_energy_kwh})"
            )
        return self


class OptimizationRequest(BaseModel):
    model_config = {"extra": "forbid"}

    scenario_id: str = Field(..., min_length=1, description="Unique scenario identifier")
    operator_notes: list[str] = Field(..., min_length=1, max_length=3, description="1 to 3 operator notes")
    hours: list[HourInput] = Field(..., min_length=24, max_length=24, description="Exactly 24 hourly records")
    battery: BatteryInput = Field(..., description="Battery technical and operational parameters")

    @field_validator("operator_notes")
    @classmethod
    def validate_non_empty_notes(cls, notes: list[str]) -> list[str]:
        for idx, note in enumerate(notes):
            if not note or not note.strip():
                raise ValueError(f"operator_notes[{idx}] must be a non-empty string")
        return notes

    @model_validator(mode="after")
    def validate_hours_sequence(self) -> "OptimizationRequest":
        if len(self.hours) != 24:
            raise ValueError(f"Expected exactly 24 hours in input, received {len(self.hours)}")
        
        seen_hours = set()
        for h in self.hours:
            if h.hour in seen_hours:
                raise ValueError(f"Duplicate hour found in hours array: hour {h.hour}")
            seen_hours.add(h.hour)
            
        expected_hours = set(range(24))
        if seen_hours != expected_hours:
            missing = sorted(list(expected_hours - seen_hours))
            raise ValueError(f"Missing hours in hours array: {missing}")

        return self
