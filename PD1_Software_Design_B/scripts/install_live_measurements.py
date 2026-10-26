import ast
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "station" / "engine.py"
MODULE = ROOT / "station" / "rehab_extension" / "live.py"
MARKER = "# PD1_REHAB_LIVE_MEASUREMENTS_V1"

CODE = r'''
"""Parallel measurement stream. Never modifies legacy evaluator inputs."""
import json
import math
from functools import wraps
from pathlib import Path
from .angles import measure

SETTINGS = (
    Path(__file__).resolve().parents[2]
    / "config" / "rehab_extension" / "settings.json"
)

class OneEuro:
    def __init__(self, minimum, beta, derivative):
        if (
            not all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v)
                for v in (minimum, beta, derivative)
            )
            or minimum <= 0 or beta < 0 or derivative <= 0
        ):
            raise ValueError("PT filter parameters are missing or invalid")
        self.minimum, self.beta, self.derivative = minimum, beta, derivative
        self.t = self.raw = self.filtered = None
        self.dx = 0.0

    def update(self, value, t):
        if self.t is None:
            self.t, self.raw, self.filtered = t, value, value
            return value
        dt = t - self.t
        if dt <= 0:
            return self.filtered

        def alpha(cutoff):
            return 1.0 / (1.0 + 1.0 / (2 * math.pi * cutoff * dt))

        a = alpha(self.derivative)
        self.dx += a * ((value - self.raw) / dt - self.dx)
        a = alpha(self.minimum + self.beta * abs(self.dx))
        self.filtered += a * (value - self.filtered)
        self.t, self.raw = t, value
        return self.filtered

class LiveMeasurements:
    def __init__(self):
        self.filters = {}
        self.identity = None
        self.error = None
        self.settings = None
        self.reload()

    def reload(self):
        try:
            self.settings = json.loads(
                SETTINGS.read_text(encoding="utf-8-sig")
            )
            self.error = None
        except (OSError, ValueError) as exc:
            self.settings = None
            self.error = str(exc)

    def update(self, engine, landmarks, t):
        session = engine.session
        identity = (
            session.get("client_session_id") if session else None,
            engine.exercise_key, engine.side,
        )
        if identity != self.identity:
            self.identity = identity
            self.filters.clear()
            self.reload()

        result = {
            "measurement_space": "world_3d_inferred",
            "method": "neutral_zero_extension_preview",
            "clinical_approval": False,
            "used_by_legacy_evaluator": False,
            "monotonic_seconds": t,
            "side": engine.side,
            "joints": {},
        }

        if self.settings is None:
            result["state"] = "Configuration unavailable"
            result["reason"] = self.error
            return result

        tracking = self.settings["tracking"]
        threshold = tracking["minimum_landmark_visibility"]
        spec = tracking["filter"]
        try:
            if spec["method"] != "one_euro":
                raise ValueError("Unsupported filter method")
            for joint in ("hip", "knee", "ankle"):
                if joint not in self.filters:
                    self.filters[joint] = OneEuro(
                        spec["min_cutoff"], spec["beta"],
                        spec["derivative_cutoff"],
                    )
            joints = measure(
                getattr(landmarks, "world_landmarks", None),
                engine.side, threshold,
                body_frame=None,
            )
        except (ValueError, TypeError, KeyError) as exc:
            self.filters.clear()
            result["state"] = "PT criteria not set"
            result["reason"] = str(exc)
            return result

        for joint, reading in joints.items():
            raw = reading["angle"]
            reading["raw_angle"] = raw
            if reading["tracked"]:
                reading["angle"] = self.filters[joint].update(raw, t)
            else:
                # Reinitialize rather than smooth across a tracking gap.
                self.filters.pop(joint, None)

        joints["ankle"]["knee_position_deg"] = joints["knee"]["angle"]
        result["joints"] = joints
        result["state"] = "Measurement preview"
        result["hip_calibration"] = "Required"
        return result

def install(cls):
    if getattr(cls, "_pd1_live_measurements", False):
        return
    original_step = cls._step
    original_publish = cls._publish

    @wraps(original_step)
    def step(self, landmarks, t):
        if not hasattr(self, "_rehab_live"):
            self._rehab_live = LiveMeasurements()
        paused = self.session is not None and self.session["phase"] == "paused"
        if not paused:
            try:
                self._rehab_measurements = self._rehab_live.update(
                    self, landmarks, t
                )
            except Exception:
                import logging
                logging.getLogger("station.rehab").exception(
                    "Extension measurement failed; legacy evaluation unchanged"
                )
                self._rehab_measurements = {
                    "state": "Measurement unavailable",
                    "clinical_approval": False,
                    "joints": {},
                }
        elif hasattr(self, "_rehab_measurements"):
            self._rehab_measurements = {
                **self._rehab_measurements, "state": "Paused"
            }
        return original_step(self, landmarks, t)

    @wraps(original_publish)
    def publish(self, t, landmarks):
        original_publish(self, t, landmarks)
        with self._lock:
            result = dict(getattr(self, "_rehab_measurements", {
                "state": "Waiting for camera processing", "joints": {}
            }))
            if landmarks is None or self.camera_error:
                result = {
                    **result,
                    "state": "Tracking uncertain",
                    "joints": {},
                }
            self.state = {**self.state, "rehab_measurements": result}

    cls._step = step
    cls._publish = publish
    cls._pd1_live_measurements = True
'''

