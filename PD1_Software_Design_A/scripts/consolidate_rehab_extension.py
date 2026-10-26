import ast
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path.cwd()
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
EXT = ROOT / "station" / "rehab_extension"
stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
BACKUP = ROOT / "patch_backups" / f"consolidation_{stamp}"
BACKUP.mkdir(parents=True)

OLD_CONNECT = """    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db
"""

NEW_CONNECT = """    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()
"""

def save_backup(path):
    target = BACKUP / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

def corrected_storage(code):
    result = code.replace(
        "INSERT INTO rehab_reps VALUES (?,?,?,?,?,?,?,?)",
        "INSERT INTO rehab_reps VALUES (?,?,?,?,?,?,?)",
    )
    if OLD_CONNECT in result:
        if "from contextlib import contextmanager" not in result:
            result = result.replace(
                "import sqlite3\n",
                "import sqlite3\nfrom contextlib import contextmanager\n",
                1,
            )
        result = result.replace(OLD_CONNECT, NEW_CONNECT, 1)
    compile(result, "storage.py", "exec")
    return result

def run_installer(name):
    path = ROOT / "scripts" / name
    if not path.is_file():
        raise RuntimeError(
            f"Missing scripts/{name}. Save that earlier installer first."
        )
    print(f"\nRUNNING: {name}", flush=True)
    result = subprocess.run([str(PYTHON), str(path)], cwd=ROOT)
    if result.returncode:
        raise RuntimeError(f"{name} failed. Stop here; review its output.")

def ensure_pair(feature, module, test, installer):
    present = module.is_file()
    tested = test.is_file()
    if present and tested:
        print(f"PRESERVED: {feature}", flush=True)
        return
    if present != tested:
        raise RuntimeError(
            f"Partial installation of {feature}. "
            "Existing files were not overwritten."
        )
    run_installer(installer)

