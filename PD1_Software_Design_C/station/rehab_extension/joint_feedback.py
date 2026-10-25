
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
