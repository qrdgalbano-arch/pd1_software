import ast
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
PACKAGE = ROOT / "station" / "rehab_extension"
HELPER = PACKAGE / "history_recovery.py"
BRIDGE = PACKAGE / "session_bridge.py"
ENGINE = ROOT / "station" / "engine.py"
UI = ROOT / "web" / "rehab-summary.js"
HTML = ROOT / "web" / "index.html"
TEST = ROOT / "tests" / "test_rehab_history_recovery.py"
README = ROOT / "README_REHAB_EXTENSION.md"
MARKER = "# PD1_HISTORY_RECOVERY_V1"

HELPER_CODE = r'''
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
'''

TEST_CODE = r'''
"""Artificial software fixtures, not patient validation evidence."""
import tempfile
import unittest
from pathlib import Path
from station.rehab_extension.storage import RehabStore
from station.rehab_extension.history_recovery import (
    enrich_summary, recover_interrupted,
)

class HistoryRecoveryTests(unittest.TestCase):
    def test_directions_are_separate(self):
        summary = {
            "moving_joint": "ankle",
            "directional_arom": {
                "dorsiflexion": {}, "plantarflexion": {}
            },
        }
        reps = [
            dict(rep_index=1, direction="positive", peak=10, tracking_valid=True),
            dict(rep_index=2, direction="positive", peak=20, tracking_valid=True),
            dict(rep_index=3, direction="negative", peak=40, tracking_valid=True),
        ]
        previous = [{
            "timestamp": "previous",
            "summary": {
                "directional_arom": {
                    "dorsiflexion": {"avg_peak_arom": 12, "max_peak": 18},
                    "plantarflexion": {"avg_peak_arom": 30, "max_peak": 35},
                }
            },
        }]
        result = enrich_summary(summary, previous, reps, True)
        self.assertEqual(
            result["directional_arom"]["dorsiflexion"]["avg_peak_arom"], 15
        )
        self.assertEqual(
            result["directional_arom"]["dorsiflexion"]["difference_deg"], 3
        )
        self.assertEqual(
            result["directional_arom"]["plantarflexion"]["difference_deg"], 10
        )

    def test_missing_history_is_not_fabricated(self):
        result = enrich_summary(
            {"moving_joint": "ankle", "directional_arom": {}}, [], [], False
        )
        entry = result["directional_arom"]["dorsiflexion"]
        self.assertIsNone(entry["avg_peak_arom"])
        self.assertIsNone(entry["difference_deg"])
        self.assertEqual(entry["history_status"], "No previous session")
        self.assertEqual(entry["trend"], [])

    def test_recovery_preserves_rep_data(self):
        with tempfile.TemporaryDirectory() as folder:
            store = RehabStore(Path(folder) / "test.sqlite3")
            session = store.start("fixture", "knee", "left", "leg", "test")
            store.add_rep(session, 1, 50)
            self.assertEqual(recover_interrupted(store), [session])
            self.assertEqual(store.valid_peaks(session), [50])
            self.assertEqual(recover_interrupted(store), [])
            with store.connect() as db:
                row = db.execute(
                    "SELECT status FROM rehab_sessions WHERE id=?", (session,)
                ).fetchone()
                self.assertEqual(row["status"], "interrupted")

if __name__ == "__main__":
    unittest.main()
'''

DRAW_JS = r'''
function drawRehabTrend(label, points) {
  const valid = points.filter(p =>
    typeof p.value === "number" && Number.isFinite(p.value)
  );
  if (!valid.length) return;
  const heading = document.createElement("h3");
  heading.textContent = label;
  panel.append(heading);

  if (valid.length > 1) {
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 220;
    canvas.style.width = "100%";
    canvas.style.maxWidth = "640px";
    canvas.style.background = "#fff";
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", label);
    panel.append(canvas);
    const context = canvas.getContext("2d");
    if (context) {
      const low = Math.min(...valid.map(p => p.value));
      const high = Math.max(...valid.map(p => p.value));
      const span = high - low || 1;
      context.strokeStyle = "#066e69";
      context.lineWidth = 3;
      context.beginPath();
      valid.forEach((p, i) => {
        const x = 40 + i * 560 / (valid.length - 1);
        const y = 180 - (p.value - low) * 140 / span;
        if (i) context.lineTo(x, y); else context.moveTo(x, y);
      });
      context.stroke();
    }
  }
  const list = document.createElement("ul");
  for (const point of valid) {
    const item = document.createElement("li");
    item.textContent = `${point.label}: ${degrees(point.value)}`;
    list.append(item);
  }
  panel.append(list);
}

function percentage(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)}%` : "Not assessed";
}
'''

