# Agent Guide

Use this file to route future work to the right source quickly. The project is a lightweight kiosk dashboard for a `1920x480` sidecar display: a Windows PC agent collects metrics, a FastAPI backend stores and streams them, and a React/Vite frontend renders the dashboard.

## Project Rules

- When adding new files, add them to git unless they are ignored or temporary.
- Keep the backend, frontend, and agent metric contracts aligned. The Python server and agent share `backend/app/models.py`; the frontend mirror lives in `frontend/src/types.ts`.
- The backend does not generate fake metrics. Empty or missing data should show as waiting/unavailable in the frontend.

## Source Map

### Root

- `README.md`: high-level architecture, quick start, Docker build examples, API sample payload, and kiosk summary.
- `.gitignore` / `.dockerignore`: repo hygiene for generated files and container build context.
- `LICENSE`: project license.

### Backend: `backend/`

FastAPI service that validates incoming metrics, stores the latest payload plus short history, and streams updates to dashboard clients.

- `backend/app/main.py`: API and WebSocket entry point. Owns FastAPI app setup, CORS, token-protected `POST /api/metrics`, read endpoints, `/ws`, `/health`, and static frontend fallback serving.
- `backend/app/models.py`: canonical Python Pydantic API schema shared by the backend and agent. Update this when the metric payload contract changes.
- `backend/app/agent.py`: optional Windows metrics agent. Owns environment loading, diagnostic HTTP server, rate tracking, psutil CPU/RAM/network/disk collection, temperature lookup, NVIDIA GPU lookup, peripheral battery lookup, payload assembly, and POSTing metrics.
- `backend/app/state.py`: in-memory metrics store. Owns latest payload, history trimming, live/stale/offline status calculation, and WebSocket update waiting.
- `backend/app/config.py`: environment-backed settings such as token, stale/offline thresholds, history window, app port, and static directory.
- `backend/tests/test_api.py`: API smoke tests for health, content types, auth, schema acceptance, and validation rejection.
- `backend/pyproject.toml`: installable Python package. The default install is the server; `backend[agent]` adds agent-only collector dependencies.
- `backend/requirements.txt` and `backend/requirements-dev.txt`: runtime and test dependency files used by existing Docker/test workflows.
- `backend/Dockerfile`: backend container image. It also serves the built frontend when static assets are present.
- `backend/pytest.ini`: pytest configuration.
- `backend/SidecarDeckAgent.ps1` and `backend/SidecarDeckAgent.bat`: Windows agent install/control scripts.
- `backend/agent.env.example`: example agent environment values.

Useful backend commands:

```powershell
cd backend
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload --port 8080
pip install -e .
sidecar-deck-server
```

### Frontend: `frontend/`

React/Vite dashboard optimized for the ultrawide kiosk. It connects to `/ws`, renders latest state and short history, and should remain readable at `1920x480`.

- `frontend/src/App.tsx`: main dashboard composition and data flow. Owns WebSocket connection, derived display values, CPU/RAM/GPU cards, compact rotating panels, and missing-data fallbacks.
- `frontend/src/types.ts`: TypeScript mirror of the backend/agent metric payload. Keep this synchronized with `backend/app/models.py`.
- `frontend/src/format.ts`: display formatting helpers for percentages, bytes, throughput, clock, age, and GB pairs.
- `frontend/src/Sparkline.tsx`: reusable SVG sparkline for metric history.
- `frontend/src/RankedMeterList.tsx`: reusable ranked/paged meter list for processes, thermals, disk volumes, and batteries.
- `frontend/src/styles.css`: all kiosk layout and visual styling. Be careful with fixed-height behavior and text overflow at `1920x480`.
- `frontend/src/main.tsx`: React bootstrapping.
- `frontend/vite.config.ts`: Vite React config and dev proxies for `/api`, `/health`, and `/ws` to `localhost:8080`.
- `frontend/package.json`: npm scripts and frontend dependencies.
- `frontend/nginx/default.conf.template`: production nginx proxy/static config for the frontend container.
- `frontend/Dockerfile`: standalone frontend container image.

