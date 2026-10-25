
let panel;
let lastSignature;

function ensurePanel() {
  if (panel) return;
  const host = document.getElementById("screen-summary");
  if (!host) return;
  panel = document.createElement("section");
  panel.id = "rehab-session-summary";
  panel.style.marginBlock = "24px";
  host.append(panel);
}

function line(label, value) {
  const p = document.createElement("p");
  p.textContent = `${label}: ${value}`;
  panel.append(p);
}

function degrees(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)}°` : "Unavailable";
}

export function renderRehabSession(state) {
  if (!state) return;
  ensurePanel();
  if (!panel) return;
  const summary = state.rehab_session_summary;
  const error = state.rehab_recording_error;
  const signature = JSON.stringify([summary?.session_id, error]);
  if (signature === lastSignature) return;
  lastSignature = signature;
  panel.replaceChildren();

  const title = document.createElement("h2");
  title.textContent = "Extension summary — unapproved preview";
  panel.append(title);

  if (error) line("Recording error", error);
  if (!summary) {
    line("Status", "No extension summary available for this exercise yet");
    return;
  }

  line("Exercise", summary.exercise_id);
  line("Extension repetitions completed", summary.reps_completed);
  line("Incomplete repetition at stop", summary.unfinished_rep ? "Yes" : "No");
  line("Peak AROM", degrees(summary.max_peak));
  line("Reference", degrees(summary.assessment?.reference_deg));
  line("Layer A", summary.assessment?.label || "Assessment unavailable");
  if (summary.assessment?.tag) line("Assessment status", summary.assessment.tag);
  if (summary.assessment?.note) line("Assessment note", summary.assessment.note);
  line("Approval", "Not approved — research preview only");

  for (const [name, result] of Object.entries(summary.directional_arom || {})) {
    line(`${name} peak`, degrees(result.peak_deg));
    line(`${name} reference`, degrees(result.assessment.reference_deg));
    line(`${name} Layer A`, result.assessment.label);
    if (result.assessment.tag) line(`${name} status`, result.assessment.tag);
    line(`${name} average`, degrees(result.avg_peak_arom));
    line(`${name} previous average`, degrees(result.previous_avg_peak_arom));
    line(`${name} previous best`, degrees(result.previous_max_peak));
    const change = result.difference_deg;
    line(`${name} change`, typeof change === "number"
      ? `${change >= 0 ? "+" : ""}${change.toFixed(1)}°`
      : result.history_status);
    if (summary.trend_status === "Configured") {
      const directionalPoints = (result.trend || []).map(p => ({
        label: p.timestamp, value: p.avg_peak_arom
      }));
      directionalPoints.push({
        label: "Current session", value: result.avg_peak_arom
      });
      drawRehabTrend(`${name} session-average trend`, directionalPoints);
    }

  }

  line(
    "Layer B",
    `${summary.target_reached_count} reached; ` +
    `${summary.target_not_reached_count} not reached; ` +
    `${summary.target_unassessed_count} unassessed`
  );

  for (const [joint, result] of Object.entries(
    summary.supporting_joint_monitoring || {}
  )) {
    line(`Layer C — ${joint}`, result.state);
    line(`${joint} within prescribed limits`, percentage(result.within_percent));
    line(`${joint} tracking coverage`, percentage(result.tracking_coverage_percent));
    line(`${joint} assessment coverage`, percentage(result.assessment_coverage_percent));
    if (result.timing_note) line(`${joint} timing`, result.timing_note);

  }

  line("Average rep peak", degrees(summary.avg_peak_arom));
  line("Best rep", degrees(summary.max_peak));
  line("Previous-session average", degrees(summary.previous_avg_peak_arom));
  line("Previous-session best", degrees(summary.previous_max_peak));
  const delta = summary.difference_deg;
  line("Change vs previous session",
    typeof delta === "number" ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}°`
      : summary.history_status);
  line("History", summary.trend_status);
  line("Recording note", summary.evaluation_note);

  if (summary.telemetry_write_failed) {
    line("Warning", "Some telemetry could not be written");
  }

  const points = (summary.trend || []).map(item => ({
    label: item.timestamp,
    value: item.summary?.avg_peak_arom,
  }));
  if (typeof summary.avg_peak_arom === "number") {
    points.push({label: "Current session", value: summary.avg_peak_arom});
  }
  const valid = points.filter(p =>
    typeof p.value === "number" && Number.isFinite(p.value)
  );

  // Show only recorded data; never generate example values.
  if (summary.trend_status === "Configured" && valid.length > 1) {
    const chart = document.createElement("canvas");
    chart.width = 640;
    chart.height = 220;
    chart.style.width = "100%";
    chart.style.maxWidth = "640px";
    chart.style.background = "#fff";
    chart.setAttribute("role", "img");
    chart.setAttribute("aria-label", "Recorded session average peak AROM trend");
    panel.append(chart);

    const ctx = chart.getContext("2d");
    if (ctx) {
      const lo = Math.min(...valid.map(p => p.value));
      const hi = Math.max(...valid.map(p => p.value));
      const span = hi - lo || 1;
      ctx.strokeStyle = "#066e69";
      ctx.lineWidth = 3;
      ctx.beginPath();
      valid.forEach((p, i) => {
        const x = 40 + i * 560 / (valid.length - 1);
        const y = 180 - (p.value - lo) / span * 140;
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
      ctx.stroke();
    }

    const list = document.createElement("ul");
    valid.forEach(p => {
      const li = document.createElement("li");
      li.textContent = `${p.label}: ${degrees(p.value)}`;
      list.append(li);
    });
    panel.append(list);
  }

  line(
    "Decision authority",
    "Remains with the patient and the physical therapist. This tool does not diagnose."
  );
}


function drawRehabTrend(label, points) {
  const valid = points.filter(p =>
    typeof p.value === "number" && Number.isFinite(p.value)
  );
  if (!valid.length) return;
  const heading = document.createElement("h3");
  heading.textContent = label;
  panel.append(heading);

  if (valid.length > 1) {
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 220;
    canvas.style.width = "100%";
    canvas.style.maxWidth = "640px";
    canvas.style.background = "#fff";
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", label);
    panel.append(canvas);
    const context = canvas.getContext("2d");
    if (context) {
      const low = Math.min(...valid.map(p => p.value));
      const high = Math.max(...valid.map(p => p.value));
      const span = high - low || 1;
      context.strokeStyle = "#066e69";
      context.lineWidth = 3;
      context.beginPath();
      valid.forEach((p, i) => {
        const x = 40 + i * 560 / (valid.length - 1);
        const y = 180 - (p.value - low) * 140 / span;
        if (i) context.lineTo(x, y); else context.moveTo(x, y);
      });
      context.stroke();
    }
  }
  const list = document.createElement("ul");
  for (const point of valid) {
    const item = document.createElement("li");
    item.textContent = `${point.label}: ${degrees(point.value)}`;
    list.append(item);
  }
  panel.append(list);
}

function percentage(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(1)}%` : "Not assessed";
}
