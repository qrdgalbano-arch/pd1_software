
"""Fail-closed clinical-extension guard; legacy demo is explicitly labeled."""
import json
from functools import wraps
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "rehab_extension"

def start_permission(settings):
    # Approved use remains unavailable until the new evaluator, PT approval
    # verification, and validation checks are integrated.
    mode = settings.get("unapproved_mode")
    if mode == "demo" and settings.get("extension_enabled") is False:
        return {
            "mode": "demo",
            "approved": False,
            "evaluation": "legacy_unapproved",
        }
    raise ValueError(
        "Exercise start blocked: approved clinical integration is not ready. "
        "For nonclinical testing only, set extension_enabled=false and "
        "unapproved_mode='demo' in config/rehab_extension/settings.json."
    )

def install(cls):
    if getattr(cls, "_pd1_approval_guard", False):
        return

    original_start = cls.start_session
    original_snapshot = cls.snapshot

    @wraps(original_start)
    def start_session(self, *args, **kwargs):
        try:
            settings = json.loads(
                (CONFIG / "settings.json").read_text(encoding="utf-8-sig")
            )
            permission = start_permission(settings)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Exercise start blocked: clinical configuration is "
                "missing or invalid."
            ) from exc

        result = original_start(self, *args, **kwargs)
        # Metadata only; do not alter clinical evaluation.
        self._rehab_permission = permission
        return result

    @wraps(original_snapshot)
    def snapshot(self):
        state = dict(original_snapshot(self))
        state["rehab_extension"] = dict(getattr(
            self, "_rehab_permission",
            {"mode": "blocked", "approved": False}
        ))
        return state

    cls.start_session = start_session
    cls.snapshot = snapshot
    cls._pd1_approval_guard = True
