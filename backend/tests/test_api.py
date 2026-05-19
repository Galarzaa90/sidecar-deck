from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.models import CurrentWeather, ForecastDay, WeatherEnvelope


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
        "/api/weather": "application/json",
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


def test_weather_unconfigured() -> None:
    response = client.get("/api/weather")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unconfigured"
    assert body["locationLabel"] is None
    assert body["current"] is None
    assert body["forecast"] == []


def test_weather_uses_configured_location(monkeypatch) -> None:
    async def fake_weather_for_location(location: str) -> WeatherEnvelope:
        assert location == "Tucson, AZ"
        return WeatherEnvelope(
            status="ok",
            locationLabel="Tucson, Arizona, US",
            updatedAt="2026-05-18T20:00:00Z",
            current=CurrentWeather(temperatureC=32.1, apparentTemperatureC=31.5, weatherCode=0, condition="Clear", windKph=9.2),
            forecast=[
                ForecastDay(
                    date="2026-05-18",
                    condition="Clear",
                    weatherCode=0,
                    temperatureMinC=20.0,
                    temperatureMaxC=34.0,
                    precipitationChancePercent=0,
                )
            ],
        )

    app.dependency_overrides[get_settings] = lambda: Settings(WEATHER_LOCATION="Tucson, AZ")
    monkeypatch.setattr("app.main.weather_for_location", fake_weather_for_location)
    try:
        response = client.get("/api/weather")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["locationLabel"] == "Tucson, Arizona, US"
    assert body["current"]["condition"] == "Clear"
    assert body["forecast"][0]["temperatureMaxC"] == 34.0
