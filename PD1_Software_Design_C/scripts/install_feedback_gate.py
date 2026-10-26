import ast
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "station" / "exercises.py"
MODULE = ROOT / "station" / "feedback_gate.py"
CONFIG = ROOT / "config" / "feedback_ui.json"
MARKER = "# PD1_FEEDBACK_GATE_V1"

DEFAULTS = {
    "enabled": True,
    "minimum_display_seconds": 2.5,
    "same_category_update_seconds": 4.0,
    "priorities": {
        "positioning": 100,
        "wrong_leg_raised": 90,
        "default_deviation": 80,
        "too_fast": 75,
        "over_range": 70,
        "rep_invalid": 60,
        "rep_incomplete": 55,
        "tracking_ok": 30,
        "rep_valid": 10,
        "default": 20
    }
}

CODE = r'''
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
'''

def main():
    original = TARGET.read_bytes()
    source = original.decode("utf-8-sig")
    if MARKER in source:
        print("Already installed. No files changed.")
        return

    tree = ast.parse(source)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef)
        and n.name == "ExerciseEvaluator"
    )
    names = {
        n.name for n in cls.body
        if isinstance(n, ast.FunctionDef)
    }
    required = {
        "__init__", "_say", "update",
        "_tracking_ok", "_check_deviations"
    }
    if not required <= names:
        raise SystemExit("STOP: evaluator structure differs; no files changed.")
    if MODULE.exists() or CONFIG.exists():
        raise SystemExit("STOP: extension files already exist; no files changed.")

    suffix = (
        "\n\n" + MARKER + "\n"
        "from station.feedback_gate import install as _install_feedback_gate\n"
        "_install_feedback_gate(ExerciseEvaluator)\n"
    )
    updated = source + suffix
    compile(updated, str(TARGET), "exec")
    compile(CODE, str(MODULE), "exec")

    # Presentation tests, without camera or clinical thresholds.
    namespace = {"__file__": str(MODULE)}
    exec(compile(CODE, str(MODULE), "exec"), namespace)
    gate = namespace["Gate"](DEFAULTS)
    good = ("rep_valid", "Good", "success", 10)
    wrong = ("wrong_leg_raised", "Check prescribed leg", "error", 90)
    assert gate.choose([good], 0) == good
    assert gate.choose([wrong], 0.1) == wrong
    assert gate.choose([good], 0.2) is None
    assert gate.choose([wrong], 1) is None
    assert gate.choose([good], 3) == good

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = ROOT / "patch_backups" / f"feedback_{stamp}"
    backup.mkdir(parents=True)
    shutil.copy2(TARGET, backup / "exercises.py")

    if TARGET.read_bytes() != original:
        raise RuntimeError("Evaluator changed during installation")

    try:
        MODULE.write_text(CODE, encoding="utf-8")
        CONFIG.write_text(
            json.dumps(DEFAULTS, indent=2) + "\n", encoding="utf-8"
        )
        TARGET.write_text(updated, encoding="utf-8")
    except Exception:
        TARGET.write_bytes(original)
        MODULE.unlink(missing_ok=True)
        CONFIG.unlink(missing_ok=True)
        raise

    print("Feedback gate installed. Syntax and arbitration tests passed.")
    print(f"Backup: {backup / 'exercises.py'}")
    print("Settings: config/feedback_ui.json")
    print("Restart the station. No clinical evaluation rules changed.")

if __name__ == "__main__":
    main()