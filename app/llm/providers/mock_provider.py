"""Deterministic mock directive interpreter for testing, offline evaluation, and CI/CD."""

import re
from typing import Any, Optional
from app.llm.base import DirectiveInterpreter
from app.schemas.directives import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeAdjustment,
    NoDischargeAdjustment,
    MaxGridAdjustment,
)


class MockDirectiveInterpreter(DirectiveInterpreter):
    """Semantic interpreter using deterministic pattern recognition for testing and offline runs."""

    def _parse_time_window(self, text: str) -> list[int]:
        """Extracts start-inclusive, end-exclusive whole hours from common natural language time expressions."""
        text_lower = text.lower()
        
        # Regex for "X (am|pm) (to|until|between) Y (am|pm)" or "noon to Y pm"
        # Special replacements
        t = text_lower.replace("noon", "12 pm").replace("midnight", "12 am")

        # 24-hour format: e.g. "14:00 to 17:00", "between 14:00 and 17:00", "14:00-17:00"
        h24_match = re.search(r"(?:between|from)?\s*(\d{1,2}):00\s*(?:and|to|until|-)\s*(\d{1,2}):00", t)
        if h24_match:
            s_h = int(h24_match.group(1))
            e_h = int(h24_match.group(2))
            if 0 <= s_h <= 24 and 0 <= e_h <= 24:
                if s_h < e_h:
                    return list(range(s_h, min(e_h, 24)))
                elif s_h > e_h:
                    return list(range(s_h, 24)) + list(range(0, e_h))
                else:
                    return [s_h]

        # "hours X to Y" or "hours X-Y"
        hours_match = re.search(r"(?:hours?|hrs?)\s*(\d{1,2})\s*(?:and|to|until|-)\s*(\d{1,2})", t)
        if hours_match:
            s_h = int(hours_match.group(1))
            e_h = int(hours_match.group(2))
            if 0 <= s_h <= 24 and 0 <= e_h <= 24:
                if s_h < e_h:
                    return list(range(s_h, min(e_h, 24)))
                elif s_h > e_h:
                    return list(range(s_h, 24)) + list(range(0, e_h))
                else:
                    return [s_h]

        patterns = [
            r"(?:between|from)?\s*(\d{1,2})\s*(am|pm)\s*(?:and|to|until|-)\s*(\d{1,2})\s*(am|pm)",
            r"(\d{1,2})\s*(am|pm)\s*-\s*(\d{1,2})\s*(am|pm)",
        ]
        
        for p in patterns:
            match = re.search(p, t)
            if match:
                start_h = int(match.group(1))
                start_ampm = match.group(2)
                end_h = int(match.group(3))
                end_ampm = match.group(4)
                
                # Convert 12-hour to 24-hour
                if start_ampm == "pm" and start_h != 12:
                    start_h += 12
                elif start_ampm == "am" and start_h == 12:
                    start_h = 0

                if end_ampm == "pm" and end_h != 12:
                    end_h += 12
                elif end_ampm == "am" and end_h == 12:
                    end_h = 0
                    
                if start_h < end_h:
                    return list(range(start_h, end_h))
                elif start_h > end_h:
                    # Wraparound if any
                    return list(range(start_h, 24)) + list(range(0, end_h))
                else:
                    return [start_h]

        return []

    async def interpret(
        self,
        operator_notes: list[str],
        battery_context: dict[str, Any],
    ) -> list[DirectiveInterpretation]:
        interpretations: list[DirectiveInterpretation] = []
        capacity = float(battery_context.get("capacity_kwh", 200.0))

        for idx, note in enumerate(operator_notes):
            n_lower = note.lower()
            hours = self._parse_time_window(note)

            # 1. Solar Reduction
            if any(w in n_lower for w in ("solar", "pv", "rooftop", "photovoltaic", "sun")) and any(
                w in n_lower for w in ("reduc", "drop", "cleaning", "dust", "fog", "cloud", "fall", "remain")
            ):
                # Detect percentage or fraction
                # Check for "X% reduction" or "reduced by X%"
                pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", n_lower)
                fraction_match = re.search(r"(one-fifth|one fifth|half|quarter|one-third)", n_lower)
                
                factor = 0.5  # default
                if pct_match:
                    pct = float(pct_match.group(1))
                    if any(w in n_lower for w in ("reduction", "reduced", "drop", "decrease", "down")):
                        # X% reduction -> (100 - X)% remains
                        factor = max(0.0, min(1.0, (100.0 - pct) / 100.0))
                    else:
                        # "usable solar is X%" -> factor is X/100
                        factor = max(0.0, min(1.0, pct / 100.0))
                elif fraction_match:
                    f_str = fraction_match.group(1)
                    if "one-fifth" in f_str or "one fifth" in f_str:
                        factor = 0.2
                    elif "half" in f_str:
                        factor = 0.5
                    elif "quarter" in f_str:
                        factor = 0.25

                if not hours:
                    hours = [11, 12, 13]  # Fallback midday window

                interpretations.append(
                    DirectiveInterpretation(
                        note_index=idx,
                        applies=True,
                        directive_type="solar_reduction",
                        structured_adjustment=SolarReductionAdjustment(hours=hours, factor=round(factor, 4)),
                        explanation=f"Solar output reduced to {factor*100:.1f}% of forecast during hours {hours}.",
                    )
                )

            # 2. Minimum Battery Reserve
            elif any(w in n_lower for w in ("reserve", "stored", "keep at least", "emergency reserve", "retain")) and not any(
                w in n_lower for w in ("calibrated", "past", "visitor", "personnel")
            ):
                # Check for absolute kWh or relative %
                kwh_match = re.search(r"(\d+(?:\.\d+)?)\s*kwh", n_lower)
                pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", n_lower)
                
                if kwh_match:
                    reserve_kwh = float(kwh_match.group(1))
                elif pct_match:
                    pct = float(pct_match.group(1))
                    reserve_kwh = (pct / 100.0) * capacity
                elif "half" in n_lower:
                    reserve_kwh = 0.5 * capacity
                else:
                    reserve_kwh = 100.0

                if not hours:
                    hours = [18, 19, 20]

                interpretations.append(
                    DirectiveInterpretation(
                        note_index=idx,
                        applies=True,
                        directive_type="minimum_battery_reserve",
                        structured_adjustment=MinimumBatteryReserveAdjustment(
                            hours=hours, minimum_energy_kwh=round(reserve_kwh, 2)
                        ),
                        explanation=f"Maintain minimum battery reserve of {reserve_kwh:.1f} kWh during hours {hours}.",
                    )
                )

            # 3. No Charge Window
            elif any(w in n_lower for w in ("no charge", "no-charge", "do not charge", "don't charge", "prohibit charging", "avoid charging", "charging is unavailable", "charging unavailable", "prevents battery charging", "cannot charge", "disable charging", "charger circuit", "inverter inspection")):
                if not hours:
                    hours = [14, 15]

                interpretations.append(
                    DirectiveInterpretation(
                        note_index=idx,
                        applies=True,
                        directive_type="no_charge_window",
                        structured_adjustment=NoChargeAdjustment(hours=hours),
                        explanation=f"Battery charging is unavailable during hours {hours}.",
                    )
                )

            # 4. No Discharge Window
            elif any(w in n_lower for w in ("no discharge", "no-discharge", "do not discharge", "don't discharge", "prohibit discharge", "prohibit discharging", "avoid discharging", "prohibits battery discharge", "discharging is unavailable", "discharging unavailable", "cannot discharge", "disable discharging", "relay testing", "frequency stabilization")):
                if not hours:
                    hours = [17, 18]

                interpretations.append(
                    DirectiveInterpretation(
                        note_index=idx,
                        applies=True,
                        directive_type="no_discharge_window",
                        structured_adjustment=NoDischargeAdjustment(hours=hours),
                        explanation=f"Battery discharging is prohibited during hours {hours}.",
                    )
                )

            # 5. Max Grid Window
            elif any(w in n_lower for w in ("grid", "import", "substation", "cap grid", "do not exceed", "maximum", "limit")) and any(
                w in n_lower for w in ("kwh", "cap", "limit", "surcharge")
            ) and not any(w in n_lower for w in ("calibrated", "menu")):
                kwh_match = re.search(r"(\d+(?:\.\d+)?)\s*kwh", n_lower)
                cap_kwh = float(kwh_match.group(1)) if kwh_match else 150.0

                if not hours:
                    hours = [18, 19, 20]

                interpretations.append(
                    DirectiveInterpretation(
                        note_index=idx,
                        applies=True,
                        directive_type="max_grid_window",
                        structured_adjustment=MaxGridAdjustment(hours=hours, max_grid_kwh=round(cap_kwh, 2)),
                        explanation=f"Grid electricity import capped at {cap_kwh:.1f} kWh during hours {hours}.",
                    )
                )

            # 6. Distractor / No-op
            else:
                interpretations.append(
                    DirectiveInterpretation(
                        note_index=idx,
                        applies=False,
                        directive_type="no_op",
                        structured_adjustment=None,
                        explanation="Administrative note; does not affect today's energy schedule.",
                    )
                )

        return interpretations
