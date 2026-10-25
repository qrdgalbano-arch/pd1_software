
"""Separate local extension store; no camera images."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .core import compare_sessions

DEFAULT_DB = (
    Path(__file__).resolve().parents[2]
    / "data" / "rehab_extension.sqlite3"
)

class RehabStore:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS rehab_sessions (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    exercise_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    design_scope TEXT NOT NULL,
                    config_version TEXT NOT NULL,
                    reference_edition TEXT,
                    measurement_method TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'running'
                );
                CREATE TABLE IF NOT EXISTS rehab_reps (
                    session_id TEXT NOT NULL,
                    rep_index INTEGER NOT NULL,
                    peak_angle_moving_joint REAL,
                    supporting_joint_angles TEXT NOT NULL,
                    target_reached INTEGER,
                    time_outside_limits TEXT NOT NULL,
                    tracking_valid INTEGER NOT NULL,
                    PRIMARY KEY(session_id, rep_index),
                    FOREIGN KEY(session_id) REFERENCES rehab_sessions(id)
                );
                CREATE TABLE IF NOT EXISTS rehab_summaries (
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES rehab_sessions(id)
                );
                CREATE TABLE IF NOT EXISTS rehab_telemetry (
                    session_id TEXT NOT NULL,
                    timestamp_seconds REAL NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES rehab_sessions(id)
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def start(
        self, patient_id, exercise_id, side, design_scope,
        config_version, reference_edition=None,
        measurement_method="world_xyz_neutral_zero_v1",
    ):
        if design_scope not in ("component", "leg", "whole_body"):
            raise ValueError("Invalid design_scope")
        if side not in ("left", "right"):
            raise ValueError("Invalid side")
        session_id = str(uuid4())
        with self.connect() as db:
            db.execute(
                "INSERT INTO rehab_sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id, str(patient_id),
                    datetime.now(timezone.utc).isoformat(),
                    exercise_id, side, design_scope, config_version,
                    reference_edition, measurement_method, "running",
                ),
            )
        return session_id

    def add_rep(
        self, session_id, rep_index, peak_angle_moving_joint,
        supporting_joint_angles=None, target_reached=None,
        time_outside_limits=None, tracking_valid=True,
    ):
        if target_reached is not None and type(target_reached) is not bool:
            raise ValueError("target_reached must be bool or None")
        # Strict JSON rejects NaN/infinity before persistence.
        json.dumps(peak_angle_moving_joint, allow_nan=False)
        angles = json.dumps(supporting_joint_angles or {}, allow_nan=False)
        outside = json.dumps(time_outside_limits or {}, allow_nan=False)
        with self.connect() as db:
            status = db.execute(
                "SELECT status FROM rehab_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if status is None or status["status"] != "running":
                raise ValueError("Session is missing or already finished")
            db.execute(
                "INSERT INTO rehab_reps VALUES (?,?,?,?,?,?,?)",
                (
                    session_id, rep_index, peak_angle_moving_joint,
                    angles,
                    None if target_reached is None else int(target_reached),
                    outside, int(tracking_valid),
                ),
            )

    def telemetry(self, session_id, timestamp_seconds, payload):
        encoded = json.dumps(payload, allow_nan=False)
        json.dumps(timestamp_seconds, allow_nan=False)
        with self.connect() as db:
            db.execute(
                "INSERT INTO rehab_telemetry VALUES (?,?,?)",
                (session_id, timestamp_seconds, encoded),
            )

    def valid_peaks(self, session_id):
        with self.connect() as db:
            rows = db.execute(
                """SELECT peak_angle_moving_joint FROM rehab_reps
                WHERE session_id=? AND tracking_valid=1
                AND peak_angle_moving_joint IS NOT NULL ORDER BY rep_index""",
                (session_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def history(self, session_id, count):
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("Configure a positive history session count")
        with self.connect() as db:
            current = db.execute(
                "SELECT rowid AS order_id,* FROM rehab_sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if current is None:
                raise ValueError("Unknown session")
            # Scope is intentionally NOT a comparison criterion.
            rows = db.execute(
                """SELECT s.id,s.timestamp,u.payload
                FROM rehab_sessions s
                JOIN rehab_summaries u ON s.id=u.session_id
                WHERE s.status != 'interrupted' AND s.patient_id=? AND s.exercise_id=? AND s.side=?
                AND s.measurement_method=? AND s.config_version=?
                AND s.reference_edition IS ?
                AND s.rowid < ?
                ORDER BY s.rowid DESC LIMIT ?""",
                (
                    current["patient_id"], current["exercise_id"],
                    current["side"], current["measurement_method"],
                    current["config_version"], current["reference_edition"],
                    current["order_id"], count,
                ),
            ).fetchall()
        return [
            dict(
                id=r["id"], timestamp=r["timestamp"],
                summary=json.loads(r["payload"]),
            ) for r in rows
        ]

    def finish(
        self, session_id, assessment, supporting_times,
        trend_count, status="finished",
    ):
        if status not in ("finished", "stopped", "interrupted"):
            raise ValueError("Invalid finish status")
        prior = self.history(session_id, trend_count)
        peaks = self.valid_peaks(session_id)
        previous = self.valid_peaks(prior[0]["id"]) if prior else None
        summary = compare_sessions(peaks, previous)
        summary.update({
            "wnl_label": assessment["label"],
            "provisional_flag": assessment["provisional"],
            "assessment": assessment,
            "supporting_joint_monitoring": {},
            "trend": list(reversed(prior)),
        })
        for joint, times in supporting_times.items():
            within, outside, uncertain = (
                float(times.get(k, 0))
                for k in ("within_seconds", "outside_seconds", "uncertain_seconds")
            )
            if min(within, outside, uncertain) < 0:
                raise ValueError("Monitoring durations cannot be negative")
            valid = within + outside
            total = valid + uncertain
            summary["supporting_joint_monitoring"][joint] = {
                "within_percent": 100 * within / valid if valid else None,
                "tracking_coverage_percent": 100 * valid / total if total else None,
                "within_seconds": within,
                "outside_seconds": outside,
                "uncertain_seconds": uncertain,
            }

        with self.connect() as db:
            rows = db.execute(
                "SELECT target_reached FROM rehab_reps WHERE session_id=?",
                (session_id,),
            ).fetchall()
            reached = sum(r[0] == 1 for r in rows)
            missed = sum(r[0] == 0 for r in rows)
            assessed = reached + missed
            summary.update({
                "reps_completed": len(rows),
                "target_reached_count": reached,
                "target_not_reached_count": missed,
                "target_unassessed_count": len(rows) - assessed,
                "completion_rate": reached / assessed if assessed else None,
            })
            encoded = json.dumps(summary, allow_nan=False)
            db.execute(
                "INSERT INTO rehab_summaries VALUES (?,?)",
                (session_id, encoded),
            )
            db.execute(
                "UPDATE rehab_sessions SET status=? WHERE id=?",
                (status, session_id),
            )
        return summary
