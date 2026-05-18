# Sidecar Deck

Lightweight kiosk dashboard for a `1920x480` ultrawide sidecar display. The homelab server runs the backend API and dashboard frontend, while a Windows PC agent pushes live machine metrics. The Raspberry Pi only opens the dashboard URL in Chromium kiosk mode.

<img width="1270" height="360" alt="Sidecar Deck dashboard" src="https://github.com/user-attachments/assets/ca66d608-d94c-4d7a-a10e-d76822393365" />

## Project Layout

- [agent](agent/README.md): Windows Python process that collects host metrics and posts them to the backend.
- [backend](backend/README.md): FastAPI service that stores the latest metrics, keeps short history, and streams updates over WebSocket.
- [frontend](frontend/README.md): React/Vite dashboard optimized for the sidecar display.
- [docs](docs): setup notes for Raspberry Pi kiosk mode and Windows agent startup.

## How It Fits Together

1. The backend exposes `/api/metrics`, `/api/metrics/latest`, `/api/metrics/history`, `/health`, and `/ws`.
2. The Windows agent reads local CPU, RAM, network, disk, uptime, hostname, temperature, and optional GPU data.
3. The agent posts metrics to the backend using a bearer token.
4. The frontend reads the latest state and listens on `/ws` so the kiosk display updates live.
5. The Raspberry Pi launches Chromium directly against the frontend URL.

The backend does not generate placeholder metrics. The dashboard stays in a waiting state until a real agent posts data.

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

For host metrics from a Windows machine, install the [agent](agent/README.md):

```powershell
sidecar-deck-agentctl install --dashboard-url http://homelab.local:8080 --metrics-token change-me --hostname gaming-pc
```

Use `sidecar-deck-agentctl start`, `stop`, `restart`, `status`, `update`, and `uninstall` to manage the Windows background task.

## Docker Images

Build and run the backend image:

```bash
docker build -t sidecar-deck-backend -f backend/Dockerfile .
docker run --rm -p 8080:8080 --env-file backend/.env.example sidecar-deck-backend
```

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
    "cpu": {"usagePercent": 42.5},
    "memory": {
      "usagePercent": 68.1,
      "usedBytes": 21904333209,
      "totalBytes": 34359738368,
      "topProcesses": [
        {"name": "chrome.exe", "pid": 8424, "rssBytes": 3161092096, "usagePercent": 9.2}
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
