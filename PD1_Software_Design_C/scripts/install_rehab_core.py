from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "station" / "rehab_extension"
TEST = ROOT / "tests" / "test_rehab_core_extension.py"

CORE = r'''
"""Shared assessment and visual feedback; independent of avatar scope."""
import math

WNL = "Within Normal Limits"
DECREASED = "Decreased Range of Motion"
UNAVAILABLE = "Assessment unavailable"

def finite(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )

def assess_arom(peak, reference, wnl_tolerance=None, tracked=True):
    """Peak/reference are directional magnitudes, not signed ankle angles."""
    provisional = wnl_tolerance is None
    result = {
        "label": UNAVAILABLE,
        "provisional": provisional,
        "tag": "Provisional – PT criteria not set" if provisional else None,
        "note": None,
        "peak_deg": peak if finite(peak) else None,
        "reference_deg": reference if finite(reference) else None,
    }
    if not tracked or not finite(peak) or not finite(reference):
        return result
    if peak < 0 or reference < 0:
        return result
    tolerance = 0 if provisional else wnl_tolerance
    if not finite(tolerance) or tolerance < 0:
        return result
    result["label"] = DECREASED if peak < reference - tolerance else WNL
    if peak > reference:
        result["note"] = "exceeds reference"
    return result

def position(angle, target, tolerance, tracked=True, approved=False):
    if not tracked or not finite(angle):
        return {"label": "Tracking uncertain", "deviation_deg": None}
    if (
        not approved
        or not finite(target)
        or not finite(tolerance)
        or tolerance < 0
    ):
        return {"label": "PT criteria not set", "deviation_deg": None}
    deviation = angle - target
    return {
        "label": (
            "Within prescribed limits"
            if abs(deviation) <= tolerance
            else "Outside prescribed limits"
        ),
        "deviation_deg": deviation,
    }

def redness(
    deviation, tolerance, full_scale, *,
    tracked=True, approved=False,
    moving=False, inside_prescribed_range=False,
):
    if not tracked or not approved:
        return 0.0
    if moving and inside_prescribed_range:
        return 0.0
    if not all(finite(v) for v in (deviation, tolerance, full_scale)):
        return 0.0
    if tolerance < 0 or full_scale <= 0:
        return 0.0
    return max(0.0, min(1.0, (abs(deviation) - tolerance) / full_scale))

def joint_redness(scope, parameters):
    """Rendering scope never changes evaluation of the three joints."""
    if scope not in ("component", "leg", "whole_body"):
        raise ValueError("Unknown design_scope")
    return {
        name: redness(**parameters[name]) if name in parameters else 0.0
        for name in ("hip", "knee", "ankle")
    }

def target_completion(peak, target, tolerance, *, endpoint=False, approved=False):
    if not endpoint:
        return None
    if not approved or not all(finite(v) for v in (peak, target, tolerance)):
        return None
    if tolerance < 0:
        return None
    return "Target reached" if peak >= target - tolerance else "Target not reached"

def compare_sessions(current_peaks, previous_peaks=None):
    current = [v for v in current_peaks if finite(v)]
    previous = [
        v for v in (previous_peaks or []) if finite(v)
    ]
    average = sum(current) / len(current) if current else None
    prior_average = sum(previous) / len(previous) if previous else None
    return {
        "avg_peak_arom": average,
        "max_peak": max(current) if current else None,
        "previous_avg_peak_arom": prior_average,
        "previous_max_peak": max(previous) if previous else None,
        "difference_deg": (
            average - prior_average
            if average is not None and prior_average is not None
            else None
        ),
        "history_status": (
            "Previous session available" if previous else "No previous session"
        ),
    }
'''

TESTS = r'''
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
'''

def main():
    files = {
        PACKAGE / "__init__.py": '"""Additive rehabilitation extension."""\n',
        PACKAGE / "core.py": CORE,
        TEST: TESTS,
    }
    for path in files:
        if path.exists():
            raise SystemExit(f"STOP: file already exists: {path}")
    for path, text in files.items():
        compile(text, str(path), "exec")

    written = []
    try:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            written.append(path)
        result = subprocess.run(
            [
                sys.executable, "-m", "unittest", "discover",
                "-s", "tests", "-p", "test_rehab_core_extension.py", "-v"
            ],
            cwd=ROOT,
        )
        if result.returncode:
            raise RuntimeError("Core tests failed")
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    print("Shared core installed. Tests passed.")
    print("Existing evaluator and UI have NOT been changed.")

if __name__ == "__main__":
    main()