# Design C Prototype (rule-based, no backend)

Browser-only prototype. Pose estimation: MediaPipe Pose Landmarker (model kept at `PD1_Software_Design_C/models/pose_landmarker_full.task`). All assessment is rule-based (joint angles + state machine). No DTW, no ML classifier, no database, no server code. 3D digital twin uses `PD1_Software_Design_C/avatar/Design C/scene.glb` with a 2D fallback.

## Run
From the repository root:

    python -m http.server 8000

Open http://localhost:8000/prototype/ in Chrome/Edge and allow the camera. Internet is needed for the MediaPipe script/WASM (jsDelivr CDN).

Short demo: `?reps=2&rest=10` (2 reps per leg per set, 10 s rest).

If the landmark dots are not on your body, change "Pose view rotation" under the camera view (Auto / 0 / 90 / -90).

## Workflow
Patient ID (any 7 digits) -> exercise list -> (skip prompt + reason if previous exercise not done) -> instructions -> Start Session -> target pose shown first -> position check -> avatar mirrors the patient -> leg is chosen by the patient -> reps counted when form is correct (range is reported separately) -> switch leg -> 3-minute rest (extend +1 min) -> set 2 (first 2 valid reps confirm resume) -> summary.

## Normal limits (summary classification only)
Set in `prototype/config.js` as `wnl_min_deg`. Provisional until the PT confirms.

| Exercise | Limit | Basis |
|---|---|---|
| Straight Leg Raise (hip flexion, knee straight) | 70 deg | Healthy-adult mean 70 deg, range 30-90 deg (PMC2505147). Passive test; the prototype measures active. |
| Prone Leg Flexion (knee flexion) | 135 deg | AAOS 135 deg; CDC male 20-44 mean 137.7 deg. No prone-specific norm found. |
| Straight knee | 0 deg target | Norkin p.246; >5 deg beyond zero is hyperextension. Tolerances in config are PT settings. |

Norkin & White p.200 (hip flexion 100 deg AMA / 120 deg AAOS) and p.244 (knee flexion 150 deg AMA, supine) are general joint-motion values and are not used as the classification cutoffs.

The exercise target per rep (`target_deg`) and the ghost angle (`ghost_deg`) are rehab goals, separate from the normal limits. All start/rest/target/speed/tolerance angles were carried over from the old branch and are not PT-validated.
