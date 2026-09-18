# GridWise — Official Specification Freeze (SPEC.md)

**Status:** FROZEN  
**Target Event:** BUP CSE Fest 2026 — Preliminary Hackathon  
**Challenge:** GridWise — LLM-Assisted Smart Campus Energy Optimization Challenge  
**Canonical Docs:** `BUP_CSE_FEST_2026_Preliminary_Problem_Statement_GridWise_LLM.pdf` & `BUP_CSE_FEST_2026_Participant_Guide_&_Evaluation_Rubric_GridWise_LLM.pdf`

---

## 1. Technical Architecture & Decisions

```text
Language              Python 3.11
Web API Framework     FastAPI
Data Validation       Pydantic v2
Configuration         pydantic-settings
HTTP Client           httpx
Optimization Model    Continuous Linear Program (PuLP)
Primary Solver        HiGHS (via highspy)
Fallback Solver       CBC (PULP_CBC_CMD)
Containerization      Docker (python:3.11-slim)
Production Server     Uvicorn (0.0.0.0:8000)
```

The system operates as a strict multi-stage deterministic pipeline:
1. **Request Validation**: Pydantic v2 validates structural and numerical bounds.
2. **LLM Semantic Interpretation**: Generative model translates natural language notes into typed directive adjustments.
3. **Deterministic Guardrails**: Untrusted model output is verified against invariants; invalid structures are rejected/retried.
4. **Constraint Compilation**: Validated directives are compiled into 24-hour mathematical upper/lower bounds.
5. **Continuous Linear Program**: Full-horizon 24-hour LP minimizes grid cost subject to all hard operational constraints.
6. **Output Reconstruction**: Signed flow $B[h]$ is mapped to battery actions (`charge`, `discharge`, `idle`) and rounded.
7. **Independent Replay Validator**: Schedule is audited against 21 physical, battery, solar, and directive invariants.
8. **Totals Recalculation**: `total_grid_kwh`, `total_cost_bdt`, and `peak_grid_kwh` are deterministically recomputed from `hourly_plan`.
9. **API Response**: Successful payload returned; if any invariant fails, a controlled error is returned instead of an invalid schedule.

---

## 2. API Endpoints

### 2.1 Health Check
- **Route**: `GET /health`
- **Auth**: None
- **Response**: `200 OK`
  ```json
  {
    "status": "ok"
  }
  ```
- **Readiness**: Must respond within 60 seconds of container startup.

### 2.2 Energy Optimization
- **Route**: `POST /optimize-energy`
- **Auth**: None
- **Content-Type**: `application/json`
- **Response**: `200 OK` on success, `400 Bad Request` on malformed/invalid input, `500 Internal Server Error` on controlled internal failure.

---

## 3. Data Contracts & Schemas

### 3.1 Request Schema (`OptimizationRequest`)
```json
{
  "scenario_id": "STRING",
  "operator_notes": ["STRING (1 to 3 non-empty items)"],
  "hours": [
    {
      "hour": 0,
      "demand_kwh": 100.0,
      "solar_kwh": 0.0,
      "tariff_bdt_per_kwh": 6.0
    }
  ],
  "battery": {
    "capacity_kwh": 200.0,
    "initial_energy_kwh": 100.0,
    "minimum_energy_kwh": 40.0,
    "max_charge_kwh_per_hour": 50.0,
    "max_discharge_kwh_per_hour": 50.0
  }
}
```

#### Invariants & Cross-Field Validations:
- `len(hours) == 24` exactly.
- `set(h.hour for h in hours) == {0, 1, ..., 23}` (no duplicates, no missing hours).
- `1 <= len(operator_notes) <= 3`, all non-empty strings.
- `capacity_kwh >= 0`.
- `0 <= initial_energy_kwh <= capacity_kwh`.
- `0 <= minimum_energy_kwh <= capacity_kwh`.
- `initial_energy_kwh >= minimum_energy_kwh`.
- `max_charge_kwh_per_hour >= 0`, `max_discharge_kwh_per_hour >= 0`.
- All numbers must be finite (reject `NaN`, `Infinity`, `-Infinity`).
- `demand_kwh >= 0`, `solar_kwh >= 0`.

### 3.2 Supported Directive Types & Shapes
Only these 6 directive types are permitted:

1. **`solar_reduction`**:
   ```json
   {
     "hours": [11, 12, 13],
     "factor": 0.2
   }
   ```
   - `factor` represents the **fraction that remains usable** ($0.0 \le \text{factor} \le 1.0$).
   - Rule: "80% reduction" $\rightarrow 20\%$ remains $\rightarrow \text{factor} = 0.20$.

2. **`minimum_battery_reserve`**:
   ```json
   {
     "hours": [18, 19, 20],
     "minimum_energy_kwh": 100.0
   }
   ```
   - Relative percentage (e.g. "keep 50% capacity") must be converted using battery `capacity_kwh`.
   - $0.0 \le \text{minimum\_energy\_kwh} \le \text{capacity\_kwh}$.

3. **`no_charge_window`**:
   ```json
   {
     "hours": [14, 15]
   }
   ```

4. **`no_discharge_window`**:
   ```json
   {
     "hours": [17, 18]
   }
   ```

5. **`max_grid_window`**:
   ```json
   {
     "hours": [19, 20, 21],
     "max_grid_kwh": 120.0
   }
   ```
   - $\text{max\_grid\_kwh} \ge 0.0$.

6. **`no_op`**:
   - Relevant for unrelated, administrative, or distractor notes.
   - Requires: `applies = false`, `structured_adjustment = null`.

