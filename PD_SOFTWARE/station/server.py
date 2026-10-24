"""Local station server: UI, MJPEG preview, live state WebSocket, session control.

Run:  uvicorn station.server:app --host 127.0.0.1 --port 8080
The camera stream is served on 127.0.0.1 only; nothing is streamed to the backend.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from station.config import AVATAR_DIR, CONFIG_DIR, WEB_DIR, get_settings, load_exercise_config
from station.engine import ExerciseEngine
from station.storage import LocalStore
from station.sync import BackendClient, BackendError, SyncWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
settings = get_settings()
store = LocalStore(settings.database_path)
client = BackendClient(settings)
sync_worker = SyncWorker(client, store, settings.sync_interval_seconds)
engine = ExerciseEngine(settings, store, on_session_saved=sync_worker.trigger)


@asynccontextmanager
async def lifespan(_: FastAPI):
    engine.start()
    sync_worker.start()
    yield
    engine.stop()
    sync_worker.stop()


app = FastAPI(title="QMMC PD1 Component Twin Station", version="0.1.0", lifespan=lifespan)


class StartSessionRequest(BaseModel):
    patient_id: int = Field(gt=0)
    prescription_id: int = Field(gt=0)
    side: str = Field(pattern="^(left|right)$")


class PreviewRequest(BaseModel):
    exercise_key: str
    side: str = Field(pattern="^(left|right)$")


# ------------------------------------------------------------------ pages
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/config/avatar_map.json", include_in_schema=False)
def avatar_map() -> FileResponse:
    return FileResponse(CONFIG_DIR / "avatar_map.json")


# ------------------------------------------------------------- backend data
@app.get("/api/patients")
def patients() -> dict:
    try:
        data = client.patients()
        store.cache_patients(data)
        return {"source": "backend", "patients": data}
    except (BackendError, Exception) as exc:
        cached = store.cached_patients()
        if not cached:
            raise HTTPException(503, f"Backend unavailable and no cached patients: {exc}")
        return {"source": "cache", "patients": cached}


@app.get("/api/patients/{patient_id}/prescriptions")
def prescriptions(patient_id: int) -> dict:
    try:
        data = client.prescriptions(patient_id)
        store.cache_prescriptions(patient_id, data)
        return {"source": "backend", "prescriptions": data}
    except (BackendError, Exception) as exc:
        cached = store.cached_prescriptions(patient_id)
        if not cached:
            raise HTTPException(503, f"Backend unavailable and no cached prescriptions: {exc}")
        return {"source": "cache", "prescriptions": cached}


def _find(items: list[dict], item_id: int) -> dict | None:
    return next((i for i in items if i["id"] == item_id), None)


# ---------------------------------------------------------- session control
@app.post("/api/session/start")
def start_session(request: StartSessionRequest) -> dict:
    patient = _find(store.cached_patients(), request.patient_id)
    prescription = _find(store.cached_prescriptions(request.patient_id), request.prescription_id)
    if patient is None or prescription is None:
        raise HTTPException(404, "Load the patient and prescription first")
    try:
        return engine.start_session(patient, prescription, request.side)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/session/stop")
def stop_session() -> dict:
    summary = engine.stop_session("stopped_by_staff")
    if summary is None:
        raise HTTPException(409, "No session is running")
    return summary


@app.post("/api/preview")
def preview(request: PreviewRequest) -> dict:
    try:
        engine.set_preview(request.exercise_key, request.side)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.get("/api/exercises")
def exercises() -> dict:
    return load_exercise_config()["exercises"]


@app.get("/api/sessions")
def local_sessions(limit: int = 50) -> list[dict]:
    rows = store.list_sessions(limit)
    for row in rows:
        row["repetitions"] = json.loads(row.pop("repetitions_json"))
        row["metrics"] = json.loads(row.pop("metrics_json"))
    return rows


@app.post("/api/sync")
def sync_now() -> dict:
    store.retry_failed()
    sync_worker.trigger()
    return {"queued": True}


@app.get("/api/status")
def status() -> dict:
    return {
        "backend_url": settings.backend_url,
        "backend_online": client.online,
        "sync": store.count_by_sync_status(),
        "last_sync_error": sync_worker.last_error,
    }


# ---------------------------------------------------------- live streams
@app.get("/video.mjpg", include_in_schema=False)
async def video() -> StreamingResponse:
    async def frames():
        last_seq = -1
        while True:
            jpg = engine.jpeg
            if jpg is not None and engine.jpeg_seq != last_seq:
                last_seq = engine.jpeg_seq
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpg
                    + b"\r\n"
                )
            await asyncio.sleep(1.0 / settings.stream_fps)

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, private", "Pragma": "no-cache"},
    )


@app.websocket("/ws/state")
async def state_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(engine.snapshot())
            await asyncio.sleep(1.0 / 30)
    except (WebSocketDisconnect, RuntimeError):
        return


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/avatar", StaticFiles(directory=AVATAR_DIR, check_dir=False), name="avatar")
