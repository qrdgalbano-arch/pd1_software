
"""Presentation arbitration only; does not change clinical evaluation."""
import json
import logging
import math
from functools import wraps
from pathlib import Path

log = logging.getLogger("station.feedback")
PATH = Path(__file__).resolve().parents[1] / "config" / "feedback_ui.json"

class Gate:
    def __init__(self, cfg):
        self.cfg = cfg
        self.key = None
        self.priority = -1
        self.shown_at = float("-inf")

    def choose(self, candidates, t):
        if not candidates:
            return None
        chosen = sorted(
            candidates,
            key=lambda p: (-p[3], p[0], p[1]),
        )[0]
        key = chosen[:3]
        if key == self.key:
            return None
        if self.key is not None and chosen[3] <= self.priority:
            wait = self.cfg["minimum_display_seconds"]
            if key[0] == self.key[0]:
                wait = max(
                    wait, self.cfg["same_category_update_seconds"]
                )
            if t - self.shown_at < wait:
                return None
        self.key = key
        self.priority = chosen[3]
        self.shown_at = t
        return chosen

def load_config():
    cfg = json.loads(PATH.read_text(encoding="utf-8-sig"))
    for key in (
        "minimum_display_seconds", "same_category_update_seconds"
    ):
        value = cfg[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"Invalid feedback setting: {key}")
    for value in cfg["priorities"].values():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("Feedback priorities must be finite numbers")
    return cfg

def install(cls):
    if getattr(cls, "_pd1_feedback_installed", False):
        return

    original_init = cls.__init__
    original_say = cls._say
    original_update = cls.update

    @wraps(original_init)
    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            self._ui_gate = Gate(load_config())
        except Exception:
            log.exception("Feedback config invalid; using original feedback")
            self._ui_gate = None
        self._ui_batch = None

    @wraps(original_say)
    def say(self, prompt_id, text, level):
        if self._ui_batch is not None:
            self._ui_batch.append((prompt_id, text, level))
            return
        # Engine lifecycle messages remain immediate.
        original_say(self, prompt_id, text, level)
        gate = getattr(self, "_ui_gate", None)
        if gate:
            gate.key = None
            gate.priority = -1
            gate.shown_at = float("-inf")

    @wraps(original_update)
    def update(self, joints, t):
        gate = getattr(self, "_ui_gate", None)
        if not gate or not gate.cfg.get("enabled", False):
            return original_update(self, joints, t)

        self._ui_batch = []
        try:
            result = original_update(self, joints, t)
            proposals = list(self._ui_batch)
        finally:
            self._ui_batch = None

        tracking_ok, _ = self._tracking_ok(joints)
        if not tracking_ok:
            # Suppress stale form checks while tracking is uncertain.
            proposals = [
                p for p in proposals if p[0] == "positioning"
            ]
        else:
            # Existing evaluator emits deviations on entry only.
            # Keep confirmed conditions eligible every frame.
            for key in sorted(self._active_deviations):
                proposals.append((
                    key, self.messages.get(key, key), "error"
                ))
            if not proposals:
                proposals.append((
                    "continue",
                    "Continue following your prescribed exercise.",
                    "info",
                ))

        priorities = gate.cfg["priorities"]
        deviations = set(self.messages)
        candidates = []
        for key, text, level in proposals:
            fallback = (
                priorities["default_deviation"]
                if key in deviations else priorities["default"]
            )
            priority = priorities.get(key, fallback)
            candidates.append((key, text, level, priority))

        chosen = gate.choose(candidates, t)
        if chosen:
            original_say(self, *chosen[:3])
        return result

    cls.__init__ = initialize
    cls._say = say
    cls.update = update
    cls._pd1_feedback_installed = True
