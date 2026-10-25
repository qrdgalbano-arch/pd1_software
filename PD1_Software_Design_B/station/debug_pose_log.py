
"""Opt-in local debug telemetry. No camera images or patient names."""
import hashlib
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("station.debug_pose")

def clean(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return {
        key: clean(getattr(value, key))
        for key in ("x", "y", "z", "visibility", "presence")
        if hasattr(value, key)
    }

class PoseLog:
    def __init__(self):
        self.file = None
        self.failed = False
        self.count = 0

    def write(self, event, **payload):
        if self.file is None:
            return
        try:
            row = {
                "event": event,
                "utc": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
            self.file.write(
                json.dumps(clean(row), allow_nan=False) + "\n"
            )
            self.file.flush()
        except Exception:
            self.failed = True
            log.exception("POSE DEBUG LOG FAILED; exercise evaluation continues")
            self.close()

    def close(self):
        handle, self.file = self.file, None
        if handle:
            try:
                handle.close()
            except Exception:
                log.exception("Could not close pose debug log")

    def start(self, engine):
        self.close()
        self.failed = False
        self.count = 0
        if os.getenv("PD1_DEBUG_POSE", "0") != "1":
            return
        try:
            folder = ROOT / "debug_pose_logs"
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
            key = "".join(
                c if c.isalnum() or c in "_-" else "_"
                for c in engine.exercise_key
            )
            path = folder / f"{stamp}_{key}.txt"
            self.file = path.open("x", encoding="utf-8")
            cfg = json.dumps(
                clean(engine.cfg), sort_keys=True, allow_nan=False
            )
            digest = hashlib.sha256(cfg.encode()).hexdigest()
            self.write(
                "start",
                exercise=engine.exercise_key,
                prescribed_side=engine.side,
                config_sha256=digest,
                config_version=engine.cfg.get("config_version"),
                measurement_space="world_3d_inferred",
                clinically_validated=False,
                format_version=1,
            )
            print(f"POSE DEBUG LOG: {path}", flush=True)
        except Exception:
            self.failed = True
            self.close()
            log.exception("POSE DEBUG LOG COULD NOT START")

    def sample(self, engine, landmarks, t):
        if self.file is None:
            return
        self.count += 1
        self.write(
            "sample",
            sample_index=self.count,
            monotonic_seconds=t,
            phase=engine.session.get("phase"),
            prescribed_side=engine.side,
            active_side=getattr(engine.twin, "active_side", None),
            pose_detected=landmarks is not None,
            image_landmarks=landmarks,
            world_landmarks=getattr(landmarks, "world_landmarks", None),
            joints=engine.twin.as_dict(),
            camera_error=engine.camera_error,
        )

    def end(self, reason):
        self.write("end", reason=reason, samples=self.count)
        self.close()

def start(engine):
    try:
        instance = getattr(engine, "_debug_pose_log", None)
        if instance is None:
            instance = PoseLog()
            engine._debug_pose_log = instance
        instance.start(engine)
    except Exception:
        log.exception("Pose debug start hook failed")

def sample(engine, landmarks, t):
    try:
        instance = getattr(engine, "_debug_pose_log", None)
        if instance and engine.session is not None:
            instance.sample(engine, landmarks, t)
    except Exception:
        log.exception("Pose debug sample hook failed")

def end(engine, reason):
    try:
        instance = getattr(engine, "_debug_pose_log", None)
        if instance:
            instance.end(reason)
    except Exception:
        log.exception("Pose debug end hook failed")
