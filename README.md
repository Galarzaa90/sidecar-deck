# Sidecar Deck

Lightweight kiosk dashboard for a `1920x480` ultrawide sidecar display. The homelab server runs the backend API and dashboard frontend, while a Windows PC agent pushes live machine metrics. The Raspberry Pi only opens the dashboard URL in Chromium kiosk mode.

<img width="1270" height="360" alt="Sidecar Deck dashboard" src="https://github.com/user-attachments/assets/ca66d608-d94c-4d7a-a10e-d76822393365" />

## Project Layout

- [backend](backend/README.md): Python package for the FastAPI metrics server and optional Windows metrics agent.
- [frontend](frontend/README.md): React/Vite dashboard optimized for the sidecar display.
- [docs](docs): setup notes for Raspberry Pi kiosk mode and Windows agent startup.

## How It Fits Together

1. The backend exposes `/api/metrics`, `/api/metrics/latest`, `/api/metrics/history`, `/api/weather`, `/health`, and `/ws`.
2. The Windows agent reads local CPU, RAM, network, disk, uptime, hostname, temperature, and optional GPU data.
3. The agent posts metrics to the backend using a bearer token.
4. The frontend reads the latest state and listens on `/ws` so the kiosk display updates live.
5. The Raspberry Pi launches Chromium directly against the frontend URL.

The backend does not generate placeholder metrics. The dashboard stays in a waiting state until a real agent posts data.
When the agent is waiting or offline, the dashboard switches to standby mode with connection status, clock, and optional weather from `WEATHER_LOCATION`.

## Quick Start

Run the backend:

```bash
cd backend
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8080
```

Or install the default server package:

```bash
cd backend
pip install -e .
sidecar-deck-server
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the dashboard:

```text
http://localhost:5173
```

For host metrics from a Windows machine, install the optional agent from the [backend package](backend/README.md):

```powershell
.\SidecarDeckAgent.ps1 install -DashboardUrl http://homelab.local:8080 -MetricsToken change-me -Hostname gaming-pc
```

Use `SidecarDeckAgent.ps1 start`, `stop`, `restart`, `status`, `update`, and `uninstall` to manage the Windows background task.

## Docker Images

Build and run the backend image:

```bash
docker build -t sidecar-deck-backend -f backend/Dockerfile .
docker run --rm -p 8080:8080 --env-file backend/.env.example sidecar-deck-backend
```

Set `WEATHER_LOCATION` in the backend environment, such as `WEATHER_LOCATION=Tucson, AZ` or `WEATHER_LOCATION=Springfield, Illinois`, to enable standby weather.

Build and run the standalone frontend image:

```bash
docker build -t sidecar-deck-frontend -f frontend/Dockerfile .
docker run --rm -p 8081:8080 -e BACKEND_URL=http://host.docker.internal:8080 sidecar-deck-frontend
```

The frontend image serves the built Vite app through nginx and proxies same-origin API/WebSocket traffic to `BACKEND_URL`.

## API Summary

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
    "cpu": {
      "usagePercent": 42.5,
      "topProcesses": [
        {"name": "chrome.exe", "pids": [8424, 9012], "processCount": 2, "usagePercent": 12.4}
      ]
    },
    "memory": {
      "usagePercent": 68.1,
      "usedBytes": 21904333209,
      "totalBytes": 34359738368,
      "topProcesses": [
        {"name": "chrome.exe", "pids": [8424, 9012], "processCount": 2, "rssBytes": 3161092096, "usagePercent": 9.2}
      ]
    },
    "gpu": {"name": "NVIDIA GeForce RTX 4070", "usagePercent": 76.4, "memoryUsedBytes": 8147483648, "memoryTotalBytes": 12884901888},
    "temperatures": [
      {"id": "cpu-package", "label": "CPU Package", "temperatureC": 61.2},
      {"id": "gpu-core", "label": "GPU Core", "temperatureC": 67.8}
    ],
    "network": {"rxBytesPerSecond": 1200000, "txBytesPerSecond": 350000}
  }'
```

Live dashboard clients connect to:

```text
ws://<server>:8080/ws
```

## Kiosk Setup

Example Chromium launch on the Raspberry Pi:

```bash
chromium-browser --kiosk http://homelab.local:8080
```

The UI is designed first for `1920x480` with no normal-operation scrolling. Wider or normal desktop browser sizes get a simple responsive fallback for testing.

For full Raspberry Pi preparation steps, see [docs/raspberry-pi-kiosk.md](docs/raspberry-pi-kiosk.md). For Windows background startup, see [docs/windows-agent-startup.md](docs/windows-agent-startup.md).
