
"""Geometric test fixtures, not patient measurements or PT tolerances."""
import math
import unittest
from station.rehab_extension.angles import (
    knee_flexion, ankle_motion, hip_flexion, measure,
)

class AngleTests(unittest.TestCase):
    def test_knee_neutral(self):
        self.assertAlmostEqual(
            knee_flexion((0,1,0), (0,0,0), (0,-1,0)), 0
        )

    def test_knee_bent(self):
        self.assertAlmostEqual(
            knee_flexion((0,1,0), (0,0,0), (1,0,0)), 90
        )

    def test_ankle_neutral(self):
        self.assertAlmostEqual(
            ankle_motion((0,1,0), (0,0,0), (0,0,0), (0,0,1)), 0
        )

    def test_dorsiflexion(self):
        self.assertAlmostEqual(
            ankle_motion((0,1,0), (0,0,0), (0,0,0), (0,1,1)), 45
        )

    def test_plantarflexion(self):
        self.assertAlmostEqual(
            ankle_motion((0,1,0), (0,0,0), (0,0,0), (0,-1,1)), -45
        )

    def test_hip_neutral_and_flexed(self):
        down, front = (0,-1,0), (0,0,1)
        self.assertAlmostEqual(
            hip_flexion((0,0,0), down, down, front), 0
        )
        self.assertAlmostEqual(
            hip_flexion((0,0,0), front, down, front), 90
        )

    def test_hip_extension_negative(self):
        self.assertAlmostEqual(
            hip_flexion(
                (0,0,0), (0,-1,-1), (0,-1,0), (0,0,1)
            ), -45
        )

    def test_rotation_invariance(self):
        def rotate(p):
            x, y, z = p
            return (z, x, y)
        original = [(0,1,0), (0,0,0), (1,-1,0)]
        self.assertAlmostEqual(
            knee_flexion(*original),
            knee_flexion(*(rotate(p) for p in original)),
        )

    def test_missing_tracking(self):
        result = measure({}, "left", 0.5)
        self.assertEqual(result["knee"]["state"], "Tracking uncertain")
        self.assertIsNone(result["ankle"]["angle"])
        self.assertEqual(result["hip"]["state"], "Calibration required")

    def test_visibility_and_knee_context(self):
        coords = {
            23: (0,2,0), 25: (0,1,0), 27: (0,0,0),
            29: (0,0,0), 31: (0,0,1),
        }
        points = {
            str(i): dict(zip(("x","y","z"), p), visibility=1)
            for i, p in coords.items()
        }
        result = measure(points, "left", 0.5)
        self.assertAlmostEqual(result["ankle"]["knee_position_deg"], 0)
        points["31"]["visibility"] = 0
        self.assertFalse(measure(points, "left", 0.5)["ankle"]["tracked"])

    def test_no_visibility_default(self):
        with self.assertRaises(ValueError):
            measure({}, "left", None)

    def test_degenerate_geometry(self):
        with self.assertRaises(ValueError):
            knee_flexion((0,0,0), (0,0,0), (0,1,0))

if __name__ == "__main__":
    unittest.main()
