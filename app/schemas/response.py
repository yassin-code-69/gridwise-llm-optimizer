"""Response schemas matching the official GridWise contract."""

import math
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.schemas.directives import DirectiveInterpretation


BatteryAction = Literal["charge", "discharge", "idle"]


class HourlyPlanEntry(BaseModel):
    model_config = {"extra": "forbid"}

    hour: int = Field(..., ge=0, le=23, description="Hour index (0-23)")
    grid_kwh: float = Field(..., ge=0.0, description="Grid electricity imported in kWh")
    solar_used_kwh: float = Field(..., ge=0.0, description="Rooftop solar electricity used in kWh")
    battery_action: BatteryAction = Field(..., description="Action taken: charge, discharge, or idle")
    battery_kwh: float = Field(..., ge=0.0, description="Battery energy magnitude in kWh (0 if idle)")
    battery_energy_after_kwh: float = Field(..., ge=0.0, description="Battery state of charge at end of hour in kWh")

    @field_validator("grid_kwh", "solar_used_kwh", "battery_kwh", "battery_energy_after_kwh")
    @classmethod
    def validate_finite(cls, v: float, info) -> float:
        if not math.isfinite(v):
            raise ValueError(f"HourlyPlanEntry.{info.field_name} must be finite")
        return v

    @model_validator(mode="after")
    def validate_action_magnitude(self) -> "HourlyPlanEntry":
        if self.battery_action == "idle" and self.battery_kwh > 1e-6:
            raise ValueError(f"battery_action is 'idle' but battery_kwh is {self.battery_kwh} (must be 0)")
        return self


class OptimizationResponse(BaseModel):
    model_config = {"extra": "forbid"}

    scenario_id: str = Field(..., description="Scenario ID echoed from request")
    directive_interpretation: list[DirectiveInterpretation] = Field(
        ..., description="Machine-readable interpretation for every operator note"
    )
    hourly_plan: list[HourlyPlanEntry] = Field(
        ..., min_length=24, max_length=24, description="Optimal 24-hour dispatch schedule"
    )
    total_grid_kwh: float = Field(..., ge=0.0, description="Total 24-hour grid electricity imported in kWh")
    total_cost_bdt: float = Field(..., ge=0.0, description="Total 24-hour electricity cost in BDT")
    peak_grid_kwh: float = Field(..., ge=0.0, description="Maximum single-hour grid import in kWh")
    plan_summary: str = Field(..., min_length=1, description="Concise deterministic strategy summary")

    @field_validator("total_grid_kwh", "total_cost_bdt", "peak_grid_kwh")
    @classmethod
    def validate_finite_totals(cls, v: float, info) -> float:
        if not math.isfinite(v):
            raise ValueError(f"OptimizationResponse.{info.field_name} must be finite")
        return v

    @model_validator(mode="after")
    def validate_response_invariants(self) -> "OptimizationResponse":
        if len(self.hourly_plan) != 24:
            raise ValueError(f"hourly_plan must contain exactly 24 entries, received {len(self.hourly_plan)}")
        for idx, entry in enumerate(self.hourly_plan):
            if entry.hour != idx:
                raise ValueError(f"hourly_plan[{idx}].hour is {entry.hour}, expected {idx}")
        return self
