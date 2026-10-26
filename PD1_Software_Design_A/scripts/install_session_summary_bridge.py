import ast
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
ENGINE = ROOT / "station" / "engine.py"
APP = ROOT / "web" / "app.js"
HTML = ROOT / "web" / "index.html"
PACKAGE = ROOT / "station" / "rehab_extension"
MODULE = PACKAGE / "session_bridge.py"
UI = ROOT / "web" / "rehab-summary.js"
MARKER = "# PD1_REHAB_SESSION_BRIDGE_V1"
APP_MARKER = "// PD1_REHAB_SUMMARY_V1"

CODE = r'''
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

ALIASES = {
    "straight_leg_raising": "straight_leg_raise",
    "straight_leg_raise": "straight_leg_raise",
    "prone_leg_flexion": "prone_knee_flexion",
    "prone_knee_flexion": "prone_knee_flexion",
    "ankle_pumps": "ankle_pumps",
}

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
'''

JAVASCRIPT = r'''
let panel;
let lastSignature;

function ensurePanel() {
  if (panel) return;
  const host = document.getElementById("screen-summary");
  if (!host) return;
  panel = document.createElement("section");
  panel.id = "rehab-session-summary";
  panel.style.marginBlock = "24px";
  host.append(panel);
}

function line(label, value) {
  const p = document.createElement("p");
  p.textContent = `${label}: ${value}`;
  panel.append(p);
}

function degrees(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)}°` : "Unavailable";
}

export function renderRehabSession(state) {
  if (!state) return;
  ensurePanel();
  if (!panel) return;
  const summary = state.rehab_session_summary;
  const error = state.rehab_recording_error;
  const signature = JSON.stringify([summary?.session_id, error]);
  if (signature === lastSignature) return;
  lastSignature = signature;
  panel.replaceChildren();

  const title = document.createElement("h2");
  title.textContent = "Extension summary — unapproved preview";
  panel.append(title);

  if (error) line("Recording error", error);
  if (!summary) {
    line("Status", "No extension summary available for this exercise yet");
    return;
  }

  line("Exercise", summary.exercise_id);
  line("Extension repetitions completed", summary.reps_completed);
  line("Incomplete repetition at stop", summary.unfinished_rep ? "Yes" : "No");
  line("Peak AROM", degrees(summary.max_peak));
  line("Reference", degrees(summary.assessment?.reference_deg));
  line("Layer A", summary.assessment?.label || "Assessment unavailable");
  if (summary.assessment?.tag) line("Assessment status", summary.assessment.tag);
  if (summary.assessment?.note) line("Assessment note", summary.assessment.note);
  line("Approval", "Not approved — research preview only");

  for (const [name, result] of Object.entries(summary.directional_arom || {})) {
    line(`${name} peak`, degrees(result.peak_deg));
    line(`${name} reference`, degrees(result.assessment.reference_deg));
    line(`${name} Layer A`, result.assessment.label);
    if (result.assessment.tag) line(`${name} status`, result.assessment.tag);
  }

  line(
    "Layer B",
    `${summary.target_reached_count} reached; ` +
    `${summary.target_not_reached_count} not reached; ` +
    `${summary.target_unassessed_count} unassessed`
  );

  for (const [joint, result] of Object.entries(
    summary.supporting_joint_monitoring || {}
  )) {
    line(`Layer C — ${joint}`, result.state);
  }

  line("Average rep peak", degrees(summary.avg_peak_arom));
  line("Best rep", degrees(summary.max_peak));
  line("Previous-session average", degrees(summary.previous_avg_peak_arom));
  line("Previous-session best", degrees(summary.previous_max_peak));
  const delta = summary.difference_deg;
  line("Change vs previous session",
    typeof delta === "number" ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}°`
      : summary.history_status);
  line("History", summary.trend_status);
  line("Recording note", summary.evaluation_note);

  if (summary.telemetry_write_failed) {
    line("Warning", "Some telemetry could not be written");
  }

  const points = (summary.trend || []).map(item => ({
    label: item.timestamp,
    value: item.summary?.avg_peak_arom,
  }));
  if (typeof summary.avg_peak_arom === "number") {
    points.push({label: "Current session", value: summary.avg_peak_arom});
  }
  const valid = points.filter(p =>
    typeof p.value === "number" && Number.isFinite(p.value)
  );

  // Show only recorded data; never generate example values.
  if (summary.trend_status === "Configured" && valid.length > 1) {
    const chart = document.createElement("canvas");
    chart.width = 640;
    chart.height = 220;
    chart.style.width = "100%";
    chart.style.maxWidth = "640px";
    chart.style.background = "#fff";
    chart.setAttribute("role", "img");
    chart.setAttribute("aria-label", "Recorded session average peak AROM trend");
    panel.append(chart);

    const ctx = chart.getContext("2d");
    if (ctx) {
      const lo = Math.min(...valid.map(p => p.value));
      const hi = Math.max(...valid.map(p => p.value));
      const span = hi - lo || 1;
      ctx.strokeStyle = "#066e69";
      ctx.lineWidth = 3;
      ctx.beginPath();
      valid.forEach((p, i) => {
        const x = 40 + i * 560 / (valid.length - 1);
        const y = 180 - (p.value - lo) / span * 140;
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
      ctx.stroke();
    }

    const list = document.createElement("ul");
    valid.forEach(p => {
      const li = document.createElement("li");
      li.textContent = `${p.label}: ${degrees(p.value)}`;
      list.append(li);
    });
    panel.append(list);
  }

  line(
    "Decision authority",
    "Remains with the patient and the physical therapist. This tool does not diagnose."
  );
}
'''

