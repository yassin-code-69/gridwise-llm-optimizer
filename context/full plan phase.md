নিচে আমি শুধু **FULL PLAN PHASE** দিচ্ছি—আগের context repeat করছি না। এটাকে তুমি তোমার coding agent-এর implementation roadmap হিসেবে ব্যবহার করতে পারো।

এই plan official specification-এর architecture—**LLM interpretation → deterministic validation → optimizer → final validation**—এবং judge যেসব জিনিস independently verify করবে, সেগুলো মাথায় রেখে বানানো।  

একটা কথা শুরুতেই clear: software-এ literally “এক বিন্দু ভুল হবে না” guarantee করা যায় না। তাই এই plan-এর design principle হচ্ছে **ভুল হওয়ার জায়গাগুলোকে layers, invariants, replay validation, public regression এবং randomized testing দিয়ে response বের হওয়ার আগেই detect করা।**

---

# GridWise — Full Implementation Plan

## 0. Final Technical Decisions

Implementation শুরু করার আগে এগুলো freeze থাকবে।

```text
Language              Python 3.11
API                    FastAPI
Schema Validation      Pydantic v2
Configuration          pydantic-settings
HTTP Client            httpx
LLM                    Provider abstraction
Optimization           Continuous Linear Programming
Modeling               PuLP
Primary Solver         HiGHS
Fallback Solver        CBC
Testing                pytest + pytest-asyncio
Containerization       Docker
Production Server      Uvicorn
```

Primary optimization:

```text
Exact LP
NOT heuristic
NOT greedy
NOT LLM-generated scheduling
```

Official objective হচ্ছে 24-hour total grid electricity cost minimize করা এবং সব constraints hard constraints হিসেবে satisfy করা। 

---

# PHASE 0 — Specification Freeze

## Objective

এক লাইন code লেখার আগে official behavior machine-readable engineering rules-এ freeze করা।

## Agent tasks

একটা internal document বানাবে:

```text
docs/SPEC.md
```

এখানে থাকবে:

```text
API endpoints
request schema
response schema
directive enums
directive object shapes
time semantics
solar percentage semantics
battery equations
energy balance
end neutrality
numeric tolerance
error semantics
performance limits
Docker requirements
```

### Exact endpoints

```text
GET /health
POST /optimize-energy
```

এগুলো change করা যাবে না। 

### Exact supported directives

```text
solar_reduction
minimum_battery_reserve
no_charge_window
no_discharge_window
max_grid_window
no_op
```



### Time rule freeze

```text
start inclusive
end exclusive
```

Example:

```text
1 PM -> 3 PM
=
[13, 14]
```



### Solar percentage freeze

```text
80% reduction
=
20% remains
=
factor 0.2
```



## Definition of Done

Agent যেন কোনো later phase-এ specification guess না করে।

যে behavior official docs-এ নেই, সেখানে comment থাকবে:

```text
ENGINEERING DECISION
```

Official requirement হিসেবে pretend করবে না।

---

# PHASE 1 — Repository Foundation

Repository:

```text
gridwise-llm-optimizer
```

Recommended structure:

```text
gridwise-llm-optimizer/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── errors.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── request.py
│   │   ├── response.py
│   │   └── directives.py
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── interpreter.py
│   │   ├── prompts.py
│   │   └── providers/
│   │       ├── __init__.py
│   │       └── provider.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── guardrails.py
│   │   ├── constraint_compiler.py
│   │   ├── optimizer.py
│   │   ├── reconstruction.py
│   │   ├── replay_validator.py
│   │   └── totals.py
│   │
│   └── services/
│       ├── __init__.py
│       └── optimization_service.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── public_cases/
│   ├── randomized/
│   └── reliability/
│
├── samples/
│   └── public_cases.json
│
├── scripts/
│   ├── run_public_cases.py
│   ├── benchmark.py
│   └── smoke_test.py
│
├── docs/
│   └── SPEC.md
│
├── Dockerfile
├── .dockerignore
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── README.md
└── Makefile
```

## Important rule

এই ধরনের structure করা যাবে না:

```text
main.py
  - API
  - LLM
  - optimizer
  - validation
  - all logic
```

আমাদের দরকার isolated modules যাতে hidden-test failure হলে exact layer identify করা যায়।

---

# PHASE 2 — Dependency Lock

Dependencies roughly:

```txt
fastapi
uvicorn[standard]
pydantic
pydantic-settings
httpx

pulp
highspy

pytest
pytest-asyncio
```

Chosen LLM provider-এর SDK add হবে।

## Version policy

Contest submission-এর আগে versions pin করতে হবে।

Example:

```text
fastapi==...
pydantic==...
pulp==...
highspy==...
```

Reason:

