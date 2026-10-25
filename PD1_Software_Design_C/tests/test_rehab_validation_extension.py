
"""Artificial numerical fixtures for software tests, not validation evidence."""
import unittest
from station.rehab_extension.validation import analyze

def row(person, camera, pt):
    return dict(
        participant_code=person, exercise_id="test", joint="knee",
        side="left", testing_condition="test",
        measurement_method="test", config_version="test",
        knee_position_deg="", camera_deg=camera, goniometer_deg=pt,
    )

class ValidationTests(unittest.TestCase):
    def test_statistics(self):
        result = analyze([
            row("a", 8, 10), row("b", 10, 10), row("c", 12, 10)
        ])
        self.assertAlmostEqual(result["mean_absolute_error_deg"], 4/3)
        self.assertEqual(result["bias_camera_minus_pt_deg"], 0)
        self.assertEqual(result["sample_sd_difference_deg"], 2)
        self.assertAlmostEqual(result["upper_limit_deg"], 3.92)
        self.assertFalse(result["deployment_approved"])

    def test_repeated_participants(self):
        result = analyze([row("a", 8, 10), row("a", 12, 10)])
        self.assertTrue(result["repeated_participants"])
        self.assertIsNone(result["upper_limit_deg"])

    def test_single_pair(self):
        result = analyze([row("a", 8, 10)])
        self.assertIsNone(result["lower_limit_deg"])

    def test_mixed_conditions_rejected(self):
        a, b = row("a", 8, 10), row("b", 12, 10)
        b["side"] = "right"
        with self.assertRaises(ValueError):
            analyze([a, b])

if __name__ == "__main__":
    unittest.main()
