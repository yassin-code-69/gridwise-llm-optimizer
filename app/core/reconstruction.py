"""Reconstructs the official response-style hourly plan from raw LP solver results."""

from app.core.optimizer import RawOptimizationResult
from app.schemas.request import OptimizationRequest
from app.schemas.response import HourlyPlanEntry, BatteryAction

EPSILON = 1e-7


def reconstruct_hourly_plan(
    request: OptimizationRequest,
    raw: RawOptimizationResult,
) -> list[HourlyPlanEntry]:
    """Converts continuous LP solution vectors into the 24-hour response schema.

    - Resolves continuous signed flow B[h] into 'charge', 'discharge', or 'idle'.
    - Preserves high precision (rounded to 6 decimal places).
    - Ensures exact numerical energy balance.
    """
    sorted_hours = sorted(request.hours, key=lambda x: x.hour)
    entries: list[HourlyPlanEntry] = []

    for h in range(24):
        demand = sorted_hours[h].demand_kwh
        b_flow = raw.battery_flow[h]
        raw_solar = raw.solar_used[h]
        raw_energy = raw.battery_energy[h]

        if b_flow > EPSILON:
            action: BatteryAction = "charge"
            b_kwh = abs(b_flow)
        elif b_flow < -EPSILON:
            action = "discharge"
            b_kwh = abs(b_flow)
        else:
            action = "idle"
            b_kwh = 0.0

        # High precision rounding
        solar_used = round(max(0.0, raw_solar), 6)
        b_kwh = round(b_kwh, 6)
        energy_after = round(max(0.0, raw_energy), 6)

        # Reconcile exact grid import from energy balance:
        # grid = demand + charge - discharge - solar_used
        charge_amt = b_kwh if action == "charge" else 0.0
        discharge_amt = b_kwh if action == "discharge" else 0.0
        exact_grid = max(0.0, demand + charge_amt - discharge_amt - solar_used)
        grid_kwh = round(exact_grid, 6)

        entries.append(
            HourlyPlanEntry(
                hour=h,
                grid_kwh=grid_kwh,
                solar_used_kwh=solar_used,
                battery_action=action,
                battery_kwh=b_kwh,
                battery_energy_after_kwh=energy_after,
            )
        )

    return entries
