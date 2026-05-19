from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from .models import CurrentWeather, ForecastDay, WeatherEnvelope


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


WEATHER_CODES = {
    0: "Clear",
    1: "Mostly Clear",
    2: "Partly Cloudy",
    3: "Cloudy",
    45: "Fog",
    48: "Rime Fog",
    51: "Light Drizzle",
    53: "Drizzle",
    55: "Heavy Drizzle",
    56: "Freezing Drizzle",
    57: "Freezing Drizzle",
    61: "Light Rain",
    63: "Rain",
    65: "Heavy Rain",
    66: "Freezing Rain",
    67: "Freezing Rain",
    71: "Light Snow",
    73: "Snow",
    75: "Heavy Snow",
    77: "Snow Grains",
    80: "Light Showers",
    81: "Showers",
    82: "Heavy Showers",
    85: "Snow Showers",
    86: "Snow Showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


def weather_condition(code: Any) -> str:
    if code is None:
        return "Unavailable"
    try:
        return WEATHER_CODES.get(int(code), "Unavailable")
    except (TypeError, ValueError):
        return "Unavailable"


def first_list_item(data: dict[str, list[Any]], key: str, index: int = 0) -> Any:
    values = data.get(key) or []
    return values[index] if index < len(values) else None


async def weather_for_location(location: str) -> WeatherEnvelope:
    clean_location = location.strip()
    if not clean_location:
        return WeatherEnvelope(status="unconfigured", updatedAt=datetime.now(timezone.utc))

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            geocode_response = await client.get(
                GEOCODING_URL,
                params={"name": clean_location, "count": 1, "language": "en", "format": "json"},
            )
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()
            result = (geocode_data.get("results") or [None])[0]
            if not result:
                return WeatherEnvelope(status="not_found", locationLabel=clean_location, updatedAt=datetime.now(timezone.utc))

            forecast_response = await client.get(
                FORECAST_URL,
                params={
                    "latitude": result["latitude"],
                    "longitude": result["longitude"],
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "forecast_days": 5,
                    "timezone": "auto",
                },
            )
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="weather service unavailable") from exc

    location_label = ", ".join(
        part
        for part in [
            result.get("name"),
            result.get("admin1"),
            result.get("country_code"),
        ]
        if part
    )
    current_data = forecast_data.get("current") or {}
    daily_data = forecast_data.get("daily") or {}
    weather_code = current_data.get("weather_code")

    forecast = []
    for index, date in enumerate(daily_data.get("time") or []):
        day_code = first_list_item(daily_data, "weather_code", index)
        forecast.append(
            ForecastDay(
                date=date,
                condition=weather_condition(day_code),
                weatherCode=day_code,
                temperatureMinC=first_list_item(daily_data, "temperature_2m_min", index),
                temperatureMaxC=first_list_item(daily_data, "temperature_2m_max", index),
                precipitationChancePercent=first_list_item(daily_data, "precipitation_probability_max", index),
            )
        )

    return WeatherEnvelope(
        status="ok",
        locationLabel=location_label or clean_location,
        updatedAt=datetime.now(timezone.utc),
        current=CurrentWeather(
            temperatureC=current_data.get("temperature_2m"),
            apparentTemperatureC=current_data.get("apparent_temperature"),
            weatherCode=weather_code,
            condition=weather_condition(weather_code),
            windKph=current_data.get("wind_speed_10m"),
        ),
        forecast=forecast,
    )
