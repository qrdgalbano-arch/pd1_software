import html
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "rehab_extension"
INDEX = ROOT / "web" / "index.html"
JS = ROOT / "web" / "rehab-about.js"
MARKER = "<!-- PD1_REHAB_ABOUT_V1 -->"

SCRIPT = '''
const button = document.getElementById("rehab-about-open");
const dialog = document.getElementById("rehab-about-dialog");
const close = document.getElementById("rehab-about-close");
let previousFocus;
button?.addEventListener("click", () => {
  previousFocus = document.activeElement;
  if (!dialog.open) dialog.showModal();
});
close?.addEventListener("click", () => dialog.close());
dialog?.addEventListener("close", () => previousFocus?.focus());
'''

def escape(value):
    return html.escape(str(value), quote=True)

def load(name):
    return json.loads((CONFIG / name).read_text(encoding="utf-8-sig"))

def main():
    settings = load("settings.json")
    refs = load("references.json")
    rom = load("rom_reference.json")
    exercises = load("exercises.json")

    original = INDEX.read_bytes()
    source = original.decode("utf-8-sig")
    if MARKER in source:
        raise SystemExit(
            "About screen already installed. Reference snapshot unchanged."
        )
    if JS.exists():
        raise SystemExit("rehab-about.js already exists; nothing overwritten.")
    anchor = '<div class="header-actions">'
    if source.count(anchor) != 1 or source.count("</body>") != 1:
        raise SystemExit("Unexpected HTML layout; nothing changed.")

    reference_items = []
    for ref in refs["references"]:
        content = [
            f"<h3>{escape(ref['title'])}</h3>",
            f"<p>{escape(ref.get('use', ''))}</p>",
        ]
        for key in (
            "status", "limitation", "requested_rule", "authors", "edition"
        ):
            if key in ref:
                value = ref[key] if ref[key] is not None else "Not set"
                content.append(f"<p>{escape(key)}: {escape(value)}</p>")
        url = ref.get("url", "")
        if url.startswith("https://"):
            content.append(
                f'<p><a href="{escape(url)}" target="_blank" '
                'rel="noopener noreferrer">Open reference</a></p>'
            )
        reference_items.append("<li>" + "".join(content) + "</li>")

    table_rows = []
    for movement, item in rom["movements"].items():
        peak = item.get(
            "reference_peak_deg", item.get("reference_peak_magnitude_deg")
        )
        table_rows.append(
            f"<tr><th scope='row'>{escape(movement.replace('_', ' '))}</th>"
            f"<td>{escape(peak)}°</td></tr>"
        )

    approval_rows = []
    for name, cfg in exercises["exercises"].items():
        approved = cfg["approval"]["approved"]
        approval_rows.append(
            f"<li>{escape(name.replace('_', ' '))}: "
            f"{'Marked approved in config' if approved else 'Not approved'}</li>"
        )

    content = f"""
{MARKER}
<style>
#rehab-about-dialog {{
  margin:auto;width:min(900px,94vw);max-height:88dvh;
  padding:24px;overflow:auto;border:2px solid var(--color-border);
  border-radius:12px;background:var(--color-surface);color:var(--color-text);
  font:inherit;
}}
#rehab-about-dialog::backdrop {{background:rgba(0,0,0,.65)}}
#rehab-about-dialog h2,#rehab-about-dialog h3 {{
  margin-block:16px 8px;
}}
#rehab-about-dialog p,#rehab-about-dialog li {{margin-block:8px}}
#rehab-about-dialog ul {{padding-left:24px}}
#rehab-about-dialog th,#rehab-about-dialog td {{
  padding:8px;text-align:left;border-bottom:1px solid var(--color-border);
}}
#rehab-about-dialog a {{color:var(--color-link)}}
</style>
<dialog id="rehab-about-dialog" aria-labelledby="rehab-about-title">
  <button id="rehab-about-close" type="button" class="btn compact"
    autofocus>Close About</button>
  <h2 id="rehab-about-title">About this rehabilitation extension</h2>
  <p>{escape(settings["disclaimer"])}</p>
  <p>Research prototype. The new clinical extension is not approved for
     deployment. Legacy evaluation and extension previews remain separate.</p>

  <h3>Population ROM documentation</h3>
  <p>{escape(rom["label"])}</p>
  <p>{escape(rom["verification_status"])}.
     Reference edition: {escape(rom["reference_edition"] or "Not set")}.</p>
  <table>
    <thead><tr><th scope="col">Movement</th>
    <th scope="col">Reference peak</th></tr></thead>
    <tbody>{"".join(table_rows)}</tbody>
  </table>
  <p>These references are not safety limits, redness triggers, or exercise
     targets. SLR requires a PT-set knee-extended expected AROM, not the
     general 120° hip-flexion reference. Ankle measurements require knee
     position documentation. Patient-specific reference overrides are allowed.</p>

  <h3>References and limitations</h3>
  <ul>{"".join(reference_items)}</ul>

  <h3>Configuration status at installation</h3>
  <ul>{"".join(approval_rows)}</ul>
  <p>This page is a configuration snapshot, not approval verification.
     Do not treat an approval flag alone as permission for clinical use.</p>

  <h3>PT_SET parameters</h3>
  <p>Moving-joint ranges, endpoints and tolerances; supporting-joint targets
     where unspecified and all tolerances; redness scales; repetition
     thresholds, timing and hold requirements; WNL tolerances;
     knee-extended SLR expected AROM; patient reference overrides;
     tracking visibility and filter parameters.</p>
  <p>Supplied PT_SET values remain null until a PT enters and approves them.</p>

  <h3>Visual feedback</h3>
  <p>{escape(settings["redness_description"])}</p>
  <p>Redness is not pain, injury, inflammation, measured joint stress,
     or a diagnosis. Shared proportional-redness integration is pending.</p>

  <h3>Validation</h3>
  <p>The installed validation utility calculates descriptive comparisons.
     Passing software tests does not establish clinical accuracy.
     Real matched camera/goniometer readings and PT review are required.</p>
</dialog>
<script type="module" src="/static/rehab-about.js?v=1"></script>
"""

    button = (
        '<button id="rehab-about-open" type="button" '
        'class="btn compact">About / References</button>'
    )
    updated = source.replace(anchor, anchor + "\n" + button, 1)
    updated = updated.replace("</body>", content + "\n</body>", 1)

    backup = ROOT / "patch_backups" / datetime.now().strftime(
        "about_%Y%m%d_%H%M%S_%f"
    )
    backup.mkdir(parents=True)
    shutil.copy2(INDEX, backup / "index.html")
    if INDEX.read_bytes() != original:
        raise RuntimeError("HTML changed during installation")

    try:
        JS.write_text(SCRIPT, encoding="utf-8")
        INDEX.write_text(updated, encoding="utf-8")
    except Exception:
        INDEX.write_bytes(original)
        JS.unlink(missing_ok=True)
        raise

    print("About / References screen installed.")
    print(f"Backup: {backup}")
    print("Configuration snapshot only; no clinical rules changed.")
    print("Refresh browser with Ctrl+F5. Browser verification required.")

if __name__ == "__main__":
    main()