#### Time Convention:
- All windows are **start-inclusive, end-exclusive** whole hours.
- Example: "1 PM to 3 PM" $\rightarrow [13, 14]$.
- `hours` array must be integers within $0..23$, unique, and sorted in ascending order.

### 3.3 Directive Interpretation Entry
```json
{
  "note_index": 0,
  "applies": true,
  "directive_type": "solar_reduction",
  "structured_adjustment": {
    "hours": [11, 12, 13],
    "factor": 0.2
  },
  "explanation": "Solar output reduced by 80% due to dust storm."
}
```
- Exactly one interpretation entry per input note.
- Output array ordered by `note_index` $0..N-1$.

### 3.4 Response Schema (`OptimizationResponse`)
```json
{
  "scenario_id": "SAMPLE-01",
  "directive_interpretation": [ ... ],
  "hourly_plan": [
    {
      "hour": 0,
      "grid_kwh": 60.0,
      "solar_used_kwh": 0.0,
      "battery_action": "idle",
      "battery_kwh": 0.0,
      "battery_energy_after_kwh": 100.0
    }
  ],
  "total_grid_kwh": 2150.45,
  "total_cost_bdt": 22450.80,
  "peak_grid_kwh": 185.0,
  "plan_summary": "Shifted battery charging to low-tariff off-peak hours..."
}
```

---

## 4. Mathematical Optimization Model

Let $h \in \{0, 1, \dots, 23\}$ index the hours.

### 4.1 Decision Variables
- $G[h] \ge 0$: Grid electricity import in hour $h$ (kWh).
- $S[h] \ge 0$: Solar electricity used in hour $h$ (kWh).
- $B[h] \in [-\text{max\_discharge}, \text{max\_charge}]$: Signed battery energy flow (kWh).
  - $B[h] > 0$: Battery charging.
  - $B[h] < 0$: Battery discharging.
  - $B[h] = 0$: Battery idle.
- $E[h]$: Battery stored energy immediately after hour $h$ (kWh).

### 4.2 Hard Constraints
1. **Solar Availability**:
   $$0 \le S[h] \le \text{effective\_solar}[h]$$
   where $\text{effective\_solar}[h] = \text{solar\_kwh}[h] \times \text{factor}$ if restricted.

2. **Energy Balance**:
   $$G[h] + S[h] = \text{demand\_kwh}[h] + B[h]$$
   *(Equivalent to: $G[h] + S[h] + \text{discharge}[h] = \text{demand\_kwh}[h] + \text{charge}[h]$)*

3. **Battery State Transitions**:
   $$E[0] = \text{initial\_energy\_kwh} + B[0]$$
   $$E[h] = E[h-1] + B[h], \quad \forall h \in \{1, \dots, 23\}$$

4. **Battery Energy Bounds**:
   $$\text{minimum\_energy}[h] \le E[h] \le \text{capacity\_kwh}$$
   where $\text{minimum\_energy}[h] = \max(\text{base\_minimum}, \text{active\_directive\_reserve})$.

5. **Directive Window Restrictions**:
   - If charging forbidden in hour $h$: $B[h] \le 0$.
   - If discharging forbidden in hour $h$: $B[h] \ge 0$.
   - If grid import capped in hour $h$: $G[h] \le \text{max\_grid}[h]$.

6. **End-of-Day Neutrality**:
   $$E[23] = \text{initial\_energy\_kwh}$$
   *(Hard equality constraint; battery is not a one-time source of free energy)*

### 4.3 Objective Function
Minimize total grid electricity cost over 24 hours:
$$\min \sum_{h=0}^{23} G[h] \times \text{tariff\_bdt\_per\_kwh}[h]$$

---

## 5. Output Reconstruction & Precision
- $\epsilon = 10^{-7}$.
- If $B[h] > \epsilon$: `battery_action = "charge"`, `battery_kwh = round(B[h], 6)`.
- If $B[h] < -\epsilon$: `battery_action = "discharge"`, `battery_kwh = round(abs(B[h]), 6)`.
- Otherwise: `battery_action = "idle"`, `battery_kwh = 0.0`.
- $E[h]$ is serialized as `battery_energy_after_kwh = round(E[h], 6)`.
- Residual numerical adjustments are applied so energy balance holds to within $0.001$.

---

## 6. Independent Replay Validation Invariants
Before generating an HTTP 200 response, the finalized `hourly_plan` is independently checked:
1. Exactly 24 records, hours $0..23$.
2. All values finite and non-negative (except valid zero).
3. If action is `idle`, `battery_kwh == 0`.
4. Charge rate $\le \text{max\_charge} + 10^{-4}$.
5. Discharge rate $\le \text{max\_discharge} + 10^{-4}$.
6. Battery state transition: $|E[h] - (E[h-1] \pm \text{battery\_kwh})| \le 0.01$.
7. Stored energy within $[\text{minimum\_energy}[h] - 0.01, \text{capacity} + 0.01]$.
8. Solar usage $\le \text{effective\_solar}[h] + 0.01$.
9. No charge / no discharge windows strictly respected.
10. Grid cap strictly respected: $G[h] \le \text{max\_grid}[h] + 0.01$.
11. Energy balance: $|(G + S + \text{discharge}) - (\text{demand} + \text{charge})| \le 0.01$.
12. End-of-day neutrality: $|E[23] - \text{initial\_energy\_kwh}| \le 0.01$.

---

## 7. Performance & Operational Requirements
- **Request Timeout**: Hard timeout at 30 seconds.
- **Latency Target**: p95 $\le 5.0$ seconds for full points.
- **Docker Environment**: Linux AMD64/ARM64 container on port 8000.
- **Secrets Management**: Zero secrets baked into git or docker image; all runtime config via env variables.
