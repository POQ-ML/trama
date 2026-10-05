"""Health check da API TRAMA (nível integração).

Exige a stack local no ar (`docker compose up`). Pula se indisponível.
"""

import httpx
import pytest


def test_api_health():
    try:
        resp = httpx.get("http://localhost:8000/api/v1/health", timeout=5)
    except httpx.ConnectError:
        pytest.skip("stack local indisponível (docker compose up)")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
