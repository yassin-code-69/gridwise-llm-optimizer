"""Compiles validated operator directives into per-hour numerical mathematical constraints."""

from dataclasses import dataclass
from typing import Optional
from app.schemas.directives import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
)
from app.schemas.request import OptimizationRequest


@dataclass
class EffectiveConstraints:
    effective_solar: list[float]      # len 24: Upper bound on usable solar (kWh)
    minimum_energy: list[float]       # len 24: Lower bound on battery energy after hour (kWh)
    charge_allowed: list[bool]        # len 24: False if charging prohibited
    discharge_allowed: list[bool]     # len 24: False if discharging prohibited
    max_grid: list[float]             # len 24: Upper bound on grid import (kWh), inf if uncapped


def compile_constraints(
    request: OptimizationRequest,
    directives: list[DirectiveInterpretation],
) -> EffectiveConstraints:
    """Translates scenario parameters and validated directives into 24-hour mathematical bounds.

    ENGINEERING DECISION:
    When multiple independent directives affect the same hour:
    - solar_reduction: enforces the strictest upper bound min(effective_solar, original * factor).
    - minimum_battery_reserve: enforces the highest reserve requirement max(minimum_energy, reserve).
    - max_grid_window: enforces the lowest grid cap min(max_grid, cap).
    - no_charge_window / no_discharge_window: any prohibition disables the respective action.
    """
    # Sort hours to guarantee index matches hour
    sorted_hours = sorted(request.hours, key=lambda x: x.hour)

    # Initialize baseline constraints
    effective_solar = [h.solar_kwh for h in sorted_hours]
    minimum_energy = [request.battery.minimum_energy_kwh for _ in range(24)]
    charge_allowed = [True for _ in range(24)]
    discharge_allowed = [True for _ in range(24)]
    max_grid = [float("inf") for _ in range(24)]

    # Compile active directives
    for directive in directives:
        if not directive.applies or directive.structured_adjustment is None:
            continue

        adj = directive.structured_adjustment
        dtype = directive.directive_type

        if dtype == "solar_reduction" and isinstance(adj, SolarReductionAdjustment):
            for h in adj.hours:
                bound = sorted_hours[h].solar_kwh * adj.factor
                effective_solar[h] = min(effective_solar[h], bound)

        elif dtype == "minimum_battery_reserve" and isinstance(adj, MinimumBatteryReserveAdjustment):
            for h in adj.hours:
                minimum_energy[h] = max(minimum_energy[h], adj.minimum_energy_kwh)

        elif dtype == "no_charge_window" and isinstance(adj, NoChargeAdjustment):
            for h in adj.hours:
                charge_allowed[h] = False

        elif dtype == "no_discharge_window" and isinstance(adj, NoDischargeAdjustment):
            for h in adj.hours:
                discharge_allowed[h] = False

        elif dtype == "max_grid_window" and isinstance(adj, MaxGridAdjustment):
            for h in adj.hours:
                max_grid[h] = min(max_grid[h], adj.max_grid_kwh)

    return EffectiveConstraints(
        effective_solar=effective_solar,
        minimum_energy=minimum_energy,
        charge_allowed=charge_allowed,
        discharge_allowed=discharge_allowed,
        max_grid=max_grid,
    )
