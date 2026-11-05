// PT-configurable clinical settings. Edit here only; patients never enter these values.
//
// wnl_min_deg = "within normal limits" cutoff used ONLY for the summary classification.
// It is separate from the exercise target (target_deg / ghost_deg), which is the rehab goal per rep.
//
// Sources (all PROVISIONAL until the PT confirms):
//  Straight Leg Raise, hip flexion with knee straight: 70 deg
//    Mean of 200 healthy people (range 30-90 deg), PMC2505147 (Measurement of Hip Range of Flexion-Extension and Straight-leg Raising).
//    NOT the general hip-flexion value (Norkin & White p.200: AMA 100 / AAOS 120 deg), which is for a knee-flexed test.
//    Source is passive SLR; the prototype measures ACTIVE SLR, so expect lower values.
//  Prone Leg Flexion, knee flexion: 135 deg
//    AAOS normal knee flexion 135 deg; ExRx.net Ely's test (prone) 135 deg; CDC Normal Joint ROM Study male 20-44 mean 137.7 deg.
//    Norkin & White p.244 AMA 150 deg is a supine value and is higher than the CDC means.
//    No prone-specific norm found; PT to confirm.
//  Straight knee: target 0 deg (Norkin p.246); >5 deg beyond zero is hyperextension.
//    knee_max_deg / thigh_max_deg tolerances are NOT from a standard: set from measurement error and PT approval.
export const CONFIG = {
  patient: { name: "Aries Rio", sex: "Male", age: 21 },
  sets: 2,
  repsPerSet: 8,
  legs: ["left", "right"],
  restSeconds: 180,
  restExtendSeconds: 60,
  resumeValidReps: 2,
  minVisibility: 0.5,
  holdReadySeconds: 1.0,
  deviationConfirmSeconds: 0.4,
  exercises: [
    {
      id: "slr", name: "Straight Leg Raise", joint: "Hip", motion: "hip flexion",
      prescription: "2 Sets x 8 Reps", frequency: "Daily", posture: "supine",
      camera: "Camera at the side of the mat, 2-3 m away, so your whole body (head to feet) is in view.",
      instructions: ["Lie on your back; bend the other knee.", "Keep the exercising knee straight.", "Lift the leg slowly, then lower it to the mat."],
      rest_max_deg: 12, rep_start_deg: 25, target_deg: 40, max_speed_dps: 220,
      knee_max_deg: 15, ghost_deg: 45,
      wnl_min_deg: 70, wnl_source: "Healthy-adult mean 70 deg, range 30-90 deg (PMC2505147); provisional, PT to confirm"
    },
    {
      id: "plf", name: "Prone Leg Flexion", joint: "Knee", motion: "knee flexion",
      prescription: "2 Sets x 8 Reps", frequency: "Daily", posture: "prone",
      camera: "Camera at the side of the mat, 2-3 m away, so your whole body (head to feet) is in view.",
      instructions: ["Lie on your stomach with legs straight.", "Keep your thigh on the mat.", "Bend the knee to bring the heel toward you, then lower slowly."],
      rest_max_deg: 16, rep_start_deg: 30, target_deg: 65, max_speed_dps: 180,
      thigh_max_deg: 15, ghost_deg: 70,
      wnl_min_deg: 135, wnl_source: "AAOS normal knee flexion 135 deg; CDC male 20-44 mean 137.7 deg; provisional, PT to confirm"
    }
  ]
};
