# GridWise LLM Energy Optimizer — Full Project Context

> **Purpose**
>
> This document is the complete engineering context for building the BUP CSE Fest 2026 Hackathon preliminary solution for the **GridWise — LLM-Assisted Smart Campus Energy Optimization Challenge**.
>
> This file contains **context only**. It intentionally does **not** include an implementation phase plan, milestone sequence, sprint plan, or task-by-task roadmap.

---

## 1. Official Source of Truth

The implementation must follow the official challenge package.

### Canonical challenge specification

**`BUP_CSE_FEST_2026_Preliminary_Problem_Statement_GridWise_LLM.pdf`**

This is the canonical source for:

- challenge behavior
- API contract
- request and response schema
- operator-note interpretation
- supported directive types
- deterministic LLM guardrails
- battery behavior
- energy accounting
- mathematical optimization validity
- hidden-evaluation semantics

### Canonical participation, deployment, and scoring specification

**`BUP_CSE_FEST_2026_Participant_Guide_&_Evaluation_Rubric_GridWise_LLM.pdf`**

This is the canonical source for:

- deployment rules
- repository requirements
- Docker fallback requirements
- performance targets
- evaluation weights
- penalties
- tie-breakers
- documentation and reproducibility requirements

### Public validation reference

**`BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json`**

This contains 10 fully worked public examples.

Each case includes:

- one input scenario
- 1–3 operator notes
- the expected machine-checkable directive interpretation
- one valid optimal 24-hour reference schedule

The public cases are examples only.

They are **not** the hidden judge set.

Never hard-code:

- public case IDs
- public note wording
- public numeric values
- public expected schedules
- reference totals

If any engineering assumption conflicts with the official Problem Statement, the official Problem Statement wins.

---

# 2. System Mission

Build one production-quality public HTTP API service that receives:

- a 24-hour campus demand profile
- a 24-hour rooftop solar availability profile
- a 24-hour grid electricity tariff profile
- battery configuration
- 1 to 3 natural-language operator notes

and returns:

- one machine-checkable interpretation for every operator note
- a valid 24-hour energy schedule
- total grid electricity usage
- total grid electricity cost
- peak grid import
- a short human-readable strategy summary

The solution must:

1. understand operator notes using a language-capable generative model
2. map each note to one supported directive type or `no_op`
3. validate all model-produced structured output deterministically
4. compile validated directives into mathematical constraints
5. solve the complete 24-hour optimization problem
6. reconstruct the official response schema
7. independently replay the returned schedule
8. recompute all totals from the final hourly plan
9. return HTTP 200 only when the finalized plan is valid

The central system rule is:

```text
Understand
  -> Validate
  -> Compile Constraints
  -> Optimize
  -> Reconstruct
  -> Replay
  -> Recalculate
  -> Return
```

Correctness always comes before cost optimization.

A cheap but invalid schedule is a failed solution.

---

# 3. Core Challenge Mental Model

The smart campus can satisfy electrical demand using:

1. **Grid electricity**
2. **Rooftop solar**
3. **Battery storage**

The next 24 hours of the following are already known:

- electricity demand
- solar availability
- grid tariff

The system must decide, for each hour:

- how much grid electricity to buy
- how much solar to use
- whether the battery should charge, discharge, or remain idle
- how much energy remains in the battery after the hour

The additional difficulty is that campus operators can provide short natural-language notes describing temporary conditions.

Examples:

- solar availability is reduced because panels are being cleaned
- battery charging is unavailable during maintenance
- battery discharging is unavailable during protection testing
- a minimum emergency battery reserve is required
- grid import is temporarily capped
- a note is unrelated to energy scheduling and must be ignored

The language model handles **semantic interpretation**.

The optimization solver handles **mathematical scheduling**.

The deterministic validator sits between them.

The LLM should never directly control the mathematical schedule.

---

# 4. Required High-Level Architecture

The preferred architecture is:

```text
                     +-----------------------+
                     | Incoming HTTP Request |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | Request Validation    |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | LLM Note Interpreter  |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | Deterministic         |
                     | Guardrail Validator   |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | Directive Compiler    |
                     | / Constraint Builder  |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | Exact LP Optimizer    |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | Output Reconstruction |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | Independent Replay    |
                     | Validator             |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | Totals Recalculation  |
                     +-----------+-----------+
                                 |
                                 v
                     +-----------------------+
                     | API Response          |
                     +-----------------------+
```

Important separation-of-concerns rules:

- LLM code must not contain optimization logic.
- Optimizer code must not interpret natural language.
- LLM output must never reach the optimizer without deterministic validation.
- Solver output must not be trusted without independent replay.
- Final totals must be recalculated from the exact values returned in `hourly_plan`.

---

# 5. Mandatory LLM Requirement

A language-capable generative model must directly participate in interpreting `operator_notes`.

The model's structured interpretation must be part of the actual path that produces the optimizer constraints.

The following must **not** be used as the sole interpreter:

- exact phrase matching
- regex-only parsing
- keyword-only parsing
- hard-coded public sample phrases
- lookup tables based on public examples
- using AI only for `plan_summary`
- using AI only for documentation
- using AI only for cosmetic response text

Deterministic preprocessing and postprocessing are allowed and recommended.

However, deterministic code may not replace the required model-based semantic interpretation step.

---

# 6. Public API Contract

The judging service must expose exactly:

```http
GET /health
POST /optimize-energy
```

Do not rename these endpoints.

The judging endpoint must not require:

- authentication
- a login page
- dashboard interaction
- manual approval
- VPN access
- a private network

The service must accept JSON and return JSON.

---

# 7. Health Endpoint

## Request

```http
GET /health
```

## Required successful response

```json
{
  "status": "ok"
}
```

The endpoint must return HTTP 200 when the service is ready.

The health endpoint should be:

- extremely fast
- deterministic
- independent from a live LLM call
- independent from a full optimization run

Official readiness expectation: `/health` should be ready within 60 seconds of service startup.

---

# 8. `POST /optimize-energy` Request Model

Required top-level structure:

```json
{
  "scenario_id": "GRID-101",
  "operator_notes": [
    "Example note"
  ],
  "hours": [],
  "battery": {}
}
```

---

## 8.1 `scenario_id`

Type:

```text
string
```

The response must echo the exact same value.

---

## 8.2 `operator_notes`

Type:

```text
array of 1 to 3 non-empty strings
```

Rules:

- minimum 1 note
- maximum 3 notes
- every note refers to the same 24-hour scenario
- every note must produce exactly one interpretation entry
- notes can be relevant or irrelevant
- irrelevant notes must become `no_op`

---

## 8.3 `hours`

The array must contain exactly 24 entries.

Each item:

```json
{
  "hour": 0,
  "demand_kwh": 100,
  "solar_kwh": 0,
  "tariff_bdt_per_kwh": 6
}
```

Required behavior:

- exactly 24 entries
- exactly one entry for every hour `0..23`
- no duplicate hour
- no missing hour
- all machine-critical numeric values must be finite
- demand cannot be negative
- solar availability cannot be negative

Internally, after validation, the implementation may safely normalize the records into hour-indexed arrays.

---

## 8.4 `battery`

