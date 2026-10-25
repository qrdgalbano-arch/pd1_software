"""Local SQLite storage: offline cache of patients/prescriptions and session records.

Raw video is never stored. Session records stay 'pending' until uploaded.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cached_patients (
    id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL,
    cached_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cached_prescriptions (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    cached_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    client_session_id TEXT PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    prescription_id INTEGER NOT NULL,
    exercise_key TEXT NOT NULL,
    exercise_name TEXT NOT NULL,
    affected_side TEXT NOT NULL,
    status TEXT NOT NULL,
    valid_repetitions INTEGER NOT NULL,
    invalid_repetitions INTEGER NOT NULL,
    incomplete_repetitions INTEGER NOT NULL,
    error_count INTEGER NOT NULL,
    error_summary TEXT NOT NULL,
    arom_classification TEXT,
    peak_rom_degrees REAL,
    duration_seconds INTEGER NOT NULL,
    device_recorded_at TEXT NOT NULL,
    repetitions_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    sync_attempts INTEGER NOT NULL DEFAULT 0,
    last_sync_error TEXT,
    synced_at TEXT
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalStore:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # --- offline cache --------------------------------------------------------
    def cache_patients(self, patients: list[dict]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO cached_patients (id, payload, cached_at) VALUES (?, ?, ?)",
                [(p["id"], json.dumps(p), utc_now()) for p in patients],
            )
            self._conn.commit()

    def cached_patients(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM cached_patients").fetchall()
        patients = [json.loads(r["payload"]) for r in rows]
        return sorted(patients, key=lambda p: p.get("full_name", ""))

    def cache_prescriptions(self, patient_id: int, prescriptions: list[dict]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cached_prescriptions WHERE patient_id = ?", (patient_id,))
            self._conn.executemany(
                "INSERT OR REPLACE INTO cached_prescriptions (id, patient_id, payload, cached_at) VALUES (?, ?, ?, ?)",
                [(p["id"], patient_id, json.dumps(p), utc_now()) for p in prescriptions],
            )
            self._conn.commit()

    def cached_prescriptions(self, patient_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM cached_prescriptions WHERE patient_id = ?", (patient_id,)
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    # --- session records ------------------------------------------------------
    def save_session(self, record: dict) -> None:
        columns = ", ".join(record)
        placeholders = ", ".join("?" for _ in record)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO sessions ({columns}) VALUES ({placeholders})",
                list(record.values()),
            )
            self._conn.commit()

    def list_sessions(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY device_recorded_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def pending_sessions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE sync_status = 'pending' ORDER BY device_recorded_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def count_by_sync_status(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT sync_status, COUNT(*) AS n FROM sessions GROUP BY sync_status"
            ).fetchall()
        return {r["sync_status"]: r["n"] for r in rows}

    def mark_sync(self, client_session_id: str, status: str, error: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE sessions
                   SET sync_status = ?, sync_attempts = sync_attempts + 1,
                       last_sync_error = ?, synced_at = CASE WHEN ? = 'synced' THEN ? ELSE synced_at END
                   WHERE client_session_id = ?""",
                (status, error, status, utc_now(), client_session_id),
            )
            self._conn.commit()

    def retry_failed(self) -> None:
        with self._lock:
            self._conn.execute("UPDATE sessions SET sync_status = 'pending' WHERE sync_status = 'failed'")
            self._conn.commit()
