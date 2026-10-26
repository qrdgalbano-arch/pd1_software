from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "station" / "rehab_extension" / "storage.py"
TEST = ROOT / "tests" / "test_rehab_storage_extension.py"

CODE = '\n"""Separate local extension store; no camera images."""\nimport json\nimport sqlite3\nfrom contextlib import contextmanager\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nfrom uuid import uuid4\n\nfrom .core import compare_sessions\n\nDEFAULT_DB = (\n    Path(__file__).resolve().parents[2]\n    / "data" / "rehab_extension.sqlite3"\n)\n\nclass RehabStore:\n    def __init__(self, path=DEFAULT_DB):\n        self.path = Path(path)\n        self.path.parent.mkdir(parents=True, exist_ok=True)\n        with self.connect() as db:\n            db.executescript("""\n                CREATE TABLE IF NOT EXISTS rehab_sessions (\n                    id TEXT PRIMARY KEY,\n                    patient_id TEXT NOT NULL,\n                    timestamp TEXT NOT NULL,\n                    exercise_id TEXT NOT NULL,\n                    side TEXT NOT NULL,\n                    design_scope TEXT NOT NULL,\n                    config_version TEXT NOT NULL,\n                    reference_edition TEXT,\n                    measurement_method TEXT NOT NULL,\n                    status TEXT NOT NULL DEFAULT \'running\'\n                );\n                CREATE TABLE IF NOT EXISTS rehab_reps (\n                    session_id TEXT NOT NULL,\n                    rep_index INTEGER NOT NULL,\n                    peak_angle_moving_joint REAL,\n                    supporting_joint_angles TEXT NOT NULL,\n                    target_reached INTEGER,\n                    time_outside_limits TEXT NOT NULL,\n                    tracking_valid INTEGER NOT NULL,\n                    PRIMARY KEY(session_id, rep_index),\n                    FOREIGN KEY(session_id) REFERENCES rehab_sessions(id)\n                );\n                CREATE TABLE IF NOT EXISTS rehab_summaries (\n                    session_id TEXT PRIMARY KEY,\n                    payload TEXT NOT NULL,\n                    FOREIGN KEY(session_id) REFERENCES rehab_sessions(id)\n                );\n                CREATE TABLE IF NOT EXISTS rehab_telemetry (\n                    session_id TEXT NOT NULL,\n                    timestamp_seconds REAL NOT NULL,\n                    payload TEXT NOT NULL,\n                    FOREIGN KEY(session_id) REFERENCES rehab_sessions(id)\n                );\n            """)\n\n    @contextmanager\n    def connect(self):\n        db = sqlite3.connect(self.path)\n        try:\n            db.row_factory = sqlite3.Row\n            db.execute("PRAGMA foreign_keys=ON")\n            with db:\n                yield db\n        finally:\n            db.close()\n\n    def start(\n        self, patient_id, exercise_id, side, design_scope,\n        config_version, reference_edition=None,\n        measurement_method="world_xyz_neutral_zero_v1",\n    ):\n        if design_scope not in ("component", "leg", "whole_body"):\n            raise ValueError("Invalid design_scope")\n        if side not in ("left", "right"):\n            raise ValueError("Invalid side")\n        session_id = str(uuid4())\n        with self.connect() as db:\n            db.execute(\n                "INSERT INTO rehab_sessions VALUES (?,?,?,?,?,?,?,?,?,?)",\n                (\n                    session_id, str(patient_id),\n                    datetime.now(timezone.utc).isoformat(),\n                    exercise_id, side, design_scope, config_version,\n                    reference_edition, measurement_method, "running",\n                ),\n            )\n        return session_id\n\n    def add_rep(\n        self, session_id, rep_index, peak_angle_moving_joint,\n        supporting_joint_angles=None, target_reached=None,\n        time_outside_limits=None, tracking_valid=True,\n    ):\n        if target_reached is not None and type(target_reached) is not bool:\n            raise ValueError("target_reached must be bool or None")\n        # Strict JSON rejects NaN/infinity before persistence.\n        json.dumps(peak_angle_moving_joint, allow_nan=False)\n        angles = json.dumps(supporting_joint_angles or {}, allow_nan=False)\n        outside = json.dumps(time_outside_limits or {}, allow_nan=False)\n        with self.connect() as db:\n            status = db.execute(\n                "SELECT status FROM rehab_sessions WHERE id=?", (session_id,)\n            ).fetchone()\n            if status is None or status["status"] != "running":\n                raise ValueError("Session is missing or already finished")\n            db.execute(\n                "INSERT INTO rehab_reps VALUES (?,?,?,?,?,?,?)",\n                (\n                    session_id, rep_index, peak_angle_moving_joint,\n                    angles,\n                    None if target_reached is None else int(target_reached),\n                    outside, int(tracking_valid),\n                ),\n            )\n\n    def telemetry(self, session_id, timestamp_seconds, payload):\n        encoded = json.dumps(payload, allow_nan=False)\n        json.dumps(timestamp_seconds, allow_nan=False)\n        with self.connect() as db:\n            db.execute(\n                "INSERT INTO rehab_telemetry VALUES (?,?,?)",\n                (session_id, timestamp_seconds, encoded),\n            )\n\n    def valid_peaks(self, session_id):\n        with self.connect() as db:\n            rows = db.execute(\n                """SELECT peak_angle_moving_joint FROM rehab_reps\n                WHERE session_id=? AND tracking_valid=1\n                AND peak_angle_moving_joint IS NOT NULL ORDER BY rep_index""",\n                (session_id,),\n            ).fetchall()\n        return [row[0] for row in rows]\n\n    def history(self, session_id, count):\n        if isinstance(count, bool) or not isinstance(count, int) or count < 1:\n            raise ValueError("Configure a positive history session count")\n        with self.connect() as db:\n            current = db.execute(\n                "SELECT rowid AS order_id,* FROM rehab_sessions WHERE id=?",\n                (session_id,),\n            ).fetchone()\n            if current is None:\n                raise ValueError("Unknown session")\n            # Scope is intentionally NOT a comparison criterion.\n            rows = db.execute(\n                """SELECT s.id,s.timestamp,u.payload\n                FROM rehab_sessions s\n                JOIN rehab_summaries u ON s.id=u.session_id\n                WHERE s.patient_id=? AND s.exercise_id=? AND s.side=?\n                AND s.measurement_method=? AND s.config_version=?\n                AND s.reference_edition IS ?\n                AND s.rowid < ?\n                ORDER BY s.rowid DESC LIMIT ?""",\n                (\n                    current["patient_id"], current["exercise_id"],\n                    current["side"], current["measurement_method"],\n                    current["config_version"], current["reference_edition"],\n                    current["order_id"], count,\n                ),\n            ).fetchall()\n        return [\n            dict(\n                id=r["id"], timestamp=r["timestamp"],\n                summary=json.loads(r["payload"]),\n            ) for r in rows\n        ]\n\n    def finish(\n        self, session_id, assessment, supporting_times,\n        trend_count, status="finished",\n    ):\n        if status not in ("finished", "stopped", "interrupted"):\n            raise ValueError("Invalid finish status")\n        prior = self.history(session_id, trend_count)\n        peaks = self.valid_peaks(session_id)\n        previous = self.valid_peaks(prior[0]["id"]) if prior else None\n        summary = compare_sessions(peaks, previous)\n        summary.update({\n            "wnl_label": assessment["label"],\n            "provisional_flag": assessment["provisional"],\n            "assessment": assessment,\n            "supporting_joint_monitoring": {},\n            "trend": list(reversed(prior)),\n        })\n        for joint, times in supporting_times.items():\n            within, outside, uncertain = (\n                float(times.get(k, 0))\n                for k in ("within_seconds", "outside_seconds", "uncertain_seconds")\n            )\n            if min(within, outside, uncertain) < 0:\n                raise ValueError("Monitoring durations cannot be negative")\n            valid = within + outside\n            total = valid + uncertain\n            summary["supporting_joint_monitoring"][joint] = {\n                "within_percent": 100 * within / valid if valid else None,\n                "tracking_coverage_percent": 100 * valid / total if total else None,\n                "within_seconds": within,\n                "outside_seconds": outside,\n                "uncertain_seconds": uncertain,\n            }\n\n        with self.connect() as db:\n            rows = db.execute(\n                "SELECT target_reached FROM rehab_reps WHERE session_id=?",\n                (session_id,),\n            ).fetchall()\n            reached = sum(r[0] == 1 for r in rows)\n            missed = sum(r[0] == 0 for r in rows)\n            assessed = reached + missed\n            summary.update({\n                "reps_completed": len(rows),\n                "target_reached_count": reached,\n                "target_not_reached_count": missed,\n                "target_unassessed_count": len(rows) - assessed,\n                "completion_rate": reached / assessed if assessed else None,\n            })\n            encoded = json.dumps(summary, allow_nan=False)\n            db.execute(\n                "INSERT INTO rehab_summaries VALUES (?,?)",\n                (session_id, encoded),\n            )\n            db.execute(\n                "UPDATE rehab_sessions SET status=? WHERE id=?",\n                (status, session_id),\n            )\n        return summary\n'

