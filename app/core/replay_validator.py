"""Independent deterministic replay validator.

Audits the finalized 24-hour schedule against all physical, operational,
directive, and end-of-day invariants before any API response is returned.
"""

import math
from typing import Optional
from app.core.constraint_compiler import EffectiveConstraints
from app.errors import ReplayValidationError
from app.schemas.directives import DirectiveInterpretation
from app.schemas.request import OptimizationRequest
from app.schemas.response import HourlyPlanEntry

TOLERANCE = 0.01  # Official 0.01 kWh invariant tolerance


def validate_hourly_plan_replay(
    request: OptimizationRequest,
    constraints: EffectiveConstraints,
    hourly_plan: list[HourlyPlanEntry],
    directives: Optional[list[DirectiveInterpretation]] = None,
) -> None:
    """Independently verifies every rule of the finalized 24-hour dispatch schedule.

    If directives are provided, also independently recomputes effective constraints
    directly from raw inputs and audits the constraint compiler.

    Raises:
        ReplayValidationError: On any violation of official invariants.
    """
    if len(hourly_plan) != 24:
        raise ReplayValidationError(f"Replay failed: Plan has {len(hourly_plan)} hours instead of 24")

    sorted_hours = sorted(request.hours, key=lambda x: x.hour)
    batt = request.battery

    # 0. Independent compiler audit if directives are supplied
    if directives is not None:
        indep_effective_solar = [sorted_hours[h].solar_kwh for h in range(24)]
        indep_min_energy = [batt.minimum_energy_kwh for _ in range(24)]
        indep_charge_allowed = [True] * 24
        indep_discharge_allowed = [True] * 24
        indep_max_grid = [float("inf")] * 24

        for d in directives:
            if not d.applies or d.directive_type == "no_op":
                continue
            adj = d.structured_adjustment
            if adj is None:
                continue
            if d.directive_type == "solar_reduction":
                factor = getattr(adj, "factor", 1.0)
                for h in getattr(adj, "hours", []):
                    indep_effective_solar[h] = min(indep_effective_solar[h], sorted_hours[h].solar_kwh * factor)
            elif d.directive_type == "minimum_battery_reserve":
                reserve = getattr(adj, "minimum_energy_kwh", batt.minimum_energy_kwh)
                for h in getattr(adj, "hours", []):
                    indep_min_energy[h] = max(indep_min_energy[h], reserve)
            elif d.directive_type == "no_charge_window":
                for h in getattr(adj, "hours", []):
                    indep_charge_allowed[h] = False
            elif d.directive_type == "no_discharge_window":
                for h in getattr(adj, "hours", []):
                    indep_discharge_allowed[h] = False
            elif d.directive_type == "max_grid_window":
                cap = getattr(adj, "max_grid_kwh", float("inf"))
                for h in getattr(adj, "hours", []):
                    indep_max_grid[h] = min(indep_max_grid[h], cap)

        for h in range(24):
            if abs(constraints.effective_solar[h] - indep_effective_solar[h]) > 1e-4:
                raise ReplayValidationError(
                    f"Replay compiler audit failed hour {h}: effective_solar compiled={constraints.effective_solar[h]:.4f} != recomputed={indep_effective_solar[h]:.4f}"
                )
            if abs(constraints.minimum_energy[h] - indep_min_energy[h]) > 1e-4:
                raise ReplayValidationError(
                    f"Replay compiler audit failed hour {h}: minimum_energy compiled={constraints.minimum_energy[h]:.4f} != recomputed={indep_min_energy[h]:.4f}"
                )
            if constraints.charge_allowed[h] != indep_charge_allowed[h]:
                raise ReplayValidationError(
                    f"Replay compiler audit failed hour {h}: charge_allowed compiled={constraints.charge_allowed[h]} != recomputed={indep_charge_allowed[h]}"
                )
            if constraints.discharge_allowed[h] != indep_discharge_allowed[h]:
                raise ReplayValidationError(
                    f"Replay compiler audit failed hour {h}: discharge_allowed compiled={constraints.discharge_allowed[h]} != recomputed={indep_discharge_allowed[h]}"
                )
            if abs(constraints.max_grid[h] - indep_max_grid[h]) > 1e-4:
                raise ReplayValidationError(
                    f"Replay compiler audit failed hour {h}: max_grid compiled={constraints.max_grid[h]:.4f} != recomputed={indep_max_grid[h]:.4f}"
                )

    energy_before = batt.initial_energy_kwh

    for h in range(24):
        entry = hourly_plan[h]
        hour_data = sorted_hours[h]
        demand = hour_data.demand_kwh

        # 1. Hour identity
        if entry.hour != h:
            raise ReplayValidationError(f"Replay failed: Hour mismatch at index {h}, entry has hour {entry.hour}")

        # 2. Finite checks
        for name, val in [
            ("grid_kwh", entry.grid_kwh),
            ("solar_used_kwh", entry.solar_used_kwh),
            ("battery_kwh", entry.battery_kwh),
            ("battery_energy_after_kwh", entry.battery_energy_after_kwh),
        ]:
            if not math.isfinite(val):
                raise ReplayValidationError(f"Replay failed hour {h}: {name} is not finite ({val})")

        # 3. Non-negativity
        if entry.grid_kwh < -1e-6:
            raise ReplayValidationError(f"Replay failed hour {h}: grid_kwh cannot be negative ({entry.grid_kwh})")
        if entry.solar_used_kwh < -1e-6:
            raise ReplayValidationError(f"Replay failed hour {h}: solar_used_kwh cannot be negative ({entry.solar_used_kwh})")
        if entry.battery_kwh < -1e-6:
            raise ReplayValidationError(f"Replay failed hour {h}: battery_kwh cannot be negative ({entry.battery_kwh})")

        # 4. Action and Idle magnitude
        action = entry.battery_action
        if action not in ("charge", "discharge", "idle"):
            raise ReplayValidationError(f"Replay failed hour {h}: Unknown battery action '{action}'")

        if action == "idle" and entry.battery_kwh > 1e-4:
            raise ReplayValidationError(
                f"Replay failed hour {h}: battery_action is 'idle' but battery_kwh is {entry.battery_kwh}"
            )

        # 5. Rate Limits
        if action == "charge" and entry.battery_kwh > batt.max_charge_kwh_per_hour + 1e-4:
            raise ReplayValidationError(
                f"Replay failed hour {h}: Charge rate {entry.battery_kwh} exceeds max_charge {batt.max_charge_kwh_per_hour}"
            )
        if action == "discharge" and entry.battery_kwh > batt.max_discharge_kwh_per_hour + 1e-4:
            raise ReplayValidationError(
                f"Replay failed hour {h}: Discharge rate {entry.battery_kwh} exceeds max_discharge {batt.max_discharge_kwh_per_hour}"
            )

        # 6. Battery state transition
        if action == "charge":
            expected_after = energy_before + entry.battery_kwh
        elif action == "discharge":
            expected_after = energy_before - entry.battery_kwh
        else:
            expected_after = energy_before

        diff_state = abs(entry.battery_energy_after_kwh - expected_after)
        if diff_state > TOLERANCE:
            raise ReplayValidationError(
                f"Replay failed hour {h}: Battery transition mismatch. "
                f"Energy before: {energy_before:.4f}, Action: {action}, Magnitude: {entry.battery_kwh:.4f}. "
                f"Expected: {expected_after:.4f}, Reported: {entry.battery_energy_after_kwh:.4f} (diff={diff_state:.6f})"
            )

        # 7. Battery capacity and reserve bounds
        if entry.battery_energy_after_kwh > batt.capacity_kwh + TOLERANCE:
            raise ReplayValidationError(
                f"Replay failed hour {h}: Battery energy {entry.battery_energy_after_kwh:.4f} exceeds capacity {batt.capacity_kwh:.4f}"
            )
        min_required = constraints.minimum_energy[h]
        if entry.battery_energy_after_kwh < min_required - TOLERANCE:
            raise ReplayValidationError(
                f"Replay failed hour {h}: Battery energy {entry.battery_energy_after_kwh:.4f} below required reserve {min_required:.4f}"
            )

        # 8. Solar availability constraint
        max_solar = constraints.effective_solar[h]
        if entry.solar_used_kwh > max_solar + TOLERANCE:
            raise ReplayValidationError(
                f"Replay failed hour {h}: Solar used {entry.solar_used_kwh:.4f} exceeds effective solar {max_solar:.4f}"
            )

        # 9. Simultaneous no-charge and no-discharge window constraint
        if not constraints.charge_allowed[h] and not constraints.discharge_allowed[h]:
            if action != "idle" or entry.battery_kwh > 1e-4:
                raise ReplayValidationError(
                    f"Replay failed hour {h}: Both charge and discharge prohibited, action must be idle with 0 kWh (got action={action}, kwh={entry.battery_kwh})"
                )

        # 10. No-charge window constraint
        if not constraints.charge_allowed[h] and action == "charge" and entry.battery_kwh > 1e-4:
            raise ReplayValidationError(f"Replay failed hour {h}: Charging attempted during prohibited no_charge_window")

        # 11. No-discharge window constraint
        if not constraints.discharge_allowed[h] and action == "discharge" and entry.battery_kwh > 1e-4:
            raise ReplayValidationError(f"Replay failed hour {h}: Discharging attempted during prohibited no_discharge_window")

        # 12. Grid cap constraint
        grid_cap = constraints.max_grid[h]
        if grid_cap < float("inf") and entry.grid_kwh > grid_cap + TOLERANCE:
            raise ReplayValidationError(
                f"Replay failed hour {h}: Grid import {entry.grid_kwh:.4f} exceeds max_grid cap {grid_cap:.4f}"
            )

        # 13. Energy Balance
        charge_energy = entry.battery_kwh if action == "charge" else 0.0
        discharge_energy = entry.battery_kwh if action == "discharge" else 0.0
        supply = entry.grid_kwh + entry.solar_used_kwh + discharge_energy
        consumption = demand + charge_energy
        balance_diff = abs(supply - consumption)
        if balance_diff > TOLERANCE:
            raise ReplayValidationError(
                f"Replay failed hour {h}: Energy balance violation. "
                f"Supply (grid+solar+discharge) = {supply:.4f}, Consumption (demand+charge) = {consumption:.4f}, diff = {balance_diff:.6f}"
            )

        energy_before = entry.battery_energy_after_kwh

    # 14. End-of-day battery neutrality
    final_diff = abs(energy_before - batt.initial_energy_kwh)
    if final_diff > TOLERANCE:
        raise ReplayValidationError(
            f"Replay failed: End-of-day battery neutrality broken. "
            f"Initial energy: {batt.initial_energy_kwh:.4f}, Final energy: {energy_before:.4f}, diff = {final_diff:.6f}"
        )
