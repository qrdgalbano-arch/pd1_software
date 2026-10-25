from .history_recovery import enrich_summary


"""Parallel extension evaluation and recording. Clinical use stays disabled."""

import copy

import hashlib

import json

import logging

import math

from functools import wraps

from pathlib import Path



from .core import assess_arom, compare_sessions

from .storage import RehabStore



log = logging.getLogger("station.rehab.sessions")

ROOT = Path(__file__).resolve().parents[2]

CONFIG = ROOT / "config" / "rehab_extension"



ALIASES = {'straight_leg_raising': 'straight_leg_raise', 'straight_leg_raise': 'straight_leg_raise', 'ankle_pumps': 'ankle_pumps', 'ankle_pump': 'ankle_pumps'}



def finite(value):

    return (

        isinstance(value, (int, float))

        and not isinstance(value, bool)

        and math.isfinite(value)

    )



class PreviewEvaluator:

    """Independent endpoint segmentation; no legacy angles or thresholds."""

    def __init__(self, cfg):

        self.cfg = cfg

        self.primary = cfg["moving_joint"]

        self.active = None

        self.reps = []

        self.note = "Waiting for tracked measurements"



    def update(self, joints, t):

        reading = joints.get(self.primary, {})

        value = reading.get("angle")

        if not reading.get("tracked") or not finite(value):

            if self.active:

                self.active["tracking_valid"] = False

            self.note = "Moving joint unavailable"

            return None



        rep_cfg = self.cfg["repetition"]

        start = rep_cfg["start_threshold_deg"]

        rest = rep_cfg["return_threshold_deg"]

        if not finite(start) or not finite(rest):

            self.note = "Not assessed: PT repetition criteria not set"

            return None

        if start <= rest or rest < 0:

            self.note = "Not assessed: invalid repetition thresholds"

            return None



        # Ankle directions remain separate, not one maximum signed angle.

        direction = "positive" if value >= 0 else "negative"

        magnitude = abs(value) if self.primary == "ankle" else value



        if self.active is None and magnitude > start:

            self.active = {

                "peak": magnitude,

                "direction": direction,

                "tracking_valid": True,

                "started": t,

            }

        if self.active is None:

            self.note = "Waiting for repetition"

            return None



        rep = self.active

        same_direction = direction == rep["direction"] or self.primary != "ankle"

        if same_direction:

            rep["peak"] = max(rep["peak"], magnitude)



        if magnitude <= rest or not same_direction:

            finished = {

                **rep,

                "ended": t,

                "rep_index": len(self.reps) + 1,

                # No authenticated approval integration yet.

                "target_reached": None,

            }

            self.reps.append(finished)

            self.active = None

            self.note = "Preview repetition recorded; target unassessed"

            return finished



        self.note = "Preview repetition in progress"

        return None



