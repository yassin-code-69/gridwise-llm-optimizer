#!/usr/bin/env python3
"""Run all 10 public sample cases and report detailed results."""

import sys
import json
import time
import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

def run_all_public_cases(base_url: str = DEFAULT_BASE_URL):
    print(f"Loading sample cases from samples/public_cases.json ...")
    with open("samples/public_cases.json", "r") as f:
        cases = json.load(f)
        
    print(f"Testing {len(cases)} cases against {base_url} ...\n")
    results = []
    
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        for idx, case in enumerate(cases, 1):
            sc_id = case["scenario_id"]
            payload = {
                "scenario_id": sc_id,
                "operator_notes": case["operator_notes"],
                "hours": case["hours"],
                "battery": case["battery"]
            }
            
            t0 = time.perf_counter()
            try:
                resp = client.post("/optimize-energy", json=payload)
                elapsed = time.perf_counter() - t0
                if resp.status_code == 200:
                    data = resp.json()
                    status = "PASS"
                    cost = data.get("total_cost_bdt", 0)
                    grid = data.get("total_grid_kwh", 0)
                    peak = data.get("peak_grid_kwh", 0)
                    err = ""
                else:
                    status = "FAIL"
                    cost, grid, peak = 0, 0, 0
                    err = f"HTTP {resp.status_code}: {resp.text[:100]}"
            except Exception as e:
                elapsed = time.perf_counter() - t0
                status = "ERROR"
                cost, grid, peak = 0, 0, 0
                err = str(e)[:100]
                
            results.append({
                "case": sc_id,
                "status": status,
                "time_ms": round(elapsed * 1000, 1),
                "grid_kwh": grid,
                "cost_bdt": cost,
                "peak_kwh": peak,
                "error": err
            })
            print(f"[{idx:02d}/{len(cases):02d}] {sc_id:<12} | Status: {status:<5} | Time: {elapsed*1000:6.1f} ms | Cost: {cost:10.2f} BDT | Error: {err}")

    print("\n" + "=" * 80)
    print(f"{'Case':<12} | {'Status':<6} | {'Time (ms)':<10} | {'Grid (kWh)':<12} | {'Cost (BDT)':<12} | {'Peak (kWh)':<10}")
    print("-" * 80)
    passed = 0
    for r in results:
        if r["status"] == "PASS":
            passed += 1
        print(f"{r['case']:<12} | {r['status']:<6} | {r['time_ms']:<10.1f} | {r['grid_kwh']:<12.2f} | {r['cost_bdt']:<12.2f} | {r['peak_kwh']:<10.2f}")
    print("=" * 80)
    print(f"Total: {passed}/{len(cases)} passed.")
    return passed == len(cases)

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    all_passed = run_all_public_cases(url)
    sys.exit(0 if all_passed else 1)
