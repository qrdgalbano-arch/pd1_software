
export function renderAnkleReference(state) {
  if (!["ankle_pump", "ankle_pumps"].includes(state?.exercise_key)) return;
  const label = document.getElementById("live-arom");
  if (label) {
    label.textContent =
      "Population references: dorsiflexion +20°; plantarflexion −50°; " +
      "neutral 0°. Not prescribed targets.";
  }
}
