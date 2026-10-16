"""Opt-in live Gemini smoke test (free tier, synthetic data only).

Usage:
    export GEMINI_API_KEY='<sua-chave>'   # nunca commitar
    export TRAMA_LLM_LIVE_TEST=1
    python scripts/llm_smoke.py

Sem TRAMA_LLM_LIVE_TEST=1: informa o skip e sai 0 (nunca roda por padrão,
nunca no CI). Usa apenas prompt sintético; não envia dado de terceiros
(o free tier pode usar o conteúdo para melhoria — ADR-0005/REQ-0021).
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))


def main() -> int:
    if os.environ.get("TRAMA_LLM_LIVE_TEST") != "1":
        print("SKIP: TRAMA_LLM_LIVE_TEST != 1 (live smoke opt-in, pulado por padrão).")
        return 0
    if not os.environ.get("GEMINI_API_KEY"):
        print("SKIP: GEMINI_API_KEY ausente; nada a testar ao vivo.")
        return 0

    from app.services.llm.base import LLMRequest
    from app.services.llm.config import LLMConfig, create_provider
    from app.services.llm.telemetry import InMemoryTelemetrySink, observe

    async def run() -> int:
        cfg = LLMConfig.from_env()
        provider = create_provider(cfg)
        sink = InMemoryTelemetrySink()
        req = LLMRequest(
            user_input="Diga apenas: 'smoke ok'. (teste sintético, sem dados reais)",
            system_instruction="Responda de forma mínima.",
            max_output_tokens=32,
        )
        try:
            resp = await observe(provider, req, sink)
        except Exception as exc:  # noqa: BLE001 - smoke: relata e sai nonzero
            print(f"LIVE FAIL: {type(exc).__name__}: {exc}")
            return 1
        rec = sink.records[-1]
        print(f"LIVE OK: provider={resp.provider} model={resp.model} "
              f"text={resp.text[:80]!r} in={rec.input_tokens} out={rec.output_tokens} "
              f"total={rec.total_tokens} latency_ms={rec.duration_ms:.0f} "
              f"retries={rec.retry_count} cost={rec.cost_usd}")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
