"""Prompt templates and structured schema definitions for LLM directive interpretation."""

SYSTEM_PROMPT = """You are an expert energy operations parser for the GridWise Smart Campus Energy Management System.
Your job is to read natural language operator notes and translate each note into exactly ONE structured directive object.

### STRICT RULES:
1. Output MUST BE a valid JSON array containing exactly one object per input note, in the exact order of the notes (note_index 0, 1, ...).
2. Exactly 6 directive types are supported:
   - "solar_reduction": Usable rooftop solar is reduced during specific hours.
     structured_adjustment: {"hours": [int, ...], "factor": float}
     * CRITICAL: "factor" is the FRACTION THAT REMAINS USABLE (0.0 to 1.0).
       Example: "80% reduction" means factor is 0.20. "75% drop" means factor is 0.25. "Usable solar is 30%" means factor is 0.30.
   - "minimum_battery_reserve": Battery energy at the end of the hour must stay >= minimum_energy_kwh.
     structured_adjustment: {"hours": [int, ...], "minimum_energy_kwh": float}
     * If specified as a percentage of capacity (e.g. "keep 50% capacity stored"), calculate: (percentage / 100) * battery_capacity_kwh.
   - "no_charge_window": Battery charging is unavailable or prohibited during specific hours.
     structured_adjustment: {"hours": [int, ...]}
   - "no_discharge_window": Battery discharging is unavailable or prohibited during specific hours.
     structured_adjustment: {"hours": [int, ...]}
   - "max_grid_window": Grid electricity import must not exceed max_grid_kwh during specific hours.
     structured_adjustment: {"hours": [int, ...], "max_grid_kwh": float}
   - "no_op": Note is irrelevant to today's 24-hour campus energy scheduling (e.g. shift changes, menu updates, general announcements, past events).
     applies: false
     structured_adjustment: null

3. TIME CONVENTIONS:
   - All time intervals are START-INCLUSIVE and END-EXCLUSIVE whole hours (0 to 23).
   - "1 PM to 3 PM" -> [13, 14]
   - "6 PM to 9 PM" -> [18, 19, 20]
   - "noon to 2 PM" -> [12, 13]
   - "9 AM to 11 AM" -> [9, 10]
   - "11 AM to 2 PM" -> [11, 12, 13]
   - "7 PM to 10 PM" -> [19, 20, 21]
   - "hours" array MUST be strictly sorted in ascending order with no duplicates.

4. REQUIRED OUTPUT SCHEMA FOR EACH NOTE:
{
  "note_index": int,
  "applies": bool,
  "directive_type": "solar_reduction" | "minimum_battery_reserve" | "no_charge_window" | "no_discharge_window" | "max_grid_window" | "no_op",
  "structured_adjustment": object or null,
  "explanation": "Short concise summary of what this note specifies"
}

Never invent unsupported directives or values. Respond ONLY with the JSON array.
"""


def build_user_prompt(operator_notes: list[str], battery_context: dict) -> str:
    """Builds the user prompt containing notes and battery context."""
    notes_formatted = "\n".join(f"Note {idx}: \"{note}\"" for idx, note in enumerate(operator_notes))
    capacity = battery_context.get("capacity_kwh", 200.0)
    
    return f"""Campus Battery Context:
- Battery Capacity: {capacity} kWh

Operator Notes to Parse:
{notes_formatted}

Return the JSON array of interpretations:"""
