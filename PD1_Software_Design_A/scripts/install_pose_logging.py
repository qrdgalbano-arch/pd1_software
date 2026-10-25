import ast
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "station" / "engine.py"
MODULE = ROOT / "station" / "debug_pose_log.py"
MARKER = "# PD1_DEBUG_POSE_LOG_V1"

LOGGER = r'''
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
'''

def main():
    original = ENGINE.read_bytes()
    source = original.decode("utf-8-sig")
    if MARKER in source:
        print("Already installed. No files changed.")
        return
    if MODULE.exists():
        raise SystemExit("STOP: debug_pose_log.py already exists; no files changed.")

    tree = ast.parse(source)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "ExerciseEngine"
    )
    methods = {
        n.name: n for n in cls.body
        if isinstance(n, ast.FunctionDef)
    }

    def assignment(method, name, value):
        matches = [
            n for n in ast.walk(methods[method])
            if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Constant)
            and n.value.value is value
            and any(
                isinstance(t, ast.Attribute)
                and isinstance(t.value, ast.Name)
                and t.value.id == "self"
                and t.attr == name
                for t in n.targets
            )
        ]
        if len(matches) != 1:
            raise ValueError(f"Unexpected structure: {method}.{name}")
        return matches[0]

    start_node = assignment("start_session", "last_summary", None)
    end_node = assignment("_finish_session", "session", None)

    step = methods["_step"]
    updates = [
        n for n in step.body
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Call)
        and ast.unparse(n.value.func) == "self.twin.update"
    ]
    if len(updates) != 1:
        raise ValueError("Expected one direct twin.update in _step")
    update = updates[0]
    if "world_landmarks" not in ast.unparse(update):
        raise ValueError("Expected world-landmark analysis; no files changed")

    lines = source.splitlines(keepends=True)
    edits = [
        (start_node.lineno - 1,
         "from station.debug_pose_log import start as debug_start\n"
         "debug_start(self)\n"),
        (update.end_lineno,
         "from station.debug_pose_log import sample as debug_sample\n"
         "debug_sample(self, landmarks, t)\n"),
        (end_node.lineno - 1,
         "from station.debug_pose_log import end as debug_end\n"
         "debug_end(self, reason)\n"),
    ]
    for offset, code in sorted(edits, reverse=True):
        reference = lines[offset - 1] if offset == update.end_lineno else lines[offset]
        indent = reference[:len(reference) - len(reference.lstrip())]
        if offset == update.end_lineno:
            reference = lines[update.lineno - 1]
            indent = reference[:len(reference) - len(reference.lstrip())]
        lines.insert(
            offset,
            "".join(indent + row + "\n" for row in code.splitlines())
        )

    updated = "".join(lines) + "\n" + MARKER + "\n"
    compile(updated, str(ENGINE), "exec")
    compile(LOGGER, str(MODULE), "exec")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = ROOT / "patch_backups" / f"pose_logging_{stamp}"
    backup.mkdir(parents=True)
    shutil.copy2(ENGINE, backup / "engine.py")

    if ENGINE.read_bytes() != original:
        raise RuntimeError("Engine changed during installation")

    ignore = ROOT / ".gitignore"
    old_ignore = ignore.read_bytes() if ignore.exists() else None
    if old_ignore is not None:
        (backup / "gitignore.original").write_bytes(old_ignore)
    try:
        MODULE.write_text(LOGGER, encoding="utf-8")
        ENGINE.write_text(updated, encoding="utf-8")
        existing = ignore.read_text(encoding="utf-8-sig") if ignore.exists() else ""
        additions = [
            rule for rule in ("/debug_pose_logs/", "/patch_backups/")
            if rule not in existing.splitlines()
        ]
        if additions:
            ignore.write_text(
                existing.rstrip() + "\n" + "\n".join(additions) + "\n",
                encoding="utf-8"
            )
    except Exception:
        ENGINE.write_bytes(original)
        MODULE.unlink(missing_ok=True)
        if old_ignore is not None:
            ignore.write_bytes(old_ignore)
        elif ignore.exists():
            ignore.unlink()
        raise

    print("Pose logger installed; Python syntax checks passed.")
    print(f"Engine backup: {backup / 'engine.py'}")
    print("Enable with: $env:PD1_DEBUG_POSE = '1'")
    print("Logs: PD_SOFTWARE/debug_pose_logs/")
    print("No clinical thresholds or evaluation rules changed.")

if __name__ == "__main__":
    main()