"""Abstract base class for LLM directive interpreters."""

from abc import ABC, abstractmethod
from typing import Any
from app.schemas.directives import DirectiveInterpretation


class DirectiveInterpreter(ABC):
    """Vendor-agnostic interface for translating natural language notes to directives."""

    @abstractmethod
    async def interpret(
        self,
        operator_notes: list[str],
        battery_context: dict[str, Any],
    ) -> list[DirectiveInterpretation]:
        """Interprets a list of operator notes and returns typed DirectiveInterpretation objects.

        Args:
            operator_notes: 1 to 3 natural language notes from the operator.
            battery_context: Dict containing 'capacity_kwh' and other battery parameters.

        Returns:
            list[DirectiveInterpretation]: Exactly one object per note, in note order.
        """
        pass
