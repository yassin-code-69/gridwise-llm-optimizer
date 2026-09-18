#!/usr/bin/env python3
"""Benchmark script to measure latency distribution (p50, p95, max) and reliability."""

import sys
import json
import time
import httpx
import statistics

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
NUM_REQUESTS = 20

def run_benchmark(base_url: str = DEFAULT_BASE_URL, num_requests: int = NUM_REQUESTS):
    print(f"=== GridWise Performance Benchmark ===")
    print(f"Target URL: {base_url}")
    print(f"Iterations: {num_requests} requests\n")
    
    with open("samples/public_cases.json", "r") as f:
        cases = json.load(f)
        
    latencies = []
    success_count = 0
    failure_count = 0
    
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        # Warm-up request
        print("Running warm-up request...")
        try:
            client.get("/health")
        except Exception as e:
            print(f"Warning: Health check warm-up failed: {e}")
            
        for i in range(num_requests):
            case = cases[i % len(cases)]
            payload = {
                "scenario_id": f"BENCH-{i+1:03d}",
                "operator_notes": case["operator_notes"],
                "hours": case["hours"],
                "battery": case["battery"]
            }
            
            t0 = time.perf_counter()
            try:
                resp = client.post("/optimize-energy", json=payload)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if resp.status_code == 200:
                    success_count += 1
                    latencies.append(elapsed_ms)
                    print(f"Req #{i+1:02d}: OK in {elapsed_ms:6.1f} ms")
                else:
                    failure_count += 1
                    print(f"Req #{i+1:02d}: FAILED (HTTP {resp.status_code}) in {elapsed_ms:6.1f} ms")
            except Exception as e:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                failure_count += 1
                print(f"Req #{i+1:02d}: ERROR ({e}) in {elapsed_ms:6.1f} ms")

    if not latencies:
        print("\nNo successful requests recorded.")
        return False
        
    latencies.sort()
    p50 = statistics.median(latencies)
    idx_95 = int(0.95 * len(latencies))
    p95 = latencies[min(idx_95, len(latencies)-1)]
    mean_val = statistics.mean(latencies)
    min_val = min(latencies)
    max_val = max(latencies)
    
    print("\n" + "=" * 50)
    print(f"Benchmark Results ({num_requests} requests):")
    print(f"  Success Rate : {success_count}/{num_requests} ({success_count/num_requests*100:.1f}%)")
    print(f"  Min Latency  : {min_val:6.1f} ms")
    print(f"  Mean Latency : {mean_val:6.1f} ms")
    print(f"  P50 (Median) : {p50:6.1f} ms")
    print(f"  P95 Latency  : {p95:6.1f} ms")
    print(f"  Max Latency  : {max_val:6.1f} ms")
    print("=" * 50)
    
    # Official requirement: p95 <= 5000 ms for full points
    if p95 <= 5000:
        print("  [SUCCESS] P95 is <= 5000 ms (Full performance points threshold met!)")
    else:
        print("  [WARNING] P95 exceeded 5000 ms.")
        
    return failure_count == 0

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    n = int(sys.argv[2]) if len(sys.argv) > 2 else NUM_REQUESTS
    ok = run_benchmark(url, n)
    sys.exit(0 if ok else 1)
