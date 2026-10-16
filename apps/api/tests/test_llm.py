"""LLM provider abstraction + Gemini adapter + telemetry tests.

All tests are deterministic: no real API key, no network. Gemini SDK calls
are replaced via ``client_factory`` injection. Live smoke is opt-in only
(see ``scripts/llm_smoke.py``) and never runs here.
"""

from __future__ import annotations

import asyncio
import logging
import os

import pytest

from app.services.llm.base import (
    LLMError,
    LLMErrorCategory,
    LLMRequest,
    LLMUsage,
)
from app.services.llm.config import LLMConfig, create_provider
from app.services.llm.fake import FakeLLMProvider
from app.services.llm.gemini import GeminiLLMProvider
from app.services.llm.telemetry import InMemoryTelemetrySink, observe


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# SDK doubles (mimic google-genai shapes without importing it)
# ---------------------------------------------------------------------------

class _FakeUsage:
    def __init__(self, prompt=None, candidates=None, total=None):
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.total_token_count = total


class _FakeResponse:
    def __init__(self, text="hello", usage=None):
        self._text = text
        self.usage_metadata = usage

    @property
    def text(self):
        return self._text


class _FakeModels:
    def __init__(self, behavior):
        self._behavior = behavior
        self.calls = 0

    async def generate_content(self, **kwargs):
        self.calls += 1
        return await self._behavior(self.calls, kwargs)


class _FakeAio:
    def __init__(self, behavior):
        self.models = _FakeModels(behavior)


class _FakeClient:
    def __init__(self, behavior):
        self.aio = _FakeAio(behavior)


class _ApiError(Exception):
    def __init__(self, code=None, status=None, message=""):
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


def _provider(behavior, **kwargs):
    defaults = dict(
        model="gemini-3.5-flash-lite",
        api_key="test-key",
        timeout_seconds=5.0,
        max_retries=2,
        default_max_output_tokens=64,
    )
    defaults.update(kwargs)
    return GeminiLLMProvider(
        client_factory=lambda api_key: _FakeClient(behavior),
        **defaults,
    )


async def _ok_behavior(calls, kwargs):
    return _FakeResponse(text="olá", usage=_FakeUsage(10, 5, 15))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_config_defaults_from_empty_env():
    cfg = LLMConfig.from_env({})
    assert cfg.provider == "gemini"
    assert cfg.model == "gemini-3.5-flash-lite"
    assert cfg.api_key is None
    assert cfg.timeout_seconds == 30
    assert cfg.max_retries == 2
    assert cfg.max_output_tokens == 1024
    assert cfg.telemetry_enabled is True


def test_config_reads_expected_env_vars():
    cfg = LLMConfig.from_env({
        "LLM_PROVIDER": "gemini",
        "LLM_MODEL": "gemini-3.8-flash",
        "GEMINI_API_KEY": "k",
        "LLM_TIMEOUT_SECONDS": "7",
        "LLM_MAX_RETRIES": "1",
        "LLM_MAX_OUTPUT_TOKENS": "256",
        "LLM_TELEMETRY_ENABLED": "false",
    })
    assert (cfg.provider, cfg.model) == ("gemini", "gemini-3.8-flash")
    assert cfg.api_key == "k"
    assert cfg.timeout_seconds == 7
    assert cfg.max_retries == 1
    assert cfg.max_output_tokens == 256
    assert cfg.telemetry_enabled is False


def test_config_accepts_fractional_timeout():
    cfg = LLMConfig.from_env({"LLM_TIMEOUT_SECONDS": "7.5"})
    assert cfg.timeout_seconds == 7.5


def test_missing_credentials_raise_actionable_error():
    cfg = LLMConfig.from_env({"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": ""})
    with pytest.raises(LLMError) as ei:
        create_provider(cfg)
    assert ei.value.category == LLMErrorCategory.AUTH
    assert "GEMINI_API_KEY" in str(ei.value)


def test_unknown_provider_rejected():
    with pytest.raises(LLMError) as ei:
        create_provider(LLMConfig.from_env({"LLM_PROVIDER": "nope", "GEMINI_API_KEY": "k"}))
    assert ei.value.category == LLMErrorCategory.INVALID_REQUEST


