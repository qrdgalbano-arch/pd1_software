
// Parallel measurements only; never changes exercise evaluation.
let panel, status, reason, body;

function ensurePanel() {
  if (panel) return true;
  const live = document.getElementById("screen-live");
  if (!live) return false;

  panel = document.createElement("details");
  panel.id = "rehab-measurement-preview";
  panel.className = "joint-details";
  panel.open = true;

  const heading = document.createElement("summary");
  heading.textContent = "Extension measurements — unapproved preview";
  panel.append(heading);

  const note = document.createElement("p");
  note.className = "hint";
  note.textContent =
    "Separate research stream. These values do not drive the current " +
    "rep counter, clinical labels, or avatar redness.";
  panel.append(note);

  status = document.createElement("p");
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  panel.append(status);

  reason = document.createElement("p");
  reason.className = "hint";
  panel.append(reason);

  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const table = document.createElement("table");
  const caption = document.createElement("caption");
  caption.textContent = "Neutral-zero world-XYZ estimates";
  table.append(caption);

  const head = document.createElement("thead");
  const row = document.createElement("tr");
  for (const label of ["Joint", "Raw angle", "Filtered angle", "State"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    row.append(th);
  }
  head.append(row);
  table.append(head);
  body = document.createElement("tbody");
  table.append(body);
  wrap.append(table);
  panel.append(wrap);

  const anchor = live.querySelector(".joint-details");
  if (anchor) anchor.insertAdjacentElement("afterend", panel);
  else live.append(panel);
  return true;
}

function degrees(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)}°` : "—";
}

export function renderRehabPreview(state) {
  if (!state || !ensurePanel()) return;
  const data = state.rehab_measurements;
  const disconnected = data == null;
  const paused = state.phase === "paused";
  const uncertain = state.camera_error || state.pose_detected === false;

  const label = disconnected ? "Waiting for extension stream"
    : paused ? "Paused — readings held"
    : uncertain ? "Tracking uncertain"
    : data.state || "Waiting for measurements";

  const text = `Extension status: ${label}`;
  if (status.textContent !== text) status.textContent = text;
  reason.textContent = disconnected
    ? "Restart the station after installing the live measurement extension."
    : data.reason || (
      "Hip requires body-frame calibration. Camera-inferred depth is " +
      "not a validated goniometer measurement."
    );

  const rows = [];
  for (const joint of ["hip", "knee", "ankle"]) {
    const reading = data?.joints?.[joint];
    const valid = !paused && !uncertain && reading?.tracked === true;
    const tr = document.createElement("tr");
    const cells = [
      joint[0].toUpperCase() + joint.slice(1),
      valid ? degrees(reading.raw_angle) : "—",
      valid ? degrees(reading.angle) : "—",
      paused ? "Paused"
        : uncertain ? "Tracking uncertain"
        : reading?.state || label,
    ];
    for (const value of cells) {
      const cell = document.createElement("td");
      cell.textContent = value;
      tr.append(cell);
    }
    rows.push(tr);
  }
  body.replaceChildren(...rows);
}
