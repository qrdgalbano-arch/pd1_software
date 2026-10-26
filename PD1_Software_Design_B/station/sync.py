"""Backend client and background synchronization to the QMMC PD1 FastAPI backend.

Uses only existing backend routes plus POST /staff/sessions:
  POST /auth/login, POST /auth/refresh, GET /staff/patients,
  GET /staff/patients/{id}/prescriptions, POST /staff/sessions
"""

import logging
import threading

import httpx

from station.config import StationSettings, match_exercise_key
from station.storage import LocalStore

log = logging.getLogger("station.sync")


class BackendError(Exception):
    pass


class BackendClient:
    def __init__(self, settings: StationSettings):
        self.settings = settings
        self._http = httpx.Client(base_url=settings.backend_url.rstrip("/"), timeout=10.0)
        self._access: str | None = None
        self._refresh: str | None = None
        self._lock = threading.Lock()
        self.online = False

    def _login(self) -> None:
        if not self.settings.station_staff_password:
            raise BackendError("STATION_STAFF_PASSWORD is not set in station/.env")
        response = self._http.post(
            "/auth/login",
            data={
                "username": self.settings.station_staff_email,
                "password": self.settings.station_staff_password,
            },
        )
        if response.status_code != 200:
            raise BackendError(f"Station login failed ({response.status_code}): {response.text}")
        tokens = response.json()
        self._access, self._refresh = tokens["access_token"], tokens["refresh_token"]

    def _refresh_tokens(self) -> bool:
        if not self._refresh:
            return False
        response = self._http.post("/auth/refresh", json={"refresh_token": self._refresh})
        if response.status_code != 200:
            return False
        tokens = response.json()
        self._access, self._refresh = tokens["access_token"], tokens["refresh_token"]
        return True

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        with self._lock:
            try:
                if self._access is None:
                    self._login()
                headers = {"Authorization": f"Bearer {self._access}"}
                response = self._http.request(method, path, headers=headers, **kwargs)
                if response.status_code == 401:
                    if not self._refresh_tokens():
                        self._login()
                    headers = {"Authorization": f"Bearer {self._access}"}
                    response = self._http.request(method, path, headers=headers, **kwargs)
                self.online = True
                return response
            except httpx.HTTPError as exc:
                self.online = False
                raise BackendError(f"Backend unreachable: {exc}") from exc

    def health(self) -> bool:
        try:
            self.online = self._http.get("/health", timeout=3.0).status_code == 200
        except httpx.HTTPError:
            self.online = False
        return self.online

    # --- data used by the station -------------------------------------------
    def patients(self) -> list[dict]:
        response = self.request("GET", "/staff/patients")
        response.raise_for_status()
        return [p for p in response.json() if p.get("is_active", True)]

    def prescriptions(self, patient_id: int) -> list[dict]:
        response = self.request("GET", f"/staff/patients/{patient_id}/prescriptions")
        response.raise_for_status()
        result = []
        for item in response.json():
            key = match_exercise_key(item["exercise"]["name"])
            if item.get("is_active") and key:
                result.append({**item, "exercise_key": key})
        return result

    def upload_session(self, record: dict) -> httpx.Response:
        payload = {
            "client_session_id": record["client_session_id"],
            "patient_id": record["patient_id"],
            "prescription_id": record["prescription_id"],
            "status": record["status"],
            "repetitions_completed": record["valid_repetitions"],
            "duration_seconds": record["duration_seconds"],
            "error_count": record["error_count"],
            "error_summary": record["error_summary"][:2000],
            "valid_repetitions": record["valid_repetitions"],
            "invalid_repetitions": record["invalid_repetitions"],
            "incomplete_repetitions": record["incomplete_repetitions"],
            "arom_classification": record["arom_classification"],
            "peak_rom_degrees": record["peak_rom_degrees"],
            "affected_side": record["affected_side"],
            "device_recorded_at": record["device_recorded_at"],
        }
        return self.request("POST", "/staff/sessions", json=payload)


class SyncWorker(threading.Thread):
    def __init__(self, client: BackendClient, store: LocalStore, interval_s: int):
        super().__init__(daemon=True, name="sync-worker")
        self.client = client
        self.store = store
        self.interval_s = interval_s
        self._wake = threading.Event()
        self._stop_event = threading.Event()
        self.last_error: str | None = None

    def trigger(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake.set()

    def sync_once(self) -> int:
        uploaded = 0
        for record in self.store.pending_sessions():
            try:
                response = self.client.upload_session(record)
            except BackendError as exc:
                self.last_error = str(exc)
                return uploaded  # offline: keep pending, retry later
            if response.status_code in (200, 201):
                self.store.mark_sync(record["client_session_id"], "synced")
                uploaded += 1
            elif response.status_code >= 500:
                self.last_error = f"Server error {response.status_code}"
                return uploaded
            else:
                self.store.mark_sync(
                    record["client_session_id"], "failed",
                    f"{response.status_code}: {response.text[:300]}",
                )
        self.last_error = None
        return uploaded

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self.store.pending_sessions():
                    count = self.sync_once()
                    if count:
                        log.info("Uploaded %d session record(s)", count)
                else:
                    self.client.health()
            except Exception as exc:  # keep the worker alive
                self.last_error = str(exc)
                log.exception("Sync failed")
            self._wake.wait(self.interval_s)
            self._wake.clear()
