"""Gemini adapter implementing :class:`LLMProvider` via ``google-genai``.

Official sources of truth:
  - SDK + text generation: https://ai.google.dev/gemini-api/docs/text-generation
  - Models (verified 2026-10-13): https://ai.google.dev/gemini-api/docs/models
    (new projects → ``gemini-3.5-flash-lite`` or ``gemini-3.8-flash``;
    2.5 endpoints restricted to past users; 2.0 shut down).
  - Rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
    (RPM/TPM/RPD per project; RPD resets midnight Pacific; 429 on breach).

Implementation choices:
  - Uses the stable ``client.aio.models.generate_content`` path (async,
    first-class usage_metadata) instead of the newer Interactions API to
    keep mocks deterministic and the dependency surface minimal.
  - ``temperature``/``top_p``/``top_k`` are intentionally NOT sent: Gemini
    3.6+ models ignore them (deprecation warnings).
  - Bounded retries (default 2) only for transient/timeout/RPM-rate-limit.
    Never retries AUTH, INVALID_REQUEST, QUOTA_EXHAUSTED, EMPTY_RESPONSE.
  - Free-tier note: do not assume limits are constant; backoff is bounded
    to avoid wasting quota (see docs/llm-provider.md).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable

from app.services.llm.base import (
    LLMError,
    LLMErrorCategory,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)

_QUOTA_HINTS = (
    "quota",
    "daily",
    "per day",
    "rpd",
    "tpd",
    "exhausted",
    "limit: 0",
    "free tier",
)


def _safe_message(category: LLMErrorCategory, detail: str = "") -> str:
    base = {
        LLMErrorCategory.AUTH: "Gemini authentication failed. Check GEMINI_API_KEY and key permissions.",
        LLMErrorCategory.INVALID_REQUEST: "Gemini rejected the request as invalid. Check model name and parameters.",
        LLMErrorCategory.RATE_LIMIT: "Gemini rate limit reached. Retry after a short backoff.",
        LLMErrorCategory.QUOTA_EXHAUSTED: "Gemini quota exhausted (e.g. free-tier daily limit). Will not retry; try later or switch project/billing.",
        LLMErrorCategory.TIMEOUT: "Gemini request timed out.",
        LLMErrorCategory.TRANSIENT: "Gemini transient error. Retried within configured bounds.",
        LLMErrorCategory.EMPTY_RESPONSE: "Gemini returned no text content.",
        LLMErrorCategory.UNKNOWN: "Gemini request failed.",
    }[category]
    return f"{base} {detail}".strip()


def classify_exception(exc: BaseException) -> tuple[LLMErrorCategory, bool]:
    """Map an SDK/transport exception to (category, retryable)."""
    name = type(exc).__name__
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "Timeout" in name:
        return LLMErrorCategory.TIMEOUT, True
    code = getattr(exc, "code", None)
    status = str(getattr(exc, "status", "") or "").upper()
    msg = str(getattr(exc, "message", "") or str(exc) or "").lower()
    if code in (401, 403) or status in ("UNAUTHENTICATED", "PERMISSION_DENIED"):
        return LLMErrorCategory.AUTH, False
    if code in (400, 404, 422) or status in (
        "INVALID_ARGUMENT",
        "NOT_FOUND",
        "FAILED_PRECONDITION",
    ):
        return LLMErrorCategory.INVALID_REQUEST, False
    if code == 429 or status == "RESOURCE_EXHAUSTED" or "429" in msg or "resource_exhausted" in msg:
        if any(h in msg for h in _QUOTA_HINTS):
            return LLMErrorCategory.QUOTA_EXHAUSTED, False
        return LLMErrorCategory.RATE_LIMIT, True
    if code in (500, 502, 503, 504) or status in (
        "INTERNAL",
        "UNAVAILABLE",
        "DEADLINE_EXCEEDED",
        "UNKNOWN",
    ):
        return LLMErrorCategory.TRANSIENT, True
    if "ClientError" in name or "client_error" in msg:
        return LLMErrorCategory.INVALID_REQUEST, False
    return LLMErrorCategory.UNKNOWN, False


def extract_usage(response: Any) -> LLMUsage:
    """Pull token counts when available; ``None`` when absent (never invented)."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return LLMUsage()
    def _as_int(value: Any) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None
    return LLMUsage(
        input_tokens=_as_int(getattr(meta, "prompt_token_count", None)),
        output_tokens=_as_int(getattr(meta, "candidates_token_count", None)),
        total_tokens=_as_int(getattr(meta, "total_token_count", None)),
    )


