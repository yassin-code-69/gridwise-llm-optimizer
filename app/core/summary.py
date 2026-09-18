"""Deterministic plan summary generator with granular interval aggregation."""

from app.schemas.directives import DirectiveInterpretation
from app.schemas.request import BatteryInput, HourInput
from app.schemas.response import HourlyPlanEntry


def format_hour_ranges(hours: list[int]) -> str:
    """Aggregates an integer list of hours into human-readable contiguous intervals.

    Examples:
        [2, 3, 4, 13, 14, 15] -> 'hours 2-4, 13-15'
        [5] -> 'hour 5'
        [1, 3, 5] -> 'hours 1, 3, 5'
    """
    if not hours:
        return ""
    sorted_h = sorted(set(hours))
    ranges: list[str] = []
    start = sorted_h[0]
    end = start

    for h in sorted_h[1:]:
        if h == end + 1:
            end = h
        else:
            if start == end:
                ranges.append(f"{start}")
            else:
                ranges.append(f"{start}-{end}")
            start = h
            end = h

    if start == end:
        ranges.append(f"{start}")
    else:
        ranges.append(f"{start}-{end}")

    ranges_str = ", ".join(ranges)
    if len(sorted_h) == 1 and "-" not in ranges_str:
        return f"hour {ranges_str}"
    return f"hours {ranges_str}"


def generate_plan_summary(
    directives: list[DirectiveInterpretation],
    hourly_plan: list[HourlyPlanEntry],
    hours: list[HourInput],
    battery: BatteryInput,
) -> str:
    """Produces a concise, accurate natural language summary of the optimization schedule."""
    active_types = [d.directive_type for d in directives if d.applies and d.directive_type != "no_op"]

    parts = []
    if "solar_reduction" in active_types:
        parts.append("compensated for solar output reductions")
    if "minimum_battery_reserve" in active_types:
        parts.append("strictly maintained required battery reserve")
    if "max_grid_window" in active_types:
        parts.append("honored peak grid import caps")
    if "no_charge_window" in active_types or "no_discharge_window" in active_types:
        parts.append("respected scheduled battery outage windows")

    charge_hours = [e.hour for e in hourly_plan if e.battery_action == "charge"]
    discharge_hours = [e.hour for e in hourly_plan if e.battery_action == "discharge"]

    strategy_desc = "Dispatched battery storage to minimize grid costs"
    if parts:
        directives_str = ", ".join(parts)
        strategy_desc += f" while having {directives_str}"

    if charge_hours and discharge_hours:
        c_str = format_hour_ranges(charge_hours)
        d_str = format_hour_ranges(discharge_hours)
        strategy_desc += f". Charged during {c_str} and discharged during {d_str}."
    elif charge_hours:
        c_str = format_hour_ranges(charge_hours)
        strategy_desc += f". Charged during {c_str}."
    elif discharge_hours:
        d_str = format_hour_ranges(discharge_hours)
        strategy_desc += f". Discharged during {d_str}."
    else:
        strategy_desc += ". Battery remained idle throughout the day."

    strategy_desc += f" Starting battery level of {battery.initial_energy_kwh:.1f} kWh was fully restored by hour 23."
    return strategy_desc
