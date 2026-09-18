"""Google Gemini directive interpreter using async httpx REST client."""

import json
import logging
import re
from typing import Any
import httpx
from app.config import settings
from app.errors import LLMProviderError
from app.llm.base import DirectiveInterpreter
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas.directives import DirectiveInterpretation

logger = logging.getLogger(__name__)


class GeminiDirectiveInterpreter(DirectiveInterpreter):
    """Interprets operator notes using Google Gemini generative API."""

    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        timeout: float = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL or "gemini-flash-lite-latest"
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    async def interpret(
        self,
        operator_notes: list[str],
        battery_context: dict[str, Any],
    ) -> list[DirectiveInterpretation]:
        if not self.api_key:
            raise LLMProviderError("LLM_API_KEY is not configured for Gemini provider")

        user_prompt = build_user_prompt(operator_notes, battery_context)
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.api_key,
        }

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.0,
            },
        }

        # Models to attempt (configured model first, then fast available fallbacks if 503/timeout)
        candidate_models = [self.model]
        for fallback in ["gemini-flash-lite-latest", "gemini-3.1-flash-lite"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        last_error = None
        for current_model in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent"
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    if response.status_code != 200:
                        err_text = response.text[:200]
                        logger.warning(
                            f"Gemini model {current_model} returned {response.status_code}: {err_text}"
                        )
                        last_error = LLMProviderError(f"Gemini API returned status {response.status_code}: {err_text}")
                        continue

                    data = response.json()
                    candidate = data["candidates"][0]["content"]["parts"][0]["text"]
                    
                    # Clean markdown fence if present
                    clean_text = candidate.strip()
                    if clean_text.startswith("```"):
                        clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                        clean_text = re.sub(r"\s*```$", "", clean_text)

                    parsed = json.loads(clean_text)

                    if isinstance(parsed, list):
                        raw_list = parsed
                    elif isinstance(parsed, dict) and "interpretations" in parsed:
                        raw_list = parsed["interpretations"]
                    else:
                        raw_list = next((v for v in parsed.values() if isinstance(v, list)), [parsed])

                    return [DirectiveInterpretation.model_validate(item) for item in raw_list]

            except httpx.TimeoutException as e:
                logger.warning(f"Gemini model {current_model} timed out after {self.timeout}s")
                last_error = LLMProviderError(f"Gemini API timed out after {self.timeout}s: {e}")
                continue
            except json.JSONDecodeError as e:
                logger.warning(f"Gemini model {current_model} returned non-JSON text: {e}")
                last_error = LLMProviderError(f"Gemini API returned malformed JSON: {e}")
                continue
            except Exception as e:
                if isinstance(e, LLMProviderError):
                    last_error = e
                else:
                    last_error = LLMProviderError(f"Gemini API communication error: {e}")
                continue

        raise last_error or LLMProviderError("All candidate Gemini models failed to produce a valid response.")