class Attempt:

    def __init__(self, engine):

        self.settings = json.loads(

            (CONFIG / "settings.json").read_text(encoding="utf-8-sig")

        )

        all_exercises = json.loads(

            (CONFIG / "exercises.json").read_text(encoding="utf-8-sig")

        )

        self.references = json.loads(

            (CONFIG / "rom_reference.json").read_text(encoding="utf-8-sig")

        )

        self.key = ALIASES.get(engine.exercise_key)

        if self.key is None:

            raise ValueError("Exercise is outside the extension's three-exercise scope")

        self.cfg = all_exercises["exercises"][self.key]

        self.ev = PreviewEvaluator(self.cfg)

        self.store = RehabStore()

        documents = {

            "settings": self.settings,

            "exercises": all_exercises,

            "references": self.references,

        }

        self.fingerprint = hashlib.sha256(

            json.dumps(

                documents, sort_keys=True, allow_nan=False

            ).encode("utf-8")

        ).hexdigest()

        scope = getattr(engine, "_rehab_scope", None)

        self.scope_source = "browser" if scope else "configuration"

        self.scope = scope or self.settings["design_scope"]

        self.id = self.store.start(

            engine.session["patient"]["id"],

            self.key, engine.side, self.scope,

            self.fingerprint,

            self.references.get("reference_edition"),

            measurement_method="extension_preview_unapproved_v1",

        )

        self.last_sample = None

        self.paused = False

        self.telemetry_failed = False



    def sample(self, engine):

        data = getattr(engine, "_rehab_measurements", None)

        if not data:

            return

        t = data.get("monotonic_seconds")

        if not finite(t) or t == self.last_sample:

            return

        self.last_sample = t



        if engine.session and engine.session["phase"] == "paused":

            self.paused = True

            return

        if self.paused:

            # Do not credit a repetition that spans a pause.

            self.ev.active = None

            self.paused = False



        joints = data.get("joints", {})

        phase = engine.session.get("phase") if engine.session else "finished"

        rep = None

        if phase == "exercising":

            rep = self.ev.update(joints, t)



        scope = getattr(engine, "_rehab_scope", None) or self.scope

        payload = {

            "measurement": data,

            "phase": phase,

            "design_scope": scope,

            "config_sha256": self.fingerprint,

            "clinical_approval": False,

            "evaluator_note": self.ev.note,

            "displayed_prompt": (

                engine.evaluator.snapshot().get("prompt")

                if engine.evaluator else None

            ),

        }

        try:

            self.store.telemetry(self.id, t, payload)

        except Exception:

            self.telemetry_failed = True

            log.exception("Extension telemetry write failed")



        if rep:

            self.store.add_rep(

                self.id,

                rep["rep_index"],

                rep["peak"] if rep["tracking_valid"] else None,

                supporting_joint_angles={

                    joint: {

                        "angle": reading.get("angle"),

                        "tracked": reading.get("tracked", False),

                    }

                    for joint, reading in joints.items()

                    if joint != self.ev.primary

                },

                target_reached=None,

                tracking_valid=rep["tracking_valid"],

            )



    def finish(self, reason):

        reps = self.ev.reps

        peaks = [r["peak"] for r in reps if r["tracking_valid"]]

        moving = self.ev.primary

        if self.key == "straight_leg_raise":

            reference = self.cfg["assessment"]["slr_expected_arom_deg"]

        elif self.key == "prone_knee_flexion":

            reference = self.references["movements"]["knee_flexion"]["reference_peak_deg"]

        else:

            reference = None



        override = self.cfg["assessment"]["reference_override_deg"]

        if finite(override):

            reference = override



        n = self.settings["history"]["trend_session_count"]

        valid_n = isinstance(n, int) and not isinstance(n, bool) and n > 0

        # One previous session is intrinsic to the requested comparison.

        history = self.store.history(self.id, n if valid_n else 1)

        previous = (

            self.store.valid_peaks(history[0]["id"]) if history else None

        )



        if moving == "ankle":

            # A pooled ankle magnitude is not a valid directional AROM result.

            stats = compare_sessions([], [])

        else:

            stats = compare_sessions(peaks, previous)



        assessment = assess_arom(

            max(peaks) if peaks and moving != "ankle" else None,

            reference,

            self.cfg["assessment"]["wnl_tolerance_deg"],

        )



        directions = {}

        if moving == "ankle":

            for direction, name, reference_key in (

                ("positive", "dorsiflexion", "reference_peak_deg"),

                ("negative", "plantarflexion", "reference_peak_magnitude_deg"),

            ):

                selected = [

                    r["peak"] for r in reps

                    if r["direction"] == direction and r["tracking_valid"]

                ]

                ref = self.references["movements"]["ankle_" + name][reference_key]

                directions[name] = {

                    "peak_deg": max(selected) if selected else None,

                    "assessment": assess_arom(

                        max(selected) if selected else None,

                        ref, self.cfg["assessment"]["wnl_tolerance_deg"],

                    ),

                }



        summary = {

            **stats,

            "session_id": self.id,

            "exercise_id": self.key,

            "moving_joint": moving,

            "design_scope_at_start": self.scope,

            "scope_source": self.scope_source,

            "config_sha256": self.fingerprint,

            "clinical_approval": False,

            "mode": "Unapproved extension preview",

            "rep_boundary_source": "extension_configured_thresholds",

            "legacy_session_end_reason": reason,

            "reps_completed": len(reps),

            "unfinished_rep": self.ev.active is not None,

            "target_reached_count": 0,

            "target_not_reached_count": 0,

            "target_unassessed_count": len(reps),

            "completion_rate": None,

            "assessment": assessment,

            "wnl_label": assessment["label"],

            "provisional_flag": assessment["provisional"],

            "directional_arom": directions,

            "supporting_joint_monitoring": {

                joint: {

                    "state": "Not assessed: verified PT approval unavailable",

                    "within_percent": None,

                    "tracking_coverage_percent": None,

                }

                for joint in self.cfg["supporting_joints"]

            },

            "trend": list(reversed(history)) if valid_n and moving != "ankle" else [],

            "trend_status": (

                "Directional ankle history not integrated"

                if moving == "ankle"

                else "Configured" if valid_n

                else "History chart length not configured"

            ),

            "telemetry_write_failed": self.telemetry_failed,

            "evaluation_note": self.ev.note,

        }

        if moving == "ankle":

            summary["history_status"] = "See separate directional AROM results"

        elif history and not previous:

            summary["history_status"] = "Previous session has no valid comparable peaks"



        summary = enrich_summary(summary, history, reps, valid_n)

        with self.store.connect() as db:

            db.execute(

                "INSERT INTO rehab_summaries VALUES (?,?)",

                (self.id, json.dumps(summary, allow_nan=False)),

            )

            db.execute(

                "UPDATE rehab_sessions SET status=? WHERE id=?",

                ("finished", self.id),

            )

        return summary