def extract_text(response: Any) -> str | None:
    """Best-effort text extraction; ``None`` when missing/empty."""
    try:
        text = getattr(response, "text", None)
    except Exception:
        return None
    if isinstance(text, str) and text.strip():
        return text
    # Fallback: walk candidates -> content -> parts (SDK shape varies).
    try:
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                chunk = getattr(part, "text", None)
                if isinstance(chunk, str) and chunk.strip():
                    return chunk
    except Exception:
        return None
    return None


class GeminiLLMProvider(LLMProvider):
    """Async Gemini Flash adapter behind the provider-independent contract."""

    provider_name = "gemini"

    def __init__(
        self,
        model: str = "gemini-3.5-flash-lite",
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        default_max_output_tokens: int = 1024,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not api_key:
            raise LLMError(
                _safe_message(LLMErrorCategory.AUTH)
                + " Set GEMINI_API_KEY in the environment.",
                category=LLMErrorCategory.AUTH,
                provider=self.provider_name,
                model=model,
            )
        self.model = model
        self._api_key = api_key
        self._timeout = float(timeout_seconds)
        self._max_retries = max(0, int(max_retries))
        self._default_max_tokens = int(default_max_output_tokens)
        self._client_factory = client_factory
        self._client: Any | None = None

    # -- internals ------------------------------------------------------
    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory(api_key=self._api_key)
            return self._client
        try:
            from google import genai  # lazy: keeps import-time dep-free
        except ImportError as exc:
            raise LLMError(
                "google-genai SDK is not installed. Run: pip install google-genai.",
                category=LLMErrorCategory.UNKNOWN,
                provider=self.provider_name,
                model=self.model,
            ) from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _build_config(self, request: LLMRequest) -> Any:
        try:
            from google.genai import types
        except ImportError as exc:
            raise LLMError(
                "google-genai SDK is not installed. Run: pip install google-genai.",
                category=LLMErrorCategory.UNKNOWN,
                provider=self.provider_name,
                model=self.model,
            ) from exc
        kwargs: dict[str, Any] = {
            "max_output_tokens": request.max_output_tokens or self._default_max_tokens,
        }
        if request.system_instruction:
            kwargs["system_instruction"] = request.system_instruction
        if request.response_mime_type:
            kwargs["response_mime_type"] = request.response_mime_type
        if request.response_json_schema:
            kwargs["response_json_schema"] = request.response_json_schema
        return types.GenerateContentConfig(**kwargs)

    async def _call_once(self, request: LLMRequest) -> Any:
        client = self._get_client()
        config = self._build_config(request)
        aio_models = client.aio.models
        return await asyncio.wait_for(
            aio_models.generate_content(
                model=self.model,
                contents=request.user_input,
                config=config,
            ),
            timeout=self._timeout,
        )

    # -- public ---------------------------------------------------------
    async def generate(self, request: LLMRequest) -> LLMResponse:
        attempts = 0
        last_error: LLMError | None = None
        while attempts <= self._max_retries:
            try:
                raw = await self._call_once(request)
            except LLMError:
                raise
            except asyncio.CancelledError:
                # Preserve task cancellation so outer run/explainer deadlines
                # can become TimeoutError instead of an UNKNOWN provider error.
                raise
            except BaseException as exc:  # SDK/transport errors → normalized
                category, retryable = classify_exception(exc)
                last_error = LLMError(
                    _safe_message(category),
                    category=category,
                    provider=self.provider_name,
                    model=self.model,
                    retry_count=attempts,
                )
                if not retryable or attempts >= self._max_retries:
                    raise last_error from None
                attempts += 1
                await asyncio.sleep(min(0.2 * (2 ** (attempts - 1)), 2.0))
                continue

            text = extract_text(raw)
            if not text:
                raise LLMError(
                    _safe_message(LLMErrorCategory.EMPTY_RESPONSE),
                    category=LLMErrorCategory.EMPTY_RESPONSE,
                    provider=self.provider_name,
                    model=self.model,
                    retry_count=attempts,
                )
            return LLMResponse(
                text=text,
                provider=self.provider_name,
                model=self.model,
                usage=extract_usage(raw),
                request_id=request.request_id or uuid.uuid4().hex,
                retry_count=attempts,
            )
        # Unreachable in practice; guards against loop-exit without result.
        raise last_error or LLMError(
            _safe_message(LLMErrorCategory.UNKNOWN),
            category=LLMErrorCategory.UNKNOWN,
            provider=self.provider_name,
            model=self.model,
            retry_count=attempts,
        )