def main():
    sys.path.insert(0, str(ROOT))
    required = [
        BRIDGE, ENGINE, UI, HTML,
        PACKAGE / "storage.py", PACKAGE / "joint_feedback.py",
    ]
    if not all(path.is_file() for path in required):
        raise SystemExit("STOP: previous session/feedback/storage patches required.")
    if HELPER.exists() or TEST.exists():
        raise SystemExit("History/recovery files already exist; nothing overwritten.")

    storage = PACKAGE / "storage.py"
    originals = {
        path: path.read_bytes() for path in (BRIDGE, ENGINE, UI, HTML, storage)
    }
    if README.exists():
        originals[README] = README.read_bytes()

    bridge = originals[BRIDGE].decode("utf-8-sig")
    engine = originals[ENGINE].decode("utf-8-sig")
    ui = originals[UI].decode("utf-8-sig")
    html = originals[HTML].decode("utf-8-sig")
    storage_text = originals[storage].decode("utf-8-sig")

    if MARKER in engine:
        raise SystemExit("Recovery hook already present; nothing overwritten.")

    anchor = "        with self.store.connect() as db:"
    if bridge.count(anchor) != 1:
        raise SystemExit("STOP: unexpected summary-save structure.")
    bridge_new = (
        "from .history_recovery import enrich_summary\n" + bridge
    )
    bridge_new = bridge_new.replace(
        anchor,
        "        summary = enrich_summary(summary, history, reps, valid_n)\n\n"
        + anchor,
        1,
    )

    # Prevent incomplete recovered attempts being used as prior benchmarks.
    history_anchor = "WHERE s.patient_id=? AND s.exercise_id=? AND s.side=?"
    if storage_text.count(history_anchor) != 1:
        raise SystemExit("STOP: unexpected storage history query.")
    storage_new = storage_text.replace(
        history_anchor,
        "WHERE s.status != 'interrupted' AND "
        "s.patient_id=? AND s.exercise_id=? AND s.side=?",
        1,
    )

    support_anchor = '    line(`Layer C — ${joint}`, result.state);'
    if ui.count(support_anchor) != 1:
        raise SystemExit("STOP: supporting-joint summary UI differs.")
    ui_new = ui.replace(
        support_anchor,
        support_anchor + r'''
    line(`${joint} within prescribed limits`, percentage(result.within_percent));
    line(`${joint} tracking coverage`, percentage(result.tracking_coverage_percent));
    line(`${joint} assessment coverage`, percentage(result.assessment_coverage_percent));
    if (result.timing_note) line(`${joint} timing`, result.timing_note);
''',
        1,
    )

    direction_anchor = (
        '    if (result.assessment.tag) '
        'line(`${name} status`, result.assessment.tag);'
    )
    if ui_new.count(direction_anchor) != 1:
        raise SystemExit("STOP: directional summary UI differs.")
    ui_new = ui_new.replace(
        direction_anchor,
        direction_anchor + r'''
    line(`${name} average`, degrees(result.avg_peak_arom));
    line(`${name} previous average`, degrees(result.previous_avg_peak_arom));
    line(`${name} previous best`, degrees(result.previous_max_peak));
    const change = result.difference_deg;
    line(`${name} change`, typeof change === "number"
      ? `${change >= 0 ? "+" : ""}${change.toFixed(1)}°`
      : result.history_status);
    if (summary.trend_status === "Configured") {
      const directionalPoints = (result.trend || []).map(p => ({
        label: p.timestamp, value: p.avg_peak_arom
      }));
      directionalPoints.push({
        label: "Current session", value: result.avg_peak_arom
      });
      drawRehabTrend(`${name} session-average trend`, directionalPoints);
    }
''',
        1,
    )
    ui_new += "\n" + DRAW_JS

    engine_new = (
        engine + "\n\n" + MARKER + "\n"
        "from station.rehab_extension.history_recovery import "
        "install_recovery as _install_rehab_recovery\n"
        "_install_rehab_recovery(ExerciseEngine)\n"
    )
    html_new = html.replace(
        "/static/rehab-summary.js?v=1",
        "/static/rehab-summary.js?v=2",
    )
    # The module import is in app.js, not normally HTML.
    app = ROOT / "web" / "app.js"
    originals[app] = app.read_bytes()
    app_text = originals[app].decode("utf-8-sig")
    if app_text.count("/static/rehab-summary.js?v=1") != 1:
        raise SystemExit("STOP: summary module import differs.")
    app_new = app_text.replace(
        "/static/rehab-summary.js?v=1", "/static/rehab-summary.js?v=2", 1
    )
    import re
    html_new, count = re.subn(
        r'(/static/app\.js)(?:\?[^"\']*)?(?=["\'])',
        r'\1?v=rehab-history-2', html_new
    )
    if count != 1:
        raise SystemExit("STOP: app.js HTML reference differs.")

    for path, content in (
        (HELPER, HELPER_CODE), (TEST, TEST_CODE),
        (BRIDGE, bridge_new), (ENGINE, engine_new), (storage, storage_new),
    ):
        compile(content, str(path), "exec")

    node = shutil.which("node")
    if node:
        for content in (ui_new, app_new):
            result = subprocess.run(
                [node, "--input-type=module", "--check"],
                input=content, text=True, encoding="utf-8", capture_output=True,
            )
            if result.returncode:
                raise RuntimeError(result.stderr)

    backup = ROOT / "patch_backups" / datetime.now().strftime(
        "history_recovery_%Y%m%d_%H%M%S_%f"
    )
    backup.mkdir(parents=True)
    for path in originals:
        target = backup / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    updates = {
        HELPER: HELPER_CODE, TEST: TEST_CODE,
        BRIDGE: bridge_new, ENGINE: engine_new, storage: storage_new,
        UI: ui_new, HTML: html_new, app: app_new,
    }
    if any(path.read_bytes() != value for path, value in originals.items()):
        raise RuntimeError("Project changed during installation")

    try:
        for path, text in updates.items():
            path.write_text(text, encoding="utf-8")

        checked = subprocess.run(
            [
                sys.executable, "-X", "utf8", "-m", "unittest", "discover",
                "-s", "tests", "-p", "test_rehab_history_recovery.py", "-v"
            ],
            cwd=ROOT,
        )
        if checked.returncode:
            raise RuntimeError("History/recovery tests failed")

        previous_readme = (
            originals[README].decode("utf-8-sig") if README in originals else ""
        )
        README.write_text(
            previous_readme + """

## History/recovery integration update

- Directional ankle averages, prior comparisons, and recorded-data trends added.
- Supporting-joint percentages and coverage are displayed when assessed.
- Running extension sessions at engine startup become interrupted.
- Existing repetition and telemetry rows are preserved.
- Interrupted sessions are excluded from prior-session benchmarks.
- Recovery tests use artificial fixtures, not patient validation measurements.

### Still not complete
- Calibrated hip anatomical frame.
- Authenticated/version-bound PT approval and approved runtime execution.
- Full replacement of legacy evaluation and session-ending decisions.
- Validated monitoring and target/hold/timing rules.
- Full camera/browser regression and real goniometer validation.
- Exact reference-edition/leaflet verification.

Clinical deployment is not approved.
""",
            encoding="utf-8",
        )
    except Exception:
        for path, content in originals.items():
            path.write_bytes(content)
        HELPER.unlink(missing_ok=True)
        TEST.unlink(missing_ok=True)
        if README not in originals:
            README.unlink(missing_ok=True)
        raise

    print("HISTORY + COVERAGE DISPLAY + INTERRUPTION RECOVERY INSTALLED.")
    print("Three persistent tests passed.")
    print(f"Backup: {backup}")
    print("Legacy evaluator remains active; clinical approval is unavailable.")
    print("Do not run a second station process against the same extension database.")

if __name__ == "__main__":
    main()
