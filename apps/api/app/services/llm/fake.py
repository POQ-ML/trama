"""Deterministic fake provider for tests (no network, no key)."""

from __future__ import annotations

from app.services.llm.base import (
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)


class FakeLLMProvider(LLMProvider):
    """In-memory fake implementing the provider-independent contract."""

    def __init__(
        self,
        model: str = "fake-flash",
        text: str = "fake response",
        usage: LLMUsage | None = None,
        error: LLMError | None = None,
    ) -> None:
        self.provider_name = "fake"
        self.model = model
        self._text = text
        self._usage = usage or LLMUsage(input_tokens=3, output_tokens=5, total_tokens=8)
        self._error = error
        self.calls: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return LLMResponse(
            text=self._text,
            provider=self.provider_name,
            model=self.model,
            usage=self._usage,
            request_id=request.request_id,
            retry_count=0,
        )
