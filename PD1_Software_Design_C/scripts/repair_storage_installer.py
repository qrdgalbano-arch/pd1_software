import ast
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_rehab_storage.py"

OLD_CONNECT = '''    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db
'''

NEW_CONNECT = '''    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()
'''

def main():
    original = INSTALLER.read_bytes()
    text = original.decode("utf-8-sig")
    tree = ast.parse(text)
    assignments = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CODE"
            for target in node.targets
        )
    ]
    if len(assignments) != 1:
        raise SystemExit("STOP: expected one CODE block; nothing changed.")

    node = assignments[0]
    code = ast.literal_eval(node.value)

    if "INSERT INTO rehab_reps VALUES (?,?,?,?,?,?,?,?)" not in code:
        raise SystemExit("STOP: expected insert not found; nothing changed.")
    if code.count(OLD_CONNECT) != 1:
        raise SystemExit("STOP: expected connection method not found.")

    code = code.replace(
        "INSERT INTO rehab_reps VALUES (?,?,?,?,?,?,?,?)",
        """INSERT INTO rehab_reps (
                    session_id, rep_index, peak_angle_moving_joint,
                    supporting_joint_angles, target_reached,
                    time_outside_limits, tracking_valid
                ) VALUES (?,?,?,?,?,?,?)""",
        1,
    )
    code = code.replace(
        "import sqlite3\n",
        "import sqlite3\nfrom contextlib import contextmanager\n",
        1,
    )
    code = code.replace(OLD_CONNECT, NEW_CONNECT, 1)
    compile(code, "storage.py", "exec")

    # Replace the embedded module, leaving the test and installer logic intact.
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [
        "CODE = " + repr(code) + "\n"
    ]
    updated = "".join(lines)
    compile(updated, str(INSTALLER), "exec")

    remaining = [
        ROOT / "station" / "rehab_extension" / "storage.py",
        ROOT / "tests" / "test_rehab_storage_extension.py",
    ]
    if any(path.exists() for path in remaining):
        raise SystemExit(
            "STOP: previous installation files remain. "
            "Do not delete databases; report this message."
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder = ROOT / "patch_backups" / f"storage_installer_{stamp}"
    folder.mkdir(parents=True)
    shutil.copy2(INSTALLER, folder / INSTALLER.name)

    if INSTALLER.read_bytes() != original:
        raise RuntimeError("Installer changed during repair")

    INSTALLER.write_text(updated, encoding="utf-8")
    print("Installer repaired: 7-column insert and explicit connection closure.")
    print(f"Backup: {folder}")
    print("Now rerun install_rehab_storage.py.")

if __name__ == "__main__":
    main()