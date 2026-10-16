"""Provider-independent LLM usage telemetry.

Captured per request (when the provider reports it):
  request_id, provider, model, start timestamp, duration/latency,
  input/output/total tokens, success flag, normalized error category,
  retry count.

Deliberately NOT captured: full prompts, full responses, personal academic
data, API keys, or any sensitive payload. Missing token metrics stay
``None`` (never invented). Monetary cost is always ``None`` (unavailable):
no reliable pricing data exists at runtime, so cost is reported as
unavailable rather than zero.

Telemetry works for any ``LLMProvider`` via ``observe()`` — it is not
implemented exclusively inside the Gemini adapter.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.core.logging import get_logger
from app.services.llm.base import LLMError, LLMErrorCategory, LLMProvider, LLMRequest, LLMResponse

logger = get_logger("trama.llm.telemetry")


@dataclass(frozen=True)
class LLMTelemetryRecord:
    request_id: str
    provider: str
    model: str
    started_at: datetime
    duration_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    success: bool = True
    error_category: str | None = None
    retry_count: int = 0
    cost_usd: float | None = None  # always None: unavailable, never fabricated
    telemetry_id: str = field(default="")


class TelemetrySink(Protocol):
    def record(self, record: LLMTelemetryRecord) -> None: ...


class LoggingTelemetrySink:
    """Structured-log sink. Logs counts/outcomes only — never payloads."""

    def record(self, record: LLMTelemetryRecord) -> None:
        logger.info(
            "llm_request provider=%s model=%s success=%s "
            "in=%s out=%s total=%s duration_ms=%.1f retries=%d err=%s req=%s",
            record.provider,
            record.model,
            record.success,
            record.input_tokens,
            record.output_tokens,
            record.total_tokens,
            record.duration_ms,
            record.retry_count,
            record.error_category,
            record.request_id,
        )


class InMemoryTelemetrySink:
    """Test sink: keeps records in memory for assertions."""

    def __init__(self) -> None:
        self.records: list[LLMTelemetryRecord] = []

    def record(self, record: LLMTelemetryRecord) -> None:
        self.records.append(record)


async def observe(
    provider: LLMProvider,
    request: LLMRequest,
    sink: TelemetrySink | None = None,
) -> LLMResponse:
    """Run ``provider.generate`` and record provider-independent telemetry."""
    active = sink if sink is not None else LoggingTelemetrySink()
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        response = await provider.generate(request)
    except LLMError as exc:
        active.record(
            LLMTelemetryRecord(
                request_id=request.request_id,
                provider=exc.provider or getattr(provider, "provider_name", "unknown"),
                model=exc.model or getattr(provider, "model", "unknown"),
                started_at=started,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                success=False,
                error_category=exc.category.value,
                retry_count=exc.retry_count,
                cost_usd=None,
            )
        )
        raise
    except Exception:
        active.record(
            LLMTelemetryRecord(
                request_id=request.request_id,
                provider=getattr(provider, "provider_name", "unknown"),
                model=getattr(provider, "model", "unknown"),
                started_at=started,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                success=False,
                error_category=LLMErrorCategory.UNKNOWN.value,
                retry_count=0,
                cost_usd=None,
            )
        )
        raise
    active.record(
        LLMTelemetryRecord(
            request_id=request.request_id,
            provider=response.provider,
            model=response.model,
            started_at=started,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
            success=True,
            error_category=None,
            retry_count=response.retry_count,
            cost_usd=None,
        )
    )
    return response
