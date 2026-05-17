from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_post_requires_token() -> None:
    response = client.post("/api/metrics", json={"host": "pc"})
    assert response.status_code == 401


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
                "topProcesses": [{"name": "browser.exe", "pid": 100, "rssBytes": 512, "usagePercent": 25.0}],
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["host"] == "pc"
    assert body["latest"]["cpu"]["usagePercent"] == 42.5
    assert body["latest"]["memory"]["topProcesses"][0]["name"] == "browser.exe"


def test_post_rejects_invalid_payload() -> None:
    response = client.post(
        "/api/metrics",
        headers={"Authorization": "Bearer change-me"},
        json={"host": "pc", "cpu": {"usagePercent": 101}},
    )
    assert response.status_code == 422