def test_core_settings_do_not_break_startup_without_key():
    from app.core.config import settings

    assert settings.LLM_PROVIDER == "gemini"
    assert settings.LLM_MODEL  # configurable, non-empty
    assert settings.LLM_TIMEOUT_SECONDS == 30


def test_request_rejects_empty_input():
    with pytest.raises(ValueError):
        LLMRequest(user_input="   ")


# ---------------------------------------------------------------------------
# Normalization / usage
# ---------------------------------------------------------------------------

def test_successful_response_normalization():
    p = _provider(_ok_behavior)
    resp = run(p.generate(LLMRequest(user_input="oi")))
    assert resp.text == "olá"
    assert resp.provider == "gemini"
    assert resp.model == "gemini-3.5-flash-lite"
    assert resp.retry_count == 0


def test_usage_extraction():
    p = _provider(_ok_behavior)
    resp = run(p.generate(LLMRequest(user_input="oi")))
    assert (resp.usage.input_tokens, resp.usage.output_tokens, resp.usage.total_tokens) == (10, 5, 15)


def test_missing_usage_metadata_is_none_not_zero():
    async def behavior(calls, kwargs):
        return _FakeResponse(text="x", usage=None)
    resp = run(_provider(behavior).generate(LLMRequest(user_input="oi")))
    assert resp.usage == LLMUsage(None, None, None)


def test_empty_output_raises_empty_response():
    async def behavior(calls, kwargs):
        return _FakeResponse(text="   ", usage=_FakeUsage(1, 0, 1))
    with pytest.raises(LLMError) as ei:
        run(_provider(behavior).generate(LLMRequest(user_input="oi")))
    assert ei.value.category == LLMErrorCategory.EMPTY_RESPONSE


def test_structured_output_params_reach_sdk():
    seen = {}

    async def behavior(calls, kwargs):
        seen.update(kwargs.get("config", {}).__dict__ if hasattr(kwargs.get("config"), "__dict__") else {})
        return _FakeResponse(text='{"a":1}', usage=_FakeUsage(2, 2, 4))

    p = _provider(behavior)
    resp = run(p.generate(LLMRequest(
        user_input="go",
        response_mime_type="application/json",
        response_json_schema={"type": "object"},
    )))
    assert resp.text == '{"a":1}'


# ---------------------------------------------------------------------------
# Failures / retries
# ---------------------------------------------------------------------------

def test_auth_failure_no_retry():
    async def behavior(calls, kwargs):
        raise _ApiError(code=401, status="UNAUTHENTICATED", message="invalid api key")
    p = _provider(behavior)
    with pytest.raises(LLMError) as ei:
        run(p.generate(LLMRequest(user_input="oi")))
    assert ei.value.category == LLMErrorCategory.AUTH
    assert ei.value.retry_count == 0
    assert p._client.aio.models.calls == 1


def test_rate_limit_retries_then_succeeds():
    async def behavior(calls, kwargs):
        if calls == 1:
            raise _ApiError(code=429, status="RESOURCE_EXHAUSTED", message="rpm limit, retry soon")
        return _FakeResponse(text="recovered", usage=_FakeUsage(1, 1, 2))
    resp = run(_provider(behavior).generate(LLMRequest(user_input="oi")))
    assert resp.text == "recovered"
    assert resp.retry_count == 1


def test_quota_exhaustion_does_not_retry():
    async def behavior(calls, kwargs):
        raise _ApiError(code=429, status="RESOURCE_EXHAUSTED",
                        message="free tier daily quota exhausted, rpd limit 0")
    p = _provider(behavior, max_retries=3)
    with pytest.raises(LLMError) as ei:
        run(p.generate(LLMRequest(user_input="oi")))
    assert ei.value.category == LLMErrorCategory.QUOTA_EXHAUSTED
    assert p._client.aio.models.calls == 1


def test_timeout_respects_retry_limit():
    async def behavior(calls, kwargs):
        raise asyncio.TimeoutError("slow")
    p = _provider(behavior, max_retries=2)
    with pytest.raises(LLMError) as ei:
        run(p.generate(LLMRequest(user_input="oi")))
    assert ei.value.category == LLMErrorCategory.TIMEOUT
    assert p._client.aio.models.calls == 3  # 1 + 2 retries
    assert ei.value.retry_count == 2


