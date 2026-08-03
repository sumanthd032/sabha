"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from sabha.main import APP_VERSION, app

client = TestClient(app)


def test_health_reports_ok_status() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_build_metadata() -> None:
    body = client.get("/api/health").json()
    assert body["version"] == APP_VERSION
    assert isinstance(body["commit"], str) and body["commit"] != ""
    assert isinstance(body["started_at"], str) and body["started_at"] != ""
