import ast
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "station" / "engine.py"
HTML = ROOT / "web" / "index.html"
MODULE = ROOT / "station" / "rehab_extension" / "approval.py"
SETTINGS = ROOT / "config" / "rehab_extension" / "settings.json"

MARKER = "# PD1_APPROVAL_GUARD_V1"
BANNER_ID = "pd1-clinical-mode-banner"

CODE = r'''
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
'''

BANNER = """
<!-- PD1 clinical mode warning: retained until approved integration is ready -->
<aside id="pd1-clinical-mode-banner" role="note"
 style="padding:12px 16px;background:#fff0bf;color:#362600;
 border-bottom:2px solid #6b4600;font-size:1rem;line-height:1.4;">
  <strong>DEMO / UNAPPROVED</strong> — Approved clinical evaluation is not active.
  Existing exercise feedback is for nonclinical testing only.
  Decision authority remains with the patient and the physical therapist.
  This tool does not diagnose.
</aside>
"""

def main():
    if not SETTINGS.is_file() or not MODULE.parent.is_dir():
        raise SystemExit("Install Parts 4 and 5 first.")

    original_engine = ENGINE.read_bytes()
    original_html = HTML.read_bytes()
    engine = original_engine.decode("utf-8-sig")
    html = original_html.decode("utf-8-sig")

    if MARKER in engine:
        raise SystemExit("Approval guard already installed; nothing changed.")
    if MODULE.exists() or BANNER_ID in html:
        raise SystemExit("Partial/conflicting installation found; nothing changed.")

    tree = ast.parse(engine)
    cls = next(
        n for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "ExerciseEngine"
    )
    names = {
        n.name for n in cls.body if isinstance(n, ast.FunctionDef)
    }
    if not {"start_session", "snapshot"} <= names:
        raise SystemExit("Unexpected engine structure; nothing changed.")
    if html.count("</header>") != 1:
        raise SystemExit("Unexpected HTML header; nothing changed.")

    updated_engine = (
        engine + "\n\n" + MARKER + "\n"
        "from station.rehab_extension.approval import install as "
        "_install_approval_guard\n"
        "_install_approval_guard(ExerciseEngine)\n"
    )
    updated_html = html.replace("</header>", "</header>\n" + BANNER, 1)

    compile(updated_engine, str(ENGINE), "exec")
    compile(CODE, str(MODULE), "exec")

    namespace = {"__file__": str(MODULE)}
    exec(compile(CODE, str(MODULE), "exec"), namespace)
    check = namespace["start_permission"]
    assert check({
        "unapproved_mode": "demo", "extension_enabled": False
    })["approved"] is False

    for config in (
        {},
        {"unapproved_mode": "blocked", "extension_enabled": False},
        {"unapproved_mode": "demo", "extension_enabled": True},
    ):
        try:
            check(config)
        except ValueError:
            pass
        else:
            raise AssertionError("Guard allowed an unsupported mode")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = ROOT / "patch_backups" / f"approval_{stamp}"
    backup.mkdir(parents=True)
    shutil.copy2(ENGINE, backup / "engine.py")
    shutil.copy2(HTML, backup / "index.html")

    if ENGINE.read_bytes() != original_engine or HTML.read_bytes() != original_html:
        raise RuntimeError("Project changed during installation")

    try:
        MODULE.write_text(CODE, encoding="utf-8")
        ENGINE.write_text(updated_engine, encoding="utf-8")
        HTML.write_text(updated_html, encoding="utf-8")
    except Exception:
        ENGINE.write_bytes(original_engine)
        HTML.write_bytes(original_html)
        MODULE.unlink(missing_ok=True)
        raise

    print("Approval guard installed; permission tests passed.")
    print(f"Backup: {backup}")
    print("Default mode BLOCKS exercise start.")
    print("No clinical rules or PT parameters were approved.")

if __name__ == "__main__":
    main()