def main():
    required = [
        PACKAGE / "core.py", PACKAGE / "storage.py",
        PACKAGE / "live.py", PACKAGE / "approval.py",
        ROOT / "station" / "rehab_extension" / "web_bridge.py",
    ]
    if not all(p.is_file() for p in required):
        raise SystemExit("STOP: install/repair previous parts first.")

    storage_source = (PACKAGE / "storage.py").read_text(encoding="utf-8-sig")
    if "INSERT INTO rehab_reps VALUES (?,?,?,?,?,?,?,?)" in storage_source:
        raise SystemExit("STOP: storage still needs the seven-column repair.")
    if "@contextmanager" not in storage_source:
        raise SystemExit("STOP: storage connection-closure repair is missing.")

    old_engine = ENGINE.read_bytes()
    old_app = APP.read_bytes()
    old_html = HTML.read_bytes()
    engine = old_engine.decode("utf-8-sig")
    app = old_app.decode("utf-8-sig")
    html = old_html.decode("utf-8-sig")

    if MARKER in engine or APP_MARKER in app or MODULE.exists() or UI.exists():
        raise SystemExit("Already/partially installed; nothing overwritten.")

    tree = ast.parse(engine)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "ExerciseEngine"
    )
    names = {
        n.name for n in cls.body if isinstance(n, ast.FunctionDef)
    }
    if not {
        "start_session", "_step", "_finish_session", "snapshot", "pause_session"
    } <= names:
        raise SystemExit("STOP: unexpected engine structure.")

    matches = list(re.finditer(
        r"\bfunction\s+render\s*\(\s*state\s*\)\s*\{", app
    ))
    if len(matches) != 1:
        raise SystemExit("STOP: expected one render(state) function.")

    position = matches[0].end()
    hook = (
        "\n  try { renderRehabSession(state); }\n"
        '  catch (error) { console.warn("Extension summary:", error); }\n'
    )
    app_new = (
        APP_MARKER + "\n"
        'import { renderRehabSession } from "/static/rehab-summary.js?v=1";\n'
        + app[:position] + hook + app[position:]
    )

    engine_new = (
        engine + "\n\n" + MARKER + "\n"
        "from station.rehab_extension.session_bridge import install "
        "as _install_rehab_sessions\n"
        "_install_rehab_sessions(ExerciseEngine)\n"
    )
    html_new, count = re.subn(
        r'(/static/app\.js)(?:\?[^"\']*)?(?=["\'])',
        r'\1?v=rehab-session-1', html,
    )
    if count != 1:
        raise SystemExit("STOP: expected one app.js reference.")

    compile(CODE, str(MODULE), "exec")
    compile(engine_new, str(ENGINE), "exec")
    sys.path.insert(0, str(ROOT))

    # Test numerical segmentation without approving any project settings.
    namespace = {"__file__": str(MODULE), "__package__": "station.rehab_extension"}
    exec(compile(CODE, str(MODULE), "exec"), namespace)
    evaluator = namespace["PreviewEvaluator"]({
        "moving_joint": "ankle",
        "repetition": {
            "start_threshold_deg": 2,
            "return_threshold_deg": 1,
        },
    })
    sample = lambda angle: {"ankle": {"tracked": True, "angle": angle}}
    evaluator.update(sample(3), 0)
    evaluator.update(sample(8), 1)
    first = evaluator.update(sample(0), 2)
    assert first["peak"] == 8 and first["direction"] == "positive"
    evaluator.update(sample(-4), 3)
    second = evaluator.update(sample(0), 4)
    assert second["direction"] == "negative"
    assert first["target_reached"] is None

    missing = namespace["PreviewEvaluator"]({
        "moving_joint": "knee",
        "repetition": {
            "start_threshold_deg": None, "return_threshold_deg": None
        },
    })
    missing.update({"knee": {"tracked": True, "angle": 60}}, 0)
    assert len(missing.reps) == 0

    node = shutil.which("node")
    if node:
        for source in (JAVASCRIPT, app_new):
            checked = subprocess.run(
                [node, "--input-type=module", "--check"],
                input=source, text=True, capture_output=True,
            )
            if checked.returncode:
                raise RuntimeError(checked.stderr)

    backup = ROOT / "patch_backups" / datetime.now().strftime(
        "session_summary_%Y%m%d_%H%M%S_%f"
    )
    backup.mkdir(parents=True)
    for path in (ENGINE, APP, HTML):
        target = backup / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    if (
        ENGINE.read_bytes() != old_engine or APP.read_bytes() != old_app
        or HTML.read_bytes() != old_html
    ):
        raise RuntimeError("Project changed during installation")

    try:
        MODULE.write_text(CODE, encoding="utf-8")
        UI.write_text(JAVASCRIPT, encoding="utf-8")
        ENGINE.write_text(engine_new, encoding="utf-8")
        APP.write_text(app_new, encoding="utf-8")
        HTML.write_text(html_new, encoding="utf-8")
    except Exception:
        ENGINE.write_bytes(old_engine)
        APP.write_bytes(old_app)
        HTML.write_bytes(old_html)
        MODULE.unlink(missing_ok=True)
        UI.unlink(missing_ok=True)
        raise

    print("EVALUATION PREVIEW + RECORDING + SUMMARY INSTALLED.")
    print("Segmentation tests passed; test values are not clinical defaults.")
    print(f"Backup: {backup}")
    print("Clinical approval remains unavailable.")
    print("Legacy repetition counting/session endings remain unchanged.")
    print("Ankle directional history and supporting-joint monitoring remain pending.")

if __name__ == "__main__":
    main()
