import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "config" / "rehab_extension"

def joint(target=None, enabled=True, confirm=False):
    return {
        "enabled": enabled,
        "target_deg": target,
        "tolerance_deg": None,
        "redness_full_scale_deg": None,
        "pt_confirmation_required": confirm,
    }

def exercise(moving, position, supporting):
    return {
        "moving_joint": moving,
        "testing_position": position,
        "approval": {
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "approved_config_sha256": None,
        },
        "moving_joint_protocol": {
            "range_min_deg": None,
            "range_max_deg": None,
            "target_deg": None,
            "target_tolerance_deg": None,
            "redness_full_scale_deg": None,
        },
        "repetition": {
            "start_threshold_deg": None,
            "return_threshold_deg": None,
            "minimum_duration_seconds": None,
            "required_hold_seconds": None,
        },
        "assessment": {
            "reference_override_deg": None,
            "wnl_tolerance_deg": None,
            "slr_expected_arom_deg": None,
        },
        "supporting_joints": supporting,
    }

def schema(value):
    if value is None:
        return {
            "type": ["number", "null"],
            "description": "PT_SET: null until supplied and approved by the PT."
        }
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    if isinstance(value, list):
        return {"type": "array", "items": {}}
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {k: schema(v) for k, v in value.items()},
            "required": list(value),
            "additionalProperties": False,
        }
    raise TypeError(type(value))

