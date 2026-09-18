"""Randomized robustness tests evaluating LP optimizer and replay validator across random numeric profiles."""

import random
import pytest
from app.core.constraint_compiler import compile_constraints
from app.core.optimizer import solve_energy_schedule
from app.core.reconstruction import reconstruct_hourly_plan
from app.core.replay_validator import validate_hourly_plan_replay
from app.core.totals import recalculate_totals
from app.schemas.directives import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
)
from app.schemas.request import BatteryInput, HourInput, OptimizationRequest


@pytest.mark.parametrize("scenario_idx", range(25))
def test_randomized_scenario_feasibility(scenario_idx):
    """Tests 25 randomized valid scenarios ensuring 100% optimal solve and replay pass rate."""
    rng = random.Random(42 + scenario_idx)

    capacity = rng.uniform(200.0, 400.0)
    min_energy = rng.uniform(30.0, 60.0)
    initial_energy = rng.uniform(min_energy + 20.0, capacity - 20.0)
    max_charge = rng.uniform(40.0, 80.0)
    max_discharge = rng.uniform(40.0, 80.0)

    battery = BatteryInput(
        capacity_kwh=round(capacity, 2),
        initial_energy_kwh=round(initial_energy, 2),
        minimum_energy_kwh=round(min_energy, 2),
        max_charge_kwh_per_hour=round(max_charge, 2),
        max_discharge_kwh_per_hour=round(max_discharge, 2),
    )

    hours = []
    for h in range(24):
        demand = rng.uniform(40.0, 180.0)
        # Solar bell curve between 7 and 17
        solar = rng.uniform(40.0, 120.0) if 7 <= h <= 17 else 0.0
        tariff = rng.uniform(5.0, 20.0)
        hours.append(
            HourInput(
                hour=h,
                demand_kwh=round(demand, 2),
                solar_kwh=round(solar, 2),
                tariff_bdt_per_kwh=round(tariff, 2),
            )
        )

    # Add random directive
    directives = []
    choice = rng.choice(["none", "solar", "reserve", "no_charge", "no_discharge", "grid_cap"])
    if choice == "solar":
        directives.append(
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type="solar_reduction",
                structured_adjustment=SolarReductionAdjustment(hours=[11, 12, 13], factor=0.4),
                explanation="Random solar drop",
            )
        )
    elif choice == "reserve":
        directives.append(
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type="minimum_battery_reserve",
                structured_adjustment=MinimumBatteryReserveAdjustment(
                    hours=[18, 19], minimum_energy_kwh=round(min_energy + 15.0, 2)
                ),
                explanation="Random reserve",
            )
        )
    elif choice == "no_charge":
        directives.append(
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type="no_charge_window",
                structured_adjustment=NoChargeAdjustment(hours=[14, 15]),
                explanation="Random no charge",
            )
        )
    elif choice == "no_discharge":
        directives.append(
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type="no_discharge_window",
                structured_adjustment=NoDischargeAdjustment(hours=[8, 9]),
                explanation="Random no discharge",
            )
        )
    elif choice == "grid_cap":
        directives.append(
            DirectiveInterpretation(
                note_index=0,
                applies=True,
                directive_type="max_grid_window",
                structured_adjustment=MaxGridAdjustment(hours=[19, 20], max_grid_kwh=220.0),
                explanation="Random grid cap",
            )
        )

    req = OptimizationRequest(
        scenario_id=f"RANDOM-{scenario_idx:03d}",
        operator_notes=["Random scenario test"],
        hours=hours,
        battery=battery,
    )

    constraints = compile_constraints(req, directives)
    raw_res = solve_energy_schedule(req, constraints)
    plan = reconstruct_hourly_plan(req, raw_res)

    # Must pass replay with 0 errors
    validate_hourly_plan_replay(req, constraints, plan)

    # Totals must compute
    total_grid, total_cost, peak_grid = recalculate_totals(plan, hours)
    assert total_grid >= 0.0
    assert total_cost >= 0.0
    assert peak_grid >= 0.0
