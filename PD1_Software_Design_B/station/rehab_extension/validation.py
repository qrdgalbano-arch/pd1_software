
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
