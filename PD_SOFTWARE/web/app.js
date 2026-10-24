import { TwinAvatar } from "/static/avatar.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const calibrate = params.has("calibrate");
const avatar = new TwinAvatar($("avatar"));
let prescriptions = [];
let lastPromptSeq = -1;
let lastPhase = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `${response.status} ${response.statusText}`);
  return body;
}

function showPrompt(text, level = "info") {
  const el = $("prompt");
  el.textContent = text;
  el.className = `prompt ${level}`;
}

function speak(text) {
  if (!$("audio").checked || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

function option(value, label) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = label;
  return o;
}

async function loadPatients() {
  try {
    const { source, patients } = await api("/api/patients");
    const select = $("patient");
    select.replaceChildren(option("", "Select patient"), ...patients.map((p) => option(p.id, p.full_name)));
    if (source === "cache") showPrompt("Offline: using cached patient list.", "warning");
  } catch (err) {
    showPrompt(`Cannot load patients: ${err.message}`, "error");
  }
}

async function loadPrescriptions() {
  const patientId = $("patient").value;
  const select = $("prescription");
  select.replaceChildren();
  prescriptions = [];
  if (!patientId) return;
  try {
    const data = await api(`/api/patients/${patientId}/prescriptions`);
    prescriptions = data.prescriptions;
    if (!prescriptions.length) {
      select.append(option("", "No supported prescriptions"));
      return;
    }
    select.append(...prescriptions.map((p) => option(p.id,
      `${p.exercise.name} - ${p.repetitions_target} reps, ${Math.round(p.duration_limit_seconds / 60)} min`)));
    await updatePreview();
  } catch (err) {
    showPrompt(`Cannot load prescriptions: ${err.message}`, "error");
  }
}

async function updatePreview() {
  const p = prescriptions.find((x) => String(x.id) === $("prescription").value);
  if (!p) return;
  try {
    await api("/api/preview", { method: "POST", body: JSON.stringify({ exercise_key: p.exercise_key, side: $("side").value }) });
  } catch (_) { /* a session is running */ }
}

async function startSession() {
  try {
    await api("/api/session/start", {
      method: "POST",
      body: JSON.stringify({
        patient_id: Number($("patient").value),
        prescription_id: Number($("prescription").value),
        side: $("side").value,
      }),
    });
  } catch (err) {
    showPrompt(`Cannot start: ${err.message}`, "error");
  }
}

async function stopSession() {
  try { await api("/api/session/stop", { method: "POST" }); }
  catch (err) { showPrompt(err.message, "error"); }
}

function fmtTime(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function jointStatus(state) {
  const devs = new Set(state.evaluation?.active_deviations || []);
  const devJoint = { knee_bent: "knee", thigh_lifted: "hip" };
  const status = {};
  for (const [name, j] of Object.entries(state.joints)) {
    status[name] = !j.tracked ? "lost" : [...devs].some((d) => devJoint[d] === name) ? "deviation" : "ok";
  }
  return status;
}

function render(state) {
  $("fps").textContent = `${state.fps} FPS (pose ${state.pose_ms} ms)`;
  $("exercise-name").textContent = state.exercise.name;
  $("camera-view").textContent = state.camera_error ? `Camera: ${state.camera_error}` : state.exercise.camera_view;
  $("instructions").replaceChildren(...state.exercise.instructions.map((t) => {
    const li = document.createElement("li"); li.textContent = t; return li;
  }));

  const status = jointStatus(state);
  const rows = Object.entries(state.joints).map(([name, j]) => {
    const tr = document.createElement("tr");
    const cls = status[name] === "lost" ? "lost" : status[name] === "deviation" ? "dev" : "";
    const rom = j.rom_max === null ? "--" : `${j.rom_min} to ${j.rom_max}°`;
    for (const text of [name, j.tracked ? `${j.angle}°` : "not tracked", `${j.velocity_dps}°/s`, rom, `${j.hold_seconds}s`]) {
      const td = document.createElement("td"); td.textContent = text; td.className = cls; tr.append(td);
    }
    return tr;
  });
  $("joints").tBodies[0].replaceChildren(...rows);

  const ev = state.evaluation;
  const session = state.session;
  const summary = state.last_summary;
  const counts = ev || (summary && { valid: summary.valid_repetitions, invalid: summary.invalid_repetitions, incomplete: summary.incomplete_repetitions }) || { valid: 0, invalid: 0, incomplete: 0 };
  $("valid").textContent = counts.valid;
  $("invalid").textContent = counts.invalid;
  $("incomplete").textContent = counts.incomplete;
  const [lo, hi] = state.exercise.rom_standard_deg;
  if (session) {
    $("target").textContent = `Target: ${session.repetitions_target} valid reps · ROM standard ${lo}-${hi}°`;
    $("timer").textContent = `Time: ${fmtTime(session.elapsed_seconds)} / ${fmtTime(session.duration_limit_seconds)} (${state.phase})`;
  } else {
    $("target").textContent = `ROM standard ${lo}-${hi}°`;
    $("timer").textContent = summary ? `Last session: ${summary.status}, ${fmtTime(summary.duration_seconds)}` : "Time: --";
  }
  if (ev) {
    const live = ev.live_peak_deg !== null ? ` · current rep ${ev.live_peak_deg}° (${ev.live_arom})` : "";
    const sessionArom = ev.session_peak_deg !== null ? `${ev.session_arom} (median peak ${ev.session_peak_deg}°)` : "--";
    $("arom").textContent = `AROM: ${sessionArom}${live}`;
    if (ev.prompt && ev.prompt.seq !== lastPromptSeq) {
      lastPromptSeq = ev.prompt.seq;
      showPrompt(ev.prompt.text, ev.prompt.level);
      speak(ev.prompt.text);
    }
  } else if (summary) {
    $("arom").textContent = `AROM: ${summary.arom_classification || "--"}${summary.peak_rom_degrees !== null ? ` (median peak ${summary.peak_rom_degrees}°)` : ""}`;
  }

  const running = Boolean(session);
  $("start").disabled = running || !$("prescription").value;
  $("stop").disabled = !running;
  for (const id of ["patient", "prescription", "side"]) $(id).disabled = running;
  if (lastPhase !== state.phase) {
    if (state.phase === "finished" && summary) {
      showPrompt(`Session saved: ${summary.status}. ${summary.valid_repetitions} valid repetitions.`, "success");
      speak("Session saved.");
      lastPromptSeq = -1;
    }
    lastPhase = state.phase;
    loadSessions();
  }

  if (!calibrate) {
    const angles = Object.fromEntries(Object.entries(state.joints).map(([k, j]) => [k, j.tracked ? j.angle : undefined]));
    avatar.update(angles, status, state.exercise, state.side);
  } else {
    avatar.update({ hip: +$("cal-hip").value, knee: +$("cal-knee").value, ankle: +$("cal-ankle").value },
      { hip: "ok", knee: "ok", ankle: "ok" }, state.exercise, state.side);
  }
}

function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/state`);
  ws.onmessage = (event) => render(JSON.parse(event.data));
  ws.onclose = () => setTimeout(connect, 1000);
}

async function loadSessions() {
  try {
    const rows = await api("/api/sessions?limit=15");
    $("sessions").tBodies[0].replaceChildren(...rows.map((r) => {
      const tr = document.createElement("tr");
      for (const text of [
        new Date(r.device_recorded_at).toLocaleString(), r.exercise_name, r.status,
        `${r.valid_repetitions} / ${r.invalid_repetitions} / ${r.incomplete_repetitions}`,
        `${r.arom_classification || "--"}${r.peak_rom_degrees !== null ? ` (${r.peak_rom_degrees}°)` : ""}`,
        fmtTime(r.duration_seconds), r.sync_status,
      ]) { const td = document.createElement("td"); td.textContent = text; tr.append(td); }
      return tr;
    }));
  } catch (_) { /* ignore */ }
}

async function pollStatus() {
  try {
    const s = await api("/api/status");
    $("backend").textContent = `Backend: ${s.backend_online ? "online" : "offline"}`;
    $("sync").textContent = `Sync: ${s.sync.pending || 0} pending, ${s.sync.synced || 0} synced, ${s.sync.failed || 0} failed`;
  } catch (_) { $("backend").textContent = "Backend: --"; }
}

$("patient").addEventListener("change", loadPrescriptions);
$("prescription").addEventListener("change", updatePreview);
$("side").addEventListener("change", updatePreview);
$("start").addEventListener("click", startSession);
$("stop").addEventListener("click", stopSession);
$("sync-now").addEventListener("click", async () => { await api("/api/sync", { method: "POST" }); setTimeout(() => { pollStatus(); loadSessions(); }, 1500); });
$("calibration").hidden = !calibrate;

const info = await avatar.load();
$("tris").textContent = `Avatar: ${info.source}, ${info.triangles} triangles`;
await loadPatients();
loadSessions();
pollStatus();
setInterval(pollStatus, 5000);
setInterval(loadSessions, 15000);
connect();
