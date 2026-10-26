from datetime import datetime
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "web" / "app.js"
HTML = ROOT / "web" / "index.html"
MODULE = ROOT / "web" / "rehab-preview.js"
MARKER = "// PD1_REHAB_PREVIEW_V1"

JS = r'''
// Parallel measurements only; never changes exercise evaluation.
let panel, status, reason, body;

function ensurePanel() {
  if (panel) return true;
  const live = document.getElementById("screen-live");
  if (!live) return false;

  panel = document.createElement("details");
  panel.id = "rehab-measurement-preview";
  panel.className = "joint-details";
  panel.open = true;

  const heading = document.createElement("summary");
  heading.textContent = "Extension measurements — unapproved preview";
  panel.append(heading);

  const note = document.createElement("p");
  note.className = "hint";
  note.textContent =
    "Separate research stream. These values do not drive the current " +
    "rep counter, clinical labels, or avatar redness.";
  panel.append(note);

  status = document.createElement("p");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  panel.append(status);

  reason = document.createElement("p");
  reason.className = "hint";
  panel.append(reason);

  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const table = document.createElement("table");
  const caption = document.createElement("caption");
  caption.textContent = "Neutral-zero world-XYZ estimates";
  table.append(caption);

  const head = document.createElement("thead");
  const row = document.createElement("tr");
  for (const label of ["Joint", "Raw angle", "Filtered angle", "State"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    row.append(th);
  }
  head.append(row);
  table.append(head);
  body = document.createElement("tbody");
  table.append(body);
  wrap.append(table);
  panel.append(wrap);

  const anchor = live.querySelector(".joint-details");
  if (anchor) anchor.insertAdjacentElement("afterend", panel);
  else live.append(panel);
  return true;
}

function degrees(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)}°` : "—";
}

export function renderRehabPreview(state) {
  if (!state || !ensurePanel()) return;
  const data = state.rehab_measurements;
  const disconnected = data == null;
  const paused = state.phase === "paused";
  const uncertain = state.camera_error || state.pose_detected === false;

  const label = disconnected ? "Waiting for extension stream"
    : paused ? "Paused — readings held"
    : uncertain ? "Tracking uncertain"
    : data.state || "Waiting for measurements";

  const text = `Extension status: ${label}`;
  if (status.textContent !== text) status.textContent = text;
  reason.textContent = disconnected
    ? "Restart the station after installing the live measurement extension."
    : data.reason || (
      "Hip requires body-frame calibration. Camera-inferred depth is " +
      "not a validated goniometer measurement."
    );

  const rows = [];
  for (const joint of ["hip", "knee", "ankle"]) {
    const reading = data?.joints?.[joint];
    const valid = !paused && !uncertain && reading?.tracked === true;
    const tr = document.createElement("tr");
    const cells = [
      joint[0].toUpperCase() + joint.slice(1),
      valid ? degrees(reading.raw_angle) : "—",
      valid ? degrees(reading.angle) : "—",
      paused ? "Paused"
        : uncertain ? "Tracking uncertain"
        : reading?.state || label,
    ];
    for (const value of cells) {
      const cell = document.createElement("td");
      cell.textContent = value;
      tr.append(cell);
    }
    rows.push(tr);
  }
  body.replaceChildren(...rows);
}
'''

def main():
    app_original = APP.read_bytes()
    html_original = HTML.read_bytes()
    app = app_original.decode("utf-8-sig")
    html = html_original.decode("utf-8-sig")

    if MARKER in app:
        raise SystemExit("Preview already installed; nothing changed.")
    if MODULE.exists():
        raise SystemExit("rehab-preview.js already exists; nothing overwritten.")

    pattern = r"\bfunction\s+render\s*\(\s*state\s*\)\s*\{"
    matches = list(re.finditer(pattern, app))
    if len(matches) != 1:
        raise SystemExit("STOP: expected one render(state) function.")

    insert = matches[0].end()
    hook = (
        "\n  // Presentation errors must not stop existing UI updates.\n"
        "  try { renderRehabPreview(state); }\n"
        '  catch (error) { console.warn("Rehab preview:", error); }\n'
    )
    updated_app = (
        MARKER + "\n"
        'import { renderRehabPreview } from '
        '"/static/rehab-preview.js?v=1";\n'
        + app[:insert] + hook + app[insert:]
    )

    updated_html, count = re.subn(
        r'(/static/app\.js)(?:\?[^"\']*)?(?=["\'])',
        r'\1?v=rehab-preview-1',
        html,
    )
    if count != 1:
        raise SystemExit("STOP: expected one app.js reference in HTML.")

    backup = ROOT / "patch_backups" / datetime.now().strftime(
        "measurement_preview_%Y%m%d_%H%M%S_%f"
    )
    backup.mkdir(parents=True)
    shutil.copy2(APP, backup / "app.js")
    shutil.copy2(HTML, backup / "index.html")

    if APP.read_bytes() != app_original or HTML.read_bytes() != html_original:
        raise RuntimeError("Project files changed during installation")

    try:
        MODULE.write_text(JS, encoding="utf-8")
        APP.write_text(updated_app, encoding="utf-8")
        HTML.write_text(updated_html, encoding="utf-8")
    except Exception:
        APP.write_bytes(app_original)
        HTML.write_bytes(html_original)
        MODULE.unlink(missing_ok=True)
        raise

    print("Measurement preview installed.")
    print(f"Backup: {backup}")
    print("Browser verification required; no clinical logic changed.")

if __name__ == "__main__":
    main()