Required object:

```json
{
  "capacity_kwh": 200,
  "initial_energy_kwh": 100,
  "minimum_energy_kwh": 40,
  "max_charge_kwh_per_hour": 50,
  "max_discharge_kwh_per_hour": 50
}
```

Meaning:

### `capacity_kwh`

Maximum energy the battery can store.

### `initial_energy_kwh`

Battery energy at the beginning of hour 0.

### `minimum_energy_kwh`

Base minimum reserve level the battery must never go below.

### `max_charge_kwh_per_hour`

Maximum energy that can be added to the battery in one hour.

### `max_discharge_kwh_per_hour`

Maximum energy that can be removed from the battery in one hour.

Recommended deterministic input invariants:

```text
capacity_kwh >= 0

0 <= initial_energy_kwh <= capacity_kwh

0 <= minimum_energy_kwh <= capacity_kwh

initial_energy_kwh >= minimum_energy_kwh

max_charge_kwh_per_hour >= 0

max_discharge_kwh_per_hour >= 0
```

All values must be finite.

---

# 9. Supported Directive Types

Only these six directive types exist:

```text
solar_reduction
minimum_battery_reserve
no_charge_window
no_discharge_window
max_grid_window
no_op
```

Never invent another directive type.

Hidden tests may paraphrase the language, but they do not require unpublished directive types.

---

# 10. `solar_reduction`

Meaning:

Usable solar is reduced during specific hours.

Required structured adjustment:

```json
{
  "hours": [12, 13],
  "factor": 0.25
}
```

Mathematical meaning:

```text
effective_solar[h] =
original_solar[h] * factor
```

for each listed hour.

## Critical factor rule

`factor` means the **fraction that remains usable**.

It is **not** the percentage lost.

Examples:

```text
80% reduction
-> 20% remains
-> factor = 0.20
```

```text
75% reduction
-> factor = 0.25
```

```text
50% reduction
-> factor = 0.50
```

```text
"usable solar should be 25% of forecast"
-> factor = 0.25
```

```text
"one-fifth of normal output remains"
-> factor = 0.20
```

This rule is machine-critical.

---

# 11. `minimum_battery_reserve`

Meaning:

Battery energy after an affected hour must remain at or above a required level.

Required structured adjustment:

```json
{
  "hours": [18, 19, 20],
  "minimum_energy_kwh": 100
}
```

Mathematical effect:

```text
battery_energy_after[h] >=
max(
    base minimum_energy_kwh,
    directive minimum_energy_kwh
)
```

for each affected hour.

The natural-language reserve may be absolute or relative.

Example:

```text
capacity = 200 kWh

"Keep at least 50% of battery capacity stored from 6 PM until 9 PM."
```

must become:

```text
minimum_energy_kwh = 100
hours = [18, 19, 20]
```

Therefore the LLM interpreter must receive enough battery context to convert percentage-based reserve language correctly.

---

# 12. `no_charge_window`

Meaning:

Battery charging is unavailable during listed hours.

Required structured adjustment:

```json
{
  "hours": [14, 15]
}
```

Mathematical effect:

```text
battery charge amount = 0
```

for every affected hour.

Under the recommended signed battery-flow LP model:

```text
B[h] <= 0
```

during affected hours.

---

# 13. `no_discharge_window`

Meaning:

Battery discharging is unavailable during listed hours.

Required structured adjustment:

```json
{
  "hours": [18, 19]
}
```

Mathematical effect:

```text
battery discharge amount = 0
```

for every affected hour.

Under the recommended signed battery-flow model:

```text
B[h] >= 0
```

during affected hours.

---

# 14. `max_grid_window`

Meaning:

Grid import must stay at or below a specified limit during listed hours.

Required structured adjustment:

```json
{
  "hours": [18, 19, 20],
  "max_grid_kwh": 155
}
```

Mathematical effect:

```text
grid_kwh[h] <= max_grid_kwh
```

for each listed hour.

---

# 15. `no_op`

Meaning:

The note does not affect the current 24-hour energy schedule.

Required semantics:

```json
{
  "note_index": 1,
  "applies": false,
  "directive_type": "no_op",
  "structured_adjustment": null,
  "explanation": "This note does not affect today's energy schedule."
}
```

Critical rules:

```text
no_op -> applies = false
no_op -> structured_adjustment = null
```

Every non-`no_op` directive must use:

```text
applies = true
```

Do not transform unrelated administrative notes into energy rules.

---

# 16. Whole-Hour Time Convention

All time windows are:

```text
start-inclusive
end-exclusive
```

Examples:

```text
1 PM to 3 PM
-> [13, 14]
```

```text
2 AM to 5 AM
-> [2, 3, 4]
```

```text
6 PM to 8 PM
-> [18, 19]
```

```text
6 PM to 9 PM
-> [18, 19, 20]
```

```text
6 PM to 10 PM
-> [18, 19, 20, 21]
```

```text
11 AM to 1 PM
-> [11, 12]
```

```text
noon to 2 PM
-> [12, 13]
```

Every `hours` array inside a structured directive must be:

- integer-only
- within `0..23`
- unique
- ascending

Never include the exclusive end hour.

---

# 17. Directive Interpretation Response Contract

Every input note must produce exactly one object:

```json
{
  "note_index": 0,
  "applies": true,
  "directive_type": "no_charge_window",
  "structured_adjustment": {
    "hours": [14, 15]
  },
  "explanation": "Battery charging is unavailable during the stated period."
}
```

Required fields:

```text
note_index
applies
directive_type
structured_adjustment
explanation
```

Rules:

- exactly one interpretation per note
- no missing notes
- no duplicate mappings
- no invented note index
- entries returned in `note_index` order
- selected directive must be supported
- adjustment shape must exactly match the selected directive
- explanation may be short natural language
- explanation wording does not need to match a reference sentence byte-for-byte

Machine-checkable fields are the priority.

---

# 18. LLM Responsibilities

The LLM should perform only semantic interpretation.

Responsibilities:

1. Decide whether each note affects today's energy schedule.
2. Return `no_op` for irrelevant notes.
3. Select exactly one supported directive for relevant notes.
4. Normalize time language into whole-hour arrays.
5. Extract required numeric values.
6. Normalize percentage language correctly.
7. Use battery capacity when a reserve percentage must be converted to kWh.
8. Return exactly one result for every note.
9. Preserve note mapping.
10. Never invent unsupported directives or base scenario data.

The LLM must **not**:

- create the 24-hour schedule
- optimize grid cost
- decide battery dispatch directly
- modify base demand
- modify base tariff
- modify battery parameters unless a supported directive explicitly requires a derived structured value

---

# 19. Recommended LLM Interface

Keep provider-specific logic behind a narrow abstraction.

Conceptual interface:

```python
class DirectiveInterpreter:
    async def interpret(
        self,
        operator_notes,
        battery_context,
    ) -> list[DirectiveInterpretation]:
        ...
```

Recommended configuration:

```text
LLM_PROVIDER
LLM_MODEL
LLM_API_KEY
LLM_TIMEOUT_SECONDS
```

Recommended model behavior:

```text
temperature = 0
structured JSON output
strict JSON schema
small response token budget
short deterministic prompt
explicit timeout
```

