# Rehabilitation extension: implementation status

Research/demo only. Clinical deployment is not approved.

Decision authority remains with the patient and the physical therapist. This tool does not diagnose.

## Installed building blocks
- Shared AROM classification and joint-redness functions.
- Neutral-zero XYZ geometric angle functions.
- Parallel live measurement preview; legacy evaluation unchanged.
- Separate local storage and history utilities.
- Offline paired goniometer-validation utility.
- PT configuration templates, demo guard, About screen.

## PT_SET
Unspecified targets, tolerances, redness scales, repetition thresholds/timing, SLR expected AROM, patient overrides, tracking visibility and filter parameters require PT input and approval. Do not replace nulls with guessed values.

## References
- Norkin & White, Measurement of Joint Motion: A Guide to Goniometry; edition/table verification pending.
- AAOS Total Knee Replacement Exercise Guide: positioning and instructions only, not universal clinical thresholds or an OA protocol for patients without replacement.
- Royal Devon SLR protocol: exact document verification pending.
- Sirona prone-knee protocol: exact document verification pending.
- Patient-specific PT-approved project protocol: pending.

## Not yet integrated
- Calibrated hip anatomical frame and real-world measurement validation.
- PT approval verification and shared live exercise evaluator.
- Automatic new-session, repetition, and telemetry recording.
- Shared proportional avatar redness in Designs A/B/C.
- Final post-exercise summary and historical trend UI.
- End-to-end camera/browser regression testing.

## Tests and startup
Run the extension unittest suites before further integration.
PowerShell startup:
```powershell
$env:STATION_PORT = "18080"
powershell -NoProfile -File ".\run_station.ps1"
```

Passing unit tests does not establish clinical accuracy or complete the live-system requirements.


## History/recovery integration update

- Directional ankle averages, prior comparisons, and recorded-data trends added.
- Supporting-joint percentages and coverage are displayed when assessed.
- Running extension sessions at engine startup become interrupted.
- Existing repetition and telemetry rows are preserved.
- Interrupted sessions are excluded from prior-session benchmarks.
- Recovery tests use artificial fixtures, not patient validation measurements.

### Still not complete
- Calibrated hip anatomical frame.
- Authenticated/version-bound PT approval and approved runtime execution.
- Full replacement of legacy evaluation and session-ending decisions.
- Validated monitoring and target/hold/timing rules.
- Full camera/browser regression and real goniometer validation.
- Exact reference-edition/leaflet verification.

Clinical deployment is not approved.
