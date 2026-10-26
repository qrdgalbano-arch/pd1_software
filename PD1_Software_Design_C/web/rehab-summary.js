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

function line(text) {
  const p = document.createElement("p");
  p.textContent = text;
  panel.append(p);
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

  if (error) line(`Recording error: ${error}`);
  if (!summary) return;

  const text = typeof summary.report_text === "string" ? summary.report_text : "";
  if (!text) {
    line("Extension summary is not available for this session.");
    return;
  }

  const lines = text.split("\n");
  const title = document.createElement("h2");
  title.textContent = lines[0];
  panel.append(title);
  for (const entry of lines.slice(1)) line(entry);

  if (summary.telemetry_write_failed) {
    line("Warning: some telemetry could not be written.");
  }
}
