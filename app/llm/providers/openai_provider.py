"""OpenAI / OpenAI-compatible directive interpreter using httpx."""

import json
from typing import Any
import httpx
from app.config import settings
from app.errors import LLMProviderError
from app.llm.base import DirectiveInterpreter
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.schemas.directives import DirectiveInterpretation


class OpenAIDirectiveInterpreter(DirectiveInterpreter):
    """Interprets notes using OpenAI or OpenAI-compatible chat completion endpoints."""

    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or settings.LLM_TIMEOUT_SECONDS

    async def interpret(
        self,
        operator_notes: list[str],
        battery_context: dict[str, Any],
    ) -> list[DirectiveInterpretation]:
        if not self.api_key:
            raise LLMProviderError("LLM_API_KEY is not configured for OpenAI provider")

        user_prompt = build_user_prompt(operator_notes, battery_context)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )

                if response.status_code != 200:
                    raise LLMProviderError(
                        f"OpenAI provider returned status {response.status_code}: {response.text[:200]}"
                    )

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                # Parse JSON content
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "interpretations" in parsed:
                    raw_list = parsed["interpretations"]
                elif isinstance(parsed, list):
                    raw_list = parsed
                else:
                    # Look for first list value in dict
                    raw_list = next((v for v in parsed.values() if isinstance(v, list)), [parsed])

                return [DirectiveInterpretation.model_validate(item) for item in raw_list]

        except httpx.TimeoutException as e:
            raise LLMProviderError(f"OpenAI provider timed out after {self.timeout}s: {e}")
        except json.JSONDecodeError as e:
            raise LLMProviderError(f"OpenAI provider returned malformed JSON: {e}")
        except Exception as e:
            if isinstance(e, LLMProviderError):
                raise
            raise LLMProviderError(f"OpenAI provider communication error: {e}")
