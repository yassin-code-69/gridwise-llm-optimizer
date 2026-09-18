"""Deterministic guardrail layer for validating untrusted LLM output."""

import math
from typing import Optional
from app.errors import LLMOutputValidationError
from app.schemas.directives import (
    DirectiveInterpretation,
    DirectiveType,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
)
from app.schemas.request import BatteryInput

ALLOWED_DIRECTIVES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


def validate_llm_interpretations(
    interpretations: list[DirectiveInterpretation],
    operator_notes: list[str],
    battery: BatteryInput,
) -> list[DirectiveInterpretation]:
    """Deterministically validates structured directive interpretations against official rules.

    Raises:
        LLMOutputValidationError: If any rule or invariant is violated.
    """
    if not isinstance(interpretations, list):
        raise LLMOutputValidationError("LLM interpretations must be a list of objects")

    expected_count = len(operator_notes)
    if len(interpretations) != expected_count:
        raise LLMOutputValidationError(
            f"Expected exactly {expected_count} interpretations for {expected_count} notes, got {len(interpretations)}"
        )

    # Validate note indices coverage: must be exactly 0..N-1
    returned_indices = [item.note_index for item in interpretations]
    expected_indices = set(range(expected_count))
    if set(returned_indices) != expected_indices:
        raise LLMOutputValidationError(
            f"Note indices do not match expected range 0..{expected_count - 1}. Found: {returned_indices}"
        )

    # Ensure sorted order by note_index
    sorted_interps = sorted(interpretations, key=lambda x: x.note_index)

    for item in sorted_interps:
        idx = item.note_index
        dtype = item.directive_type

        if dtype not in ALLOWED_DIRECTIVES:
            raise LLMOutputValidationError(f"Note {idx}: Unsupported directive type '{dtype}'")

        if dtype == "no_op":
            if item.applies:
                raise LLMOutputValidationError(f"Note {idx}: no_op directive must have applies=false")
            if item.structured_adjustment is not None:
                raise LLMOutputValidationError(
                    f"Note {idx}: no_op directive must have structured_adjustment=null"
                )
        else:
            if not item.applies:
                raise LLMOutputValidationError(f"Note {idx}: {dtype} directive must have applies=true")
            if item.structured_adjustment is None:
                raise LLMOutputValidationError(
                    f"Note {idx}: {dtype} directive must have non-null structured_adjustment"
                )

            adj = item.structured_adjustment

            # Check hours common to all active directives
            if not hasattr(adj, "hours") or not isinstance(adj.hours, list) or not adj.hours:
                raise LLMOutputValidationError(f"Note {idx}: Directive {dtype} requires non-empty hours list")

            hours = adj.hours
            if len(hours) != len(set(hours)):
                raise LLMOutputValidationError(f"Note {idx}: Duplicate hours in directive window: {hours}")

            if hours != sorted(hours):
                raise LLMOutputValidationError(f"Note {idx}: Hours window must be strictly ascending: {hours}")

            for h in hours:
                if not isinstance(h, int) or isinstance(h, bool):
                    raise LLMOutputValidationError(f"Note {idx}: Hour {h} must be an integer")
                if not (0 <= h <= 23):
                    raise LLMOutputValidationError(f"Note {idx}: Hour {h} is outside allowable 0..23 range")

            # Check directive-specific attributes
            if dtype == "solar_reduction":
                if not isinstance(adj, SolarReductionAdjustment):
                    raise LLMOutputValidationError(
                        f"Note {idx}: Expected SolarReductionAdjustment, got {type(adj)}"
                    )
                factor = adj.factor
                if not math.isfinite(factor) or factor < 0.0 or factor > 1.0:
                    raise LLMOutputValidationError(
                        f"Note {idx}: Solar factor {factor} must be finite and within [0.0, 1.0]"
                    )

            elif dtype == "minimum_battery_reserve":
                if not isinstance(adj, MinimumBatteryReserveAdjustment):
                    raise LLMOutputValidationError(
                        f"Note {idx}: Expected MinimumBatteryReserveAdjustment, got {type(adj)}"
                    )
                reserve = adj.minimum_energy_kwh
                if not math.isfinite(reserve) or reserve < 0.0:
                    raise LLMOutputValidationError(
                        f"Note {idx}: Minimum reserve {reserve} must be finite and non-negative"
                    )
                if reserve > battery.capacity_kwh:
                    raise LLMOutputValidationError(
                        f"Note {idx}: Minimum reserve {reserve} kWh exceeds battery capacity {battery.capacity_kwh} kWh"
                    )

            elif dtype == "no_charge_window":
                if not isinstance(adj, NoChargeAdjustment):
                    raise LLMOutputValidationError(
                        f"Note {idx}: Expected NoChargeAdjustment, got {type(adj)}"
                    )

            elif dtype == "no_discharge_window":
                if not isinstance(adj, NoDischargeAdjustment):
                    raise LLMOutputValidationError(
                        f"Note {idx}: Expected NoDischargeAdjustment, got {type(adj)}"
                    )

            elif dtype == "max_grid_window":
                if not isinstance(adj, MaxGridAdjustment):
                    raise LLMOutputValidationError(
                        f"Note {idx}: Expected MaxGridAdjustment, got {type(adj)}"
                    )
                grid_cap = adj.max_grid_kwh
                if not math.isfinite(grid_cap) or grid_cap < 0.0:
                    raise LLMOutputValidationError(
                        f"Note {idx}: Grid cap {grid_cap} must be finite and non-negative"
                    )

    return sorted_interps
