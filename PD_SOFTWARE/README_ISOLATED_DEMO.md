# Isolated rehabilitation demo

Synthetic presets only. No clinical approval, patient database, or backend sync.
Run uvicorn station.rehab_demo:app on 127.0.0.1:18080.
Original run_station.ps1 and clinical configuration are unchanged.

Config: config/demo_profile.json
Summaries: data/isolated_demo/*.summary.json
Pose logs: debug_pose_logs/isolated_demo/*.txt

Hip zero: first tracked torso-relative thigh direction. This is not validated anatomical calibration.
A/B/C reuse the existing avatar renderer. Redness colors joint markers, not whole mesh regions.
SLR expected AROM is synthetic; population references are not exercise targets.
Real camera/goniometer validation and clinical approval remain unperformed.
