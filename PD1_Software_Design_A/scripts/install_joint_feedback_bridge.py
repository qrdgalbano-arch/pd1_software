import ast
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
PACKAGE = ROOT / "station" / "rehab_extension"
ENGINE = ROOT / "station" / "engine.py"
APP = ROOT / "web" / "app.js"
HTML = ROOT / "web" / "index.html"
BACKEND = PACKAGE / "joint_feedback.py"
FRONTEND = ROOT / "web" / "rehab-joint-feedback.js"
SETTINGS = ROOT / "config" / "rehab_extension" / "settings.json"
SCHEMA = SETTINGS.parent / "schemas" / "settings.json"
MARKER = "# PD1_REHAB_JOINT_FEEDBACK_V1"
APP_MARKER = "// PD1_REHAB_JOINT_FEEDBACK_V1"

CODE = r'''
"""Shared joint feedback; approval and tracking fail closed."""
import copy
import json
import math
import logging
from functools import wraps
from .core import position, redness

log = logging.getLogger("station.rehab.feedback")
JOINTS = ("hip", "knee", "ankle")

def finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )

def evaluate_joints(cfg, readings, verified=False):
    result = {}
    moving = cfg["moving_joint"]
    for joint in JOINTS:
        reading = readings.get(joint, {})
        angle = reading.get("angle")
        tracked = reading.get("tracked") is True and finite(angle)
        entry = {
            "state": "Tracking uncertain",
            "tracked": tracked,
            "intensity": 0.0,
            "deviation_deg": None,
            "evaluated": False,
            "moving_joint": joint == moving,
        }
        result[joint] = entry
        if not tracked:
            continue
        if not verified:
            entry["state"] = "Not assessed: verified PT approval unavailable"
            continue

        if joint == moving:
            rule = cfg["moving_joint_protocol"]
            low, high = rule["range_min_deg"], rule["range_max_deg"]
            tolerance = rule["target_tolerance_deg"]
            scale = rule["redness_full_scale_deg"]
            if (
                not all(finite(v) for v in (low, high, tolerance, scale))
                or low > high or tolerance < 0 or scale <= 0
            ):
                entry["state"] = "PT criteria not set"
                continue
            inside = low <= angle <= high
            deviation = angle - min(max(angle, low), high)
            entry.update({
                "evaluated": True,
                "deviation_deg": deviation,
                "state": (
                    "Within prescribed range"
                    if abs(deviation) <= tolerance
                    else "Outside prescribed range"
                ),
                "intensity": redness(
                    deviation, tolerance, scale,
                    approved=True, tracked=True, moving=True,
                    inside_prescribed_range=inside,
                ),
            })
        else:
            rule = cfg["supporting_joints"].get(joint)
            if not rule or not rule.get("enabled"):
                entry["state"] = "Rule disabled"
                continue
            if rule.get("pt_confirmation_required"):
                entry["state"] = "PT confirmation required"
                continue
            outcome = position(
                angle, rule.get("target_deg"), rule.get("tolerance_deg"),
                tracked=True, approved=True,
            )
            entry.update(outcome)
            entry["evaluated"] = (
                outcome["label"] in (
                    "Within prescribed limits", "Outside prescribed limits"
                )
            )
            entry["state"] = outcome["label"]
            entry["intensity"] = redness(
                outcome["deviation_deg"],
                rule.get("tolerance_deg"),
                rule.get("redness_full_scale_deg"),
                tracked=True, approved=True,
            )
    return result

class Monitor:
    def __init__(self):
        self.previous = None
        self.last_t = None
        self.times = {
            j: {
                "within_seconds": 0.0,
                "outside_seconds": 0.0,
                "uncertain_seconds": 0.0,
                "unassessed_seconds": 0.0,
            } for j in JOINTS
        }
        self.feedback = {}
        self.note = "Waiting for measurements"

    def update(self, engine):
        attempt = getattr(engine, "_rehab_attempt", None)
        if attempt is None:
            return
        data = getattr(engine, "_rehab_measurements", {})
        t = data.get("monotonic_seconds")
        if not finite(t) or t == self.last_t:
            return

        permission = getattr(engine, "_rehab_permission", {})
        # Existing guard never issues verified=True.
        verified = (
            permission.get("approved") is True
            and permission.get("verified") is True
        )
        self.feedback = evaluate_joints(
            attempt.cfg, data.get("joints", {}), verified
        )
        phase = engine.session.get("phase") if engine.session else None
        gap = attempt.settings["tracking"].get(
            "maximum_monitoring_gap_seconds"
        )

        eligible = phase == "exercising"
        if (
            eligible and self.previous is not None and self.last_t is not None
            and finite(gap) and gap > 0
        ):
            dt = t - self.last_t
            if 0 < dt <= gap:
                for joint, before in self.previous.items():
                    after = self.feedback[joint]
                    duration = self.times[joint]
                    # Both endpoints must be tracked/evaluable.
                    if not before["tracked"] or not after["tracked"]:
                        duration["uncertain_seconds"] += dt
                    elif not before["evaluated"] or not after["evaluated"]:
                        duration["unassessed_seconds"] += dt
                    elif (
                        before["state"] == "Within prescribed limits"
                        and after["state"] == "Within prescribed limits"
                    ):
                        duration["within_seconds"] += dt
                    elif (
                        before["state"] == "Outside prescribed limits"
                        and after["state"] == "Outside prescribed limits"
                    ):
                        duration["outside_seconds"] += dt
                    else:
                        # Do not guess when a transition happened.
                        duration["unassessed_seconds"] += dt

        self.note = (
            "Timing unavailable: PT monitoring-gap parameter not set"
            if not finite(gap) or gap <= 0
            else "Tracked endpoint intervals only; transitions are unassessed"
        )
        self.last_t = t
        self.previous = copy.deepcopy(self.feedback) if eligible else None

    def summary(self, supporting):
        result = {}
        for joint in supporting:
            time = self.times[joint]
            assessed = time["within_seconds"] + time["outside_seconds"]
            known = assessed + time["unassessed_seconds"]
            total = known + time["uncertain_seconds"]
            result[joint] = {
                **time,
                "state": self.feedback.get(joint, {}).get(
                    "state", "Not assessed"
                ),
                "within_percent": (
                    100 * time["within_seconds"] / assessed if assessed else None
                ),
                "tracking_coverage_percent": (
                    100 * known / total if total else None
                ),
                "assessment_coverage_percent": (
                    100 * assessed / total if total else None
                ),
                "timing_note": self.note,
            }
        return result

def install(cls):
    if getattr(cls, "_rehab_joint_feedback_installed", False):
        return
    original_start = cls.start_session
    original_step = cls._step
    original_finish = cls._finish_session
    original_pause = cls.pause_session
    original_snapshot = cls.snapshot

    @wraps(original_start)
    def start(self, *args, **kwargs):
        result = original_start(self, *args, **kwargs)
        self._rehab_joint_monitor = Monitor()
        return result

    @wraps(original_step)
    def step(self, landmarks, t):
        result = original_step(self, landmarks, t)
        monitor = getattr(self, "_rehab_joint_monitor", None)
        if monitor and self.session is not None:
            try:
                monitor.update(self)
            except Exception:
                log.exception("Joint feedback update failed")
                monitor.feedback = {}
                monitor.previous = None
        return result

    @wraps(original_pause)
    def pause(self):
        result = original_pause(self)
        monitor = getattr(self, "_rehab_joint_monitor", None)
        if monitor:
            monitor.previous = None
            monitor.last_t = None
        return result

    @wraps(original_finish)
    def finish(self, t, reason):
        monitor = getattr(self, "_rehab_joint_monitor", None)
        attempt = getattr(self, "_rehab_attempt", None)
        if monitor and attempt:
            try:
                monitor.update(self)
            except Exception:
                log.exception("Final joint feedback update failed")
        result = original_finish(self, t, reason)
        summary = getattr(self, "_rehab_summary", None)
        if result is not None and summary and monitor and attempt:
            try:
                summary["supporting_joint_monitoring"] = monitor.summary(
                    attempt.cfg["supporting_joints"]
                )
                with attempt.store.connect() as db:
                    db.execute(
                        "UPDATE rehab_summaries SET payload=? WHERE session_id=?",
                        (json.dumps(summary, allow_nan=False), attempt.id),
                    )
            except Exception:
                log.exception("Supporting-joint summary persistence failed")
                self._rehab_recording_error = (
                    "Supporting-joint summary could not be persisted"
                )
        return result

    @wraps(original_snapshot)
    def snapshot(self):
        state = dict(original_snapshot(self))
        monitor = getattr(self, "_rehab_joint_monitor", None)
        feedback = copy.deepcopy(monitor.feedback) if monitor else {}
        live = getattr(self, "_rehab_measurements", {})
        eligible = (
            self.session is not None
            and self.session.get("phase") == "exercising"
            and not self.camera_error
            and state.get("pose_detected") is not False
            and live.get("state") == "Measurement preview"
        )
        if not eligible:
            feedback = {}
        state["rehab_joint_feedback"] = {
            "joints": feedback,
            "clinical_approval": False,
            "description": (
                "Joint-position deviation: color intensity indicates "
                "departure from your prescribed exercise limits."
            ),
            "timing_note": monitor.note if monitor else "Not assessed",
        }
        return state

    cls.start_session = start
    cls._step = step
    cls._finish_session = finish
    cls.pause_session = pause
    cls.snapshot = snapshot
    cls._rehab_joint_feedback_installed = True
'''

