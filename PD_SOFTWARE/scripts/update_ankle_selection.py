import ast
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
HTML = ROOT / "web" / "index.html"
APP = ROOT / "web" / "app.js"
BRIDGE = ROOT / "station" / "rehab_extension" / "session_bridge.py"
MODULE = ROOT / "web" / "ankle-reference.js"
MARKER = "// PD1_ANKLE_SELECTION_V1"

JS = r'''
export function renderAnkleReference(state) {
  if (!["ankle_pump", "ankle_pumps"].includes(state?.exercise_key)) return;
  const label = document.getElementById("live-arom");
  if (label) {
    label.textContent =
      "Population references: dorsiflexion +20°; plantarflexion −50°; " +
      "neutral 0°. Not prescribed targets.";
  }
}
'''

def main():
    originals = {
        p: p.read_bytes() for p in (HTML, APP, BRIDGE)
    }
    html = originals[HTML].decode("utf-8-sig")
    app = originals[APP].decode("utf-8-sig")
    bridge = originals[BRIDGE].decode("utf-8-sig")

    if MARKER in app or MODULE.exists():
        raise SystemExit("Already/partially installed; nothing overwritten.")

    # Only change the Design B option's visible label.
    pattern = r"""(<option\b[^>]*value=["']asset["'][^>]*>)(.*?)(</option>)"""
    def label(match):
        text = re.sub(r"\s*\(later\)", "", match.group(2), flags=re.I)
        return match.group(1) + text + match.group(3)
    html_new, count = re.subn(pattern, label, html, flags=re.S)
    if count != 1:
        raise SystemExit("STOP: expected one Design B selector option.")

    # Filter selectable prescriptions, not historical records.
    assignment = r"\bprescriptions\s*=\s*data\.prescriptions(?:\s*\|\|\s*\[\s*\])?\s*;"
    replacement = (
        "prescriptions = (data.prescriptions || []).filter(p => "
        '!["prone_leg_flexion", "prone_knee_flexion"].includes(p.exercise_key)'
        ");"
    )
    app_new, count = re.subn(assignment, replacement, app)
    if count != 1:
        raise SystemExit("STOP: prescription-loading code differs; no changes.")

    # Run the reference-label update after the regular live readings.
    render_anchor = r"renderJoints\(\s*state\s*,\s*jointStatus\(\s*state\s*\)\s*\);"
    app_new, count = re.subn(
        render_anchor,
        lambda m: m.group(0) + "\n    renderAnkleReference(state);",
        app_new,
    )
    if count != 1:
        raise SystemExit("STOP: live-render hook differs; no changes.")
    app_new = (
        MARKER + "\n"
        'import { renderAnkleReference } from "/static/ankle-reference.js?v=1";\n'
        + app_new
    )

    # The backend uses singular ankle_pump; the extension uses ankle_pumps.
    if '"ankle_pump": "ankle_pumps"' in bridge:
        bridge_new = bridge
    else:
        alias = '"ankle_pumps": "ankle_pumps",'
        if bridge.count(alias) != 1:
            raise SystemExit("STOP: extension exercise mapping differs.")
        bridge_new = bridge.replace(
            alias,
            '"ankle_pump": "ankle_pumps",\n    ' + alias,
            1,
        )
    compile(bridge_new, str(BRIDGE), "exec")

    html_new, count = re.subn(
        r'(/static/app\.js)(?:\?[^"\']*)?(?=["\'])',
        r'\1?v=ankle-selection-1', html_new,
    )
    if count != 1:
        raise SystemExit("STOP: expected one app.js reference.")

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
        "ankle_selection_%Y%m%d_%H%M%S_%f"
    )
    backup.mkdir(parents=True)
    for path in originals:
        target = backup / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    if any(p.read_bytes() != data for p, data in originals.items()):
        raise RuntimeError("Project changed during installation")

    try:
        HTML.write_text(html_new, encoding="utf-8")
        APP.write_text(app_new, encoding="utf-8")
        BRIDGE.write_text(bridge_new, encoding="utf-8")
        MODULE.write_text(JS, encoding="utf-8")
    except Exception:
        for path, data in originals.items():
            path.write_bytes(data)
        MODULE.unlink(missing_ok=True)
        raise

    print("Design B '(later)' label removed.")
    print("Prone-flexion prescriptions hidden from new exercise selections.")
    print("Existing ankle-pump prescriptions remain selectable.")
    print("Ankle population references displayed: +20 / -50 degrees.")
    print("No prescriptions, patient records, or PT thresholds changed.")
    print(f"Backup: {backup}")

if __name__ == "__main__":
    main()
