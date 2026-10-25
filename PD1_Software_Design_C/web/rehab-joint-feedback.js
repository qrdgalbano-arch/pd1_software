
import * as THREE from "three";

let latest = {};
let received = 0;

export function setRehabJointFeedback(state) {
  latest = state?.rehab_joint_feedback?.joints || {};
  received = performance.now();

  let text = document.getElementById("rehab-redness-description");
  const host = document.getElementById("twin-viewport");
  if (!text && host) {
    text = document.createElement("p");
    text.id = "rehab-redness-description";
    text.className = "hint";
    text.textContent =
      "Joint-position deviation: color intensity indicates departure " +
      "from your prescribed exercise limits.";
    host.append(text);
  }
}

export function attachRehabJointColors(avatar) {
  if (avatar._rehabJointColors) return;
  if (typeof avatar.frameCamera !== "function") {
    console.warn("Shared joint coloring unavailable: frameCamera not found");
    return;
  }
  const original = avatar.frameCamera.bind(avatar);
  const neutral = new THREE.Color(0x8a96a3);
  const red = new THREE.Color(0xef4444);

  avatar.frameCamera = function(...args) {
    const result = original(...args);
    // Transport freshness guard, not a clinical threshold.
    const fresh = performance.now() - received < 2000;
    for (const side of ["left", "right"]) {
      for (const joint of ["hip", "knee", "ankle"]) {
        const marker = this.markers?.[side]?.[joint];
        if (!marker?.material?.color) continue;
        const reading = fresh && side === this.side ? latest[joint] : null;
        const intensity = reading?.tracked === true
          && reading?.evaluated === true
          && Number.isFinite(reading.intensity)
          ? Math.max(0, Math.min(1, reading.intensity)) : 0;
        marker.material.color.copy(neutral).lerp(red, intensity);
      }
    }
    return result;
  };
  avatar._rehabJointColors = true;
}