```text
local behavior
=
Docker behavior
=
judge fallback behavior
```

হতে হবে।

---

# PHASE 3 — Configuration Layer

Create:

```text
app/config.py
```

Environment variables:

```text
LLM_PROVIDER
LLM_MODEL
LLM_API_KEY
LLM_TIMEOUT_SECONDS

PORT
LOG_LEVEL

LLM_MAX_RETRIES
```

`.env.example`:

```env
LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=4
PORT=8000
LOG_LEVEL=INFO
```

Real `.env`:

```text
.gitignore
```

এ থাকতে হবে।

API key/token repo-তে রাখা যাবে না। Official repository/security rules এটাকে explicitly require করে। 

---

# PHASE 4 — Request Schema

Create:

```text
app/schemas/request.py
```

Models:

```text
HourInput
BatteryInput
OptimizationRequest
```

### HourInput

```text
hour
demand_kwh
solar_kwh
tariff_bdt_per_kwh
```

### BatteryInput

```text
capacity_kwh
initial_energy_kwh
minimum_energy_kwh
max_charge_kwh_per_hour
max_discharge_kwh_per_hour
```

### OptimizationRequest

```text
scenario_id
operator_notes
hours
battery
```

Official input structure এবং exactly 24 hours requirement এখানে defined। 

---

# PHASE 5 — Cross-Field Input Validation

Pydantic field validation যথেষ্ট না।

Cross-field validator লাগবে।

Check:

```text
len(hours) == 24

set(hour values) ==
{0,1,...,23}

1 <= len(operator_notes) <= 3

all notes non-empty

initial <= capacity

minimum <= capacity

initial >= minimum

charge limit >= 0

discharge limit >= 0
```

সব numeric value:

```text
finite
```

Reject:

```text
NaN
Infinity
-Infinity
```

## Definition of Done

Invalid structural request optimizer-এর কাছেও যেতে পারবে না।

---

# PHASE 6 — Directive Schemas

Create:

```text
app/schemas/directives.py
```

Prefer strongly typed models.

For example:

```text
SolarReductionAdjustment
MinimumBatteryReserveAdjustment
NoChargeAdjustment
NoDischargeAdjustment
MaxGridAdjustment
```

Then:

```text
DirectiveInterpretation
```

Allowed enum exact হবে।

Possible approach:

```python
Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]
```

LLM output schema যত strict হবে hidden hallucination তত কম dangerous হবে।

---

# PHASE 7 — Response Schema

Create:

```text
app/schemas/response.py
```

Models:

```text
HourlyPlanEntry
OptimizationResponse
```

Hourly fields:

```text
hour
grid_kwh
solar_used_kwh
battery_action
battery_kwh
battery_energy_after_kwh
```

Top-level:

```text
scenario_id
directive_interpretation
hourly_plan
total_grid_kwh
total_cost_bdt
peak_grid_kwh
plan_summary
```

Official response contract-এর exact fields এগুলো। 

---

# PHASE 8 — FastAPI Skeleton

Create:

```text
app/main.py
```

Implement:

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

Implement:

```http
POST /optimize-energy
```

Initially service call placeholder হবে:

```python
result = await optimization_service.optimize(request)
```

Business logic endpoint function-এর ভিতরে লিখবে না।

---

# PHASE 9 — Error Handling

Create:

```text
app/errors.py
```

Internal error types:

```text
LLMProviderError
LLMOutputValidationError
OptimizationError
ReplayValidationError
ConfigurationError
```

Global handlers:

```text
request validation
controlled internal errors
unknown internal failure
```

Production response-এ:

```text
NO stack trace
NO API key
NO provider credentials
```

Official API contract controlled `500` চায় এবং secrets/raw stack trace expose না করতে বলে। 

---

# PHASE 10 — LLM Provider Abstraction

Create:

```text
app/llm/base.py
```

Interface:

```python
class DirectiveInterpreter(ABC):

    async def interpret(
        self,
        notes,
        battery_context,
    ):
        ...
```

Then real provider adapter।

Example:

```text
app/llm/providers/openai_provider.py
```

or chosen provider।

Core service কখনও directly vendor SDK import করবে না।

---

# PHASE 11 — LLM Prompt Engineering

Create:

```text
app/llm/prompts.py
```

Prompt should narrowly explain:

```text
You interpret energy operator notes.

Only allowed directives:
...

Return exactly one entry per note.

Time:
start inclusive
end exclusive.

80% reduction means factor 0.2.

no_op:
applies=false
structured_adjustment=null

Never invent unsupported rules.
```

Input context should include:

```text
operator notes
battery capacity
battery minimum if useful
```

LLM-কে demand profile বা full mathematical scheduling বোঝানো unnecessary।

Model-এর job narrow রাখলে reliability বাড়বে।

