"""Totals recalculation layer.

The finalized hourly_plan is the single source of truth for all aggregate totals.
Never trust LLM or intermediate solver estimates.
"""

from app.schemas.request import HourInput
from app.schemas.response import HourlyPlanEntry


def recalculate_totals(
    hourly_plan: list[HourlyPlanEntry],
    hours: list[HourInput],
) -> tuple[float, float, float]:
    """Recalculates total_grid_kwh, total_cost_bdt, and peak_grid_kwh from the plan.

    Returns:
        (total_grid_kwh, total_cost_bdt, peak_grid_kwh)
    """
    sorted_hours = sorted(hours, key=lambda x: x.hour)
    tariff_map = {h.hour: h.tariff_bdt_per_kwh for h in sorted_hours}

    total_grid = sum(entry.grid_kwh for entry in hourly_plan)
    total_cost = sum(entry.grid_kwh * tariff_map[entry.hour] for entry in hourly_plan)
    peak_grid = max(entry.grid_kwh for entry in hourly_plan)

    return (
        round(total_grid, 4),
        round(total_cost, 4),
        round(peak_grid, 4),
    )
