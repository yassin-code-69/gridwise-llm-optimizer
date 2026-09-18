#!/usr/bin/env python3
"""Smoke test script for GridWise API.

Verifies:
1. /health endpoint responds with {"status": "ok"}
2. /optimize-energy processes a valid request and produces a valid 24h schedule
"""

import sys
import json
import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

def run_smoke_test(base_url: str = DEFAULT_BASE_URL) -> bool:
    print(f"=== Running Smoke Test against {base_url} ===")
    
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        # 1. Health check
        print("\n[1/2] Checking GET /health ...")
        try:
            resp = client.get("/health")
            if resp.status_code != 200:
                print(f"FAILED: /health returned status {resp.status_code}: {resp.text}")
                return False
            data = resp.json()
            if data.get("status") != "ok":
                print(f"FAILED: /health status is not 'ok': {data}")
                return False
            print("  PASSED: /health is healthy (status: ok)")
        except Exception as e:
            print(f"FAILED: Could not reach /health: {e}")
            return False

        # 2. Optimization test
        print("\n[2/2] Checking POST /optimize-energy with SAMPLE-01 ...")
        try:
            with open("samples/public_cases.json", "r") as f:
                samples = json.load(f)
            sample_01 = samples[0]
            req_payload = {
                "scenario_id": sample_01["scenario_id"],
                "operator_notes": sample_01["operator_notes"],
                "hours": sample_01["hours"],
                "battery": sample_01["battery"],
            }
            
            resp = client.post("/optimize-energy", json=req_payload)
            if resp.status_code != 200:
                print(f"FAILED: /optimize-energy returned {resp.status_code}: {resp.text}")
                return False
            
            result = resp.json()
            assert result.get("scenario_id") == sample_01["scenario_id"], "scenario_id mismatch"
            assert len(result.get("directive_interpretation", [])) == len(sample_01["operator_notes"]), "note count mismatch"
            assert len(result.get("hourly_plan", [])) == 24, "hourly plan count != 24"
            assert result.get("total_grid_kwh", 0) >= 0, "total_grid_kwh < 0"
            assert result.get("total_cost_bdt", 0) >= 0, "total_cost_bdt < 0"
            assert result.get("peak_grid_kwh", 0) >= 0, "peak_grid_kwh < 0"
            assert len(result.get("plan_summary", "")) > 0, "empty plan_summary"
            
            print("  PASSED: /optimize-energy returned valid 24h plan:")
            print(f"    Total Grid kWh: {result['total_grid_kwh']:.2f}")
            print(f"    Total Cost BDT: {result['total_cost_bdt']:.2f}")
            print(f"    Peak Grid kWh : {result['peak_grid_kwh']:.2f}")
            print(f"    Summary       : {result['plan_summary']}")
        except Exception as e:
            print(f"FAILED: /optimize-energy check failed: {e}")
            return False

    print("\n=== ALL SMOKE TESTS PASSED SUCCESSFULLY! ===")
    return True

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    success = run_smoke_test(url)
    sys.exit(0 if success else 1)