Prefer a single model call for all 1–3 notes when reliable structured output is supported.

This usually improves:

- latency
- cost
- note-index consistency
- request overhead

The output must still contain exactly one structured interpretation per note.

---

# 20. Prompt Context Requirements

The semantic prompt should explicitly teach the model:

- the six supported directive types
- exact adjustment shape for each directive
- `no_op` semantics
- whole-hour start-inclusive/end-exclusive convention
- hours must be 0–23
- hours must be unique and ascending
- `factor` means usable fraction remaining
- 80% reduction means `factor = 0.2`
- percentage battery reserve may require capacity conversion
- unsupported directive types are forbidden
- base demand/tariff/battery parameters cannot be invented
- every note must produce exactly one output entry
- note indices must map exactly to input notes

Do not overload the LLM prompt with mathematical optimizer implementation details that are irrelevant to semantic extraction.

---

# 21. LLM Output Is Untrusted Data

Every model response must be treated as untrusted structured input.

No interpretation may reach the optimizer until deterministic validation passes.

The guardrail must verify:

## Coverage

```text
number of interpretations ==
number of operator notes
```

## Note mapping

- every `note_index` exists
- no missing note
- no duplicate note
- no extra note
- note indices correspond to actual notes

## Directive type

Must be exactly one of:

```text
solar_reduction
minimum_battery_reserve
no_charge_window
no_discharge_window
max_grid_window
no_op
```

## `applies`

```text
no_op -> false
all other directives -> true
```

## Adjustment shape

```text
no_op -> null
all other directives -> exact required object
```

## Hours

- present where required
- integers only
- range `0..23`
- unique
- ascending

## Solar factor

For `solar_reduction`:

```text
finite
0 <= factor <= 1
```

## Reserve

For `minimum_battery_reserve`:

```text
finite
>= 0
<= battery capacity
```

## Grid cap

For `max_grid_window`:

```text
finite
>= 0
```

Do not silently clamp invalid semantic values.

Example:

```text
factor = 1.7
```

must not be transformed into `1.0` and accepted.

Reject or retry.

---

# 22. LLM Failure Policy

The service must fail safely.

Possible failures include:

- model-provider timeout
- rate limit
- provider 5xx
- malformed JSON
- invalid structured output
- unsupported directive
- duplicate note index
- missing interpretation
- invalid numeric value

Recommended behavior:

```text
model request
    |
    v
strict deterministic validation
    |
    +-- valid --> continue
    |
    +-- invalid --> one controlled retry / repair attempt
                       |
                       v
                  validate again
                       |
                       +-- valid --> continue
                       |
                       +-- invalid --> controlled internal error
```

Do not use unlimited retries.

Do not silently invent a directive after a provider failure.

Do not silently downgrade an invalid interpretation to `no_op`.

Do not use a deterministic keyword parser as the sole semantic fallback.

---

# 23. Mathematical Optimization Strategy

Use an **exact continuous Linear Program (LP)**.

Recommended modeling stack:

```text
PuLP
```

Recommended primary solver:

```text
HiGHS
```

CBC is a valid practical fallback if correctly installed and tested.

Do not use the following as the primary optimizer:

- greedy scheduling
- genetic algorithms
- simulated annealing
- reinforcement learning
- LLM-generated schedules
- approximate heuristic dispatch

The official objective and all official constraints are linear.

An exact LP is simpler, faster, easier to prove correct, and better aligned with judging.

---

# 24. Why Continuous LP Is Sufficient

Represent battery movement using one signed continuous variable.

For each hour:

```text
B[h] > 0  -> battery charging
B[h] < 0  -> battery discharging
B[h] = 0  -> battery idle
```

No binary action variable is necessary because the official problem has:

- no battery efficiency loss
- no fixed startup cost
- no minimum charging duration
- no minimum discharging duration
- no binary unit-commitment behavior
- no battery cycling fee

The response action can be derived from the sign of `B[h]`.

This gives a small, exact continuous LP.

---

# 25. LP Decision Variables

For every:

```text
h in {0, 1, ..., 23}
```

define:

```text
G[h] = grid electricity purchased in hour h

S[h] = solar electricity used in hour h

B[h] = signed battery flow in hour h

E[h] = battery energy immediately after hour h
```

Variable domains:

```text
G[h] >= 0

S[h] >= 0

B[h] continuous

E[h] continuous
```

Battery-flow bounds:

```text
-max_discharge_kwh_per_hour
<= B[h] <=
max_charge_kwh_per_hour
```

---

# 26. Official Optimization Objective

Minimize total grid electricity cost over all 24 hours:

```text
minimize

SUM(
    G[h] * tariff[h]
)

for h = 0..23
```

Do not replace this with a custom weighted objective.

Do not optimize:

- battery cycle count
- peak grid usage
- total grid kWh
- solar utilization

at the expense of the official cost objective.

`peak_grid_kwh` is a required reported value, not the general optimization objective.

---

# 27. Battery State Transition

Hour 0:

```text
E[0] =
initial_energy_kwh + B[0]
```

Hours `1..23`:

```text
E[h] =
E[h-1] + B[h]
```

Interpretation:

```text
B[h] = +20
```

means the battery gained 20 kWh.

```text
B[h] = -20
```

means the battery supplied 20 kWh.

---

# 28. Battery Energy Bounds

For every hour:

```text
minimum_energy_kwh
<= E[h] <=
capacity_kwh
```

When a minimum-reserve directive is active:

```text
E[h] >= max(
    base minimum_energy_kwh,
    all active directive reserve values
)
```

All active hard reserve constraints must be respected.

---

# 29. Charge and Discharge Rate Limits

For each hour:

```text
B[h] <= max_charge_kwh_per_hour
```

and:

```text
B[h] >= -max_discharge_kwh_per_hour
```

These limits apply even when tariffs strongly encourage more aggressive battery movement.

---

# 30. Energy Balance

Official energy accounting:

```text
grid
+ solar_used
+ battery_discharge
=
demand
+ battery_charge
```

Using signed battery flow, this becomes:

```text
G[h] + S[h]
=
demand[h] + B[h]
```

Check:

### Charging

If:

```text
B[h] = +20
```

then:

```text
grid + solar =
demand + 20
```

The extra 20 kWh charges the battery.

### Discharging

If:

```text
B[h] = -20
```

then:

```text
grid + solar =
demand - 20
```

The battery provides 20 kWh toward demand.

This signed form is equivalent to the official rule.

---

# 31. Solar Availability

Base effective solar:

```text
effective_solar[h] =
original_solar[h]
```

Constraint:

```text
0 <= S[h] <= effective_solar[h]
```

Grid export is not part of the challenge.

Grid variable must never become negative.

Unused solar may be curtailed.

---

# 32. Applying `solar_reduction`

For an affected hour:

```text
effective_solar[h] =
original_solar[h] * factor
```

Then:

```text
S[h] <= effective_solar[h]
```

### Overlapping solar-reduction engineering note

The public specification does not define a special composition formula for multiple separate solar-reduction directives affecting the same hour.

Do not invent multiplicative stacking semantics.

If such a scenario occurs, a conservative constraint-based treatment is:

