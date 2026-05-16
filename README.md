# Sidecar Deck

Lightweight kiosk dashboard for a `1920x480` ultrawide sidecar display. The homelab server runs the FastAPI backend and serves the built React frontend. The Raspberry Pi only opens the dashboard URL in Chromium kiosk mode.

## Run With Docker

```bash
cp backend/.env.example backend/.env
docker compose --env-file backend/.env up --build
```

Open:

```text
http://homelab.local:8080
```

The app runs in demo mode by default, so the dashboard shows changing fake metrics before a real PC agent is connected.

## API

Health:

```bash
curl http://localhost:8080/health
```

Push real metrics:

```bash
curl -X POST http://localhost:8080/api/metrics \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "gaming-pc",
    "timestamp": "2026-05-15T19:30:00Z",
    "cpu": {"usagePercent": 42.5, "temperatureC": 61.2},
    "memory": {"usagePercent": 68.1, "usedBytes": 21904333209, "totalBytes": 34359738368},
    "gpu": {"name": "NVIDIA GeForce RTX 4070", "usagePercent": 76.4, "temperatureC": 67.8, "memoryUsedBytes": 8147483648, "memoryTotalBytes": 12884901888},
    "network": {"rxBytesPerSecond": 1200000, "txBytesPerSecond": 350000}
  }'
```

Live dashboard clients connect to:

```text
ws://<server>:8080/ws
```

## Windows PC Agent

The first agent is a Python host process so it can access local Windows metrics. It uses `psutil` for CPU, RAM, network, disk, uptime, and hostname. Temperature/GPU fields are optional and can be added through LibreHardwareMonitor, OpenHardwareMonitor, or vendor tooling without changing the backend API.

```powershell
cd agent
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
python pc_agent.py
```

Required agent environment:

```env
DASHBOARD_BASE_URL=http://homelab.local:8080
METRICS_TOKEN=change-me
PUSH_INTERVAL_SECONDS=1
HOSTNAME=gaming-pc
```

## Raspberry Pi Kiosk

Example Chromium launch:

```bash
chromium-browser --kiosk http://homelab.local:8080
```

The UI is designed first for `1920x480` with no normal-operation scrolling. Wider or normal desktop browser sizes get a simple responsive fallback for testing.

For full Raspberry Pi preparation steps, see [docs/raspberry-pi-kiosk.md](docs/raspberry-pi-kiosk.md).

## Local Development

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8080
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run dev
npm run build
```
