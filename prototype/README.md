# Design C Prototype (rule-based, no backend)

Browser-only prototype. Pose estimation: MediaPipe Pose Landmarker (model kept at `PD1_Software_Design_C/models/pose_landmarker_full.task`). All assessment is rule-based (joint angles + state machine). No DTW, no ML classifier, no database, no server code.

## Run
From the repository root:

    python -m http.server 8000

Open http://localhost:8000/prototype/ in Chrome/Edge and allow the camera. Internet is needed once for the MediaPipe script/WASM (jsDelivr CDN).

Short demo: `?reps=2&rest=10` (2 reps per leg per set, 10 s rest).

## Workflow
Patient ID (any 7 digits) -> exercise list -> (skip prompt + reason if previous exercise not done) -> instructions -> Start Session -> position check (ghost + arrows + voice) -> rep counting with feedback and sound -> switch leg -> 3-minute rest (extend +1 min) -> set 2 (first 2 valid reps confirm resume) -> summary.

## Clinical settings
All thresholds are in `prototype/config.js` (PT-configurable). Reference ROM (Norkin & White): hip flexion 100 deg AMA / 120 deg AAOS (p.200); knee flexion 150 deg AMA (p.244).

Open items for the PT: hip flexion p.200 is general hip flexion, not the straight-leg-raise test (p.218); knee flexion reference is measured supine, the exercise is prone; target/start/rest angles are carried over from the previous branch and are not PT-validated.
