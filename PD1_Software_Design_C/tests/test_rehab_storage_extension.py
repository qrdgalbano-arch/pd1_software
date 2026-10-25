
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
