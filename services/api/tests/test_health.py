from fastapi.testclient import TestClient

from services.api.app.main import app


def test_live_health_returns_request_id() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request"
    assert response.json() == {
        "status": "ok",
        "service": "api",
        "version": "0.1.0",
        "environment": "development",
        "request_id": "test-request",
    }