JS = r'''
import * as THREE from "three";

let latest = {};
let received = 0;

export function setRehabJointFeedback(state) {
  latest = state?.rehab_joint_feedback?.joints || {};
  received = performance.now();

  let text = document.getElementById("rehab-redness-description");
  const host = document.getElementById("twin-viewport");
  if (!text && host) {
    text = document.createElement("p");
    text.id = "rehab-redness-description";
    text.className = "hint";
    text.textContent =
      "Joint-position deviation: color intensity indicates departure " +
      "from your prescribed exercise limits.";
    host.append(text);
  }
}

export function attachRehabJointColors(avatar) {
  if (avatar._rehabJointColors) return;
  if (typeof avatar.frameCamera !== "function") {
    console.warn("Shared joint coloring unavailable: frameCamera not found");
    return;
  }
  const original = avatar.frameCamera.bind(avatar);
  const neutral = new THREE.Color(0x8a96a3);
  const red = new THREE.Color(0xef4444);

  avatar.frameCamera = function(...args) {
    const result = original(...args);
    // Transport freshness guard, not a clinical threshold.
    const fresh = performance.now() - received < 2000;
    for (const side of ["left", "right"]) {
      for (const joint of ["hip", "knee", "ankle"]) {
        const marker = this.markers?.[side]?.[joint];
        if (!marker?.material?.color) continue;
        const reading = fresh && side === this.side ? latest[joint] : null;
        const intensity = reading?.tracked === true
          && reading?.evaluated === true
          && Number.isFinite(reading.intensity)
          ? Math.max(0, Math.min(1, reading.intensity)) : 0;
        marker.material.color.copy(neutral).lerp(red, intensity);
      }
    }
    return result;
  };
  avatar._rehabJointColors = true;
}
'''

