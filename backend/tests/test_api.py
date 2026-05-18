from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_read_endpoints_use_expected_content_types() -> None:
    expected_content_types = {
        "/api/metrics/latest": "application/json",
        "/api/metrics/history": "application/json",
        "/openapi.json": "application/json",
        "/docs": "text/html; charset=utf-8",
    }

    for path, content_type in expected_content_types.items():
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"] == content_type


def test_post_requires_token() -> None:
    response = client.post("/api/metrics", json={"host": "pc"})
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/json"


def test_post_accepts_valid_payload() -> None:
    response = client.post(
        "/api/metrics",
        headers={"Authorization": "Bearer change-me"},
        json={
            "host": "pc",
            "timestamp": "2026-05-15T19:30:00Z",
            "cpu": {"usagePercent": 42.5, "temperatureC": 61.2},
            "memory": {
                "usagePercent": 68.1,
                "usedBytes": 1024,
                "totalBytes": 2048,
                "topProcesses": [{"name": "browser", "pids": [100, 101], "processCount": 2, "rssBytes": 512, "usagePercent": 25.0}],
            },
            "peripheralBatteries": [{"id": "keyboard", "name": "G915 X", "batteryPercent": 45, "charging": False, "source": "logitech"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["host"] == "pc"
    assert body["latest"]["cpu"]["usagePercent"] == 42.5
    assert body["latest"]["memory"]["topProcesses"][0]["name"] == "browser"
    assert body["latest"]["memory"]["topProcesses"][0]["pids"] == [100, 101]
    assert body["latest"]["memory"]["topProcesses"][0]["processCount"] == 2
    assert body["latest"]["peripheralBatteries"][0]["batteryPercent"] == 45
    assert body["latest"]["peripheralBatteries"][0]["source"] == "logitech"


def test_post_rejects_invalid_payload() -> None:
    response = client.post(
        "/api/metrics",
        headers={"Authorization": "Bearer change-me"},
        json={"host": "pc", "cpu": {"usagePercent": 101}},
    )
    assert response.status_code == 422