def main():
    required = [
        MODULE.parent / "angles.py",
        ROOT / "config" / "rehab_extension" / "settings.json",
    ]
    if not all(path.exists() for path in required):
        raise SystemExit("Install the angles and configuration steps first.")
    original = ENGINE.read_bytes()
    source = original.decode("utf-8-sig")
    if MARKER in source:
        raise SystemExit("Already installed; nothing changed.")
    if MODULE.exists():
        raise SystemExit("live.py already exists; nothing overwritten.")

    tree = ast.parse(source)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "ExerciseEngine"
    )
    names = {
        n.name for n in cls.body if isinstance(n, ast.FunctionDef)
    }
    if not {"_step", "_publish"} <= names:
        raise SystemExit("Unexpected engine structure; nothing changed.")

    updated = (
        source + "\n\n" + MARKER + "\n"
        "from station.rehab_extension.live import install as "
        "_install_live_measurements\n"
        "_install_live_measurements(ExerciseEngine)\n"
    )
    compile(CODE, str(MODULE), "exec")
    compile(updated, str(ENGINE), "exec")

    # Deterministic filter tests only, not clinical validation.
    import importlib.util
    import types
    test_module = types.ModuleType("station.rehab_extension._live_test")
    test_module.__file__ = str(MODULE)
    test_module.__package__ = "station.rehab_extension"
    exec(compile(CODE, str(MODULE), "exec"), test_module.__dict__)
    filter_ = test_module.OneEuro(1.0, 0.0, 1.0)
    assert filter_.update(0.0, 0.0) == 0.0
    assert 0.0 < filter_.update(10.0, 1.0) < 10.0

    backup = ROOT / "patch_backups" / datetime.now().strftime(
        "live_%Y%m%d_%H%M%S_%f"
    )
    backup.mkdir(parents=True)
    shutil.copy2(ENGINE, backup / "engine.py")
    if ENGINE.read_bytes() != original:
        raise RuntimeError("Engine changed during installation")

    try:
        MODULE.write_text(CODE, encoding="utf-8")
        ENGINE.write_text(updated, encoding="utf-8")
    except Exception:
        ENGINE.write_bytes(original)
        MODULE.unlink(missing_ok=True)
        raise
    print("Live measurement stream installed; syntax/filter checks passed.")
    print(f"Backup: {backup}")
    print("Legacy evaluator unchanged. Restart station.")
    print("PT parameters remain null; no values were approved.")

if __name__ == "__main__":
    # Permit imports during installer checks when launched from scripts/.
    import sys
    sys.path.insert(0, str(ROOT))
    main()