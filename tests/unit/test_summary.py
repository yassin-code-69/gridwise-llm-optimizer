"""Unit tests for granular deterministic summary generator."""

from app.core.summary import format_hour_ranges, generate_plan_summary
from app.schemas.directives import DirectiveInterpretation, SolarReductionAdjustment
from app.schemas.request import BatteryInput, HourInput
from app.schemas.response import HourlyPlanEntry


def test_format_hour_ranges():
    assert format_hour_ranges([]) == ""
    assert format_hour_ranges([5]) == "hour 5"
    assert format_hour_ranges([1, 2, 3]) == "hours 1-3"
    assert format_hour_ranges([2, 3, 4, 13, 14, 15]) == "hours 2-4, 13-15"
    assert format_hour_ranges([0, 2, 4]) == "hours 0, 2, 4"
    assert format_hour_ranges([1, 2, 4, 5, 7]) == "hours 1-2, 4-5, 7"


def test_generate_plan_summary_content():
    battery = BatteryInput(
        capacity_kwh=100.0,
        initial_energy_kwh=50.0,
        minimum_energy_kwh=20.0,
        max_charge_kwh_per_hour=25.0,
        max_discharge_kwh_per_hour=25.0,
    )
    directives = [
        DirectiveInterpretation(
            note_index=0,
            directive_type="solar_reduction",
            applies=True,
            structured_adjustment=SolarReductionAdjustment(hours=[10, 11, 12], factor=0.7),
            explanation="Reduce solar by 30%",
        )
    ]
    hours = [HourInput(hour=h, demand_kwh=10.0, solar_kwh=5.0, tariff_bdt_per_kwh=5.0) for h in range(24)]
    plan = [
        HourlyPlanEntry(
            hour=h,
            grid_kwh=10.0,
            solar_used_kwh=5.0,
            battery_action="charge" if h in (2, 3) else ("discharge" if h in (18, 19) else "idle"),
            battery_kwh=5.0 if h in (2, 3, 18, 19) else 0.0,
            battery_energy_after_kwh=50.0,
        )
        for h in range(24)
    ]

    summary = generate_plan_summary(directives, plan, hours, battery)
    assert "compensated for solar output reductions" in summary
    assert "Charged during hours 2-3" in summary
    assert "discharged during hours 18-19" in summary
    assert "50.0 kWh was fully restored by hour 23" in summary
