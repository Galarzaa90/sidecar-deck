# Sidecar Deck Backend

FastAPI service for ingesting real metrics, tracking recent history, serving health checks, and streaming live dashboard updates over WebSocket. It does not generate placeholder data.

## Local Setup

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8080
```

On Windows PowerShell:

```powershell
copy .env.example .env
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8080
```

## Environment

```env
APP_PORT=8080
METRICS_TOKEN=change-me
METRICS_STALE_SECONDS=5
METRICS_OFFLINE_SECONDS=15
HISTORY_SECONDS=600
WEATHER_LOCATION=City, Region
```

`METRICS_TOKEN` must match the token used by the agent.
`WEATHER_LOCATION` is optional. When set, the standby dashboard uses it to show current weather and a 5 day forecast.

## API

```bash
curl http://localhost:8080/health
curl http://localhost:8080/api/metrics/latest
curl http://localhost:8080/api/metrics/history
curl http://localhost:8080/api/weather
```

Push metrics:

```bash
curl -X POST http://localhost:8080/api/metrics \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"host":"gaming-pc","timestamp":"2026-05-15T19:30:00Z","cpu":{"usagePercent":42.5},"memory":{"usagePercent":68.1},"network":{"rxBytesPerSecond":1200000,"txBytesPerSecond":350000}}'
```

WebSocket clients connect to:

```text
ws://localhost:8080/ws
```

## Tests

```bash
pytest
```

## Docker

From the repository root:

```bash
docker build -t sidecar-deck-backend -f backend/Dockerfile .
docker run --rm -p 8080:8080 --env-file backend/.env sidecar-deck-backend
```