---

# PHASE 12 — Structured LLM Output

Whenever provider supports it:

```text
JSON schema / structured output
```

use করতে হবে।

Do not ask:

```text
"please return JSON"
```

and blindly parse free-form text if provider offers schema-enforced output।

Target model output:

```json
[
  {
    "note_index": 0,
    "applies": true,
    "directive_type": "solar_reduction",
    "structured_adjustment": {
      "hours": [11, 12, 13],
      "factor": 0.2
    },
    "explanation": "..."
  }
]
```

---

# PHASE 13 — Deterministic Guardrail Layer

Create:

```text
app/core/guardrails.py
```

This is one of the highest-priority files.

Official problem says LLM output must be treated as untrusted structured data until deterministic validation succeeds. 

Check all of these:

```text
interpretation count
note index coverage
duplicate indices
missing indices
directive enum
applies
adjustment schema
hours
factor
reserve
grid cap
```

---

## Guardrail — note mapping

For `N` notes:

```text
expected indices:
0..N-1
```

Must satisfy:

```text
set(returned indices) ==
set(expected indices)
```

---

## Guardrail — hours

```text
integer
0 <= hour <= 23
unique
ascending
```

---

## Guardrail — solar

```text
0 <= factor <= 1
```

---

## Guardrail — reserve

```text
0 <= reserve <= capacity
```

---

## Guardrail — grid cap

```text
max_grid >= 0
```

---

## Guardrail — `no_op`

Exactly:

```text
applies = false
structured_adjustment = null
```

---

## Guardrail — normal directives

```text
applies = true
```

---

# PHASE 14 — LLM Retry Policy

Do not make infinite retries.

Recommended:

```text
attempt 1
  ↓
validate
  ↓
valid → continue
invalid/transient error
  ↓
one retry
  ↓
validate
```

If still invalid:

```text
controlled failure
```

Retryable:

```text
timeout
429
provider 5xx
malformed structured response
```

Not endlessly retryable:

```text
configuration missing
invalid API key
persistent schema violation
```

---

# PHASE 15 — Directive Compiler

Create:

```text
app/core/constraint_compiler.py
```

Input:

```text
validated request
validated directive interpretations
```

Output:

```text
EffectiveConstraints
```

Recommended structure:

```python
effective_solar[24]
minimum_energy[24]
charge_allowed[24]
discharge_allowed[24]
max_grid[24]
```

Initialization:

```text
effective_solar[h] = original solar[h]

minimum_energy[h] = base minimum

charge_allowed[h] = True

discharge_allowed[h] = True

max_grid[h] = infinity
```

---

# PHASE 16 — Compile Solar Reduction

For every listed hour:

```text
effective_solar[h]
=
solar[h] * factor
```

If overlapping separate reductions happen and official spec still provides no special composition rule:

```text
apply strictest independent upper bound
```

Do not multiply factors automatically unless future official clarification says so।

Document this behavior as:

```text
ENGINEERING DECISION
```

---

# PHASE 17 — Compile Minimum Reserve

For each affected hour:

```text
minimum_energy[h]
=
max(
    current minimum_energy[h],
    directive minimum
)
```

This matches official reserve behavior. 

---

# PHASE 18 — Compile No-Charge

For each affected hour:

```text
charge_allowed[h] = False
```

---

# PHASE 19 — Compile No-Discharge

```text
discharge_allowed[h] = False
```

---

# PHASE 20 — Compile Grid Cap

```text
max_grid[h]
=
min(
    existing cap,
    directive cap
)
```

---

# PHASE 21 — Optimizer Interface

Create:

```text
app/core/optimizer.py
```

Public internal API:

```python
solve_energy_schedule(
    request,
    effective_constraints,
) -> RawOptimizationResult
```

Optimizer receives no raw natural language।

---

# PHASE 22 — LP Variables

For each:

```text
h = 0..23
```

variables:

```text
grid[h]
solar_used[h]
battery_flow[h]
battery_energy[h]
```

Where:

```text
battery_flow > 0
=> charge

battery_flow < 0
=> discharge

battery_flow = 0
=> idle
```

---

# PHASE 23 — LP Base Bounds

Grid:

```text
grid[h] >= 0
```

Solar:

```text
solar_used[h] >= 0
```

Battery:

```text
-max_discharge
<= battery_flow[h]
<= max_charge
```

Energy:

```text
active_minimum[h]
<= battery_energy[h]
<= capacity
```

---

# PHASE 24 — Battery State Equation

For hour 0:

```text
E[0]
=
initial_energy
+
B[0]
```

For:

```text
h = 1..23
```

```text
E[h]
=
E[h-1]
+
B[h]
```

Official battery transition rules correspond exactly to charge adding energy and discharge removing energy. 

