# Sidecar Deck Python App

FastAPI service for ingesting real metrics, tracking recent history, serving health checks, and streaming live dashboard updates over WebSocket. The same Python package also contains the optional Windows metrics agent, installed with the `agent` extra.

The server install is the default:

```bash
pip install -e .
sidecar-deck-server
```

The agent install adds collector-only dependencies:

```bash
pip install -e ".[agent]"
sidecar-deck-agent
```

Both server and agent use `app.models` as the single Python metrics contract.

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
`WEATHER_LOCATION` is optional. When set, the standby dashboard uses it to show current weather and a 5 day forecast. City/region values such as `Springfield, Illinois` are supported.
Agent configuration is documented in [agent.env.example](agent.env.example). The Windows control scripts in this folder create the `.env` file used by the agent.

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

## Agent

The agent is focused on Windows and collects system metrics via psutil, temperatures via LibreHardwareMonitor/OpenHardwareMonitor, Logitech and Bluetooth device battery levels, XInput controller battery levels, and NVIDIA GPU metrics through `nvidia-smi`.

Useful CLI probes:

```bash
sidecar-deck-agent one-shot
sidecar-deck-agent one-shot cpu
sidecar-deck-agent one-shot battery
sidecar-deck-agent debug cpu
sidecar-deck-agent debug battery
python -m app.agent debug battery
```

`SidecarDeckAgent.ps1` is the Windows installer and control script. `SidecarDeckAgent.bat` is a Command Prompt wrapper around the same PowerShell script.

Install and start the background agent from a copied script directory:

```powershell
.\SidecarDeckAgent.ps1 install -DashboardUrl http://homelab.local:8080
```

By default, the script installs `sidecar-deck[agent]` from the `backend` subdirectory of this repository. Use `-Source` to install from a different Git URL, wheel, or local package directory.

The agent starts a local-only diagnostic HTTP server by default at `http://127.0.0.1:8765`.

For full Windows startup instructions, see [../docs/windows-agent-startup.md](../docs/windows-agent-startup.md).

## Docker

From the repository root:

```bash
docker build -t sidecar-deck-backend -f backend/Dockerfile .
docker run --rm -p 8080:8080 --env-file backend/.env sidecar-deck-backend
```