def install(cls):

    if getattr(cls, "_rehab_sessions_installed", False):

        return



    original_start = cls.start_session

    original_step = cls._step

    original_finish = cls._finish_session

    original_snapshot = cls.snapshot

    original_pause = cls.pause_session



    @wraps(original_start)

    def start(self, *args, **kwargs):

        result = original_start(self, *args, **kwargs)

        self._rehab_attempt = None

        self._rehab_summary = None

        self._rehab_recording_error = None

        try:

            self._rehab_attempt = Attempt(self)

        except Exception as exc:

            self._rehab_recording_error = str(exc)

            log.exception("Extension session recording could not start")

        return result



    @wraps(original_step)

    def step(self, landmarks, t):

        result = original_step(self, landmarks, t)

        attempt = getattr(self, "_rehab_attempt", None)

        if attempt is not None and self.session is not None:

            try:

                attempt.sample(self)

            except Exception as exc:

                self._rehab_recording_error = str(exc)

                log.exception("Extension evaluation/recording failed")

        return result



    @wraps(original_pause)

    def pause(self):

        result = original_pause(self)

        attempt = getattr(self, "_rehab_attempt", None)

        if attempt:

            attempt.paused = True

        return result



    @wraps(original_finish)

    def finish(self, t, reason):

        attempt = getattr(self, "_rehab_attempt", None)

        if attempt:

            try:

                attempt.sample(self)

            except Exception:

                log.exception("Final extension sample failed")

        result = original_finish(self, t, reason)

        if result is not None and attempt:

            try:

                self._rehab_summary = attempt.finish(reason)

            except Exception as exc:

                self._rehab_recording_error = str(exc)

                log.exception("Extension summary could not be saved")

            finally:

                self._rehab_attempt = None

        return result



    @wraps(original_snapshot)

    def snapshot(self):

        result = dict(original_snapshot(self))

        result["rehab_session_summary"] = copy.deepcopy(

            getattr(self, "_rehab_summary", None)

        )

        result["rehab_recording_error"] = getattr(

            self, "_rehab_recording_error", None

        )

        attempt = getattr(self, "_rehab_attempt", None)

        result["rehab_evaluation_preview"] = (

            {

                "session_id": attempt.id,

                "state": attempt.ev.note,

                "reps_completed": len(attempt.ev.reps),

                "clinical_approval": False,

            } if attempt else None

        )

        return result



    cls.start_session = start

    cls._step = step

    cls.pause_session = pause

    cls._finish_session = finish

    cls.snapshot = snapshot

    cls._rehab_sessions_installed = True

