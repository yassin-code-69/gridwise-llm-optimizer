"""Application configuration using Pydantic Settings."""

from typing import Literal, Optional
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General LLM Settings
    LLM_PROVIDER: Literal["mock", "openai", "gemini"] = "mock"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: Optional[str] = None
    LLM_TIMEOUT_SECONDS: float = 5.0
    LLM_MAX_RETRIES: int = 2

    # Gemini Primary + Backup Credentials (Secret-safe)
    GEMINI_API_KEY_PRIMARY: Optional[SecretStr] = None
    GEMINI_API_KEY_BACKUP_1: Optional[SecretStr] = None
    GEMINI_API_KEY_BACKUP_2: Optional[SecretStr] = None
    GEMINI_API_KEY_BACKUP_3: Optional[SecretStr] = None
    GEMINI_API_KEY_BACKUP_4: Optional[SecretStr] = None

    # Optional Puku Platform Key
    PUKU_API_KEY: Optional[SecretStr] = None

    GEMINI_MODEL: str = "gemini-flash-lite-latest"
    GEMINI_REQUEST_TIMEOUT_SECONDS: float = 1.5
    GEMINI_TOTAL_DEADLINE_SECONDS: float = 4.0
    GEMINI_MAX_ATTEMPTS: int = 3
    GEMINI_CIRCUIT_FAILURE_THRESHOLD: int = 2
    GEMINI_CIRCUIT_COOLDOWN_SECONDS: float = 30.0

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

    @model_validator(mode="after")
    def populate_gemini_primary_from_legacy(self) -> "Settings":
        """Backwards compatibility: If legacy LLM_API_KEY is present, use it as primary."""
        if not self.GEMINI_API_KEY_PRIMARY and self.LLM_API_KEY:
            self.GEMINI_API_KEY_PRIMARY = SecretStr(self.LLM_API_KEY)
        return self


settings = Settings()
