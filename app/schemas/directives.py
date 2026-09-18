"""Directive schemas and adjustment object shapes."""

import math
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


def validate_hours_list(hours: list[int]) -> list[int]:
    if not hours:
        raise ValueError("hours list cannot be empty")
    for h in hours:
        if not (0 <= h <= 23):
            raise ValueError(f"Hour {h} out of bounds [0, 23]")
    if len(hours) != len(set(hours)):
        raise ValueError("Duplicate hours found in hours list")
    if hours != sorted(hours):
        raise ValueError(f"Hours list must be strictly ascending: {hours}")
    return hours


class SolarReductionAdjustment(BaseModel):
    model_config = {"extra": "forbid"}

    hours: list[int] = Field(..., description="Hours where solar output is reduced")
    factor: float = Field(..., ge=0.0, le=1.0, description="Usable solar fraction remaining (0.0 to 1.0)")

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return validate_hours_list(v)

    @field_validator("factor")
    @classmethod
    def check_factor(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("factor must be finite")
        return v


class MinimumBatteryReserveAdjustment(BaseModel):
    model_config = {"extra": "forbid"}

    hours: list[int] = Field(..., description="Hours where minimum reserve is required")
    minimum_energy_kwh: float = Field(..., ge=0.0, description="Minimum battery stored energy required in kWh")

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return validate_hours_list(v)

    @field_validator("minimum_energy_kwh")
    @classmethod
    def check_reserve(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("minimum_energy_kwh must be finite")
        return v


class NoChargeAdjustment(BaseModel):
    model_config = {"extra": "forbid"}

    hours: list[int] = Field(..., description="Hours where battery charging is prohibited")

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return validate_hours_list(v)


class NoDischargeAdjustment(BaseModel):
    model_config = {"extra": "forbid"}

    hours: list[int] = Field(..., description="Hours where battery discharging is prohibited")

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return validate_hours_list(v)


class MaxGridAdjustment(BaseModel):
    model_config = {"extra": "forbid"}

    hours: list[int] = Field(..., description="Hours where grid import is capped")
    max_grid_kwh: float = Field(..., ge=0.0, description="Maximum allowable grid import in kWh")

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return validate_hours_list(v)

    @field_validator("max_grid_kwh")
    @classmethod
    def check_grid_cap(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("max_grid_kwh must be finite")
        return v


DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]

StructuredAdjustment = Union[
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
    None,
]


class DirectiveInterpretation(BaseModel):
    model_config = {"extra": "forbid"}

    note_index: int = Field(..., ge=0, description="0-based index of the corresponding operator note")
    applies: bool = Field(..., description="True if directive affects schedule, False for no_op")
    directive_type: DirectiveType = Field(..., description="Exact directive enum")
    structured_adjustment: Optional[StructuredAdjustment] = Field(
        default=None, description="Typed parameters for the directive, or null for no_op"
    )
    explanation: str = Field(..., min_length=1, description="Concise explanation of the note interpretation")

    @model_validator(mode="after")
    def validate_directive_consistency(self) -> "DirectiveInterpretation":
        if self.directive_type == "no_op":
            if self.applies:
                raise ValueError("no_op directive must have applies=false")
            if self.structured_adjustment is not None:
                raise ValueError("no_op directive must have structured_adjustment=null")
        else:
            if not self.applies:
                raise ValueError(f"{self.directive_type} directive must have applies=true")
            if self.structured_adjustment is None:
                raise ValueError(f"{self.directive_type} directive requires non-null structured_adjustment")

            # Validate adjustment type matching
            type_mapping = {
                "solar_reduction": SolarReductionAdjustment,
                "minimum_battery_reserve": MinimumBatteryReserveAdjustment,
                "no_charge_window": NoChargeAdjustment,
                "no_discharge_window": NoDischargeAdjustment,
                "max_grid_window": MaxGridAdjustment,
            }
            expected_class = type_mapping[self.directive_type]
            if not isinstance(self.structured_adjustment, expected_class):
                # Attempt conversion if it's a dict or different model
                if isinstance(self.structured_adjustment, dict):
                    self.structured_adjustment = expected_class.model_validate(self.structured_adjustment)
                elif hasattr(self.structured_adjustment, "model_dump"):
                    self.structured_adjustment = expected_class.model_validate(self.structured_adjustment.model_dump())
                else:
                    raise ValueError(
                        f"Expected adjustment of type {expected_class.__name__} for directive {self.directive_type}, got {type(self.structured_adjustment)}"
                    )

        return self