```text
S[h] <= original_solar[h] * factor_1
S[h] <= original_solar[h] * factor_2
```

which enforces the strictest valid upper bound.

If this behavior is implemented, document it as an engineering interpretation rather than an explicit official rule.

---

# 33. Applying `no_charge_window`

For each affected hour:

```text
B[h] <= 0
```

The battery may still:

- remain idle
- discharge

unless another active constraint prevents it.

---

# 34. Applying `no_discharge_window`

For each affected hour:

```text
B[h] >= 0
```

The battery may still:

- remain idle
- charge

unless another active constraint prevents it.

---

# 35. Applying `minimum_battery_reserve`

For every affected hour:

```text
E[h] >= directive_minimum_energy_kwh
```

Combined with the base bound:

```text
E[h] >= max(
    base minimum,
    all active directive minimums
)
```

The official reserve applies to `battery_energy_after_kwh` for the listed hour.

---

# 36. Applying `max_grid_window`

For every affected hour:

```text
G[h] <= max_grid_kwh
```

If multiple grid caps apply to the same hour, every cap is a hard constraint.

Therefore the effective numeric upper bound is naturally the minimum active cap.

---

# 37. End-of-Day Battery Neutrality

Critical hard constraint:

```text
E[23] =
initial_energy_kwh
```

The battery may shift energy between hours.

It may not be consumed as free one-time electricity.

Ending below the initial battery energy is invalid.

Ending above the initial battery energy is also invalid.

---

# 38. No Battery Efficiency Term

The official challenge does not specify:

- charging efficiency
- discharging efficiency
- round-trip efficiency

Do not invent them.

Official state transitions are direct:

```text
charge:
E_after = E_before + battery_kwh
```

```text
discharge:
E_after = E_before - battery_kwh
```

---

# 39. No Grid Export

Do not permit:

```text
grid_kwh < 0
```

Do not create a solar-export revenue model.

Unused solar is curtailed.

---

# 40. Multiple Simultaneous Directives

A request may contain multiple relevant notes.

Every note remains a separate required interpretation entry.

The optimizer must enforce all applicable directives simultaneously.

Example:

```text
Note 0 -> minimum_battery_reserve
Note 1 -> max_grid_window
Note 2 -> no_op
```

The response contains all three interpretation entries.

The optimizer applies note 0 and note 1 together.

Internally, separate directives may be compiled into one effective per-hour constraint representation.

---

# 41. Recommended Constraint Compilation Representation

A clean internal numeric representation may resemble:

```python
EffectiveConstraints(
    effective_solar_by_hour,
    minimum_energy_by_hour,
    charge_allowed_by_hour,
    discharge_allowed_by_hour,
    max_grid_by_hour,
)
```

Base initialization:

```text
effective solar[h] = original solar[h]

minimum energy[h] = base minimum

charge allowed[h] = true

discharge allowed[h] = true

max grid[h] = infinity
```

Then compile validated directives into these values.

This layer should contain no natural-language processing.

---

# 42. Constraint Strengthening

When multiple hard constraints overlap:

## Reserve

Use the strongest lower bound:

```text
max(active reserves)
```

## Grid cap

Use the strongest upper bound:

```text
min(active grid caps)
```

## Charge

If any valid applicable directive forbids charging:

```text
charging is forbidden
```

## Discharge

If any valid applicable directive forbids discharging:

```text
discharging is forbidden
```

All official constraints remain hard constraints.

---

# 43. Solver Status Requirement

Never fabricate or return a plan unless the solver reaches a valid optimal solution.

Require:

```text
solver status == OPTIMAL
```

If the solver reports:

- infeasible
- unbounded
- undefined
- error
- not solved

do not construct a fake schedule.

Valid organizer scoring scenarios are expected to be feasible.

Therefore infeasibility usually indicates:

- wrong semantic extraction
- wrong constraint compilation
- an optimization modeling bug
- a solver/configuration error

Return a controlled failure rather than invalid output.

---

# 44. Numerical Precision Policy

Official normal numeric tolerance is:

```text
0.01 kWh
0.01 BDT
```

unless the official judge package later specifies a stricter value.

Internally use significantly tighter tolerances.

Recommended near-zero epsilon:

```text
1e-8
```

Do not aggressively round optimization variables.

Derive battery response action:

```text
if abs(B[h]) < epsilon:
    battery_action = "idle"
    battery_kwh = 0

elif B[h] > 0:
    battery_action = "charge"
    battery_kwh = B[h]

else:
    battery_action = "discharge"
    battery_kwh = abs(B[h])
```

Any response normalization must happen **before** final replay.

Validate the exact values that will be returned.

---

# 45. Hourly Response Model

Each of the 24 output records contains:

```json
{
  "hour": 0,
  "grid_kwh": 90,
  "solar_used_kwh": 0,
  "battery_action": "idle",
  "battery_kwh": 0,
  "battery_energy_after_kwh": 110
}
```

Allowed battery actions:

```text
charge
discharge
idle
```

Rules:

- exactly 24 records
- exactly one record per hour `0..23`
- no duplicates
- grid is non-negative
- solar used is non-negative
- battery magnitude is non-negative
- idle requires `battery_kwh = 0`
- charge/discharge magnitude respects hourly rates
- battery state must match the declared action and magnitude

---

# 46. Successful Top-Level Response

Required structure:

```json
{
  "scenario_id": "GRID-101",
  "directive_interpretation": [],
  "hourly_plan": [],
  "total_grid_kwh": 0,
  "total_cost_bdt": 0,
  "peak_grid_kwh": 0,
  "plan_summary": "..."
}
```

Required fields:

```text
scenario_id
directive_interpretation
hourly_plan
total_grid_kwh
total_cost_bdt
peak_grid_kwh
plan_summary
```

Do not omit required fields even if they can be recalculated.

---

# 47. Independent Replay Validator

The application must independently validate the finalized 24-hour schedule.

Do not rely only on LP model correctness.

The replay validator should receive:

- original request scenario
- validated structured directives
- final response-style hourly plan

It should know nothing about internal solver equations beyond the official rules.

For every hour, validate:

1. correct hour identity
2. finite values
3. non-negative grid
4. non-negative solar usage
5. valid battery action enum
6. non-negative battery magnitude
7. idle implies zero battery magnitude
8. battery transition consistency
9. maximum charge rate
10. maximum discharge rate
11. battery capacity
12. base minimum battery energy
13. directive reserve
14. effective solar availability
15. solar-reduction constraints
16. no-charge constraints
17. no-discharge constraints
18. grid-cap constraints
19. energy balance

After hour 23, validate:

20. final battery equals initial battery
21. exactly 24 unique hours were returned

If any check fails, the service must not return a successful optimization response.

---

# 48. Replay Battery State Logic

Initialize:

```text
energy_before =
initial_energy_kwh
```

For each hour:

### Charge

```text
expected_after =
energy_before + battery_kwh
```

### Discharge

```text
expected_after =
energy_before - battery_kwh
```

### Idle

```text
battery_kwh = 0

expected_after =
energy_before
```

Compare returned:

```text
battery_energy_after_kwh
```

with:

```text
expected_after
```

