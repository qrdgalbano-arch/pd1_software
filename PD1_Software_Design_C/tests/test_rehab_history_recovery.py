
"""Artificial software fixtures, not patient validation evidence."""
import tempfile
import unittest
from pathlib import Path
from station.rehab_extension.storage import RehabStore
from station.rehab_extension.history_recovery import (
    enrich_summary, recover_interrupted,
)

class HistoryRecoveryTests(unittest.TestCase):
    def test_directions_are_separate(self):
        summary = {
            "moving_joint": "ankle",
            "directional_arom": {
                "dorsiflexion": {}, "plantarflexion": {}
            },
        }
        reps = [
            dict(rep_index=1, direction="positive", peak=10, tracking_valid=True),
            dict(rep_index=2, direction="positive", peak=20, tracking_valid=True),
            dict(rep_index=3, direction="negative", peak=40, tracking_valid=True),
        ]
        previous = [{
            "timestamp": "previous",
            "summary": {
                "directional_arom": {
                    "dorsiflexion": {"avg_peak_arom": 12, "max_peak": 18},
                    "plantarflexion": {"avg_peak_arom": 30, "max_peak": 35},
                }
            },
        }]
        result = enrich_summary(summary, previous, reps, True)
        self.assertEqual(
            result["directional_arom"]["dorsiflexion"]["avg_peak_arom"], 15
        )
        self.assertEqual(
            result["directional_arom"]["dorsiflexion"]["difference_deg"], 3
        )
        self.assertEqual(
            result["directional_arom"]["plantarflexion"]["difference_deg"], 10
        )

    def test_missing_history_is_not_fabricated(self):
        result = enrich_summary(
            {"moving_joint": "ankle", "directional_arom": {}}, [], [], False
        )
        entry = result["directional_arom"]["dorsiflexion"]
        self.assertIsNone(entry["avg_peak_arom"])
        self.assertIsNone(entry["difference_deg"])
        self.assertEqual(entry["history_status"], "No previous session")
        self.assertEqual(entry["trend"], [])

    def test_recovery_preserves_rep_data(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RehabStore(Path(folder) / "test.sqlite3")
            session = store.start("fixture", "knee", "left", "leg", "test")
            store.add_rep(session, 1, 50)
            self.assertEqual(recover_interrupted(store), [session])
            self.assertEqual(store.valid_peaks(session), [50])
            self.assertEqual(recover_interrupted(store), [])
            with store.connect() as db:
                row = db.execute(
                    "SELECT status FROM rehab_sessions WHERE id=?", (session,)
                ).fetchone()
                self.assertEqual(row["status"], "interrupted")

if __name__ == "__main__":
    unittest.main()
