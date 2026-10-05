from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_v1_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "trama-api"
    assert "database" in body
