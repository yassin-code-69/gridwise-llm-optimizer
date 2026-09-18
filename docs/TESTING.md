# GridWise Testing, Verification & Evaluation Guide

This document provides complete instructions for executing the GridWise test suite, running the public benchmark scenarios, and evaluating submissions with the local judge harness.

---

## 1. Overview of the Test Suite

The test suite contains **81 automated tests** categorized into 5 distinct tiers:

| Tier | Test Path | Count | Scope |
|---|---|---|---|
| **Unit Tests** | `tests/unit/` | 38 | Schemas, Pydantic validators, deterministic guardrails, constraint compiler, HiGHS LP optimizer, output reconstruction, 21-rule replay validator, totals recalculation, LRU cache, and Gemini key manager. |
| **Integration Tests** | `tests/integration/` | 4 | FastAPI HTTP endpoint lifecycle, `/health`, `/optimize-energy`, custom error handlers, and HTTP 400/500 code verification. |
| **Public Cases Regression** | `tests/public_cases/` | 1 | End-to-end evaluation against all 10 official public scenarios in `samples/public_cases.json`. |
| **Randomized Scenarios** | `tests/randomized/` | 25 | High-stress synthetic profiles: peak-load shifts, high-solar days, cloudy days, zero-solar winter nights, fluctuating tariffs, and random battery parameters. |
| **Reliability & Robustness** | `tests/reliability/` | 13 | Gemini credential failover (circuit breaking, invalid key exclusion), Replay corruption fuzzing (detecting deliberate plan tampering), and semantic paraphrasing. |

---

## 2. Running Automated Tests with Pytest

### Complete Test Suite
```bash
# Run all 81 tests with standard verbosity
pytest

# Run with detailed test progress
pytest -v
```

### Targeted Test Subsets
```bash
# Run unit tests only
pytest -v tests/unit/

# Run public cases regression only
pytest -v tests/public_cases/

# Run Gemini failover and credential resilience tests
pytest -v tests/reliability/test_gemini_failover.py

# Run replay corruption detection tests
pytest -v tests/reliability/test_replay_corruption.py
```

---

## 3. Official Public Cases Verification Script

The repository includes `scripts/run_public_cases.py`, which executes all 10 official public scenarios against a running instance of the API:

```bash
# Prerequisites: Start the server in another terminal
# uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run public cases against localhost:8000
python scripts/run_public_cases.py

# Or target a remote deployment / container URL
python scripts/run_public_cases.py http://127.0.0.1:8000
```

**Output Format:**
```text
Loading sample cases from samples/public_cases.json ...
Testing 10 cases against http://127.0.0.1:8000 ...

[01/10] SAMPLE-01    | Status: PASS  | Time:   12.4 ms | Cost:   22450.80 BDT | Error: 
[02/10] SAMPLE-02    | Status: PASS  | Time:    9.8 ms | Cost:   19820.50 BDT | Error: 
...
================================================================================
Case         | Status | Time (ms)  | Grid (kWh)   | Cost (BDT)   | Peak (kWh)
--------------------------------------------------------------------------------
SAMPLE-01    | PASS   | 12.4       | 2150.45      | 22450.80     | 185.00    
...
================================================================================
Total: 10/10 passed.
```

---

## 4. Local Judge CLI (`scripts/local_judge.py`)

The standalone evaluation harness (`scripts/local_judge.py`) simulates the hackathon's automated grading environment. It audits:
1. Pydantic v2 schema compliance
2. Ground-truth directive agreement (if provided)
3. 21-rule independent replay validation
4. Deterministic totals recalculation
5. Battery end-of-day neutrality ($|E[23] - E_{\text{init}}| \le 0.01$)
6. Latency threshold ($\le 5000$ ms)

### Usage Modes:

```bash
# 1. Direct in-process run using configured LLM provider (live Gemini / OpenAI)
python scripts/local_judge.py --input samples/public_cases.json

# 2. Fast offline run using deterministic mock semantic parser (zero API keys needed)
python scripts/local_judge.py --input samples/public_cases.json --mock

# 3. Single scenario evaluation
python scripts/local_judge.py --input test_request.json

# 4. HTTP evaluation against a running server or Docker container
python scripts/local_judge.py --url http://127.0.0.1:8000 --input samples/public_cases.json
```

---

## 5. Performance Benchmarking (`scripts/benchmark.py`)

Measures request latency distributions (min, mean, p50, p95, max) and verifies the official $\le 5.0$ second threshold:

```bash
# Run 20 benchmark iterations against running server
python scripts/benchmark.py http://127.0.0.1:8000 20
```

**Sample Output:**
```text
=== GridWise Performance Benchmark ===
Target URL: http://127.0.0.1:8000
Iterations: 20 requests

Req #01: OK in   11.2 ms
Req #02: OK in    8.5 ms
...
==================================================
Benchmark Results (20 requests):
  Success Rate : 20/20 (100.0%)
  Min Latency  :    7.8 ms
  Mean Latency :    9.4 ms
  P50 (Median) :    8.9 ms
  P95 Latency  :   12.1 ms
  Max Latency  :   14.5 ms
==================================================
  [SUCCESS] P95 is <= 5000 ms (Full performance points threshold met!)
```

---

## 6. End-to-End Smoke Test (`scripts/smoke_test.py`)

Verifies service liveness and checks a real optimization payload end-to-end:

```bash
python scripts/smoke_test.py http://127.0.0.1:8000
```