def main():
    sys.path.insert(0, str(ROOT))
    required = [
        PACKAGE / "session_bridge.py", PACKAGE / "core.py",
        SETTINGS, SCHEMA, ENGINE, APP, HTML,
    ]
    if not all(path.is_file() for path in required):
        raise SystemExit("STOP: session-summary bridge and previous parts required.")

    originals = {
        path: path.read_bytes() for path in (ENGINE, APP, HTML, SETTINGS, SCHEMA)
    }
    engine = originals[ENGINE].decode("utf-8-sig")
    app = originals[APP].decode("utf-8-sig")
    html = originals[HTML].decode("utf-8-sig")

    if (
        MARKER in engine or APP_MARKER in app
        or BACKEND.exists() or FRONTEND.exists()
    ):
        raise SystemExit("Already/partially installed; nothing overwritten.")

    constructors = list(re.finditer(
        r"\bavatar\s*=\s*new\s+TwinAvatar\s*\([^\n;]*\)\s*;", app
    ))
    renders = list(re.finditer(
        r"\bfunction\s+render\s*\(\s*state\s*\)\s*\{", app
    ))
    if len(constructors) != 1 or len(renders) != 1:
        raise SystemExit("STOP: expected one avatar constructor and render(state).")

    changes = [
        (
            constructors[0].end(),
            "\n    attachRehabJointColors(avatar);\n"
        ),
        (
            renders[0].end(),
            "\n  setRehabJointFeedback(state);\n"
        ),
    ]
    app_new = app
    for offset, inserted in sorted(changes, reverse=True):
        app_new = app_new[:offset] + inserted + app_new[offset:]
    app_new = (
        APP_MARKER + "\n"
        'import { setRehabJointFeedback, attachRehabJointColors } '
        'from "/static/rehab-joint-feedback.js?v=1";\n' + app_new
    )
    engine_new = (
        engine + "\n\n" + MARKER + "\n"
        "from station.rehab_extension.joint_feedback import install "
        "as _install_joint_feedback\n"
        "_install_joint_feedback(ExerciseEngine)\n"
    )
    html_new, count = re.subn(
        r'(/static/app\.js)(?:\?[^"\']*)?(?=["\'])',
        r'\1?v=rehab-joint-feedback-1', html
    )
    if count != 1:
        raise SystemExit("STOP: expected one app.js reference.")

    settings = json.loads(originals[SETTINGS].decode("utf-8-sig"))
    specification = json.loads(originals[SCHEMA].decode("utf-8-sig"))
    settings["tracking"].setdefault("maximum_monitoring_gap_seconds", None)
    tracking_schema = specification["properties"]["tracking"]
    tracking_schema["properties"]["maximum_monitoring_gap_seconds"] = {
        "type": ["number", "null"],
        "exclusiveMinimum": 0,
        "description": "PT_SET: maximum interval credited to monitoring.",
    }

    compile(CODE, str(BACKEND), "exec")
    compile(engine_new, str(ENGINE), "exec")
    namespace = {
        "__file__": str(BACKEND),
        "__package__": "station.rehab_extension",
    }
    exec(compile(CODE, str(BACKEND), "exec"), namespace)
    evaluate = namespace["evaluate_joints"]

    # Artificial fixtures only; not project clinical settings.
    cfg = {
        "moving_joint": "hip",
        "moving_joint_protocol": {
            "range_min_deg": 0, "range_max_deg": 60,
            "target_tolerance_deg": 2, "redness_full_scale_deg": 8,
        },
        "supporting_joints": {
            "knee": {
                "enabled": True, "target_deg": 0,
                "tolerance_deg": 2, "redness_full_scale_deg": 8,
            }
        },
    }
    readings = {
        "hip": {"tracked": True, "angle": 30},
        "knee": {"tracked": True, "angle": 6},
        "ankle": {"tracked": False, "angle": None},
    }
    unapproved = evaluate(cfg, readings, verified=False)
    assert all(v["intensity"] == 0 for v in unapproved.values())
    tested = evaluate(cfg, readings, verified=True)
    assert tested["hip"]["intensity"] == 0
    assert tested["knee"]["intensity"] == 0.5
    assert tested["ankle"]["intensity"] == 0
    readings["knee"]["angle"] = 1
    assert evaluate(cfg, readings, True)["knee"]["intensity"] == 0

    node = shutil.which("node")
    if node:
        for source in (JS, app_new):
            checked = subprocess.run(
                [node, "--input-type=module", "--check"],
                input=source, text=True, encoding="utf-8",
                capture_output=True,
            )
            if checked.returncode:
                raise RuntimeError(checked.stderr)

    backup = ROOT / "patch_backups" / datetime.now().strftime(
        "joint_feedback_%Y%m%d_%H%M%S_%f"
    )
    backup.mkdir(parents=True)
    for path in originals:
        target = backup / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    if any(path.read_bytes() != data for path, data in originals.items()):
        raise RuntimeError("Project changed during installation")

    try:
        BACKEND.write_text(CODE, encoding="utf-8")
        FRONTEND.write_text(JS, encoding="utf-8")
        ENGINE.write_text(engine_new, encoding="utf-8")
        APP.write_text(app_new, encoding="utf-8")
        HTML.write_text(html_new, encoding="utf-8")
        SETTINGS.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        SCHEMA.write_text(json.dumps(specification, indent=2) + "\n", encoding="utf-8")
    except Exception:
        for path, data in originals.items():
            path.write_bytes(data)
        BACKEND.unlink(missing_ok=True)
        FRONTEND.unlink(missing_ok=True)
        raise

    print("SUPPORTING-JOINT MONITOR + SHARED MARKER COLORS INSTALLED.")
    print("Unapproved/uncertain measurements remain neutral.")
    print("Moving-joint in-range exemption tests passed.")
    print("Monitoring gap parameter added as null; no clinical value assumed.")
    print(f"Backup: {backup}")
    print("Browser/camera testing and verified PT approval remain outstanding.")

if __name__ == "__main__":
    main()
