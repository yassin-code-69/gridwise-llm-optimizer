"""Domain-specific exceptions for GridWise."""

from typing import Optional


class GridWiseError(Exception):
    """Base exception for all GridWise application errors."""

    def __init__(self, message: str, status_code: int = 500, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class RequestValidationError(GridWiseError):
    """Raised when an incoming API request fails validation."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, status_code=400, details=details)


class LLMProviderError(GridWiseError):
    """Raised when the LLM provider fails (timeout, rate limit, HTTP error)."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, status_code=500, details=details)


class LLMOutputValidationError(GridWiseError):
    """Raised when LLM-produced output fails deterministic guardrail checks."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, status_code=500, details=details)


class OptimizationError(GridWiseError):
    """Raised when the mathematical solver fails or finds an infeasible state."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, status_code=500, details=details)


class ReplayValidationError(GridWiseError):
    """Raised when the reconstructed hourly plan violates any operational invariant."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, status_code=500, details=details)


class ConfigurationError(GridWiseError):
    """Raised when required configuration or solver binaries are missing."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message, status_code=500, details=details)
