"""Exact 24-hour continuous Linear Programming optimizer."""

from dataclasses import dataclass
import pulp
from app.core.constraint_compiler import EffectiveConstraints
from app.errors import OptimizationError
from app.schemas.request import OptimizationRequest


@dataclass
class RawOptimizationResult:
    grid: list[float]              # G[h] for h=0..23
    solar_used: list[float]        # S[h] for h=0..23
    battery_flow: list[float]      # B[h] for h=0..23 (signed)
    battery_energy: list[float]    # E[h] for h=0..23 (end of hour)
    objective_cost: float


def get_available_solver():
    """Returns the primary HiGHS solver if available, otherwise falls back to CBC."""
    try:
        solver = pulp.getSolver("HiGHS", msg=False)
        if solver.available():
            return solver
    except Exception:
        pass

    try:
        solver = pulp.PULP_CBC_CMD(msg=False)
        if solver.available():
            return solver
    except Exception:
        pass

    # Generic default fallback
    return pulp.PULP_CBC_CMD(msg=False)


def solve_energy_schedule(
    request: OptimizationRequest,
    constraints: EffectiveConstraints,
    forced_solver: str = None,
) -> RawOptimizationResult:
    """Formulates and solves the full 24-hour Linear Program globally.

    Raises:
        OptimizationError: If solver fails or status is not Optimal.
    """
    sorted_hours = sorted(request.hours, key=lambda x: x.hour)
    batt = request.battery

    # Create Linear Program
    prob = pulp.LpProblem("GridWise_24H_Optimization", pulp.LpMinimize)

    # 1. Decision Variables
    G = [pulp.LpVariable(f"grid_{h}", lowBound=0.0) for h in range(24)]
    S = [
        pulp.LpVariable(
            f"solar_{h}",
            lowBound=0.0,
            upBound=constraints.effective_solar[h],
        )
        for h in range(24)
    ]
    B = [
        pulp.LpVariable(
            f"battery_flow_{h}",
            lowBound=-batt.max_discharge_kwh_per_hour,
            upBound=batt.max_charge_kwh_per_hour,
        )
        for h in range(24)
    ]
    E = [
        pulp.LpVariable(
            f"battery_energy_{h}",
            lowBound=constraints.minimum_energy[h],
            upBound=batt.capacity_kwh,
        )
        for h in range(24)
    ]

    # 2. Objective: Minimize 24h Grid Electricity Cost
    prob += pulp.lpSum(G[h] * sorted_hours[h].tariff_bdt_per_kwh for h in range(24)), "Total_Cost"

    # 3. Hard Operational Constraints
    for h in range(24):
        demand = sorted_hours[h].demand_kwh

        # Energy balance: G[h] + S[h] = demand[h] + B[h]
        prob += G[h] + S[h] == demand + B[h], f"Energy_Balance_{h}"

        # Battery State Transition
        if h == 0:
            prob += E[0] == batt.initial_energy_kwh + B[0], "Battery_State_0"
        else:
            prob += E[h] == E[h - 1] + B[h], f"Battery_State_{h}"

        # No-Charge Window constraint
        if not constraints.charge_allowed[h]:
            prob += B[h] <= 0.0, f"No_Charge_{h}"

        # No-Discharge Window constraint
        if not constraints.discharge_allowed[h]:
            prob += B[h] >= 0.0, f"No_Discharge_{h}"

        # Grid Cap constraint
        if constraints.max_grid[h] < float("inf"):
            prob += G[h] <= constraints.max_grid[h], f"Grid_Cap_{h}"

    # End-of-Day Neutrality: E[23] == initial_energy_kwh
    prob += E[23] == batt.initial_energy_kwh, "End_Of_Day_Neutrality"

    # 4. Choose Solver & Solve
    if forced_solver == "CBC":
        solver = pulp.PULP_CBC_CMD(msg=False)
    elif forced_solver == "HiGHS":
        solver = pulp.getSolver("HiGHS", msg=False)
    else:
        solver = get_available_solver()

    try:
        prob.solve(solver)
    except Exception as exc:
        raise OptimizationError(f"Solver execution error: {exc}")

    status_name = pulp.LpStatus[prob.status]
    if status_name != "Optimal":
        raise OptimizationError(
            f"Optimization failed to find an optimal solution. Solver status: {status_name}"
        )

    # 5. Extract continuous solution values
    res_G = [float(pulp.value(G[h])) for h in range(24)]
    res_S = [float(pulp.value(S[h])) for h in range(24)]
    res_B = [float(pulp.value(B[h])) for h in range(24)]
    res_E = [float(pulp.value(E[h])) for h in range(24)]
    obj_cost = float(pulp.value(prob.objective))

    return RawOptimizationResult(
        grid=res_G,
        solar_used=res_S,
        battery_flow=res_B,
        battery_energy=res_E,
        objective_cost=obj_cost,
    )