Useful frontend commands:

```powershell
cd frontend
npm install
npm run build
npm run dev
```

After frontend UI changes, run the app and visually check the kiosk viewport when practical.

### Agent: `backend/app/agent.py`

Windows-focused Python process that collects local machine metrics and pushes them to the backend with bearer-token auth.

- `backend/app/agent.py`: main collector and push loop.
- `backend/app/models.py`: shared Pydantic payload schema for backend ingestion and agent emission.
- `backend/SidecarDeckAgent.ps1`: Windows install/control script. Owns virtualenv setup, package install/update, `.env` writing, Scheduled Task registration, start/stop/restart/status/uninstall/run commands, and elevated-task option.
- `backend/SidecarDeckAgent.bat`: Command Prompt wrapper around the PowerShell control script.
- `backend/pyproject.toml`: package metadata and `sidecar-deck-agent` / `sidecar-deck-agentw` entry points.
- `backend/agent.env.example`: agent environment example.

Important collector areas inside `backend/app/agent.py`:

- Environment/config constants live near the top of the file.
- Diagnostic preview server is `DiagnosticHandler` and `start_diagnostic_http_server()`.
- Throughput deltas are in `RateTracker`.
- Temperature collection and prioritization are `temperature_sensors()` through `temperature_category()`.
- Disk and top process metrics are `disk_usage_metrics()` and `top_memory_processes()`.
- GPU metrics are `nvidia_gpu_metrics()`.
- Peripheral batteries are `logitech_battery_devices()`, `bluetooth_battery_devices()`, `xinput_battery_devices()`, and their fetch/dedupe helpers.
- The final payload is assembled in `collect_metrics()` and sent by `push_metrics()`.

Useful agent commands:

```powershell
cd backend
pip install -e ".[agent]"
sidecar-deck-agent
```

### Docs: `docs/`

Operational setup notes rather than application source.

- `docs/raspberry-pi-kiosk.md`: prepares a Raspberry Pi as a Chromium kiosk only. The Pi does not run the backend or collect metrics.
- `docs/windows-agent-startup.md`: Windows Python, install directory, `.env`, Scheduled Task setup, troubleshooting, and update flow for the agent.

## Change Routing

- API shape changes: update `backend/app/models.py`, `frontend/src/types.ts`, backend tests, and any README payload examples.
- Metric ingestion/status changes: start in `backend/app/main.py` and `backend/app/state.py`.
- New collected metric: start in `backend/app/agent.py`, add schema fields in `backend/app/models.py` and `frontend/src/types.ts`, then render in `frontend/src/App.tsx`.
- Dashboard layout/visual changes: start in `frontend/src/App.tsx` and `frontend/src/styles.css`; use `Sparkline.tsx` and `RankedMeterList.tsx` for existing chart/list patterns.
- Display formatting changes: start in `frontend/src/format.ts`.
- Windows install/startup behavior: start in `backend/SidecarDeckAgent.ps1`, then update `backend/README.md` and `docs/windows-agent-startup.md`.
- Raspberry Pi kiosk behavior: update `docs/raspberry-pi-kiosk.md`.
- Container/runtime changes: check `backend/Dockerfile`, `frontend/Dockerfile`, and `frontend/nginx/default.conf.template`.

## Verification

- Backend/API: run `pytest` from `backend/`.
- Frontend: run `npm run build` from `frontend/`.
- Agent: there is no dedicated test suite currently; run `sidecar-deck-agent` interactively or use `SidecarDeckAgent.ps1 run`, then inspect the diagnostic server at `http://127.0.0.1:8765`.
- Full local flow: run backend on `8080`, frontend on `5173`, then run the agent with `DASHBOARD_BASE_URL=http://localhost:8080` and matching `METRICS_TOKEN`.