def main():
    if not PYTHON.exists() or not (ROOT / "station" / "engine.py").exists():
        raise RuntimeError("Run from the PD_SOFTWARE folder.")

    # Repair the embedded storage source, whether the installer is old
    # or was already repaired successfully.
    installer = ROOT / "scripts" / "install_rehab_storage.py"
    if installer.exists():
        original = installer.read_text(encoding="utf-8-sig")
        tree = ast.parse(original)
        blocks = [
            n for n in tree.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "CODE"
                for t in n.targets
            )
        ]
        if len(blocks) != 1:
            raise RuntimeError("Unexpected storage installer CODE structure.")
        node = blocks[0]
        before = ast.literal_eval(node.value)
        after = corrected_storage(before)
        if before != after:
            lines = original.splitlines(keepends=True)
            lines[node.lineno - 1:node.end_lineno] = [
                "CODE = " + repr(after) + "\n"
            ]
            updated = "".join(lines)
            compile(updated, str(installer), "exec")
            save_backup(installer)
            installer.write_text(updated, encoding="utf-8")
            print("REPAIRED: storage installer", flush=True)

    # Repair an installed storage module too, without touching databases.
    storage = EXT / "storage.py"
    if storage.exists():
        before = storage.read_text(encoding="utf-8-sig")
        after = corrected_storage(before)
        if before != after:
            save_backup(storage)
            storage.write_text(after, encoding="utf-8")
            print("REPAIRED: installed storage module", flush=True)

    ensure_pair(
        "shared core", EXT / "core.py",
        ROOT / "tests" / "test_rehab_core_extension.py",
        "install_rehab_core.py",
    )

    config = ROOT / "config" / "rehab_extension"
    expected_config = [
        config / name for name in (
            "settings.json", "exercises.json",
            "rom_reference.json", "references.json",
        )
    ]
    expected_config += [
        config / "schemas" / name for name in (
            "settings.json", "exercises.json",
            "rom_reference.json", "references.json",
        )
    ]
    if not any(p.exists() for p in expected_config):
        run_installer("install_rehab_config.py")
    elif not all(p.is_file() for p in expected_config):
        raise RuntimeError("Partial clinical configuration; nothing overwritten.")

    engine_path = ROOT / "station" / "engine.py"
    engine = engine_path.read_text(encoding="utf-8-sig")
    guard_module = EXT / "approval.py"
    guard_hook = "# PD1_APPROVAL_GUARD_V1" in engine
    if not guard_module.exists() and not guard_hook:
        run_installer("install_approval_guard.py")
    elif not guard_module.exists() or not guard_hook:
        raise RuntimeError("Partial approval-guard installation.")

    ensure_pair(
        "XYZ angle functions", EXT / "angles.py",
        ROOT / "tests" / "test_rehab_angles_extension.py",
        "install_rehab_angles.py",
    )
    ensure_pair(
        "session storage", EXT / "storage.py",
        ROOT / "tests" / "test_rehab_storage_extension.py",
        "install_rehab_storage.py",
    )
    ensure_pair(
        "goniometer validation", EXT / "validation.py",
        ROOT / "tests" / "test_rehab_validation_extension.py",
        "install_rehab_validation.py",
    )

    engine = engine_path.read_text(encoding="utf-8-sig")
    live_module = EXT / "live.py"
    live_hook = "# PD1_REHAB_LIVE_MEASUREMENTS_V1" in engine
    if not live_module.exists() and not live_hook:
        run_installer("install_live_measurements.py")
    elif not live_module.exists() or not live_hook:
        raise RuntimeError("Partial live-measurement installation.")

    app_path = ROOT / "web" / "app.js"
    app = app_path.read_text(encoding="utf-8-sig")
    preview = ROOT / "web" / "rehab-preview.js"
    preview_hook = "// PD1_REHAB_PREVIEW_V1" in app
    if not preview.exists() and not preview_hook:
        run_installer("install_measurement_preview.py")
    elif not preview.exists() or not preview_hook:
        raise RuntimeError("Partial measurement-preview installation.")

    html_path = ROOT / "web" / "index.html"
    html = html_path.read_text(encoding="utf-8-sig")
    about = ROOT / "web" / "rehab-about.js"
    about_hook = "<!-- PD1_REHAB_ABOUT_V1 -->" in html
    if not about.exists() and not about_hook:
        run_installer("install_rehab_about.py")
    elif not about.exists() or not about_hook:
        raise RuntimeError("Partial About installation.")

    # Syntax-check Python without importing or launching the engine.
    for path in list(EXT.glob("*.py")) + [
        engine_path, ROOT / "station" / "exercises.py"
    ]:
        compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")
    print("\nPython syntax checks passed.", flush=True)

    # Discover exactly the four extension test suites.
    sys.path.insert(0, str(ROOT))
    import unittest
    expected_tests = [
        "test_rehab_core_extension.py",
        "test_rehab_angles_extension.py",
        "test_rehab_storage_extension.py",
        "test_rehab_validation_extension.py",
    ]
    suite = unittest.TestSuite()
    for filename in expected_tests:
        found = unittest.TestLoader().discover(
            str(ROOT / "tests"), pattern=filename
        )
        if found.countTestCases() == 0:
            raise RuntimeError(f"No tests discovered: {filename}")
        suite.addTests(found)
    tested = unittest.TextTestRunner(verbosity=2).run(suite)

    # Parse all supplied JSON config/schema documents.
    for path in expected_config:
        json.loads(path.read_text(encoding="utf-8-sig"))

    # Browser modules: parse using Node if it is installed.
    node = shutil.which("node")
    javascript = "Not checked: Node.js unavailable"
    js_ok = True
    if node:
        for path in (
            ROOT / "web" / "rehab-preview.js",
            ROOT / "web" / "rehab-about.js",
        ):
            result = subprocess.run(
                [node, "--input-type=module", "--check"],
                input=path.read_text(encoding="utf-8"),
                text=True, capture_output=True,
            )
            if result.returncode:
                js_ok = False
                print(result.stderr, flush=True)
        javascript = "Passed" if js_ok else "Failed"

    settings = json.loads(
        (config / "settings.json").read_text(encoding="utf-8-sig")
    )
    exercises = json.loads(
        (config / "exercises.json").read_text(encoding="utf-8-sig")
    )

    def null_paths(value, prefix=""):
        found = []
        if isinstance(value, dict):
            for key, item in value.items():
                path = f"{prefix}.{key}" if prefix else key
                found.extend(null_paths(item, path))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                found.extend(null_paths(item, f"{prefix}[{index}]"))
        elif value is None:
            found.append(prefix)
        return found

    pending = [
        "Calibrated hip anatomical frame and real-world measurement validation",
        "PT approval verification and shared live exercise evaluator",
        "Automatic new-session, repetition, and telemetry recording",
        "Shared proportional avatar redness in Designs A/B/C",
        "Final post-exercise summary and historical trend UI",
        "End-to-end camera/browser regression testing",
    ]

    report = {
        "generated_at": datetime.now().isoformat(),
        "port": 18080,
        "tests_run": tested.testsRun,
        "tests_passed": tested.wasSuccessful(),
        "javascript_syntax": javascript,
        "json_check": "Parsed; schema semantics not validated",
        "extension_enabled": settings.get("extension_enabled"),
        "unapproved_mode": settings.get("unapproved_mode"),
        "unset_configuration_fields": (
            null_paths(settings, "settings")
            + null_paths(exercises, "exercises")
        ),
        "remaining_integration": pending,
        "clinical_deployment_ready": False,
    }

    reports = ROOT / "data" / "rehab_extension_reports"
    reports.mkdir(parents=True, exist_ok=True)
    report_path = reports / f"readiness_{stamp}.json"
    report_path.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    readme = ROOT / "README_REHAB_EXTENSION.md"
    if readme.exists():
        save_backup(readme)
    readme.write_text(
        "# Rehabilitation extension: implementation status\n\n"
        "Research/demo only. Clinical deployment is not approved.\n\n"
        "Decision authority remains with the patient and the physical "
        "therapist. This tool does not diagnose.\n\n"
        "## Installed building blocks\n"
        "- Shared AROM classification and joint-redness functions.\n"
        "- Neutral-zero XYZ geometric angle functions.\n"
        "- Parallel live measurement preview; legacy evaluation unchanged.\n"
        "- Separate local storage and history utilities.\n"
        "- Offline paired goniometer-validation utility.\n"
        "- PT configuration templates, demo guard, About screen.\n\n"
        "## PT_SET\n"
        "Unspecified targets, tolerances, redness scales, repetition "
        "thresholds/timing, SLR expected AROM, patient overrides, tracking "
        "visibility and filter parameters require PT input and approval. "
        "Do not replace nulls with guessed values.\n\n"
        "## References\n"
        "- Norkin & White, Measurement of Joint Motion: A Guide to "
        "Goniometry; edition/table verification pending.\n"
        "- AAOS Total Knee Replacement Exercise Guide: positioning and "
        "instructions only, not universal clinical thresholds or an OA "
        "protocol for patients without replacement.\n"
        "- Royal Devon SLR protocol: exact document verification pending.\n"
        "- Sirona prone-knee protocol: exact document verification pending.\n"
        "- Patient-specific PT-approved project protocol: pending.\n\n"
        "## Not yet integrated\n"
        + "".join(f"- {item}.\n" for item in pending)
        + "\n## Tests and startup\n"
        "Run the extension unittest suites before further integration.\n"
        "PowerShell startup:\n"
        "```powershell\n"
        '$env:STATION_PORT = "18080"\n'
        'powershell -NoProfile -File ".\\run_station.ps1"\n'
        "```\n\n"
        "Passing unit tests does not establish clinical accuracy or "
        "complete the live-system requirements.\n",
        encoding="utf-8",
    )

    print(f"\nReport: {report_path}", flush=True)
    print(f"README: {readme}", flush=True)
    print(f"Backups: {BACKUP}", flush=True)
    print(f"Extension tests: {tested.testsRun}", flush=True)
    print(f"JavaScript syntax: {javascript}", flush=True)
    print("Clinical deployment ready: NO", flush=True)

    if not tested.wasSuccessful() or not js_ok:
        raise RuntimeError("Checks failed. Do not proceed to further patches.")

    print("\nCONSOLIDATION PASSED.", flush=True)
    print("Existing clinical parameters and demo settings were preserved.")
    print("Live integration tasks remain; see the README.")

if __name__ == "__main__":
    main()
