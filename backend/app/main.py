from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .demo import run_demo_metrics
from .models import MetricPayload, StatusEnvelope
from .state import MetricsState


settings = get_settings()
state = MetricsState(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    demo_task = asyncio.create_task(run_demo_metrics(state))
    try:
        yield
    finally:
        demo_task.cancel()
        try:
            await demo_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Sidecar Deck", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


def require_token(authorization: str | None = Header(default=None), cfg: Settings = Depends(get_settings)) -> None:
    expected = f"Bearer {cfg.metrics_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="invalid metrics token")


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {"status": "ok", "demoMode": settings.demo_mode}


@app.get("/api/metrics/latest", response_model=StatusEnvelope)
async def latest_metrics() -> StatusEnvelope:
    return state.snapshot()


@app.get("/api/metrics/history", response_model=list[MetricPayload])
async def metric_history() -> list[MetricPayload]:
    return list(state.history)


@app.post("/api/metrics", response_model=StatusEnvelope, dependencies=[Depends(require_token)])
async def ingest_metrics(payload: MetricPayload) -> StatusEnvelope:
    await state.set_metrics(payload, source="real")
    return state.snapshot()


@app.websocket("/ws")
async def websocket_metrics(websocket: WebSocket) -> None:
    await websocket.accept()
    last_seen = None
    try:
        while True:
            snapshot = await state.wait_for_update(last_seen)
            last_seen = state.latest_received_at
            await websocket.send_json(snapshot.model_dump(mode="json"))
    except WebSocketDisconnect:
        return


static_dir = Path(settings.static_dir)
assets_dir = static_dir / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


@app.get("/{path:path}")
async def serve_frontend(path: str) -> FileResponse:
    index_path = static_dir / "index.html"
    requested = static_dir / path
    if path and requested.exists() and requested.is_file():
        return FileResponse(requested)
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="frontend has not been built")
