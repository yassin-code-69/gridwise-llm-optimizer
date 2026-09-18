"""Orchestrator and factory for LLM directive interpretation with bounded retry logic and LRU caching."""

import collections
import logging
import threading
from typing import Any, Optional
from app.config import settings
from app.core.guardrails import validate_llm_interpretations
from app.errors import LLMOutputValidationError, LLMProviderError
from app.llm.base import DirectiveInterpreter
from app.llm.providers.gemini_provider import GeminiDirectiveInterpreter
from app.llm.providers.mock_provider import MockDirectiveInterpreter
from app.llm.providers.openai_provider import OpenAIDirectiveInterpreter
from app.schemas.directives import DirectiveInterpretation
from app.schemas.request import BatteryInput

logger = logging.getLogger(__name__)


class InterpretationCache:
    """Thread-safe bounded in-memory LRU cache for structured LLM interpretations."""

    def __init__(self, maxsize: int = 256):
        self.maxsize = maxsize
        self._cache: collections.OrderedDict[tuple, list[DirectiveInterpretation]] = collections.OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def make_key(
        self,
        operator_notes: list[str],
        battery: BatteryInput,
        provider_name: str,
        model_name: str,
    ) -> tuple:
        return (
            tuple(n.strip() for n in operator_notes),
            round(battery.capacity_kwh, 4),
            round(battery.minimum_energy_kwh, 4),
            round(battery.initial_energy_kwh, 4),
            provider_name,
            model_name,
            "v1",
        )

    def get(self, key: tuple) -> Optional[list[DirectiveInterpretation]]:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self.hits += 1
                return [d.model_copy() for d in self._cache[key]]
            self.misses += 1
            return None

    def set(self, key: tuple, value: list[DirectiveInterpretation]) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = [d.model_copy() for d in value]
            if len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self.hits = 0
            self.misses = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# Global singleton cache
interpretation_cache = InterpretationCache(maxsize=256)


class LLMInterpreter:
    """Manages provider instantiation, structured inference, LRU caching, and deterministic validation retries."""

    def __init__(
        self,
        provider: Optional[DirectiveInterpreter] = None,
        cache: Optional[InterpretationCache] = None,
    ):
        if provider:
            self.provider = provider
        else:
            self.provider = self._create_provider()
        self.cache = cache if cache is not None else interpretation_cache

    def _create_provider(self) -> DirectiveInterpreter:
        p_name = settings.LLM_PROVIDER.lower()
        if p_name == "openai":
            return OpenAIDirectiveInterpreter()
        elif p_name == "gemini":
            return GeminiDirectiveInterpreter()
        elif p_name == "mock":
            return MockDirectiveInterpreter()
        else:
            logger.warning(f"Unknown provider '{p_name}', falling back to MockDirectiveInterpreter")
            return MockDirectiveInterpreter()

    async def interpret_and_validate(
        self,
        operator_notes: list[str],
        battery: BatteryInput,
    ) -> list[DirectiveInterpretation]:
        """Runs interpretation with bounded retries and applies deterministic guardrail validation.

        First checks the in-memory LRU cache. On cache miss, queries the LLM provider with retries.

        Raises:
            LLMProviderError: If all retry attempts fail due to provider communication.
            LLMOutputValidationError: If all retry attempts fail guardrail validation.
        """
        battery_ctx = {
            "capacity_kwh": battery.capacity_kwh,
            "minimum_energy_kwh": battery.minimum_energy_kwh,
            "initial_energy_kwh": battery.initial_energy_kwh,
        }

        # 1. Check bounded interpretation cache
        cache_key = self.cache.make_key(
            operator_notes,
            battery,
            settings.LLM_PROVIDER.lower(),
            getattr(self.provider, "model", "default"),
        )
        cached_raw = self.cache.get(cache_key)
        if cached_raw is not None:
            try:
                validated = validate_llm_interpretations(cached_raw, operator_notes, battery)
                logger.debug("Interpretation cache hit for operator notes.")
                return validated
            except LLMOutputValidationError:
                # Stale or corrupted cache entry, proceed to live re-inference
                pass

        max_attempts = max(1, settings.LLM_MAX_RETRIES + 1)
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                # 2. LLM inference call
                raw_interpretations = await self.provider.interpret(operator_notes, battery_ctx)

                # 3. Deterministic guardrail check
                validated = validate_llm_interpretations(raw_interpretations, operator_notes, battery)

                # 4. Cache valid raw result for subsequent identical requests
                self.cache.set(cache_key, raw_interpretations)
                return validated

            except (LLMProviderError, LLMOutputValidationError) as exc:
                last_error = exc
                logger.warning(
                    f"LLM interpretation attempt {attempt}/{max_attempts} failed: {exc}. Retrying..."
                    if attempt < max_attempts
                    else f"LLM interpretation attempt {attempt}/{max_attempts} failed permanently."
                )

        if last_error:
            raise last_error
        raise LLMOutputValidationError("Failed to obtain valid interpretations from LLM.")