---

# PHASE 25 — Energy Balance

For every hour:

```text
grid[h]
+
solar_used[h]
=
demand[h]
+
battery_flow[h]
```

This signed formulation is equivalent to official:

```text
grid
+ solar
+ discharge
=
demand
+ charge
```



---

# PHASE 26 — Solar Constraint

```text
solar_used[h]
<=
effective_solar[h]
```

Also:

```text
solar_used[h] >= 0
```

No export।

Officially unused solar can be curtailed and grid export is outside challenge scope. 

---

# PHASE 27 — No-Charge Constraint

If:

```text
charge_allowed[h] == False
```

then:

```text
battery_flow[h] <= 0
```

---

# PHASE 28 — No-Discharge Constraint

If:

```text
discharge_allowed[h] == False
```

then:

```text
battery_flow[h] >= 0
```

---

# PHASE 29 — Grid Cap Constraint

If finite cap:

```text
grid[h]
<=
max_grid[h]
```

---

# PHASE 30 — End-of-Day Neutrality

Mandatory:

```text
battery_energy[23]
=
initial_energy
```

এই constraint miss করা যাবে না।

Official spec এটাকে hard requirement করেছে। 

---

# PHASE 31 — Objective Function

Single official objective:

```text
minimize:

Σ grid[h] * tariff[h]
```

Do not add arbitrary:

```text
battery degradation penalty
peak penalty
solar reward
```

unless it is only a mathematically safe secondary tie-break that cannot worsen primary cost।

Safer contest implementation:

```text
official cost only
```

---

# PHASE 32 — Solver Configuration

Primary:

```text
HiGHS
```

through PuLP।

Fallback:

```text
CBC
```

Why two?

Not runtime dual-solve necessarily।

For development/testing:

```text
same model
solve with HiGHS
solve with CBC
compare optimal objective
```

This is an excellent way to catch:

```text
solver setup issue
numeric weirdness
```

Production can use one tested solver।

---

# PHASE 33 — Solver Status Gate

Before reading variables:

```text
status MUST BE optimal
```

If:

```text
infeasible
unbounded
undefined
not solved
```

stop।

Do not create approximate/fake response।

Because organizer-valid scoring scenarios are intended to be feasible. 

---

# PHASE 34 — Output Reconstruction

Create:

```text
app/core/reconstruction.py
```

Translate signed flow:

```text
B > epsilon
=> charge

B < -epsilon
=> discharge

abs(B) <= epsilon
=> idle
```

Recommended:

```text
epsilon = 1e-8
```

Then:

```text
battery_kwh = abs(B)
```

for charge/discharge।

Idle:

```text
battery_kwh = 0
```

---

# PHASE 35 — Precision Policy

Do not round internal LP values early।

Keep full precision through:

```text
solver
reconstruction
```

Before final API serialization, numeric normalization may happen।

Recommended response precision:

```text
6 decimal places
```

or similar।

But then **replay the rounded/normalized values that will actually be returned**।

Official normal equivalence tolerance is 0.01 kWh / 0.01 BDT. 

---

# PHASE 36 — Independent Replay Validator

Create:

```text
app/core/replay_validator.py
```

This is the second highest-priority correctness component after guardrails।

It must NOT just inspect PuLP constraints।

It independently receives:

```text
original scenario
validated directives
final reconstructed plan
```

and recalculates everything।

---

# PHASE 37 — Replay Hour Structure

Verify:

```text
len(plan) == 24
```

and:

```text
hours == 0..23 exactly
```

---

# PHASE 38 — Replay Battery Transition

Maintain:

```text
energy_before
```

Start:

```text
initial battery
```

For each hour:

### charge

```text
expected_after =
before + battery_kwh
```

### discharge

```text
expected_after =
before - battery_kwh
```

### idle

```text
battery_kwh == 0

expected_after =
before
```

Then compare:

```text
returned battery_energy_after
```

to:

```text
expected_after
```

---

# PHASE 39 — Replay Battery Bounds

Verify:

```text
active minimum
<= energy_after
<= capacity
```

Every hour।

---

# PHASE 40 — Replay Rate Limits

Charge:

```text
battery_kwh
<= max_charge
```

Discharge:

```text
battery_kwh
<= max_discharge
```

---

# PHASE 41 — Replay Solar

Recompute effective solar from original input + directives।

Then:

```text
0
<= solar_used
<= effective_solar
```

---

# PHASE 42 — Replay No-Charge

Affected hour:

```text
action != charge
```

or equivalent magnitude check।

---

# PHASE 43 — Replay No-Discharge

Affected hour:

```text
action != discharge
```

---

# PHASE 44 — Replay Reserve

Affected hour:

```text
battery_energy_after
>= active reserve
```

---