within a strict internal tolerance.

Then update:

```text
energy_before =
expected_after
```

---

# 49. Replay Energy Balance

Derive:

```text
battery_charge =
battery_kwh
if action == charge
else 0
```

```text
battery_discharge =
battery_kwh
if action == discharge
else 0
```

Check:

```text
grid_kwh
+ solar_used_kwh
+ battery_discharge
=
demand_kwh
+ battery_charge
```

for every hour.

A single violated hour invalidates the case.

---

# 50. Totals Must Be Recalculated

After the final plan passes replay:

```text
total_grid_kwh =
SUM(hour.grid_kwh)
```

```text
total_cost_bdt =
SUM(
    hour.grid_kwh
    *
    tariff_bdt_per_kwh[hour]
)
```

```text
peak_grid_kwh =
MAX(hour.grid_kwh)
```

The final `hourly_plan` is the source of truth.

Never trust:

- LLM totals
- stale optimizer-side totals
- manually edited totals
- cached totals from a pre-normalized plan

---

# 51. Optimization Quality Context

For valid optimization cases, quality is measured against organizer optimal cost.

The official ratio is based on:

```text
min(
    1,
    organizer_optimal_cost
    /
    recalculated_team_cost
)
```

Consequences:

- exact mathematical optimization matters
- invalid cases receive no optimization credit
- fake low totals provide no advantage
- a correctly modeled LP should reach the optimal or equivalent optimal cost

Equivalent optimal schedules are accepted.

The exact public action sequence does not have to match.

---

# 52. Public Sample Coverage

The 10 public samples test the following behaviors.

## SAMPLE-01

- solar-reduction note
- irrelevant distractor
- relevant + `no_op`

## SAMPLE-02

- battery charging unavailable
- `no_charge_window`

## SAMPLE-03

- reserve expressed as battery-capacity percentage
- relative percentage -> absolute kWh

## SAMPLE-04

- battery discharge prohibited
- `no_discharge_window`

## SAMPLE-05

- temporary grid-import cap
- `max_grid_window`

## SAMPLE-06

- multiple notes
- solar reduction
- no-charge window
- unrelated note
- exactly one interpretation per input note

## SAMPLE-07

- battery reserve
- grid cap
- simultaneous hard constraints

## SAMPLE-08

- separate charge and discharge outages
- different restrictions in the same scenario

## SAMPLE-09

- 80% solar reduction
- must become factor `0.2`
- distractor note

## SAMPLE-10

- battery reserve
- grid cap
- distractor
- combined evening operation

Use these as regression tests.

Never encode them as production special cases.

---

# 53. Hidden-Test Expectations

Expect hidden variation in:

- note wording
- paraphrases
- percentage wording
- clock expressions
- numeric descriptions
- distractors
- directive combinations
- demand
- solar
- tariff
- capacity
- initial energy
- reserve
- charge rate
- discharge rate

Each hidden scoring note maps to exactly one supported directive or `no_op`.

Hidden tests do not require new unpublished directive types.

Organizer-valid scoring scenarios are intended to be feasible and avoid mutually contradictory hard directives.

The system must generalize semantically.

---

# 54. Why Hard-Coded Language Rules Are Unsafe

Hidden notes can express the same meaning differently.

These can all mean the same thing:

```text
"PV production will drop to about 20%..."
```

```text
"Only one-fifth of rooftop solar will remain..."
```

```text
"Expect an 80% reduction in rooftop solar..."
```

A phrase lookup may fail.

The semantic model should normalize them into:

```text
directive_type = solar_reduction
factor = 0.2
```

Deterministic validation then verifies the result.

---

# 55. API Error Semantics

Official documented response behavior includes:

```text
200
successful health response
or successful optimization
```

```text
400
malformed JSON
or structurally invalid request
```

```text
422
optional for semantically invalid but well-formed input
```

```text
500
controlled internal failure
```

FastAPI normally returns 422 for Pydantic validation failures.

If strict alignment with the documented structural-error behavior is desired, provide a validation exception handler that returns a controlled 400 for the appropriate cases.

Do not expose:

- stack traces
- secrets
- provider credentials
- sensitive environment values

---

# 56. Security Requirements

Never commit:

- API keys
- access tokens
- passwords
- `.env`
- private credentials

Never return secrets in:

- API response bodies
- logs
- stack traces

Use environment variables.

Provide a safe `.env.example` containing only variable names/placeholders.

Challenge data is synthetic.

Do not integrate real campus, utility, billing, or personal data.

---

# 57. Recommended Runtime Configuration

At minimum:

```text
LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=
PORT=8000
LOG_LEVEL=INFO
```

Provider-specific options may exist inside the provider module.

Core application code should remain provider-independent.

---

# 58. Reliability Context

The service should remain stable under:

- repeated valid requests
- malformed input
- temporary provider failure
- provider timeout
- rate limiting
- invalid LLM structured output
- reasonable concurrent judging requests

Recommended engineering behavior:

- explicit network timeouts
- bounded retry policy
- no infinite retries
- connection reuse where possible
- controlled exceptions
- one request failure must not crash the entire service
- no invalid schedule returned merely to preserve uptime

Provider:

- credentials
- quota
- cost
- rate limits
- availability

are the team's responsibility.

---

# 59. Performance Requirements

Official limits:

```text
GET /health:
ready within 60 seconds after startup
```

```text
POST /optimize-energy:
hard timeout at 30 seconds
```

Latency scoring:

```text
p95 <= 5 seconds
-> full latency points
```

```text
>5 to 15 seconds
-> reduced latency points
```

```text
>15 to 30 seconds
-> further reduced latency points
```

```text
>30 seconds
-> timeout / failure
```

The optimization LP should normally solve very quickly.

The LLM request is expected to dominate latency.

Prioritize model/API reliability and latency over unnecessary optimizer micro-optimization.

---

# 60. Optional Interpretation Cache

A small bounded in-memory cache can be used if helpful.

A safe cache key should include all context that can influence semantic output.

Example components:

```text
normalized operator notes
battery capacity
relevant battery context
LLM model identifier
prompt/schema version
```

Do not key only on note text when the meaning depends on battery capacity.

Example:

```text
"Keep 50% of capacity in reserve."
```

produces different kWh values for different capacities.

Caching must never become a public-case lookup table.

---

# 61. Logging and Observability

Use structured logs.

Useful fields include:

```text
request_id
scenario_id
note_count
llm_provider
llm_model
llm_latency_ms
guardrail_latency_ms
solver_latency_ms
replay_latency_ms
total_latency_ms
solver_status
result_status
```

Never log:

- API keys
- Authorization headers
- secret environment variables

Avoid unnecessarily logging entire provider prompts/responses in production.

---

# 62. Recommended Internal Code Boundaries

A professional implementation can use a structure similar to:

```text
app/
  main.py
  config.py

  schemas/
    request.py
    response.py
    directives.py

  llm/
    base.py
    interpreter.py
    prompts.py
    provider.py

  core/
    guardrails.py
    directive_engine.py
    optimizer.py
    replay_validator.py
    totals.py

  services/
    optimization_service.py

  errors.py
```

Responsibilities:

## `main.py`

