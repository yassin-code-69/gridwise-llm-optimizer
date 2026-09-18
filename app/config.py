"""Application configuration using Pydantic Settings."""

from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # LLM Settings
    LLM_PROVIDER: Literal["mock", "openai", "gemini"] = "mock"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: Optional[str] = None
    LLM_TIMEOUT_SECONDS: float = 5.0
    LLM_MAX_RETRIES: int = 2

    # Server Settings
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"

    # Solver Settings
    PRIMARY_SOLVER: str = "HiGHS"
    FALLBACK_SOLVER: str = "CBC"

    # Tolerance Settings (Official spec standard is 0.01)
    TOLERANCE_KWH: float = 0.01
    TOLERANCE_BDT: float = 0.01


settings = Settings()
