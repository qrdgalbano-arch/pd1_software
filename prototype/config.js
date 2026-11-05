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
      knee_max_deg: 15,
      wnl_min_deg: 55, display_offset_deg: 15, wnl_source: "Healthy-adult mean 70 deg, range 30-90 deg (PMC2505147); provisional, PT to confirm"
    },
    {
      id: "plf", name: "Prone Leg Flexion", joint: "Knee", motion: "knee flexion",
      prescription: "2 Sets x 8 Reps", frequency: "Daily", posture: "prone",
      camera: "Camera at the side of the mat, 2-3 m away, so your whole body (head to feet) is in view.",
      instructions: ["Lie on your stomach with legs straight.", "Keep your thigh on the mat.", "Bend the knee to bring the heel toward you, then lower slowly."],
      rest_max_deg: 16, rep_start_deg: 30, target_deg: 65, max_speed_dps: 180,
      thigh_max_deg: 15,
      wnl_min_deg: 110, display_offset_deg: 25, wnl_source: "AAOS normal knee flexion 135 deg; CDC male 20-44 mean 137.7 deg; provisional, PT to confirm"
    }
  ]
};
