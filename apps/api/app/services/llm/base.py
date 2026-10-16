"""Provider-independent LLM contracts for TRAMA.

The application must depend on these interfaces, never on a provider SDK
directly in business logic. Concrete adapters (Gemini, fakes) implement
``LLMProvider``.

Design notes:
  - ``LLMRequest`` carries system instructions + user input + generation
    knobs (incl. optional JSON-schema constrained output).
  - ``LLMResponse`` is normalized across providers.
  - ``LLMUsage`` uses ``None`` for unavailable counts — never fabricated.
  - ``LLMError`` normalizes provider failures into safe categories.
  - Cost is intentionally absent: no reliable pricing available at runtime,
    so it is reported as unavailable in telemetry instead of zero.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class LLMErrorCategory(str, Enum):
    """Normalized, provider-independent failure reasons."""

    AUTH = "auth"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    EMPTY_RESPONSE = "empty_response"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LLMUsage:
    """Token usage as reported by the provider.

    ``None`` means the provider did not report the metric. Callers must
    represent missing metrics explicitly and must not invent counts.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class LLMRequest:
    """A single text-generation request."""

    user_input: str
    system_instruction: str | None = None
    max_output_tokens: int | None = None
    response_mime_type: str | None = None
    response_json_schema: dict | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.user_input or not self.user_input.strip():
            raise ValueError("user_input must be a non-empty string")


@dataclass(frozen=True)
class LLMResponse:
    """Normalized successful response from any provider."""

    text: str
    provider: str
    model: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    request_id: str = ""
    retry_count: int = 0


class LLMError(Exception):
    """Normalized, user-safe provider failure.

    ``message`` must already be sanitized (no API keys, no raw provider
    payloads, no full prompts/responses). The original exception is kept
    out of the string representation on purpose.
    """

    def __init__(
        self,
        message: str,
        *,
        category: LLMErrorCategory,
        provider: str,
        model: str,
        retry_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.provider = provider
        self.model = model
        self.retry_count = retry_count

    @property
    def is_retryable(self) -> bool:
        return self.category in {
            LLMErrorCategory.TRANSIENT,
            LLMErrorCategory.TIMEOUT,
            LLMErrorCategory.RATE_LIMIT,
        }

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.provider}/{self.model}] {self.category.value}: {self.message}"


class LLMProvider(ABC):
    """Contract every LLM adapter must implement."""

    provider_name: str = "unknown"
    model: str = "unknown"

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Submit a text-generation request and return the normalized result."""
        raise NotImplementedError
