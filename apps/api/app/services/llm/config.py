"""LLM configuration (env-driven) and provider factory.

Environment variables (consistent with ``app.core.config.Settings``)::

    LLM_PROVIDER=gemini
    LLM_MODEL=gemini-3.5-flash-lite
    GEMINI_API_KEY=
    LLM_TIMEOUT_SECONDS=30
    LLM_MAX_RETRIES=2
    LLM_MAX_OUTPUT_TOKENS=1024
    LLM_TELEMETRY_ENABLED=true

Notes:
  - Default model ``gemini-3.5-flash-lite`` verified against the official
    model list (https://ai.google.dev/gemini-api/docs/models, updated
    2026-10-13): recommended for new projects, fastest/most cost-effective.
    ``gemini-3.8-flash`` is the documented more-intelligent Flash
    alternative; any stable Flash endpoint stays configurable via
    ``LLM_MODEL`` because ADR-0005 only names "Flash / Flash-Lite"
    generically.
  - Startup never breaks when the key is absent: validation happens at the
    factory boundary (``create_provider`` / ``require_provider``), not at
    import time. Code paths that need the LLM get a clear, actionable
    ``LLMError`` instead of a silent fake success.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.services.llm.base import LLMError, LLMErrorCategory, LLMProvider

DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_PROVIDER = "gemini"


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None and value.strip() != "" else default
    except (ValueError, AttributeError):
        return default


def _parse_float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None and value.strip() != "" else default
    except (ValueError, AttributeError):
        return default


@dataclass(frozen=True)
class LLMConfig:
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    api_key: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 2
    max_output_tokens: int = 1024
    telemetry_enabled: bool = True

    @classmethod
    def from_env(cls, env: dict | None = None) -> "LLMConfig":
        src = env if env is not None else os.environ
        get = src.get if hasattr(src, "get") else os.environ.get
        raw_key = get("GEMINI_API_KEY", "") or ""
        return cls(
            provider=(get("LLM_PROVIDER", DEFAULT_PROVIDER) or DEFAULT_PROVIDER).strip().lower(),
            model=(get("LLM_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL).strip(),
            api_key=raw_key.strip() or None,
            timeout_seconds=_parse_float(get("LLM_TIMEOUT_SECONDS", "30"), 30.0),
            max_retries=_parse_int(get("LLM_MAX_RETRIES", "2"), 2),
            max_output_tokens=_parse_int(get("LLM_MAX_OUTPUT_TOKENS", "1024"), 1024),
            telemetry_enabled=_parse_bool(get("LLM_TELEMETRY_ENABLED", "true"), True),
        )


def create_provider(config: LLMConfig, **overrides) -> LLMProvider:
    """Build the configured provider, validating credentials at the boundary.

    Raises:
        LLMError: with category AUTH (missing key) or INVALID_REQUEST
            (unknown provider), carrying an actionable message.
    """
    provider = (config.provider or DEFAULT_PROVIDER).strip().lower()
    if provider == "gemini":
        if not config.api_key:
            raise LLMError(
                "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY in the "
                "environment (see .env.example) to use the Gemini provider.",
                category=LLMErrorCategory.AUTH,
                provider="gemini",
                model=config.model,
            )
        from app.services.llm.gemini import GeminiLLMProvider

        return GeminiLLMProvider(
            model=config.model,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            default_max_output_tokens=config.max_output_tokens,
            **overrides,
        )
    if provider == "fake":
        from app.services.llm.fake import FakeLLMProvider

        return FakeLLMProvider(model=config.model, **overrides)
    raise LLMError(
        f"Unknown LLM_PROVIDER '{config.provider}'. Expected 'gemini' (or 'fake' for tests).",
        category=LLMErrorCategory.INVALID_REQUEST,
        provider=config.provider,
        model=config.model,
    )


def require_provider(config: LLMConfig | None = None, **overrides) -> LLMProvider:
    """Convenience: ``create_provider(LLMConfig.from_env())``."""
    return create_provider(config or LLMConfig.from_env(), **overrides)
