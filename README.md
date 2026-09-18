# GridWise — LLM-Assisted Smart Campus Energy Optimizer

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![PuLP](https://img.shields.io/badge/PuLP-HiGHS%2FCBC-orange.svg)](https://coin-or.github.io/pulp/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063.svg)](https://docs.pydantic.dev/)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

**GridWise** is a hybrid AI + deterministic optimization service designed for the **BUP CSE Fest 2026 Hackathon** (*LLM-Assisted Smart Campus Energy Optimization Challenge*). The system coordinates natural language operator directive interpretation with continuous Linear Programming (LP) to schedule 24-hour campus energy import, rooftop solar utilization, and battery storage dispatch.

---

## Architecture Pipeline

```text
               +----------------------------------+
               |  Incoming HTTP Request (JSON)    |
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | Stage 1: Pydantic v2 Validation  |
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | Stage 2: LLM Note Interpretation |
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | Stage 3: Deterministic Guardrail |
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | Stage 4: 24h Constraint Compiler |
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | Stage 5: Exact Continuous LP     |
               |       (HiGHS / PuLP Solver)      |
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | Stage 6: Output Reconstruction   |
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | Stage 7: Independent Replay Audit|
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | Stage 8: Deterministic Totals    |
               +----------------+-----------------+
                                |
                                v
               +----------------------------------+
               | HTTP 200: Valid Optimal Plan     |
               +----------------------------------+
```

### Separation of Concerns
1. **LLM Semantic Interpreter**: Translates operator notes into 6 strict, typed directive objects. Does *not* generate mathematical schedules or calculate grid costs.
2. **Deterministic Guardrails**: Validates untrusted LLM output before it reaches the optimizer (note-index mapping, hour ranges, numeric bounds, `no_op` null semantics).
3. **Constraint Compiler**: Maps validated directives into 24-hour mathematical upper/lower bounds.
4. **Exact Linear Program**: Continuous full-horizon LP solved simultaneously over 24 hours to minimize total grid electricity cost.
5. **Independent Replay Validator**: Audits the finalized plan against 21 physical, battery, solar, rate, balance, and end-of-day neutrality rules before responding.
6. **Totals Recalculator**: Recomputes `total_grid_kwh`, `total_cost_bdt`, and `peak_grid_kwh` directly from `hourly_plan` as the single source of truth.

---

## Tech Stack

- **Language**: Python 3.11
- **API Framework**: FastAPI, Uvicorn
- **Validation**: Pydantic v2, Pydantic Settings
- **HTTP Client**: HTTPX (async)
- **Optimization**: PuLP (Continuous Linear Program)
- **Primary Solver**: HiGHS (`highspy`)
- **Fallback Solver**: CBC (`PULP_CBC_CMD`)
- **Testing**: pytest, pytest-asyncio
- **Containerization**: Docker (`python:3.11-slim`)

---

## Supported Directives & Contracts

| Directive Name | Purpose | Structured Adjustment Format |
|---|---|---|
| `solar_reduction` | Usable solar reduced during listed hours | `{"hours": [11, 12, 13], "factor": 0.2}` *(0.2 = 20% remains)* |
| `minimum_battery_reserve` | Hard lower bound on battery stored energy | `{"hours": [18, 19, 20], "minimum_energy_kwh": 100.0}` |
| `no_charge_window` | Prohibits battery charging during listed hours | `{"hours": [14, 15]}` |
| `no_discharge_window` | Prohibits battery discharging during listed hours | `{"hours": [17, 18]}` |
| `max_grid_window` | Upper bound on grid electricity import | `{"hours": [19, 20, 21], "max_grid_kwh": 150.0}` |
| `no_op` | Irrelevant / administrative notes | `applies: false`, `structured_adjustment: null` |

### Invariant Rules
- **Time Convention**: All time intervals are **start-inclusive, end-exclusive** whole hours ($0..23$). "1 PM to 3 PM" $\rightarrow [13, 14]$.
- **Solar Factor**: `factor` is the fraction that *remains usable*. An "80% reduction" means $20\%$ remains $\rightarrow \text{factor} = 0.20$.
- **Battery Invariants**:
  - Capacity: $\text{stored energy} \in [\text{min\_reserve}, \text{capacity}]$.
  - Energy Balance: $\text{Grid} + \text{Solar} + \text{Discharge} = \text{Demand} + \text{Charge}$.
  - End Neutrality: $E[23] == \text{Initial Energy}$ (hard equality constraint).

---

## Configuration & Environment Variables

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

| Variable | Type | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | string | `mock` | Selected LLM backend (`mock`, `openai`, `gemini`) |
| `LLM_MODEL` | string | `gpt-4o-mini` | Model name identifier |
| `LLM_API_KEY` | string | `None` | API key for hosted LLM provider |
| `LLM_TIMEOUT_SECONDS` | float | `5.0` | Timeout per model inference request |
| `LLM_MAX_RETRIES` | int | `2` | Bounded retries for provider/validation failures |
| `PORT` | int | `8000` | Port for Uvicorn API server |
| `HOST` | string | `0.0.0.0` | Host binding for server |
| `LOG_LEVEL` | string | `INFO` | Logging verbosity |

> **Security Note**: Never commit `.env` or API keys. The repository `.gitignore` strictly prevents secrets from being committed.

---

## Local Setup & Quickstart

### 1. Prerequisites
- Python 3.11
- `uv` (recommended) or standard `pip` / `venv`

### 2. Setup Virtual Environment
```bash
# Using uv (fastest)
uv venv --python 3.11
uv pip install -r requirements.txt

# Or using standard python
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the Service
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## API Usage & Examples

### Health Check (`GET /health`)
```bash
curl http://127.0.0.1:8000/health
```
**Response:**
```json
{
  "status": "ok"
}
```

### Optimize Energy (`POST /optimize-energy`)
```bash
curl -X POST http://127.0.0.1:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "DEMO-01",
    "operator_notes": [
      "Due to solar panel cleaning, rooftop solar output will drop by 50% from 11 AM to 2 PM.",
      "Campus shift handover scheduled at 3 PM."
    ],
    "hours": [
      {"hour": 0, "demand_kwh": 60, "solar_kwh": 0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 1, "demand_kwh": 55, "solar_kwh": 0, "tariff_bdt_per_kwh": 5.5},
      {"hour": 2, "demand_kwh": 50, "solar_kwh": 0, "tariff_bdt_per_kwh": 5.0},
      {"hour": 3, "demand_kwh": 50, "solar_kwh": 0, "tariff_bdt_per_kwh": 5.0},
      {"hour": 4, "demand_kwh": 55, "solar_kwh": 0, "tariff_bdt_per_kwh": 5.5},
      {"hour": 5, "demand_kwh": 65, "solar_kwh": 0, "tariff_bdt_per_kwh": 6.0},
      {"hour": 6, "demand_kwh": 90, "solar_kwh": 10, "tariff_bdt_per_kwh": 7.5},
      {"hour": 7, "demand_kwh": 120, "solar_kwh": 35, "tariff_bdt_per_kwh": 9.0},
      {"hour": 8, "demand_kwh": 140, "solar_kwh": 70, "tariff_bdt_per_kwh": 10.0},
      {"hour": 9, "demand_kwh": 160, "solar_kwh": 100, "tariff_bdt_per_kwh": 10.5},
      {"hour": 10, "demand_kwh": 170, "solar_kwh": 130, "tariff_bdt_per_kwh": 11.0},
      {"hour": 11, "demand_kwh": 180, "solar_kwh": 145, "tariff_bdt_per_kwh": 11.0},
      {"hour": 12, "demand_kwh": 175, "solar_kwh": 140, "tariff_bdt_per_kwh": 10.5},
      {"hour": 13, "demand_kwh": 165, "solar_kwh": 120, "tariff_bdt_per_kwh": 10.0},
      {"hour": 14, "demand_kwh": 150, "solar_kwh": 90, "tariff_bdt_per_kwh": 9.5},
      {"hour": 15, "demand_kwh": 145, "solar_kwh": 55, "tariff_bdt_per_kwh": 9.5},
      {"hour": 16, "demand_kwh": 155, "solar_kwh": 20, "tariff_bdt_per_kwh": 11.0},
      {"hour": 17, "demand_kwh": 185, "solar_kwh": 5, "tariff_bdt_per_kwh": 15.0},
      {"hour": 18, "demand_kwh": 210, "solar_kwh": 0, "tariff_bdt_per_kwh": 17.5},
      {"hour": 19, "demand_kwh": 200, "solar_kwh": 0, "tariff_bdt_per_kwh": 18.0},
      {"hour": 20, "demand_kwh": 180, "solar_kwh": 0, "tariff_bdt_per_kwh": 16.5},
      {"hour": 21, "demand_kwh": 140, "solar_kwh": 0, "tariff_bdt_per_kwh": 14.0},
      {"hour": 22, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 9.0},
      {"hour": 23, "demand_kwh": 75, "solar_kwh": 0, "tariff_bdt_per_kwh": 7.0}
    ],
    "battery": {
      "capacity_kwh": 200.0,
      "initial_energy_kwh": 100.0,
      "minimum_energy_kwh": 40.0,
      "max_charge_kwh_per_hour": 50.0,
      "max_discharge_kwh_per_hour": 50.0
    }
  }'