def main():
    exercises = {
        "config_version": "rehab-extension-1",
        "exercises": {
            "ankle_pumps": exercise(
                "ankle", "supported lying",
                {"hip": joint(), "knee": joint(0)},
            ),
            "straight_leg_raise": exercise(
                "hip", "supine with exercised knee extended",
                {
                    "knee": joint(0),
                    "ankle": joint(0, enabled=False),
                },
            ),
            "prone_knee_flexion": exercise(
                "knee", "prone",
                {
                    "hip": joint(0, confirm=True),
                    "ankle": joint(),
                },
            ),
        },
    }

    ankle = exercises["exercises"]["ankle_pumps"]
    ankle["directional_endpoints_deg"] = {
        "dorsiflexion": None,
        "plantarflexion_magnitude": None,
    }
    ankle["assess_directions_separately"] = True

    settings = {
        "config_version": "rehab-extension-1",
        "extension_enabled": False,
        "design_scope": "component",
        "scope_mapping": {
            "component": "component",
            "leg": "asset",
            "whole_body": "system",
        },
        "component_visible_joints": ["hip", "knee", "ankle"],
        "unapproved_mode": "blocked",
        "tracking": {
            "measurement_space": "world_3d_inferred",
            "minimum_landmark_visibility": None,
            "filter": {
                "method": "one_euro",
                "min_cutoff": None,
                "beta": None,
                "derivative_cutoff": None,
            },
        },
        "history": {
            "trend_session_count": None,
            "match_patient_exercise_side_and_measurement_method": True,
        },
        "disclaimer": (
            "Decision authority remains with the patient and the physical "
            "therapist. This tool does not diagnose."
        ),
        "redness_description": (
            "Joint-position deviation: color intensity indicates departure "
            "from your prescribed exercise limits."
        ),
    }

    rom = {
        "config_version": "rehab-extension-1",
        "label": "AAOS values as reproduced in Norkin & White",
        "verification_status": "Edition and table verification pending",
        "reference_edition": None,
        "purpose": "Population documentation; not exercise targets or safety limits",
        "movements": {
            "hip_flexion": {"neutral_deg": 0, "reference_peak_deg": 120},
            "knee_flexion": {"neutral_deg": 0, "reference_peak_deg": 135},
            "knee_extension": {"neutral_deg": 0, "reference_peak_deg": 0},
            "ankle_dorsiflexion": {"neutral_deg": 0, "reference_peak_deg": 20},
            "ankle_plantarflexion": {
                "neutral_deg": 0,
                "reference_peak_magnitude_deg": 50,
                "signed_direction": "negative",
            },
        },
        "measurement_requirements": {
            "store_knee_position_with_ankle_measurements": True,
            "slr_uses_pt_expected_arom_not_120_deg": True,
            "prone_135_is_not_a_required_exercise_endpoint": True,
            "allow_patient_specific_reference_override": True,
        },
    }

    references = {
        "config_version": "rehab-extension-1",
        "references": [
            {
                "id": "norkin_white",
                "title": "Measurement of Joint Motion: A Guide to Goniometry",
                "authors": "Norkin & White",
                "edition": None,
                "status": "PT must confirm edition and relevant tables",
                "use": "Conventions, landmarks, alignment, positions, neutral-zero",
            },
            {
                "id": "aaos_tkr",
                "title": "Total Knee Replacement Exercise Guide",
                "url": (
                    "https://orthoinfo.aaos.org/en/recovery/"
                    "total-knee-replacement-exercise-guide/"
                ),
                "use": "Exercise instructions and positioning only",
                "limitation": (
                    "Postoperative knee-replacement guidance; not an OA "
                    "protocol for patients without a replacement. "
                    "Not a source of AAOS-compliant thresholds."
                ),
            },
            {
                "id": "royal_devon_slr",
                "title": "Royal Devon SLR protocol",
                "status": "Exact leaflet/version and wording require verification",
                "requested_rule": "Foot at 90 degrees to shin; optional ankle rule",
            },
            {
                "id": "sirona_prone",
                "title": "Sirona prone knee flexion protocol",
                "status": "Exact leaflet/version and wording require verification",
                "requested_rule": (
                    "Hip straight and ankle flexed; numerical interpretation "
                    "requires PT approval"
                ),
            },
            {
                "id": "pt_project",
                "title": "PT-approved project protocol",
                "status": "Not approved",
                "use": "Patient targets, tolerances, and feedback interpretation",
            },
        ],
    }

    documents = {
        "settings.json": settings,
        "exercises.json": exercises,
        "rom_reference.json": rom,
        "references.json": references,
    }
    outputs = {}
    for name, document in documents.items():
        outputs[BASE / name] = document
        specification = schema(document)
        specification["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        outputs[BASE / "schemas" / name] = specification

    # Null textual identifiers are not clinical numeric parameters.
    for name in ("exercises.json",):
        props = outputs[BASE / "schemas" / name]["properties"]["exercises"]["properties"]
        for spec in props.values():
            approval = spec["properties"]["approval"]["properties"]
            for key in ("approved_by", "approved_at", "approved_config_sha256"):
                approval[key] = {"type": ["string", "null"]}

    settings_schema = outputs[BASE / "schemas" / "settings.json"]["properties"]
    settings_schema["design_scope"]["enum"] = ["component", "leg", "whole_body"]
    settings_schema["unapproved_mode"]["enum"] = ["blocked", "demo"]
    settings_schema["component_visible_joints"]["items"] = {
        "enum": ["hip", "knee", "ankle"]
    }
    settings_schema["history"]["properties"]["trend_session_count"] = {
        "type": ["integer", "null"], "minimum": 1
    }

    for name, key in (
        ("rom_reference.json", "reference_edition"),
    ):
        outputs[BASE / "schemas" / name]["properties"][key] = {
            "type": ["string", "null"]
        }

    existing = [str(p) for p in outputs if p.exists()]
    if existing:
        raise SystemExit(
            "STOP: files already exist; nothing overwritten:\n"
            + "\n".join(existing)
        )

    written = []
    try:
        for path, value in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(value, indent=2, allow_nan=False) + "\n",
                encoding="utf-8"
            )
            written.append(path)
            json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise

    print("Created 4 configuration files and 4 JSON schemas.")
    print(f"Location: {BASE}")
    print("Extension disabled; exercises unapproved; legacy rules unchanged.")
    print("Checks: JSON parsing only. Runtime approval enforcement comes next.")

if __name__ == "__main__":
    main()