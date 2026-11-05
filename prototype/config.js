// PT-configurable clinical settings. Edit here only; patients never enter these values.
// wnl_min_deg: reference "within normal limits" ROM from Norkin & White, Measurement of Joint Motion
//   hip flexion  p.200: 120 deg (AAOS) / 100 deg (AMA)   -> AMA value used (conservative)
//   knee flexion p.244: 150 deg (AMA)
// NOTE: p.200 is general hip flexion, not the dedicated straight-leg-raise test (p.218). PT to confirm.
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
      wnl_min_deg: 100, wnl_source: "AMA hip flexion 100 deg (AAOS 120 deg), Norkin & White p.200"
    },
    {
      id: "plf", name: "Prone Leg Flexion", joint: "Knee", motion: "knee flexion",
      prescription: "2 Sets x 8 Reps", frequency: "Daily", posture: "prone",
      camera: "Camera at the side of the mat, 2-3 m away, so your whole body (head to feet) is in view.",
      instructions: ["Lie on your stomach with legs straight.", "Keep your thigh on the mat.", "Bend the knee to bring the heel toward you, then lower slowly."],
      rest_max_deg: 16, rep_start_deg: 30, target_deg: 65, max_speed_dps: 180,
      thigh_max_deg: 15, ghost_deg: 70,
      wnl_min_deg: 150, wnl_source: "AMA knee flexion 150 deg, Norkin & White p.244"
    }
  ]
};