- FastAPI application
- endpoint registration
- exception handling

## `config.py`

- environment configuration

## `schemas/*`

- request models
- response models
- directive models

## `llm/*`

- provider abstraction
- semantic interpretation
- structured-output schema
- prompt definitions

## `guardrails.py`

- deterministic model-output validation

## `directive_engine.py`

- converts validated directives into numeric per-hour constraints

## `optimizer.py`

- exact mathematical LP only

## `replay_validator.py`

- independent schedule verification

## `totals.py`

- final totals from hourly plan

## `optimization_service.py`

- orchestration layer

Do not create one giant `main.py`.

---

# 63. Strict Schema Philosophy

Machine-critical schemas should reject unexpected shapes when practical.

For LLM-produced structured output, use strict validation such as:

```python
extra = "forbid"
```

where appropriate.

This catches:

- hallucinated fields
- field typos
- provider schema drift
- unexpected object shapes

Do not over-constrain valid official API input beyond the specification.

---

# 64. Determinism Philosophy

The LLM layer can have some unavoidable model variability.

Everything after model interpretation should be deterministic.

Given:

- the same valid scenario
- the same validated directive objects

the following should behave deterministically:

```text
constraint compilation
LP construction
optimization
output reconstruction
replay
totals
```

Use the provider's closest deterministic structured-output configuration.

Prefer:

```text
temperature = 0
```

where supported.

---

# 65. `plan_summary`

`plan_summary` is a short human-readable explanation.

It is not the source of truth.

It should not require a second LLM call.

It can be generated deterministically from:

- active directives
- major battery strategy
- expensive-hour shifting
- final battery restoration

Example:

```text
"Applied the evening grid cap and battery reserve, shifted battery energy toward high-tariff hours, and restored the initial battery level by the end of hour 23."
```

Keep it concise.

Do not let summary generation modify schedule logic.

---

# 66. Docker Is a Core Requirement

Docker is not optional polish.

The fallback image is part of evaluation and reproducibility.

The image must:

- be pullable from a registry
- use an exact tag or digest
- bind the service to `0.0.0.0`
- expose the documented service port
- start with the documented command
- reach `/health`
- contain no baked-in secrets
- remain available during evaluation

The Docker path should run the same core application as local and hosted deployment.

---

# 67. Recommended Docker Runtime

Recommended base image:

```text
python:3.11-slim
```

Recommended service command:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use pinned dependency versions for the submission build.

The application may support a configurable port, but the documented Docker command must be exact and tested.

---

# 68. Docker Secret Safety

Never:

```dockerfile
ENV LLM_API_KEY=<real-secret>
```

Never:

```dockerfile
COPY .env .
```

Use `.dockerignore`.

Exclude at least:

```text
.env
.git
__pycache__
.pytest_cache
local logs
temporary development artifacts
```

Provide secrets at runtime:

```text
-e LLM_API_KEY=...
```

or through deployment-platform environment configuration.

---

# 69. Docker Health Check

A Docker health check is strongly recommended.

It should verify:

```text
GET http://127.0.0.1:8000/health
```

and expect:

```json
{"status":"ok"}
```

Avoid installing unnecessary system tools only for the health check.

A small Python standard-library HTTP call is sufficient.

---

# 70. Docker Architecture Compatibility

If development happens on Apple Silicon/ARM, do not accidentally publish an ARM-only fallback image.

Prefer:

```text
linux/amd64
```

or multi-architecture:

```text
linux/amd64
linux/arm64
```

Use Docker Buildx when needed.

The final registry image must be tested from a clean environment.

---

# 71. Hosted Deployment Context

The challenge does not mandate a particular hosting provider.

Evaluation is based on:

- correctness
- accessibility
- reproducibility
- reliability

Avoid deployment configurations that create:

- large cold starts
- sleeping during judging
- hidden authentication
- blocked outbound provider calls
- very low request quotas
- unstable public URLs

Whenever practical, deploy the same Docker image that is submitted as fallback.

This reduces environment drift.

---

# 72. Repository Policy

Official expectations include:

- create a new repository after problem reveal
- keep it private during the event
- make it public after the submission deadline for evaluation
- include source code
- include dependency/configuration files
- do not commit secrets
- document external libraries/tools

Suggested repository name:

```text
gridwise-llm-optimizer
```

---

# 73. README Context

The README must be fully self-contained.

A judge should be able to reproduce the service without contacting the team.

README should document:

- problem overview
- system architecture
- LLM provider/model
- LLM role
- deterministic guardrail design
- optimizer and solver
- dependencies
- environment variable names
- exact local setup
- exact local run command
- `/health` example
- `/optimize-energy` example
- public-sample test command
- Docker build command
- Docker run command
- Docker registry pull command
- exposed port
- known limitations
- secret-handling guidance

Never place actual credentials in README.

---

# 74. Testing Philosophy

Semantic interpretation and mathematical optimization must be testable independently.

Do not make every optimizer test depend on a live model API.

Do not make every LLM test depend on an optimization solver.

The test system should separate:

```text
semantic correctness
mathematical correctness
API integration
deployment correctness
```

---

# 75. Deterministic Unit-Test Targets

Unit tests should cover:

- request validation
- response validation
- directive models
- guardrails
- note-index mapping
- hour arrays
- factor validation
- reserve validation
- grid-cap validation
- directive compilation
- LP equations
- battery transition logic
- totals
- replay validation

---

# 76. LLM Semantic Validation Tests

Use official public notes to verify:

```text
applies
directive_type
hours
factor
minimum_energy_kwh
max_grid_kwh
no_op
```

Do not require exact explanation wording.

The machine-checkable expected interpretation is what matters.

---

# 77. Optimizer Tests

Optimizer tests should bypass live LLM interpretation.

Feed validated directive objects directly.

Verify:

- optimal solver status
- all official constraints
- end-of-day neutrality
- replay success
- optimal/equivalent cost within tolerance

This isolates optimizer bugs from LLM mistakes.

---

# 78. End-to-End Tests

End-to-end tests should call:

```http
POST /optimize-energy
```

Verify:

- successful status
- scenario ID echo
- correct number/order of interpretations
- structured interpretation correctness
- exactly 24 plan entries
- replay success
- recalculated totals
- acceptable latency

Final pre-submission validation should use the actual configured model/provider as well as mocks.

---

# 79. Malformed Request Testing Context

The service should be tested against:

- malformed JSON
- missing fields
- empty note list
- more than 3 notes
- empty note string
- 23 hourly entries
- 25 hourly entries
- duplicate hour
- missing hour
- hour outside 0–23
- negative demand
- negative solar
- non-finite numbers
- invalid capacity
- initial energy above capacity
- minimum reserve above capacity
- negative rate limits

No malformed request should crash the server.

---

# 80. Malformed LLM Output Testing Context

Mock invalid model results such as:

- malformed JSON
- unsupported directive
- missing interpretation
- duplicate note index
- extra note index
- wrong note order
- `no_op` with `applies=true`
- non-`no_op` with `applies=false`
- `no_op` with non-null adjustment
- factor greater than 1
- negative factor
- reserve above battery capacity
- negative grid cap
- duplicate hours
- unsorted hours
- hour outside 0–23
- wrong structured-adjustment shape