# PHASE 45 — Replay Grid Cap

```text
grid_kwh
<= active grid cap
```

---

# PHASE 46 — Replay Energy Balance

For each hour calculate:

```text
charge =
battery_kwh if action == charge else 0

discharge =
battery_kwh if action == discharge else 0
```

Then:

```text
grid
+ solar
+ discharge
=
demand
+ charge
```

No exception।

---

# PHASE 47 — Replay End Neutrality

After hour 23:

```text
final energy
=
initial energy
```

within strict internal tolerance।

---

# PHASE 48 — Replay Failure Policy

If **one** replay rule fails:

```text
NO successful response
```

Raise:

```text
ReplayValidationError
```

Internally log:

```text
scenario
hour
rule
expected
actual
difference
```

Externally return safe error only।

---

# PHASE 49 — Totals Recalculation

Create:

```text
app/core/totals.py
```

Only after replay passes।

```text
total_grid =
sum(hour.grid)
```

```text
total_cost =
sum(
    grid[h] * tariff[h]
)
```

```text
peak_grid =
max(grid[h])
```

Never use LLM for totals।

Never trust manually accumulated totals।

Judge recalculates these from `hourly_plan`. 

---

# PHASE 50 — `plan_summary`

Generate deterministically।

No second LLM call needed।

Example logic:

```text
active solar reduction?
active reserve?
active grid cap?
battery shifted toward high tariffs?
final battery restored?
```

Example output:

> Applies the evening battery reserve and grid cap, shifts battery energy toward high-tariff hours, and restores the starting battery level by the end of the day.

Keep concise।

---

# PHASE 51 — Orchestration Service

Create:

```text
app/services/optimization_service.py
```

Exact flow:

```text
request
  ↓
LLM interpreter
  ↓
guardrails
  ↓
constraint compiler
  ↓
LP optimizer
  ↓
solver status check
  ↓
reconstruction
  ↓
replay validator
  ↓
totals
  ↓
plan summary
  ↓
response
```

This service should be the only place coordinating all layers।

---

# PHASE 52 — Unit Tests: Schemas

Create tests for:

```text
24 valid hours
23 invalid
25 invalid
duplicate invalid
missing hour invalid
negative values
invalid battery
empty notes
4 notes
```

---

# PHASE 53 — Unit Tests: Guardrails

Mock LLM outputs:

```text
valid solar
valid reserve
valid no-charge
valid no-discharge
valid grid cap
valid no_op
```

Then invalid:

```text
factor 1.2
factor -0.1
reserve > capacity
negative grid cap
hour 24
duplicate hour
unsorted hour
duplicate note_index
missing note_index
unsupported directive
wrong applies
wrong null semantics
```

All invalid cases must be rejected before optimization।

---

# PHASE 54 — Unit Tests: Constraint Compiler

For each directive:

```text
input interpretation
->
expected 24-hour effective constraints
```

Test combinations।

Example:

```text
base reserve = 40
directive reserve = 100
hour 18

expected minimum[18] = 100
```

---

# PHASE 55 — Unit Tests: LP Optimizer

Bypass LLM।

Use manually created valid directive structures।

Test:

```text
no directives
solar reduction
reserve
no-charge
no-discharge
grid cap
combined constraints
```

Every result:

```text
optimal
```

---

# PHASE 56 — Public Samples Regression

Public JSON contains 10 examples and states equivalent optimal schedules are accepted. 

For each sample perform two independent suites।

## Suite A — Semantic test

Check:

```text
note count
applies
directive_type
hours
factor/reserve/grid cap
```

Do not exact-match explanation text।

## Suite B — Mathematical test

Use expected validated directives directly with optimizer।

Verify:

```text
replay passes
optimal cost matches reference
```

within official tolerance।

This isolates:

```text
LLM failure
vs
optimizer failure
```

---

# PHASE 57 — End-to-End Public Cases

Now actual:

```http
POST /optimize-energy
```

against all 10 cases।

For each:

```text
LLM
guardrail
optimizer
replay
totals
```

must pass।

Target:

```text
10/10
```

Anything less should block submission।

---

# PHASE 58 — Replay Corruption Tests

Take valid plan।

Intentionally modify one thing।

Examples:

```text
solar + 1
grid over cap
charge during no-charge
discharge during no-discharge
battery below reserve
battery above capacity
break energy balance
wrong energy_after
wrong final battery
wrong total cost
```

Validator must reject all।

This gives enormous confidence against hidden judge replay।

---

# PHASE 59 — Randomized Synthetic Tests

Generate many numeric scenarios।

Recommended:

```text
100–500
```

during development।

Randomize:

```text
demand
solar
tariffs
capacity
initial state
minimum state
rates
```

Generate feasible directive combinations।