```

**Response Format:**
```json
{
  "scenario_id": "DEMO-01",
  "directive_interpretation": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {
        "hours": [11, 12, 13],
        "factor": 0.5
      },
      "explanation": "Solar availability reduced by 50% from 11 AM to 2 PM."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "Shift handover note does not affect energy scheduling."
    }
  ],
  "hourly_plan": [ ... 24 records ... ],
  "total_grid_kwh": 2357.5,
  "total_cost_bdt": 25560.0,
  "peak_grid_kwh": 170.0,
  "plan_summary": "Dispatched battery storage to minimize grid costs while having compensated for solar output reductions. Starting battery level of 100.0 kWh was fully restored by hour 23."
}
```

---

## Testing & Verification

The test suite covers unit models, solver cross-verification, replay invariants, corruption detection, semantic paraphrases, public sample regressions, and randomized profiles:

```bash
# Run complete test suite (61 tests)
pytest

# Run public sample regression (all 10 samples)
python scripts/run_public_cases.py

# Run latency benchmark (p50, p95, max)
python scripts/benchmark.py

# Run smoke test
python scripts/smoke_test.py
```

### Verification Matrix
- **Unit Schemas & Cross-Field Validations**: 100% pass (rejects NaN, Inf, missing hours, invalid battery bounds).
- **Deterministic Guardrails**: 100% pass (verifies note mapping, hours 0-23, factors, reserves, grid caps).
- **LP Optimality**: HiGHS and CBC cross-verified.
- **Independent Replay Validator**: Audits 21 rules and independently audits the compiler against raw directives.
- **LRU Interpretation Cache**: Safe bounded in-memory caching keyed by normalized notes, capacity, and model.
- **Latency**: P95 measured at **~9.1 ms**, far surpassing the official $\le 5.0$ second threshold.

---

## Local Judge CLI Evaluation

GridWise includes a standalone local evaluation judge that mimics the competition's hidden automated evaluation suite:

```bash
# Evaluate all 10 public scenarios with deterministic mock semantic parser (in-process)
python scripts/local_judge.py --input samples/public_cases.json --mock

