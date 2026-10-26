
"""Directional history and explicit interruption recovery."""
import json
import math
import logging
from datetime import datetime, timezone
from functools import wraps
from .storage import RehabStore

log = logging.getLogger("station.rehab.recovery")

def finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )

def enrich_summary(summary, history, reps, trend_configured):
    if summary.get("moving_joint") != "ankle":
        return summary

    directions = summary.get("directional_arom", {})
    summary["directional_repetitions"] = [
        {
            "rep_index": rep["rep_index"],
            "direction": rep["direction"],
            "peak_magnitude_deg": rep["peak"] if rep["tracking_valid"] else None,
            "tracking_valid": rep["tracking_valid"],
            "target_reached": rep.get("target_reached"),
        }
        for rep in reps
    ]

    for sign, name in (
        ("positive", "dorsiflexion"),
        ("negative", "plantarflexion"),
    ):
        current = [
            rep["peak"] for rep in reps
            if rep["direction"] == sign
            and rep["tracking_valid"] and finite(rep["peak"])
        ]
        avg = sum(current) / len(current) if current else None
        previous = (
            history[0]["summary"].get("directional_arom", {}).get(name, {})
            if history else {}
        )
        previous_avg = previous.get("avg_peak_arom")
        previous_best = previous.get("max_peak", previous.get("peak_deg"))

        entry = directions.setdefault(name, {})
        entry.update({
            "avg_peak_arom": avg,
            "max_peak": max(current) if current else None,
            "previous_avg_peak_arom": previous_avg,
            "previous_max_peak": previous_best,
            "difference_deg": (
                avg - previous_avg
                if finite(avg) and finite(previous_avg) else None
            ),
            "history_status": (
                "No previous session" if not history
                else "Previous session available" if finite(previous_avg)
                else "Previous session has no directional average"
            ),
            "trend": (
                [
                    {
                        "timestamp": item["timestamp"],
                        "avg_peak_arom": item["summary"].get(
                            "directional_arom", {}
                        ).get(name, {}).get("avg_peak_arom"),
                    }
                    for item in reversed(history)
                ] if trend_configured else []
            ),
        })
    summary["directional_arom"] = directions
    summary["trend_status"] = (
        "Configured" if trend_configured
        else "History chart length not configured"
    )
    summary["history_status"] = "See separate directional AROM results"
    return summary

def recover_interrupted(store):
    """Called once at engine construction, not whenever a store is opened."""
    recovered = []
    with store.connect() as db:
        rows = db.execute(
            """SELECT id,exercise_id,design_scope FROM rehab_sessions
            WHERE status='running'"""
        ).fetchall()
        for row in rows:
            summary = {
                "session_id": row["id"],
                "exercise_id": row["exercise_id"],
                "design_scope_at_start": row["design_scope"],
                "status": "interrupted",
                "recovered_at": datetime.now(timezone.utc).isoformat(),
                "clinical_approval": False,
                "assessment": {
                    "label": "Assessment unavailable",
                    "provisional": True,
                    "tag": "Interrupted session — assessment withheld",
                    "peak_deg": None,
                    "reference_deg": None,
                },
                "wnl_label": "Assessment unavailable",
                "provisional_flag": True,
                "avg_peak_arom": None,
                "max_peak": None,
                "completion_rate": None,
                "note": (
                    "Session ended without normal finalization. Existing "
                    "rep/telemetry rows were preserved; no result was inferred."
                ),
            }
            # Preserve an existing finalized payload if one exists.
            db.execute(
                """INSERT OR IGNORE INTO rehab_summaries
                (session_id,payload) VALUES (?,?)""",
                (row["id"], json.dumps(summary, allow_nan=False)),
            )
            db.execute(
                "UPDATE rehab_sessions SET status='interrupted' WHERE id=?",
                (row["id"],),
            )
            recovered.append(row["id"])
    return recovered

def install_recovery(cls):
    if getattr(cls, "_rehab_recovery_installed", False):
        return
    original_init = cls.__init__
    original_snapshot = cls.snapshot

    @wraps(original_init)
    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._rehab_recovery_count = 0
        self._rehab_recovery_error = None
        try:
            self._rehab_recovery_count = len(
                recover_interrupted(RehabStore())
            )
        except Exception as exc:
            self._rehab_recovery_error = str(exc)
            log.exception("Interrupted extension-session recovery failed")

    @wraps(original_snapshot)
    def snapshot(self):
        state = dict(original_snapshot(self))
        state["rehab_recovery"] = {
            "interrupted_session_count": self._rehab_recovery_count,
            "error": self._rehab_recovery_error,
        }
        return state

    cls.__init__ = initialize
    cls.snapshot = snapshot
    cls._rehab_recovery_installed = True