For each:

```text
solve
reconstruct
replay
recalculate
```

Target:

```text
0 failures
```

This is one of the strongest hidden-case preparation steps।

---

# PHASE 60 — Semantic Paraphrase Test Set

Public phrase memorization avoid করতে নিজের paraphrase suite বানাও।

Example solar:

```text
PV output will be only a fifth...
80 percent of rooftop generation will be unavailable...
Only 20 percent of forecast production remains...
```

Reserve:

```text
retain half the battery...
do not let stored energy fall below 50 percent...
keep 100 kWh available...
```

No charge/discharge/grid cap-এর জন্যও variants।

Important:

এগুলো engineering test sentences—official hidden data না।

Target হলো semantic generalization।

---

# PHASE 61 — Reliability Testing

Mock provider:

```text
timeout
429
500
malformed JSON
wrong schema
```

Expected:

```text
bounded retry
controlled error
service remains alive
```

Then next valid request should still work।

---

# PHASE 62 — Latency Instrumentation

Record internally:

```text
llm_ms
guardrail_ms
compile_ms
solver_ms
replay_ms
total_ms
```

Do not expose sensitive internals publicly।

---

# PHASE 63 — Benchmark

Create:

```text
scripts/benchmark.py
```

Run:

```text
20–50 representative requests
```

Capture:

```text
p50
p95
max
success rate
```

Official full latency points require p95 ≤ 5 seconds, with 30 seconds as hard request timeout. 

Internal target:

```text
p95 < 3–4 seconds
```

if provider supports it।

এটা engineering target, official requirement না।

---

# PHASE 64 — Solver Cross-Verification

Development-time high-confidence test:

For selected cases:

```text
same LP
solve using HiGHS
solve using CBC
```

Compare:

```text
objective
```

within tiny tolerance।

Expected:

```text
same optimum
```

This is not necessary per request in production।

It's a verification tool।

---

# PHASE 65 — Dockerfile

Docker needs to be treated as production。

Recommended structure:

```dockerfile
FROM python:3.11-slim
```

Then:

```text
install dependencies
copy application
run as non-root if practical
healthcheck
uvicorn
```

Bind:

```text
0.0.0.0
```

Guide requires tested pullable Docker fallback with documented binding/port and no baked-in secrets. 

---

# PHASE 66 — `.dockerignore`

At least:

```text
.git
.env
.venv
__pycache__
.pytest_cache
tests/cache
logs
*.pyc
```

Never copy actual environment secrets।

---

# PHASE 67 — Docker Healthcheck

Use:

```text
GET localhost:8000/health
```

from inside container।

Avoid adding `curl` just for this if unnecessary।

Python standard library health check works।

---

# PHASE 68 — Docker Local Test

Run:

```bash
docker build -t gridwise-llm-optimizer .
```

Then:

```bash
docker run --rm \
  -p 8000:8000 \
  -e LLM_PROVIDER=... \
  -e LLM_MODEL=... \
  -e LLM_API_KEY=... \
  gridwise-llm-optimizer
```

Then test:

```text
/health
```

and all 10 public cases।

---

# PHASE 69 — Docker Architecture Test

If development machine is ARM:

ensure final image supports:

```text
linux/amd64
```

Preferred:

```text
linux/amd64
linux/arm64
```

Use:

```text
docker buildx
```

if needed।

---

# PHASE 70 — Registry Push

Push exact version:

```text
v1.0.0
```

not only:

```text
latest
```

Keep exact image:

```text
repository/image:v1.0.0
```

Prefer record digest too।

Then test:

```text
docker pull
```

on clean machine/environment।

---

# PHASE 71 — Hosted Deployment

Deploy the same application।

Prefer same container image if platform allows।

Public routes:

```text
https://domain/.../health
https://domain/.../optimize-energy
```

No login।

No manual approval।

No VPN।

Official service accessibility requirement এটাই। 

---

# PHASE 72 — Production Smoke Tests

Against public URL:

```text
GET /health
```

Then 3 cases:

```text
simple one directive
multi-directive
distractor/no_op
```

Then ideally all public cases।

---

# PHASE 73 — Production Repeated Requests

Run same scenario repeatedly:

```text
10–20 times
```

Verify:

```text
no 500
no random malformed output
no rate-limit cascade
no timeout
```

LLM explanation wording may vary, but structured semantics should remain stable।

---

# PHASE 74 — Logging Review

Before submission inspect logs।

Ensure there is no:

```text
LLM_API_KEY
Authorization header
.env content
```

Logs should include useful metadata only।

---

# PHASE 75 — README

README should include:

```text
Challenge overview
Architecture
Tech stack

LLM role
Guardrail design
LP formulation
Replay validator

Environment variables

Local setup
Local run

Health curl
Optimize curl

Testing
Public sample test

Docker build
Docker run
Docker pull

Deployment details
Known limitations

Security/secrets
```

