from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "station" / "rehab_extension" / "validation.py"
TEST = ROOT / "tests" / "test_rehab_validation_extension.py"

CODE = r'''
"""Offline paired-angle validation. Never grants clinical approval."""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

FIELDS = [
    "participant_code", "exercise_id", "joint", "side",
    "testing_condition", "measurement_method", "config_version",
    "knee_position_deg", "camera_deg", "goniometer_deg",
]

def analyze(rows):
    if not rows:
        raise ValueError("No paired readings")
    pairs = []
    groups = set()
    participants = []
    for row in rows:
        for field in FIELDS:
            if field not in row:
                raise ValueError(f"Missing column: {field}")
        required_text = [
            "participant_code", "exercise_id", "joint", "side",
            "testing_condition", "measurement_method", "config_version"
        ]
        if any(not str(row[k]).strip() for k in required_text):
            raise ValueError("Required measurement metadata is blank")
        if row["side"] not in ("left", "right"):
            raise ValueError("Side must be left or right")
        if row["joint"] not in ("hip", "knee", "ankle"):
            raise ValueError("Unknown joint")
        camera = float(row["camera_deg"])
        reference = float(row["goniometer_deg"])
        if not all(math.isfinite(v) for v in (camera, reference)):
            raise ValueError("Angles must be finite")
        if row["joint"] == "ankle":
            knee = float(row["knee_position_deg"])
            if not math.isfinite(knee):
                raise ValueError("Ankle measurements need knee position")
        groups.add(tuple(row[k] for k in (
            "exercise_id", "joint", "side", "testing_condition",
            "measurement_method", "config_version"
        )))
        participants.append(row["participant_code"])
        pairs.append({
            **row,
            "pair_mean_deg": (camera + reference) / 2,
            "difference_camera_minus_pt_deg": camera - reference,
        })
    if len(groups) != 1:
        raise ValueError(
            "Analyze matching exercise/joint/side/condition/method/config "
            "groups separately."
        )
    differences = [p["difference_camera_minus_pt_deg"] for p in pairs]
    bias = statistics.mean(differences)
    repeated = len(set(participants)) != len(participants)
    enough = len(pairs) >= 2
    sd = statistics.stdev(differences) if enough else None
    eligible = enough and not repeated
    return {
        "n_pairs": len(pairs),
        "mean_absolute_error_deg": statistics.mean(map(abs, differences)),
        "bias_camera_minus_pt_deg": bias,
        "sample_sd_difference_deg": sd,
        "lower_limit_deg": bias - 1.96 * sd if eligible else None,
        "upper_limit_deg": bias + 1.96 * sd if eligible else None,
        "repeated_participants": repeated,
        "limits_status": (
            "Descriptive basic limits; assumptions not automatically verified"
            if eligible else
            "Withheld: repeated participants require repeated-measures analysis"
            if repeated else "Withheld: fewer than two pairs"
        ),
        "deployment_approved": False,
        "clinical_acceptance_criteria": None,
        "pairs": pairs,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--template", type=Path)
    args = parser.parse_args()

    if args.template:
        args.template.parent.mkdir(parents=True, exist_ok=True)
        with args.template.open("x", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(FIELDS)
        print(f"Blank template created: {args.template}")
        return

    if not args.input or not args.output:
        parser.error("Supply --input and --output, or --template")
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        report = analyze(list(csv.DictReader(handle)))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(f"Saved: {args.output}")
    print("Descriptive comparison only; no automatic clinical approval.")

if __name__ == "__main__":
    main()
'''

TESTS = r'''
"""Artificial numerical fixtures for software tests, not validation evidence."""
import unittest
from station.rehab_extension.validation import analyze

def row(person, camera, pt):
    return dict(
        participant_code=person, exercise_id="test", joint="knee",
        side="left", testing_condition="test",
        measurement_method="test", config_version="test",
        knee_position_deg="", camera_deg=camera, goniometer_deg=pt,
    )

class ValidationTests(unittest.TestCase):
    def test_statistics(self):
        result = analyze([
            row("a", 8, 10), row("b", 10, 10), row("c", 12, 10)
        ])
        self.assertAlmostEqual(result["mean_absolute_error_deg"], 4/3)
        self.assertEqual(result["bias_camera_minus_pt_deg"], 0)
        self.assertEqual(result["sample_sd_difference_deg"], 2)
        self.assertAlmostEqual(result["upper_limit_deg"], 3.92)
        self.assertFalse(result["deployment_approved"])

    def test_repeated_participants(self):
        result = analyze([row("a", 8, 10), row("a", 12, 10)])
        self.assertTrue(result["repeated_participants"])
        self.assertIsNone(result["upper_limit_deg"])

    def test_single_pair(self):
        result = analyze([row("a", 8, 10)])
        self.assertIsNone(result["lower_limit_deg"])

    def test_mixed_conditions_rejected(self):
        a, b = row("a", 8, 10), row("b", 12, 10)
        b["side"] = "right"
        with self.assertRaises(ValueError):
            analyze([a, b])

if __name__ == "__main__":
    unittest.main()
'''

def main():
    if not MODULE.parent.is_dir():
        raise SystemExit("Install the extension core first.")
    files = {MODULE: CODE, TEST: TESTS}
    for path, source in files.items():
        if path.exists():
            raise SystemExit(f"STOP: already exists: {path}")
        compile(source, str(path), "exec")
    written = []
    try:
        for path, source in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
            written.append(path)
        result = subprocess.run([
            sys.executable, "-m", "unittest", "discover",
            "-s", "tests", "-p", "test_rehab_validation_extension.py", "-v"
        ], cwd=ROOT)
        if result.returncode:
            raise RuntimeError("Validation tests failed")
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    print("Validation module installed; 4 tests passed.")
    print("No real validation readings were created.")

if __name__ == "__main__":
    main()