TESTS = r'''
import tempfile
import unittest
from pathlib import Path
from station.rehab_extension.storage import RehabStore
from station.rehab_extension.core import assess_arom

class StorageTests(unittest.TestCase):
    def test_persistence_history_scope_and_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.sqlite3"
            store = RehabStore(path)
            first = store.start("test", "knee", "left", "component", "v1")
            store.add_rep(first, 1, 50, target_reached=True)
            store.add_rep(first, 2, 70, target_reached=False)
            result = store.finish(
                first, assess_arom(70, 135), {}, 3
            )
            self.assertEqual(result["avg_peak_arom"], 60)
            self.assertEqual(result["history_status"], "No previous session")

            store = RehabStore(path)
            second = store.start("test", "knee", "left", "leg", "v1")
            store.add_rep(second, 1, 80)
            result = store.finish(
                second, assess_arom(80, 135),
                {"hip": dict(
                    within_seconds=3, outside_seconds=1, uncertain_seconds=4
                )}, 3
            )
            self.assertEqual(result["difference_deg"], 20)
            self.assertEqual(result["previous_max_peak"], 70)
            self.assertEqual(result["target_unassessed_count"], 1)
            self.assertEqual(
                result["supporting_joint_monitoring"]["hip"]["within_percent"], 75
            )
            self.assertEqual(
                result["supporting_joint_monitoring"]["hip"]["tracking_coverage_percent"],
                50
            )

            other_side = store.start("test", "knee", "right", "whole_body", "v1")
            self.assertEqual(store.history(other_side, 3), [])

    def test_unreliable_rep_excluded_from_peak(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RehabStore(Path(folder) / "test.sqlite3")
            session = store.start("test", "knee", "left", "component", "v1")
            store.add_rep(session, 1, 150, tracking_valid=False)
            self.assertEqual(store.valid_peaks(session), [])
            with self.assertRaises(ValueError):
                store.history(session, None)

if __name__ == "__main__":
    unittest.main()
'''

def main():
    if not (MODULE.parent / "core.py").exists():
        raise SystemExit("Install Part 4 first.")
    files = {MODULE: CODE, TEST: TESTS}
    for path, text in files.items():
        if path.exists():
            raise SystemExit(f"STOP: already exists: {path}")
        compile(text, str(path), "exec")
    written = []
    try:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            written.append(path)
        result = subprocess.run([
            sys.executable, "-m", "unittest", "discover",
            "-s", "tests", "-p", "test_rehab_storage_extension.py", "-v",
        ], cwd=ROOT)
        if result.returncode:
            raise RuntimeError("Storage tests failed")
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    print("Storage module installed; 2 tests passed.")
    print("Tests used a temporary database; no patient records were created.")
    print("Live recording and summary UI are not connected yet.")

if __name__ == "__main__":
    main()