Documentation/reproducibility is an explicit scoring area. 

---

# PHASE 76 — Architecture Diagram

README/video-এর জন্য diagram:

```text
Request
   ↓
Pydantic
   ↓
LLM
   ↓
Guardrails
   ↓
Constraint Compiler
   ↓
LP / HiGHS
   ↓
Reconstruction
   ↓
Replay Validator
   ↓
Totals
   ↓
Response
```

---

# PHASE 77 — 3-Minute Video

Video base score না দিলেও tie-breaker হিসেবে গুরুত্বপূর্ণ।

Very concise structure:

### 0:00–0:30

Problem।

### 0:30–1:20

Architecture।

### 1:20–2:10

LLM + guardrail + LP + replay।

### 2:10–2:40

Live request।

### 2:40–3:00

Docker / deployment / testing।

---

# PHASE 78 — Repository Security Audit

Run searches:

```text
API key patterns
.env
token
secret
password
Authorization
```

Review git history too।

Secret accidentally commit করলে শুধু current file delete করলেই হবে না।

Rotate secret and remove history where necessary।

---

# PHASE 79 — Final Hidden-Judge Simulation

Create internal local judge।

Input:

```text
scenario JSON
```

Run API।

Then independently:

```text
response schema validate

directive mapping check

effective solar rebuild

battery replay

energy balance

directive checks

end neutrality

totals recalculate

latency record
```

আমাদের local judge-এর mental model official hidden evaluation-এর মতো হওয়া উচিত। Official hidden evaluation interpretation, directive application, battery, solar, energy balance, neutrality এবং totals independently verifies। 

---

# PHASE 80 — Submission Blocking Gates

Submission blocked থাকবে যদি নিচের যেকোনোটা false হয়।

## API gate

```text
[ ] /health exact
[ ] /optimize-energy exact
[ ] public URL reachable
```

## Semantic gate

```text
[ ] 10/10 public interpretation cases
[ ] no hard-coded public wording
[ ] paraphrase suite passes
```

## Mathematical gate

```text
[ ] every public optimization case optimal
[ ] every case passes replay
[ ] final battery always neutral
```

## Numeric gate

```text
[ ] no NaN
[ ] no infinities
[ ] totals recalculate
```

## Reliability gate

```text
[ ] provider timeout safe
[ ] bad LLM output safe
[ ] server stays alive
```

## Performance gate

```text
[ ] no normal request near 30 sec
[ ] p95 measured
```

## Docker gate

```text
[ ] builds cleanly
[ ] starts cleanly
[ ] /health passes
[ ] optimize passes
[ ] image registry pull works
[ ] correct CPU architecture
[ ] no secret baked in
```

## Documentation gate

```text
[ ] README complete
[ ] commands tested
[ ] model/provider documented
[ ] Docker documented
```

---

# PHASE 81 — Severity Classification

During development, bugs classify করবে।

## P0 — Submission blocker

```text
wrong energy balance
wrong directive semantics
battery neutrality failure
Docker doesn't run
API unreachable
```

## P1 — Critical

```text
some public cases fail
occasional LLM malformed result
latency > hard target
wrong totals
```

## P2 — Important

```text
logging weak
README incomplete
non-critical code cleanup
```

## P3 — Cosmetic

```text
formatting
comments
minor naming
```

During contest:

```text
P0/P1 first
```

Never spend final 20 minutes refactoring cosmetic code while validation is failing।

---

# PHASE 82 — Git Workflow

Recommended:

```text
main
```

always working।

Small commits:

```text
feat(schema): add strict request models
feat(llm): add structured directive interpreter
feat(opt): add 24h LP model
feat(validation): add replay validator
test(samples): add public regression suite
build(docker): add production container
```

Before dangerous changes:

```text
commit first
```

4-hour hackathon-এ recoverability খুব important।

---

# PHASE 83 — Team Parallelization

যদি 3 জন team হয়:

## Engineer A — API + LLM

Own:

```text
schemas
FastAPI
provider
prompt
guardrails
```

## Engineer B — Optimization

Own:

```text
constraint compiler
LP model
solver
reconstruction
```

## Engineer C — Verification + Deployment

Own:

```text
replay validator
public test harness
random tests
Docker
deployment
benchmark
README
```

### Integration contract

A and B-এর মাঝখানে interface:

```text
validated directives
```

B and C-এর মাঝখানে:

```text
hourly plan
```

এই separation parallel কাজকে safe করবে।

---

# PHASE 84 — 2-Person Team

### Engineer A

```text
API
schemas
LLM
guardrails
deployment
```

### Engineer B

