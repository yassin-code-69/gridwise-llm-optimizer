"""Local Judge CLI — Independent verification and evaluation runner.

Simulates the official hidden-judge evaluation by running test scenarios through
the API or service and verifying:
  1. Response schema compliance (Pydantic v2)
  2. Ground-truth directive agreement (if available)
  3. Independent solar forecast rebuild
  4. Physical battery transitions, rate limits, and capacity bounds
  5. Deterministic hourly energy balance
  6. Operational directive adherence (windows, reserves, grid caps)
  7. End-of-day battery neutrality (E[23] == E_init +/- 0.01 kWh)
  8. Independent totals recalculation
  9. Latency profiling against the 5.0-second limit

Usage:
  python scripts/local_judge.py --input samples/public_cases.json
  python scripts/local_judge.py --input test_request.json
  python scripts/local_judge.py --url http://127.0.0.1:8000 --input samples/public_cases.json
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from app.core.constraint_compiler import compile_constraints
from app.core.replay_validator import validate_hourly_plan_replay
from app.core.totals import recalculate_totals
from app.errors import ReplayValidationError
from app.schemas.request import OptimizationRequest
from app.schemas.response import OptimizationResponse


class LocalJudge:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 15.0,
        verbose: bool = False,
        use_mock: bool = False,
    ):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout
        self.verbose = verbose
        self.use_mock = use_mock
        if not self.base_url:
            from app.llm.interpreter import LLMInterpreter
            from app.llm.providers.mock_provider import MockDirectiveInterpreter
            from app.services.optimization_service import OptimizationService

            interpreter = LLMInterpreter(provider=MockDirectiveInterpreter()) if use_mock else None
            self.service = OptimizationService(interpreter=interpreter)
        else:
            self.service = None

    def clean_request_payload(self, raw_scenario: dict[str, Any]) -> dict[str, Any]:
        """Extracts strictly the 4 schema-compliant fields expected by OptimizationRequest."""
        return {
            k: raw_scenario[k]
            for k in ("scenario_id", "operator_notes", "hours", "battery")
            if k in raw_scenario
        }

    async def execute_scenario(self, raw_scenario: dict[str, Any]) -> tuple[dict[str, Any], float]:
        """Runs the scenario either via HTTP POST or directly in-process."""
        payload = self.clean_request_payload(raw_scenario)
        t0 = time.perf_counter()

        if self.base_url:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.base_url}/optimize-energy", json=payload)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if res.status_code != 200:
                    raise RuntimeError(f"HTTP {res.status_code}: {res.text}")
                return res.json(), elapsed_ms
        else:
            req = OptimizationRequest.model_validate(payload)
            result = await self.service.optimize(req)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return result.model_dump(), elapsed_ms

    def judge_scenario(self, raw_scenario: dict[str, Any], raw_response: dict[str, Any], latency_ms: float) -> dict[str, Any]:
        """Performs strict independent verification of the optimization response."""
        verdict = {
            "scenario_id": raw_scenario.get("scenario_id", "UNKNOWN"),
            "latency_ms": latency_ms,
            "passed": True,
            "errors": [],
            "directives_passed": True,
            "replay_passed": True,
            "totals_passed": True,
            "neutrality_passed": True,
            "cost_bdt": 0.0,
            "grid_kwh": 0.0,
        }

        # 1. Schema Validation
        payload = self.clean_request_payload(raw_scenario)
        try:
            req = OptimizationRequest.model_validate(payload)
        except Exception as exc:
            verdict["passed"] = False
            verdict["errors"].append(f"Request schema invalid: {exc}")
            return verdict

        try:
            res = OptimizationResponse.model_validate(raw_response)
        except Exception as exc:
            verdict["passed"] = False
            verdict["errors"].append(f"Response schema invalid: {exc}")
            return verdict

        verdict["cost_bdt"] = res.total_cost_bdt
        verdict["grid_kwh"] = res.total_grid_kwh

        # 2. Latency Check (< 5000 ms)
        if latency_ms > 5000.0:
            verdict["passed"] = False
            verdict["errors"].append(f"Latency {latency_ms:.1f}ms exceeds 5000ms threshold")

        # 3. Ground Truth Directive Matching (if provided in test scenario)
        expected_dirs = raw_scenario.get("expected_interpretations") or raw_scenario.get("expected_directives")
        if expected_dirs:
            if len(res.directive_interpretation) != len(expected_dirs):
                verdict["directives_passed"] = False
                verdict["errors"].append(
                    f"Directive count mismatch: expected {len(expected_dirs)}, got {len(res.directive_interpretation)}"
                )
            else:
                for idx, exp in enumerate(expected_dirs):
                    act = res.directive_interpretation[idx]
                    exp_type = exp.get("directive_type")
                    if act.directive_type != exp_type:
                        verdict["directives_passed"] = False
                        verdict["errors"].append(
                            f"Directive {idx} type mismatch: expected {exp_type}, got {act.directive_type}"
                        )

        # 4. Independent Replay Validation
        try:
            constraints = compile_constraints(req, res.directive_interpretation)
            validate_hourly_plan_replay(req, constraints, res.hourly_plan, res.directive_interpretation)
        except ReplayValidationError as exc:
            verdict["replay_passed"] = False
            verdict["passed"] = False
            verdict["errors"].append(f"Replay validation error: {exc}")

        # 5. Independent Totals Recalculation
        calc_grid, calc_cost, calc_peak = recalculate_totals(res.hourly_plan, req.hours)
        if abs(calc_grid - res.total_grid_kwh) > 0.05:
            verdict["totals_passed"] = False
            verdict["passed"] = False
            verdict["errors"].append(
                f"Total grid mismatch: reported {res.total_grid_kwh:.2f}, recomputed {calc_grid:.2f}"
            )
        if abs(calc_cost - res.total_cost_bdt) > 0.05:
            verdict["totals_passed"] = False
            verdict["passed"] = False
            verdict["errors"].append(
                f"Total cost mismatch: reported {res.total_cost_bdt:.2f}, recomputed {calc_cost:.2f}"
            )
        if abs(calc_peak - res.peak_grid_kwh) > 0.05:
            verdict["totals_passed"] = False
            verdict["passed"] = False
            verdict["errors"].append(
                f"Peak grid mismatch: reported {res.peak_grid_kwh:.2f}, recomputed {calc_peak:.2f}"
            )

        # 6. Battery Neutrality Check
        end_energy = res.hourly_plan[23].battery_energy_after_kwh
        init_energy = req.battery.initial_energy_kwh
        if abs(end_energy - init_energy) > 0.01:
            verdict["neutrality_passed"] = False
            verdict["passed"] = False
            verdict["errors"].append(
                f"End neutrality broken: initial={init_energy:.2f}, final={end_energy:.2f}"
            )

        if verdict["errors"]:
            verdict["passed"] = False

        return verdict


def load_scenarios(target: Path) -> list[dict[str, Any]]:
    """Loads scenarios from a single JSON file (dict or list) or a directory of JSON files."""
    scenarios: list[dict[str, Any]] = []
    if target.is_file():
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                scenarios.extend(data)
            elif isinstance(data, dict):
                if "scenarios" in data and isinstance(data["scenarios"], list):
                    scenarios.extend(data["scenarios"])
                else:
                    scenarios.append(data)
    elif target.is_dir():
        for p in sorted(target.glob("*.json")):
            scenarios.extend(load_scenarios(p))
    else:
        raise FileNotFoundError(f"Input path not found: {target}")
    return scenarios


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="GridWise Local Judge — Evaluation & Replay Harness")
    parser.add_argument("--input", "-i", type=str, required=True, help="Path to scenario JSON file or directory")
    parser.add_argument("--url", "-u", type=str, default=None, help="Base URL of running service (optional)")
    parser.add_argument("--timeout", "-t", type=float, default=15.0, help="Request timeout in seconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose output")
    parser.add_argument("--mock", "-m", action="store_true", help="Run with deterministic mock semantic parser (fast offline run)")
    args = parser.parse_args()

    input_path = Path(args.input)
    scenarios = load_scenarios(input_path)
    if not scenarios:
        print(f"Error: No scenarios loaded from {input_path}")
        return 1

    print("=" * 80)
    print(f"  GRIDWISE LOCAL JUDGE — EVALUATION HARNESS")
    print(f"  Target: {input_path} ({len(scenarios)} scenarios)")
    mode_str = f"Live HTTP ({args.url})" if args.url else ("Mock Semantic (In-Process)" if args.mock else "Direct In-Process Service")
    print(f"  Execution Mode: {mode_str}")
    print("=" * 80)

    judge = LocalJudge(base_url=args.url, timeout=args.timeout, verbose=args.verbose, use_mock=args.mock)
    results = []

    header = f"{'Scenario ID':<18} | {'Verdict':<8} | {'Latency':<9} | {'Grid kWh':<10} | {'Cost BDT':<10} | {'Issues'}"
    print(header)
    print("-" * 80)

    for sc in scenarios:
        sc_id = sc.get("scenario_id", "UNKNOWN")
        try:
            resp, elapsed_ms = await judge.execute_scenario(sc)
            v = judge.judge_scenario(sc, resp, elapsed_ms)
        except Exception as exc:
            v = {
                "scenario_id": sc_id,
                "latency_ms": 0.0,
                "passed": False,
                "cost_bdt": 0.0,
                "grid_kwh": 0.0,
                "errors": [str(exc)],
            }
        results.append(v)

        status = "PASS" if v["passed"] else "FAIL"
        err_str = "; ".join(v["errors"]) if v["errors"] else "None"
        if len(err_str) > 30:
            err_str = err_str[:27] + "..."
        lat_str = f"{v['latency_ms']:.1f} ms"
        grid_str = f"{v['grid_kwh']:.1f}"
        cost_str = f"{v['cost_bdt']:.2f}"
        print(f"{v['scenario_id']:<18} | {status:<8} | {lat_str:<9} | {grid_str:<10} | {cost_str:<10} | {err_str}")

    print("-" * 80)
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    avg_latency = sum(r["latency_ms"] for r in results) / total if total > 0 else 0.0

    print(f"Summary: {passed}/{total} Passed ({failed} Failed) | Mean Latency: {avg_latency:.1f} ms")
    print("=" * 80)

    return 0 if failed == 0 else 1


def main():
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
