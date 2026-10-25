
"""Numerical fixtures below test software; they are not clinical thresholds."""
import unittest
from station.rehab_extension.core import (
    WNL, DECREASED, UNAVAILABLE, assess_arom, position, redness,
    joint_redness, target_completion, compare_sessions,
)

class CoreTests(unittest.TestCase):
    def test_low_peak_is_decreased(self):
        self.assertEqual(assess_arom(60, 135, 0)["label"], DECREASED)

    def test_above_reference(self):
        result = assess_arom(140, 135, 0)
        self.assertEqual(result["label"], WNL)
        self.assertEqual(result["note"], "exceeds reference")

    def test_provisional(self):
        result = assess_arom(135, 135)
        self.assertTrue(result["provisional"])
        self.assertEqual(result["label"], WNL)
        self.assertFalse(assess_arom(135, 135, 0)["provisional"])

    def test_missing_slr_reference(self):
        self.assertEqual(assess_arom(60, None)["label"], UNAVAILABLE)

    def test_uncertain(self):
        self.assertEqual(
            assess_arom(135, 135, 0, tracked=False)["label"], UNAVAILABLE
        )
        self.assertEqual(
            position(None, 0, 2, tracked=False)["label"], "Tracking uncertain"
        )
        self.assertEqual(redness(20, 2, 8, tracked=False, approved=True), 0)

    def test_redness_scaling(self):
        self.assertEqual(redness(2, 2, 8, approved=True), 0)
        self.assertEqual(redness(6, 2, 8, approved=True), 0.5)
        self.assertEqual(redness(100, 2, 8, approved=True), 1)

    def test_unapproved_and_missing_parameters(self):
        self.assertEqual(redness(20, 2, 8), 0)
        self.assertEqual(redness(20, None, 8, approved=True), 0)
        self.assertEqual(redness(20, 2, None, approved=True), 0)

    def test_moving_joint_inside_range(self):
        self.assertEqual(
            redness(
                20, 2, 8, approved=True,
                moving=True, inside_prescribed_range=True,
            ), 0
        )

    def test_scope_independence(self):
        parameters = {
            j: dict(deviation=6, tolerance=2, full_scale=8, approved=True)
            for j in ("hip", "knee", "ankle")
        }
        results = [
            joint_redness(s, parameters)
            for s in ("component", "leg", "whole_body")
        ]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])
        self.assertEqual(set(results[0]), {"hip", "knee", "ankle"})

    def test_endpoint_only(self):
        self.assertIsNone(target_completion(60, 60, 0, approved=True))
        self.assertEqual(
            target_completion(60, 60, 0, endpoint=True, approved=True),
            "Target reached",
        )
        self.assertIsNone(target_completion(60, None, None, endpoint=True))

    def test_history(self):
        result = compare_sessions([60, 80], [50, 70])
        self.assertEqual(result["avg_peak_arom"], 70)
        self.assertEqual(result["max_peak"], 80)
        self.assertEqual(result["difference_deg"], 10)
        self.assertEqual(
            compare_sessions([60])["history_status"], "No previous session"
        )

    def test_invalid_numbers(self):
        self.assertEqual(assess_arom(float("nan"), 135)["label"], UNAVAILABLE)
        self.assertEqual(redness(float("inf"), 2, 8, approved=True), 0)

if __name__ == "__main__":
    unittest.main()