```text
constraint compiler
optimizer
replay
tests
Docker
```

README/video দুজন parallel।

---

# PHASE 85 — Solo Workflow

If solo:

Priority strictly:

```text
Schema
↓
LLM interpretation
↓
Guardrails
↓
LP
↓
Replay
↓
Public tests
↓
Docker
↓
Deploy
↓
Docs
```

Frontend:

```text
skip
```

Not needed for scoring।

---

# PHASE 86 — 4-Hour Contest Execution Budget

এটা engineering recommendation, official schedule না।

Round window officially 4 hours। 

A strong time budget:

| Time      | Work                            |
| --------- | ------------------------------- |
| 0:00–0:20 | Repo, schemas, health           |
| 0:20–0:50 | LLM structured interpreter      |
| 0:50–1:10 | Guardrails                      |
| 1:10–1:55 | Constraint compiler + LP        |
| 1:55–2:20 | Reconstruction + replay         |
| 2:20–2:40 | Public semantic/optimizer cases |
| 2:40–3:00 | Full E2E suite                  |
| 3:00–3:20 | Docker                          |
| 3:20–3:35 | Deployment                      |
| 3:35–3:48 | README/video finalization       |
| 3:48–4:00 | Freeze + smoke tests + submit   |

If multiple engineers, Docker/tests/docs start earlier in parallel।

---

# PHASE 87 — Feature Freeze Rule

Final:

```text
15–20 minutes
```

before submission:

```text
NO new features
```

Only:

```text
P0/P1 fixes
deployment fixes
submission verification
```

No prompt redesign unless current one is failing।

No optimizer refactor unless necessary।

---

# PHASE 88 — Final Verification Matrix

Before submit, create:

| Test              | Local | Docker | Public |
| ----------------- | ----: | -----: | -----: |
| `/health`         |  PASS |   PASS |   PASS |
| Sample 01         |  PASS |   PASS |   PASS |
| Sample 02         |  PASS |   PASS |   PASS |
| ...               |  PASS |   PASS |   PASS |
| Sample 10         |  PASS |   PASS |   PASS |
| malformed JSON    |  PASS |   PASS |      - |
| timeout handling  |  PASS |   PASS |      - |
| replay corruption |  PASS |   PASS |      - |

Do not rely on:

```text
"it worked once"
```

---

# PHASE 89 — Optimization Correctness Gate

Agent must explicitly prove these before considering optimizer complete:

```text
[ ] LP sees all 24 hours simultaneously.

[ ] objective only uses grid cost.

[ ] grid cannot be negative.

[ ] solar cannot exceed effective availability.

[ ] battery flow rate bounded.

[ ] battery state transition correct.

[ ] base minimum always enforced.

[ ] reserve override enforced.

[ ] no-charge enforced.

[ ] no-discharge enforced.

[ ] grid cap enforced.

[ ] final state equals initial state.

[ ] solver status checked.

[ ] output replayed independently.
```

---

# PHASE 90 — Most Important Agent Instruction

তোমার AI coding agent-কে শেষে এই instructionটা দাও:

> **Execute this project as a specification-driven production optimization system. Do not rush directly to endpoint completion. Every layer must have explicit invariants and tests. Never trust raw LLM output; validate it deterministically. Never trust a solver result merely because it returned values; require optimal status and independently replay the exact finalized hourly plan. Never replace the exact 24-hour LP with a heuristic. Never return HTTP 200 if any official GridWise rule, operator directive, battery invariant, energy-balance equation, end-of-day neutrality condition, or recalculated total fails. Docker must run the same production application and must be tested before submission.**

আর optimizer-এর জন্য:

> **The optimizer must solve all 24 hours globally using an exact continuous Linear Program. Preserve full precision internally, enforce every official base and directive constraint as a hard mathematical constraint, require an optimal solver status, reconstruct the official hourly schema carefully, then validate that reconstructed response independently before calculating final totals. Public reference schedules are validation examples, not schedules to imitate.**

---

# Final Engineering Target

Final system:

```text
POST /optimize-energy
        ↓
Strict Request Validation
        ↓
LLM Structured Interpretation
        ↓
Deterministic Guardrails
        ↓
Per-Hour Constraint Compiler
        ↓
Exact 24-Hour Linear Program
        ↓
HiGHS Optimal Solution
        ↓
Response Reconstruction
        ↓
Independent Replay Validator
        ↓
Totals Recalculation
        ↓
Safe Structured Response
```

এই pipeline-এর একটাও correctness gate bypass করা যাবে না।

Official final reminder-এর sequence-ও essentially এটাই: **operator notes বুঝো → interpretation validate করো → optimization-এ apply করো → valid 24-hour schedule তৈরি করো → তারপর cost minimize করো।** 
