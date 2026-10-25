from datetime import datetime
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "web" / "index.html"
ORIENTATION = ROOT / "web" / "pose-orientation.js"

START = "<!-- PD1 TWIN PANEL EXTENSION START -->"
END = "<!-- PD1 TWIN PANEL EXTENSION END -->"

EXTENSION = """
<!-- PD1 TWIN PANEL EXTENSION START -->
<style id="pd1-twin-panel-extension">
  /* Presentation settings only; no clinical thresholds. */
  :root {
    --pd1-twin-panel-opacity: 92%;
    --pd1-twin-model-height: clamp(280px, 36vh, 420px);
  }

  .twin-panel.twin-single {
    background: var(--color-surface);
    background: color-mix(
      in srgb,
      var(--color-surface) var(--pd1-twin-panel-opacity),
      transparent
    );
    min-width: 0;
    overflow: visible;
  }

  /* Keep the orientation implementation mounted but hide its controls. */
  .twin-panel .orientation-shell,
  .twin-panel .orientation-controls {
    display: none !important;
  }

  .twin-panel .twin-model-surface {
    position: relative;
    display: block;
    flex: 0 0 auto !important;
    width: 100%;
    height: var(--pd1-twin-model-height) !important;
    min-height: 280px !important;
    overflow: hidden;
    border-radius: var(--radius-sm, 6px);
  }

  .twin-panel #avatar {
    position: relative;
    display: block;
    width: 100%;
    height: 100% !important;
    min-height: 0 !important;
  }

  .twin-panel #avatar canvas {
    display: block;
    max-width: 100%;
  }

  .twin-panel .twin-model-message {
    position: absolute;
    inset: 0;
    overflow: auto;
    padding: var(--space-3, 12px);
    background: var(--color-surface);
  }

  .twin-panel .pd1-depth-note {
    margin: var(--space-2, 8px) var(--space-3, 12px);
    color: var(--color-text-muted);
    font-size: var(--text-xs, 1rem);
    line-height: 1.4;
    overflow-wrap: anywhere;
  }

  @media (max-width: 800px) {
    :root {
      --pd1-twin-model-height: 320px;
    }
  }
</style>
<!-- PD1 TWIN PANEL EXTENSION END -->
"""

NOTE = """
<p id="pd1-depth-note" class="hint pd1-depth-note">
  Research mode: camera-inferred depth. Exercise thresholds require
  3D validation. Orientation is held when tracking is uncertain.
</p>
"""

def fail(message):
    sys.exit(f"STOPPED: {message}\nNo project files changed.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check compatibility without changing project files.",
    )
    args = parser.parse_args()

    if not HTML.is_file() or not ORIENTATION.is_file():
        fail("Expected web/index.html and web/pose-orientation.js.")

    original = HTML.read_bytes()
    text = original.decode("utf-8-sig")
    orientation = ORIENTATION.read_text(encoding="utf-8-sig")

    if START in text:
        if END not in text:
            fail("An incomplete previous panel extension was found.")
        print("Twin panel extension is already installed.")
        print("No files changed. Restart the station and refresh the browser.")
        return

    required = (
        'id="avatar"',
        'class="twin-model-surface"',
        'id="twin-design"',
        'class="twin-camera-controls"',
    )
    missing = [item for item in required if item not in text]
    if missing:
        fail(f"HTML structure differs. Missing: {missing}")

    if "orientation-shell" not in orientation:
        fail("The orientation control wrapper differs from the expected version.")

    anchor = '<div class="twin-camera-controls">'
    if text.count(anchor) != 1 or text.count("</head>") != 1:
        fail("Expected one camera-control section and one </head>.")

    updated = text.replace("</head>", EXTENSION + "\n</head>", 1)
    if 'id="pd1-depth-note"' not in updated:
        updated = updated.replace(anchor, NOTE + anchor, 1)

    print("Compatibility check passed.")
    print("Only web/index.html will change.")
    print("Orientation logic, avatar.js, and avatar_map.json stay unchanged.")

    if args.check:
        print("Check-only mode: no project files changed.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = ROOT / "patch_backups" / f"twin_panel_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup = backup_dir / "index.html"
    shutil.copy2(HTML, backup)

    if HTML.read_bytes() != original:
        sys.exit("STOPPED: index.html changed during the patch. No patch applied.")

    temporary = HTML.with_name("index.html.twin-panel.tmp")
    try:
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, HTML)
    finally:
        if temporary.exists():
            temporary.unlink()

    print("Twin panel extension installed.")
    print(f"Backup: {backup}")
    print(f"Original SHA256: {hashlib.sha256(original).hexdigest()}")
    print("Restart the station and press Ctrl+F5.")
    print("To restore, stop the station and run:")
    print(f'Copy-Item -LiteralPath "{backup}" -Destination "{HTML}" -Force')

if __name__ == "__main__":
    main()