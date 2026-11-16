from fastapi.testclient import TestClient

from app.main import app


def test_health_responds() -> None:
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] in {"ok", "degraded"}
    assert "database" in r.json()


def test_openapi_docs_available() -> None:
    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    assert "/health" in client.get("/openapi.json").json()["paths"]