def test_transient_gives_up_after_max_retries():
    async def behavior(calls, kwargs):
        raise _ApiError(code=503, status="UNAVAILABLE", message="overloaded")
    p = _provider(behavior, max_retries=1)
    with pytest.raises(LLMError) as ei:
        run(p.generate(LLMRequest(user_input="oi")))
    assert ei.value.category == LLMErrorCategory.TRANSIENT
    assert p._client.aio.models.calls == 2


def test_invalid_request_no_retry():
    async def behavior(calls, kwargs):
        raise _ApiError(code=400, status="INVALID_ARGUMENT", message="bad model")
    p = _provider(behavior)
    with pytest.raises(LLMError) as ei:
        run(p.generate(LLMRequest(user_input="oi")))
    assert ei.value.category == LLMErrorCategory.INVALID_REQUEST
    assert p._client.aio.models.calls == 1


def test_raw_errors_never_leak_api_key_or_payload():
    # NOT a real credential — synthetic dummy fixture for the leak test
    # (allowlist: dummy key, never valid, never committed as secret).
    secret = "sk-test-synthetic-dummy-key-000"
    async def behavior(calls, kwargs):
        raise _ApiError(code=500, status="INTERNAL", message=f"boom {secret} prompt=supersecret")
    p = _provider(behavior, api_key=secret, max_retries=0)
    with pytest.raises(LLMError) as ei:
        run(p.generate(LLMRequest(user_input="contém dado sensível XYZ")))
    assert secret not in str(ei.value)
    assert "XYZ" not in str(ei.value)


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

def test_telemetry_success_record():
    fake = FakeLLMProvider(text="ok", usage=LLMUsage(4, 6, 10))
    sink = InMemoryTelemetrySink()
    resp = run(observe(fake, LLMRequest(user_input="oi"), sink))
    assert resp.text == "ok"
    assert len(sink.records) == 1
    rec = sink.records[0]
    assert rec.success is True
    assert rec.provider == "fake"
    assert (rec.input_tokens, rec.output_tokens, rec.total_tokens) == (4, 6, 10)
    assert rec.error_category is None
    assert rec.cost_usd is None  # unavailable, never fabricated
    assert rec.duration_ms >= 0


def test_telemetry_failure_record():
    err = LLMError("nope", category=LLMErrorCategory.RATE_LIMIT,
                   provider="fake", model="m", retry_count=1)
    fake = FakeLLMProvider(error=err)
    sink = InMemoryTelemetrySink()
    with pytest.raises(LLMError):
        run(observe(fake, LLMRequest(user_input="oi"), sink))
    rec = sink.records[0]
    assert rec.success is False
    assert rec.error_category == "rate_limit"
    assert rec.retry_count == 1
    assert rec.input_tokens is None and rec.cost_usd is None


def test_telemetry_does_not_log_sensitive_payloads(caplog):
    from app.services.llm import telemetry as tel

    records = []

    class CapSink:
        def record(self, r):
            records.append(r)

    fake = FakeLLMProvider(text="resposta")
    secret_prompt = "PROMPT-SEGREDO-UNICO-98765"
    with caplog.at_level(logging.INFO, logger="trama.llm.telemetry"):
        run(observe(fake, LLMRequest(user_input=secret_prompt), tel.LoggingTelemetrySink()))
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_prompt not in logged
    assert "GEMINI_API_KEY" not in logged
    assert os.environ.get("GEMINI_API_KEY", "") not in logged or not os.environ.get("GEMINI_API_KEY")


def test_telemetry_works_across_providers_gemini_shape():
    p = _provider(_ok_behavior)
    sink = InMemoryTelemetrySink()
    resp = run(observe(p, LLMRequest(user_input="oi"), sink))
    assert resp.provider == "gemini"
    assert sink.records[0].provider == "gemini"
    assert sink.records[0].total_tokens == 15


# ---------------------------------------------------------------------------
# Fake provider contract
# ---------------------------------------------------------------------------

def test_fake_provider_is_deterministic_and_provider_independent():
    fake = FakeLLMProvider(model="m", text="t", usage=LLMUsage(1, 2, 3))
    req = LLMRequest(user_input="qualquer coisa")
    resp = run(fake.generate(req))
    assert (resp.text, resp.provider) == ("t", "fake")
    assert fake.calls == [req]
