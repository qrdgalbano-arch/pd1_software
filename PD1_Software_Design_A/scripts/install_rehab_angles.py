from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "station" / "rehab_extension" / "angles.py"
TEST = ROOT / "tests" / "test_rehab_angles_extension.py"

CODE = r'''
"""World-XYZ geometric estimates; not validated clinical goniometry."""
import math

EPS = 1e-10  # Numerical degeneracy guard, not a clinical threshold.

def vector(v):
    values = tuple(float(x) for x in v)
    if len(values) != 3 or not all(math.isfinite(x) for x in values):
        raise ValueError("Expected three finite coordinates")
    return values

def sub(a, b):
    return tuple(x - y for x, y in zip(vector(a), vector(b)))

def dot(a, b):
    return sum(x*y for x, y in zip(a, b))

def unit(v):
    v = vector(v)
    length = math.sqrt(dot(v, v))
    if length < EPS:
        raise ValueError("Degenerate direction")
    return tuple(x / length for x in v)

def between(a, b):
    a, b = unit(a), unit(b)
    return math.degrees(math.acos(max(-1, min(1, dot(a, b)))))

def knee_flexion(hip, knee, ankle):
    """Straight thigh/shank = 0 degrees flexion."""
    return 180.0 - between(sub(hip, knee), sub(ankle, knee))

def ankle_motion(knee, ankle, heel, foot_index):
    """Neutral 0; dorsiflexion positive; plantarflexion negative.

    Uses heel-to-foot-index as the foot axis. This is a geometric proxy,
    not a direct observation of the anatomical goniometer foot axis.
    Knee position must be stored alongside the result.
    """
    proximal_shank = sub(knee, ankle)
    foot_axis = sub(foot_index, heel)
    return 90.0 - between(proximal_shank, foot_axis)

def hip_flexion(hip, knee, neutral_down, anterior):
    """Signed sagittal projection in an externally calibrated body frame.

    neutral_down: direction of the thigh in anatomical neutral.
    anterior: forward anatomical direction.
    These axes must be provided in the SAME XYZ frame as the landmarks.
    They must move with the person's body, not remain camera-fixed.
    """
    down = unit(neutral_down)
    forward = vector(anterior)
    forward = unit(tuple(
        forward[i] - dot(forward, down) * down[i]
        for i in range(3)
    ))
    thigh = unit(sub(knee, hip))
    x, y = dot(thigh, down), dot(thigh, forward)
    if math.hypot(x, y) < EPS:
        raise ValueError("Hip sagittal projection is indeterminate")
    return math.degrees(math.atan2(y, x))

IDS = {
    "left": dict(hip=23, knee=25, ankle=27, heel=29, foot=31),
    "right": dict(hip=24, knee=26, ankle=28, heel=30, foot=32),
}

def read_point(points, index, threshold):
    p = points.get(str(index), points.get(index))
    if p is None:
        raise ValueError("Missing landmark")
    def get(name):
        return p.get(name) if isinstance(p, dict) else getattr(p, name, None)
    visibility = get("visibility")
    if (
        visibility is None
        or not math.isfinite(float(visibility))
        or float(visibility) < threshold
    ):
        raise ValueError("Low landmark visibility")
    return vector((get("x"), get("y"), get("z")))

def measure(world_points, side, minimum_visibility, body_frame=None):
    if side not in IDS:
        raise ValueError("Side must be left or right")
    if (
        minimum_visibility is None
        or isinstance(minimum_visibility, bool)
        or not math.isfinite(float(minimum_visibility))
        or not 0 <= float(minimum_visibility) <= 1
    ):
        raise ValueError("A configured visibility threshold is required")

    points = world_points or {}
    ids = IDS[side]
    results = {}

    def get(name):
        return read_point(points, ids[name], minimum_visibility)

    functions = {
        "knee": lambda: knee_flexion(get("hip"), get("knee"), get("ankle")),
        "ankle": lambda: ankle_motion(
            get("knee"), get("ankle"), get("heel"), get("foot")
        ),
    }
    if body_frame is not None:
        functions["hip"] = lambda: hip_flexion(
            get("hip"), get("knee"),
            body_frame["neutral_down"], body_frame["anterior"],
        )

    for joint in ("hip", "knee", "ankle"):
        if joint not in functions:
            results[joint] = {
                "angle": None, "tracked": False,
                "state": "Calibration required",
            }
            continue
        try:
            angle = functions[joint]()
            results[joint] = {
                "angle": angle, "tracked": True, "state": "Tracked",
            }
        except (ValueError, TypeError, KeyError, OverflowError):
            results[joint] = {
                "angle": None, "tracked": False,
                "state": "Tracking uncertain",
            }

    results["ankle"]["knee_position_deg"] = results["knee"]["angle"]
    return results
'''

TESTS = r'''
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
'''

def main():
    if not (MODULE.parent / "core.py").exists():
        raise SystemExit("Install Part 4 first.")
    files = {MODULE: CODE, TEST: TESTS}
    for path, code in files.items():
        if path.exists():
            raise SystemExit(f"STOP: already exists: {path}")
        compile(code, str(path), "exec")
    written = []
    try:
        for path, code in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8")
            written.append(path)
        result = subprocess.run([
            sys.executable, "-m", "unittest", "discover",
            "-s", "tests", "-p", "test_rehab_angles_extension.py", "-v",
        ], cwd=ROOT)
        if result.returncode:
            raise RuntimeError("Angle tests failed")
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    print("XYZ angle functions installed; 12 tests passed.")
    print("Existing live measurements unchanged. No clinical validation implied.")

if __name__ == "__main__":
    main()