Invalid model output must never silently reach the optimizer.

---

# 81. Replay Corruption Testing Context

Take a valid schedule and deliberately corrupt it.

Examples:

- solar exceeds effective solar
- battery charges during a no-charge hour
- battery discharges during a no-discharge hour
- grid exceeds a max-grid constraint
- battery drops below active reserve
- battery exceeds capacity
- battery transition is inconsistent
- charge rate exceeded
- discharge rate exceeded
- energy balance broken
- final battery differs from initial
- total cost altered
- total grid altered
- peak grid altered

The replay layer should detect all of these.

---

# 82. Randomized Robustness Testing

Generate synthetic valid numeric scenarios.

Vary:

- demand
- solar
- tariff
- capacity
- initial battery energy
- base minimum energy
- max charge rate
- max discharge rate
- valid directive combinations

For each scenario:

```text
solve
-> require optimal
-> reconstruct
-> replay
-> recalculate
-> require no invariant failures
```

This is useful for hidden-test robustness because hidden cases vary numeric combinations.

---

# 83. Performance Measurement Context

Measure:

```text
p50
p95
maximum latency
failure rate
```

Track component timing:

- request validation
- LLM
- guardrails
- constraint compilation
- LP solve
- reconstruction
- replay
- total request

Unexpectedly large LP latency should be investigated because the optimization problem is small.

Provider latency will normally dominate.

---

# 84. Official Scoring Context

The base 100-point score is:

| Category | Points |
|---|---:|
| LLM Directive Interpretation | 25 |
| Directive Application & Constraint Correctness | 25 |
| Optimization Quality | 10 |
| API Contract & Schema | 10 |
| Performance & Reliability | 10 |
| Deployment & Docker Fallback | 10 |
| Documentation & Local Reproducibility | 10 |
| **Total** | **100** |

Architectural priority should therefore be:

```text
semantic correctness
-> directive correctness
-> mathematical validity
-> optimization quality
-> exact API behavior
-> reliability
-> reproducibility
```

Do not prioritize decorative frontend work over judged behavior.

---

# 85. Interpretation Scoring Context

Machine-checked interpretation includes:

- relevant vs irrelevant / `no_op`
- directive type
- affected hours
- required numeric values
- adjustment object shape
- paraphrase robustness

Free-text explanation wording is not the primary exact-match target.

The system should optimize for structured semantic correctness.

---

# 86. Downstream Ground-Truth Checking

The judge does not simply trust the team's reported directive.

The schedule is checked separately against organizer ground truth.

Example:

If the real note means:

```text
no_charge_window
```

but the team's LLM incorrectly reports:

```text
no_op
```

the returned plan may still be checked against the true no-charge restriction.

If the plan charges during that period, the case can become invalid.

Therefore semantic mistakes can cause:

- interpretation score loss
- directive-application score loss
- optimization-credit loss

The interpretation layer is safety-critical for scoring.

---

# 87. Invalid-Case Consequences

A hidden case can be invalidated by:

- unmet demand
- energy-balance failure
- battery-state mismatch
- battery bound violation
- charge-rate violation
- discharge-rate violation
- effective solar overuse
- impossible negative values
- no-charge violation
- no-discharge violation
- reserve violation
- grid-cap violation
- end-of-day battery-neutrality failure

Invalid cases receive no optimization credit for that case.

Correctness before cost.

---

# 88. Public Reference Schedules Are Not Templates

The public JSON contains one valid optimal schedule per case.

The production optimizer must not imitate those schedules.

Different schedules can be accepted when they:

- obey the same directive ground truth
- satisfy all energy/battery constraints
- achieve equivalent optimal cost

Build a solver, not a lookup table.

---

# 89. Tie-Break Context

The required 3-minute architecture/solution video has no base score.

It is used when teams tie on total score.

The architecture should therefore be clean enough to explain clearly:

```text
LLM
-> strict deterministic guardrail
-> exact LP optimizer
-> independent replay validator
```

Engineering clarity matters at tie boundaries.

---

# 90. Production Engineering Principles

## Correctness over cleverness

Prefer a simple exact design over an impressive but fragile architecture.

## Separation of concerns

Keep natural-language understanding, deterministic validation, mathematical optimization, and final replay separate.

## Fail closed

A critical validation or solver failure should not produce a fake successful plan.

## Explicit invariants

Encode important rules as executable validation.

Do not rely only on comments.

## Reproducibility

The repository and Docker image should work on a clean environment.

## Minimal hidden state

No undocumented manual configuration.

## Safe observability

Failures should be diagnosable internally without leaking secrets.

---

# 91. Anti-Patterns to Avoid

Do not use:

```text
if "solar" in note:
    ...
```

as the main semantic engine.

Do not let the LLM create 24 hourly actions.

Do not accept arbitrary model-created directive names.

Do not apply raw LLM output.

Do not optimize hour-by-hour greedily.

Do not copy reference schedules.

Do not return a plan without replay validation.

Do not trust totals without recalculation.

Do not round aggressively inside optimization.

Do not silently drop malformed notes.

Do not convert uncertain notes into `no_op` merely to avoid errors.

Do not bake credentials into Docker.

Do not expose raw stack traces.

Do not submit an endpoint that only works inside a private network.

---

# 92. Dependency Philosophy

Keep the dependency graph small and auditable.

Typical categories:

```text
FastAPI
Uvicorn
Pydantic
Pydantic Settings
LLM SDK or HTTP client
PuLP
HiGHS
pytest
```

Avoid unnecessary heavyweight ML frameworks if using a hosted language model.

Fewer dependencies improve:

- Docker build speed
- startup speed
- reproducibility
- security
- debugging

---

# 93. Model/Provider Choice Philosophy

The LLM task is narrow:

```text
short natural-language note
->
small structured directive object
```

Choose a model/provider based on:

- semantic accuracy
- structured-output reliability
- latency
- stability
- quota
- rate limit
- cost
- availability during judging

A fast reliable model can be better than a slower very large model for this challenge.

The model does not need to solve the LP.

---

# 94. Provider Abstraction Principle

Provider SDK code belongs in one dedicated layer.

Do not couple optimizer/core services directly to one vendor.

The rest of the application should consume normalized internal directive objects.

This keeps the system easy to:

- test
- swap providers
- mock
- debug

---

# 95. Explanation Field Philosophy

The directive `explanation` should be concise.

Examples:

```text
"Battery charging is unavailable during maintenance."
```

```text
"An 80% reduction leaves 20% usable solar during the stated hours."
```

Do not request long hidden reasoning or chain-of-thought from the model.

The explanation is for readability, not mathematical control.

---

# 96. Exact Directive Shapes

## Solar reduction

Correct:

```json
{
  "hours": [11, 12, 13],
  "factor": 0.2
}
```

Incorrect schema style:

```json
{
  "start_hour": 11,
  "end_hour": 14,
  "reduction_percent": 80
}
```

Even though the second object is understandable, it does not match the required contract.

---

## Minimum reserve

Correct:

```json
{
  "hours": [18, 19, 20],
  "minimum_energy_kwh": 100
}
```

Not:

```json
{
  "reserve": "50%"
}
```

---

## No charge

Correct:

```json
{
  "hours": [2, 3, 4]
}
```

---

## No discharge

Correct:

```json
{
  "hours": [17, 18]
}
```

---

## Grid cap

Correct:

```json
{
  "hours": [19, 20],
  "max_grid_kwh": 180
}
```

---

# 97. `no_op` Exactness

Correct:

```json
{
  "note_index": 2,
  "applies": false,
  "directive_type": "no_op",
  "structured_adjustment": null,
  "explanation": "This note does not affect today's energy schedule."
}
```

Do not:

- omit `structured_adjustment`
- use `{}`
- use `applies=true`
- invent a meaningless numeric adjustment

---

# 98. Why Full-Horizon Optimization Is Necessary

The optimizer must reason across all 24 hours simultaneously.

A battery decision now affects:

- later battery state
- later expensive hours
- future reserve requirements
- future grid caps
- future charging restrictions
- future discharge restrictions
- the requirement to restore initial energy at the end

Example:

```text
Hour 03 tariff = 5
Hour 19 tariff = 30
```

The optimizer may buy extra grid energy cheaply at hour 03, charge the battery, and discharge at hour 19.

But only when all other constraints permit it.

This global coupling makes a full-horizon LP the correct model.

---

# 99. Why Greedy Dispatch Is Unsafe

A rule such as:

```text
"discharge whenever the current tariff is high"
```

can fail because it may consume energy needed for:

- a higher future tariff
- a future grid cap
- a future reserve window
- a no-charge period that prevents recovery
- final battery restoration

The LP optimizes the entire horizon globally.

---

# 100. Final Response Construction Order

The safest internal response flow is:

```text
validated request
    ->
validated LLM interpretations
    ->
compiled per-hour constraints
    ->
optimal LP solution
    ->
response-style hourly plan
    ->
independent replay validation
    ->
recalculated totals
    ->
deterministic plan summary
    ->
final response
```

Do not return intermediate solver values directly.

---

# 101. Controlled Error Taxonomy

Useful internal error classes include:

```text
RequestValidationError
LLMProviderError
LLMOutputValidationError
OptimizationError
ReplayValidationError
ConfigurationError
```

Externally, errors should remain safe and controlled.

Never leak:

- secrets
- detailed stack traces
- internal credentials
- raw sensitive configuration

---

# 102. Local Reproducibility Requirement

From a clean environment, a reviewer should be able to:

1. clone the repository
2. configure documented environment-variable names
3. install dependencies or use Docker
4. start the service
5. call `/health`
6. call `/optimize-energy`
7. run at least one public sample

No undocumented manual step should be necessary.

---

# 103. Docker Reproducibility Principle

Local Python, Docker, and hosted deployment should run the same application code.

Do not create separate business logic for Docker.

Environment-specific differences should be configuration only.

This minimizes:

```text
"works locally but fails in container"
```

problems.

---

# 104. Submission Artifact Context

The complete solution package includes:

- public judging endpoint
- source repository
- self-contained README
- tested Docker fallback image
- 3-minute architecture/solution video

The Docker image must remain pullable during evaluation.

The hosted endpoint must remain available during evaluation.

---

# 105. Architecture Story for Reviewers

The solution should be explainable simply:

> The LLM converts each natural-language operator note into one of six strict structured directives. Deterministic guardrails validate the model output. The validated directives are compiled into hard per-hour constraints. An exact 24-hour linear program minimizes grid electricity cost. The resulting hourly plan is independently replayed against every energy, solar, battery, directive, and end-of-day rule. Only after replay succeeds are totals recalculated and the JSON response returned.

This is the desired mental model of the entire project.

---

# 106. Definition of a Correct Solution

A solution is correct only when all of the following are true:

```text
Every input note has exactly one interpretation.

Every interpretation uses a supported directive or no_op.

Every adjustment has the exact required schema.

Time windows use start-inclusive/end-exclusive semantics.

Hours are unique, ascending, and within 0..23.

Solar percentage semantics are correct.

Percentage battery reserve conversion is correct.

LLM output passed deterministic guardrails.

Every applicable directive reached the optimization model.

The optimizer solved all 24 hours simultaneously.

Every hourly demand is satisfied.

Solar usage never exceeds effective solar.

Battery state transitions are correct.

Battery remains inside capacity/minimum bounds.

Charge and discharge limits are respected.

No-charge windows are respected.

No-discharge windows are respected.

Minimum reserves are respected.

Grid caps are respected.

Final battery energy equals initial battery energy.

The finalized hourly plan passed independent replay.

Totals were recalculated from the finalized hourly plan.

The response matches the exact API schema.
```

Only after these are satisfied is optimization cost meaningful.

---

# 107. Definition of an Excellent Solution

An excellent implementation additionally provides:

- strong paraphrase robustness
- reliable structured model output
- deterministic guardrails
- exact LP optimality
- low request latency
- bounded retries
- robust provider failure handling
- comprehensive unit tests
- public-case regression tests
- randomized numeric robustness tests
- corruption/replay tests
- clean structured logs
- no secret leakage
- reproducible Docker image
- stable public deployment
- self-contained README
- clean modular code
- easy architecture explanation

---

# 108. Agent Operating Rules

Any AI coding agent working on this project must follow these rules.

1. **Never invent official challenge behavior.**
   - If behavior is not explicitly defined, label it as an engineering decision.

2. **Never trust LLM output.**
   - Validate every machine-critical field.

3. **Never trust solver output blindly.**
   - Require optimal status and replay the finalized response.

4. **Never replace exact optimization with a heuristic when LP is available.**

5. **Never return an invalid best-effort schedule as success.**

6. **Never hard-code public sample cases.**

7. **Never expose secrets.**

8. **Keep interpretation, validation, optimization, and replay independent.**

9. **Use the official whole-hour time convention exactly.**

10. **Use solar `factor` as remaining usable fraction exactly.**

11. **Preserve precision internally.**

12. **Validate the actual values that will be returned.**

13. **Always recalculate totals from the final hourly plan.**

14. **Treat Docker as a required production artifact.**

15. **Prefer simple, auditable, testable engineering over unnecessary complexity.**

---

# 109. Critical Final Engineering Invariant

The most important invariant of the entire project is:

```text
NO SUCCESSFUL /optimize-energy RESPONSE
MAY BE RETURNED
UNTIL THE FINALIZED 24-HOUR PLAN
HAS PASSED AN INDEPENDENT
DETERMINISTIC REPLAY VALIDATOR.
```

The required pipeline is:

```text
LLM semantic extraction
        ->
strict deterministic guardrail
        ->
numeric directive compilation
        ->
exact continuous 24-hour LP
        ->
optimal solver status
        ->
hourly response reconstruction
        ->
independent replay validation
        ->
totals recalculation
        ->
successful API response
```

The application should behave like a small production optimization service, not a demo.

---

# 110. One-Line System Summary

> **GridWise is a hybrid AI + deterministic optimization service where the LLM understands operator language, strict code validates and compiles that meaning into constraints, an exact linear program minimizes 24-hour grid electricity cost, and an independent replay validator proves the final schedule is valid before the API responds.**
