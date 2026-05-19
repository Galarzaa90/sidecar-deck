from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from .models import CurrentWeather, ForecastDay, WeatherEnvelope


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


COUNTRY_HINTS = {
    "mexico": "MX",
    "mx": "MX",
    "united states": "US",
    "usa": "US",
    "us": "US",
}

US_STATE_HINTS = {
    "alabama": "Alabama",
    "al": "Alabama",
    "alaska": "Alaska",
    "ak": "Alaska",
    "arizona": "Arizona",
    "az": "Arizona",
    "arkansas": "Arkansas",
    "ar": "Arkansas",
    "california": "California",
    "ca": "California",
    "colorado": "Colorado",
    "co": "Colorado",
    "connecticut": "Connecticut",
    "ct": "Connecticut",
    "delaware": "Delaware",
    "de": "Delaware",
    "florida": "Florida",
    "fl": "Florida",
    "georgia": "Georgia",
    "ga": "Georgia",
    "hawaii": "Hawaii",
    "hi": "Hawaii",
    "idaho": "Idaho",
    "id": "Idaho",
    "illinois": "Illinois",
    "il": "Illinois",
    "indiana": "Indiana",
    "in": "Indiana",
    "iowa": "Iowa",
    "ia": "Iowa",
    "kansas": "Kansas",
    "ks": "Kansas",
    "kentucky": "Kentucky",
    "ky": "Kentucky",
    "louisiana": "Louisiana",
    "la": "Louisiana",
    "maine": "Maine",
    "me": "Maine",
    "maryland": "Maryland",
    "md": "Maryland",
    "massachusetts": "Massachusetts",
    "ma": "Massachusetts",
    "michigan": "Michigan",
    "mi": "Michigan",
    "minnesota": "Minnesota",
    "mn": "Minnesota",
    "mississippi": "Mississippi",
    "ms": "Mississippi",
    "missouri": "Missouri",
    "mo": "Missouri",
    "montana": "Montana",
    "mt": "Montana",
    "nebraska": "Nebraska",
    "ne": "Nebraska",
    "nevada": "Nevada",
    "nv": "Nevada",
    "new hampshire": "New Hampshire",
    "nh": "New Hampshire",
    "new jersey": "New Jersey",
    "nj": "New Jersey",
    "new mexico": "New Mexico",
    "nm": "New Mexico",
    "new york": "New York",
    "ny": "New York",
    "north carolina": "North Carolina",
    "nc": "North Carolina",
    "north dakota": "North Dakota",
    "nd": "North Dakota",
    "ohio": "Ohio",
    "oh": "Ohio",
    "oklahoma": "Oklahoma",
    "ok": "Oklahoma",
    "oregon": "Oregon",
    "or": "Oregon",
    "pennsylvania": "Pennsylvania",
    "pa": "Pennsylvania",
    "rhode island": "Rhode Island",
    "ri": "Rhode Island",
    "south carolina": "South Carolina",
    "sc": "South Carolina",
    "south dakota": "South Dakota",
    "sd": "South Dakota",
    "tennessee": "Tennessee",
    "tn": "Tennessee",
    "texas": "Texas",
    "tx": "Texas",
    "utah": "Utah",
    "ut": "Utah",
    "vermont": "Vermont",
    "vt": "Vermont",
    "virginia": "Virginia",
    "va": "Virginia",
    "washington": "Washington",
    "wa": "Washington",
    "west virginia": "West Virginia",
    "wv": "West Virginia",
    "wisconsin": "Wisconsin",
    "wi": "Wisconsin",
    "wyoming": "Wyoming",
    "wy": "Wyoming",
}


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


def normalize_hint(value: str) -> str:
    return " ".join(value.strip().lower().replace(".", "").split())


def location_searches(location: str) -> list[tuple[str, list[str]]]:
    clean_location = " ".join(location.replace(",", " , ").split()).replace(" ,", ",")
    searches: list[tuple[str, list[str]]] = [(clean_location, [])]

    comma_parts = [part.strip() for part in clean_location.split(",") if part.strip()]
    if len(comma_parts) > 1:
        searches.append((comma_parts[0], comma_parts[1:]))

    words = clean_location.replace(",", " ").split()
    for split_index in range(len(words) - 1, 0, -1):
        searches.append((" ".join(words[:split_index]), [" ".join(words[split_index:])]))

    unique_searches: list[tuple[str, list[str]]] = []
    seen = set()
    for name, hints in searches:
        normalized = (normalize_hint(name), tuple(normalize_hint(hint) for hint in hints))
        if name and normalized not in seen:
            unique_searches.append((name, hints))
            seen.add(normalized)
    return unique_searches


def score_geocode_result(result: dict[str, Any], hints: list[str]) -> int:
    score = 0
    admin = normalize_hint(str(result.get("admin1") or ""))
    country_code = normalize_hint(str(result.get("country_code") or ""))

    for hint in hints:
        normalized_hint = normalize_hint(hint)
        if not normalized_hint:
            continue

        country_hint = COUNTRY_HINTS.get(normalized_hint)
        state_hint = US_STATE_HINTS.get(normalized_hint)
        if country_hint and country_code == normalize_hint(country_hint):
            score += 4
        if state_hint and admin == normalize_hint(state_hint):
            score += 5
        if admin == normalized_hint:
            score += 5
        elif normalized_hint in admin or admin in normalized_hint:
            score += 2

    return score


def select_geocode_result(results: list[dict[str, Any]], hints: list[str]) -> dict[str, Any] | None:
    if not results:
        return None
    return max(results, key=lambda result: score_geocode_result(result, hints))


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
            result = None
            for search_name, hints in location_searches(clean_location):
                geocode_response = await client.get(
                    GEOCODING_URL,
                    params={"name": search_name, "count": 10, "language": "en", "format": "json"},
                )
                geocode_response.raise_for_status()
                geocode_data = geocode_response.json()
                result = select_geocode_result(geocode_data.get("results") or [], hints)
                if result:
                    break

            if result is None:
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