# Evaluate live with Gemini/OpenAI provider
python scripts/local_judge.py --input samples/public_cases.json

# Evaluate against a running HTTP server
python scripts/local_judge.py --url http://127.0.0.1:8000 --input samples/public_cases.json
```

---

## Docker Production Build & Multi-Arch Deployment

### Standard Build
```bash
docker build -t gridwise-llm-optimizer:latest .
```

### Multi-Architecture Build (x86_64 / linux/amd64 target)
```bash
docker buildx build --platform linux/amd64 -t gridwise-llm-optimizer:latest .
```

### Run Container
```bash
docker run --rm -p 8000:8000 \
  -e LLM_PROVIDER=mock \
  gridwise-llm-optimizer:latest
```

### Docker Fallback Health Check
The Docker container includes a built-in health check using Python's standard library:
```dockerfile
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').getcode() == 200 else 1)"
```

---

## Directory Layout

```text
gridwise-llm-optimizer/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application & endpoint routing
│   ├── config.py                   # Pydantic Settings & environment config
│   ├── errors.py                   # Domain exception hierarchy
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── request.py              # Input validation models (HourInput, BatteryInput)
│   │   ├── response.py             # Response models (HourlyPlanEntry, OptimizationResponse)
│   │   └── directives.py           # 6 typed directive schemas
│   ├── core/
│   │   ├── __init__.py
│   │   ├── guardrails.py           # Deterministic LLM output validator
│   │   ├── constraint_compiler.py  # Maps directives to 24h mathematical bounds
│   │   ├── optimizer.py            # Exact 24-hour continuous LP (HiGHS/PuLP)
│   │   ├── reconstruction.py       # Resolves continuous B[h] to discrete actions
│   │   ├── replay_validator.py     # Independent 21-rule schedule auditor
│   │   ├── totals.py               # Deterministic totals recomputation
│   │   └── summary.py              # Deterministic plan summary generator
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                 # Abstract DirectiveInterpreter
│   │   ├── prompts.py              # System prompt and instruction templates
│   │   ├── interpreter.py          # Provider factory with bounded retries
│   │   └── providers/
│   │       ├── mock_provider.py    # Offline semantic parser
│   │       ├── openai_provider.py  # Async OpenAI structured client
│   │       └── gemini_provider.py  # Async Google Gemini REST client
│   └── services/
│       ├── __init__.py
│       └── optimization_service.py # Orchestrator coordinating all 7 stages
├── docs/
│   └── SPEC.md                     # Frozen engineering specification
├── samples/
│   └── public_cases.json           # 10 public scenarios with ground truth
├── scripts/
│   ├── benchmark.py                # Latency & throughput benchmark
│   ├── local_judge.py              # Standalone evaluation & verification judge
│   ├── run_public_cases.py         # 10-case verification runner
│   └── smoke_test.py               # End-to-end smoke test
├── tests/
│   ├── conftest.py
│   ├── unit/                       # Schema, guardrail, compiler, optimizer tests
│   ├── integration/                # API route and error handling tests
│   ├── public_cases/               # Public regression suite
│   ├── randomized/                 # 25+ randomized synthetic scenarios
│   └── reliability/                # Corruption & paraphrase robustness tests
├── Dockerfile                      # Production container definition
├── .dockerignore
├── .env.example
├── .gitignore
├── Makefile
├── pyproject.toml
└── requirements.txt
```