/* PD1 v4 frontend: existing HTTP/WebSocket contract; no demo patients or metrics. */
const $ = (id) => document.getElementById(id);
const config = new URLSearchParams(location.search);
const calibrate = config.has("calibrate");
let avatar = null;
let avatarLoading = false;
let patients = [];
let prescriptions = [];
let sessions = [];
let latest = null;
let lastSummary = null;
let screen = "start";
let historyOrigin = "start";
let selectedJoint = "knee";
let activeSessionId = null;
let lastPromptKey = "";
let socket = null;
let connected = false;
let cameraStreamFailed = false;
let requestBusy = false;
let patientGeneration = 0;
let historyLoading = false;
let statusLoading = false;
let historyLoaded = false;
let pollTimer;
const screenTitles = {
  start: "start-title",
  live: "live-title",
  summary: "summary-title",
  sessions: "sessions-title",
};
const side = () => document.querySelector('input[name="side"]:checked').value;
const selectedPrescription = () =>
  prescriptions.find((p) => String(p.id) === $("prescription").value);
const fmtTime = (seconds) => {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};
const degrees = (value) =>
  typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value)}°`
    : "—";
const titleCase = (value) =>
  String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
const count = (value) => Math.max(0, Number(value) || 0);

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
      signal: controller.signal,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail =
        typeof body.detail === "string"
          ? body.detail
          : `${response.status} ${response.statusText}`;
      throw new Error(detail);
    }
    return body;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        "The station took too long to respond. Check the station window and try again.",
      );
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
function notice(message = "", level = "info") {
  const el = $("notice");
  el.textContent = message;
  el.className = `notice ${level}`;
  el.hidden = !message;
}
function speak(text) {
  if (!$("audio").checked || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
}
function coaching(text, level = "info") {
  const style = ["info", "success", "warning", "error"].includes(level)
    ? level
    : "info";
  $("prompt").className = `coaching ${style}`;
  $("prompt-symbol").textContent = {
    success: "✓",
    warning: "!",
    error: "!",
    info: "●",
  }[style];
  if ($("prompt-text").textContent !== text)
    $("prompt-text").textContent = text;
}
function option(value, label) {
  const el = document.createElement("option");
  el.value = value;
  el.textContent = label;
  return el;
}
function switchScreen(next, focus = true) {
  if (!(next in screenTitles)) next = "start";
  if (latest?.session) next = "live";
  if (next === "live" && !latest?.session && !calibrate)
    next = lastSummary ? "summary" : "start";
  if (next === "summary" && !lastSummary) next = "start";
  if (next === "sessions" && screen !== "sessions")
    historyOrigin = screen === "summary" ? "summary" : "start";
  screen = next;
  for (const name of Object.keys(screenTitles))
    $("screen-" + name).hidden = name !== next;
  document.body.dataset.screen = next;
  if (location.hash !== `#${next}`) history.replaceState(null, "", `#${next}`);
  if (next === "live") {
    attachCamera();
    initAvatar();
  } else {
    $("camera").removeAttribute("src");
  }
  if (next === "summary") renderSummary();
  if (next === "sessions") loadSessions();
  if (focus) {
    $(screenTitles[next]).focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
}
function attachCamera() {
  cameraStreamFailed = false;
  if (!$("camera").getAttribute("src"))
    $("camera").src = `/video.mjpg?view=${Date.now()}`;
}
async function initAvatar() {
  if (avatar || avatarLoading) {
    avatar?.resize();
    return;
  }
  avatarLoading = true;
  try {
    const { TwinAvatar } = await import("/static/avatar.js");
    avatar = new TwinAvatar($("avatar"));
    const info = await avatar.load();
    $("tris").textContent =
      `Avatar: ${info.source}, ${info.triangles.toLocaleString()} triangles`;
    $("avatar-error").hidden = true;
    avatar.resize();
    avatar.setTheme(dark);
  } catch (error) {
    $("avatar-error").hidden = false;
    $("tris").textContent =
      "Avatar unavailable; numeric joint readings remain active";
    console.warn("PD1 avatar:", error);
  } finally {
    avatarLoading = false;
  }
}
function updateControls() {
  const running = Boolean(latest?.session);
  $("start").disabled =
    running || requestBusy || !connected || !selectedPrescription();
  $("patient").disabled = running || requestBusy;
  $("prescription").disabled = running || requestBusy || !prescriptions.length;
  for (const input of document.querySelectorAll('input[name="side"]'))
    input.disabled = running || requestBusy;
  $("pause").disabled = !running || requestBusy || !connected;
  $("stop").disabled = !running || requestBusy || !connected;
  $("start-again").disabled = requestBusy || !connected || running;
}
async function loadPatients() {
  $("patient").replaceChildren(option("", "Loading patients…"));
  $("start").disabled = true;
  try {
    const data = await api("/api/patients");
    patients = data.patients || [];
    $("patient").replaceChildren(
      option(
        "",
        patients.length ? "Select a patient" : "No patients available",
      ),
      ...patients.map((p) => option(p.id, p.full_name)),
    );
    $("history-patient").replaceChildren(
      option("all", "All local patients"),
      ...patients.map((p) => option(p.id, p.full_name)),
    );
    if (data.source === "cache")
      notice(
        "Backend unavailable. Using the station’s cached patients and prescriptions.",
        "warning",
      );
    else if (!patients.length)
      notice(
        "No patients are available. Ask staff to add a patient in the backend.",
        "warning",
      );
    else notice();
  } catch (error) {
    $("patient").replaceChildren(option("", "Patients unavailable"));
    notice(`Cannot load patients: ${error.message}`, "error");
  }
  updateControls();
}
async function loadPrescriptions() {
  const generation = ++patientGeneration;
  const patientId = $("patient").value;
  prescriptions = [];
  $("prescription").replaceChildren(
    option("", patientId ? "Loading prescriptions…" : "Choose a patient first"),
  );
  updateControls();
  updateSetup();
  if (!patientId) return;
  try {
    const data = await api(
      `/api/patients/${encodeURIComponent(patientId)}/prescriptions`,
    );
    if (generation !== patientGeneration) return;
    prescriptions = data.prescriptions || [];
    $("prescription").replaceChildren(
      ...(prescriptions.length
        ? prescriptions.map((p) =>
            option(p.id, p.exercise?.name || titleCase(p.exercise_key)),
          )
        : [option("", "No supported prescriptions")]),
    );
    if (!prescriptions.length)
      notice(
        "This patient has no supported prescription. Ask staff to create or update their exercise prescription.",
        "warning",
      );
    else if (data.source === "cache")
      notice(
        "Using cached prescriptions while the backend is unavailable.",
        "warning",
      );
    else notice();
    updateSetup();
    await updatePreview();
  } catch (error) {
    if (generation !== patientGeneration) return;
    $("prescription").replaceChildren(option("", "Prescriptions unavailable"));
    notice(`Cannot load prescriptions: ${error.message}`, "error");
  }
  updateControls();
}
function updateSetup() {
  const p = selectedPrescription();
  $("setup-reps").textContent = p ? p.repetitions_target : "—";
  $("setup-time").textContent = p ? fmtTime(p.duration_limit_seconds) : "—";
  $("preview-name").textContent =
    p?.exercise?.name || "Choose a prescribed exercise";
}
async function updatePreview() {
  if (latest?.session) return;
  const p = selectedPrescription();
  if (!p) return;
  try {
    await api("/api/preview", {
      method: "POST",
      body: JSON.stringify({ exercise_key: p.exercise_key, side: side() }),
    });
  } catch (error) {
    notice(`Cannot update the exercise preview: ${error.message}`, "warning");
  }
}
async function startSession() {
  if (!selectedPrescription() || requestBusy || !connected) return;
  requestBusy = true;
  updateControls();
  notice();
  try {
    const result = await api("/api/session/start", {
      method: "POST",
      body: JSON.stringify({
        patient_id: Number($("patient").value),
        prescription_id: Number($("prescription").value),
        side: side(),
      }),
    });
    activeSessionId = result.client_session_id;
    lastPromptKey = "";
    coaching("Hold still in the starting position.");
    notice("Session started. Waiting for live station state…");
  } catch (error) {
    notice(`Cannot start: ${error.message}`, "error");
  } finally {
    requestBusy = false;
    updateControls();
  }
}
async function stopSession() {
  if (requestBusy) return;
  requestBusy = true;
  updateControls();
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  try {
    const summary = await api("/api/session/stop", { method: "POST" });
    lastSummary = summary;
    activeSessionId = null;
    latest = {
      ...latest,
      phase: "finished",
      session: null,
      last_summary: summary,
      evaluation: null,
    };
    notice();
    switchScreen("summary");
    await loadSessions();
  } catch (error) {
    notice(
      `Cannot stop: ${error.message}. If the station is unresponsive, stop moving and ask staff for help.`,
      "error",
    );
  } finally {
    requestBusy = false;
    updateControls();
  }
}
async function togglePause() {
  if (!latest?.session || requestBusy) return;
  const resume = latest.phase === "paused";
  requestBusy = true;
  updateControls();
  try {
    const result = await api(`/api/session/${resume ? "resume" : "pause"}`, {
      method: "POST",
    });
    latest = { ...latest, phase: result.phase };
    render(latest);
    if (!resume) {
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      speak("Session paused. Rest, then select resume when ready.");
    } else speak("Session resumed.");
  } catch (error) {
    notice(`Cannot ${resume ? "resume" : "pause"}: ${error.message}`, "error");
  } finally {
    requestBusy = false;
    updateControls();
  }
}
function jointStatus(state) {
  const deviations = new Set(state.evaluation?.active_deviations || []);
  const map = {
    knee_bent: "knee",
    thigh_lifted: "hip",
    wrong_leg_raised: "hip",
  };
  return Object.fromEntries(
    Object.entries(state.joints || {}).map(([name, joint]) => [
      name,
      !joint.tracked
        ? "lost"
        : [...deviations].some((d) => map[d] === name)
          ? "deviation"
          : "ok",
    ]),
  );
}
function renderJoints(state, statuses) {
  const joints = state.joints || {};
  const joint = joints[selectedJoint];
  $("component-angle").textContent = joint?.tracked
    ? degrees(joint.angle)
    : "—";
  $("component-state").textContent = !joint?.tracked
    ? `${titleCase(selectedJoint)} · not tracked`
    : `${titleCase(selectedJoint)} · ${statuses[selectedJoint] === "deviation" ? "check movement" : "tracked"}`;
  $("component-rom").textContent =
    `Measured ROM: ${joint?.rom_min != null && joint?.rom_max != null ? `${degrees(joint.rom_min)} – ${degrees(joint.rom_max)}` : "—"}`;
  $("joints").tBodies[0].replaceChildren(
    ...Object.entries(joints).map(([name, j]) => {
      const row = document.createElement("tr");
      for (const text of [
        titleCase(name),
        j.tracked ? degrees(j.angle) : "Not tracked",
        `${j.velocity_dps ?? "—"}°/s`,
        j.rom_max == null
          ? "—"
          : `${degrees(j.rom_min)} to ${degrees(j.rom_max)}`,
        `${j.hold_seconds ?? "—"}s`,
      ]) {
        const cell = document.createElement("td");
        cell.textContent = text;
        cell.className =
          statuses[name] === "deviation"
            ? "dev"
            : statuses[name] === "lost"
              ? "lost"
              : "";
        row.append(cell);
      }
      return row;
    }),
  );
  $("joint-chain").replaceChildren(
    ...["hip", "knee", "ankle"].map((name) => {
      const item = document.createElement("span");
      item.className = `chain-joint ${statuses[name] || "lost"}`;
      const label = document.createElement("span");
      label.textContent = titleCase(name);
      const value = document.createElement("b");
      value.textContent = joints[name]?.tracked
        ? degrees(joints[name].angle)
        : "Lost";
      item.append(label, value);
      return item;
    }),
  );
  const tracked = ["hip", "knee", "ankle"].filter(
    (name) => joints[name]?.tracked,
  ).length;
  $("asset-tracking").textContent =
    `${titleCase(state.side)} leg · ${tracked}/3 joints tracked`;
  $("system-status").textContent =
    tracked < 3
      ? `! Tracking: ${tracked} of 3 joints visible`
      : state.evaluation?.active_deviations?.length
        ? "! Check the coaching message"
        : "✓ Hip, knee, and ankle tracked";
  if (avatar && !calibrate)
    avatar.update(
      Object.fromEntries(
        Object.entries(joints).map(([name, j]) => [
          name,
          j.tracked ? j.angle : null,
        ]),
      ),
      statuses,
      state.exercise,
      state.side,
    );
}
function render(state) {
  if (!state?.exercise || !state.joints) return;
  latest = state;
  if (state.last_summary) lastSummary = state.last_summary;
  const session = state.session;
  const ev = state.evaluation;
  if (session && activeSessionId !== session.client_session_id) {
    activeSessionId = session.client_session_id;
    lastPromptKey = "";
  }
  if (session && screen !== "live") {
    notice();
    switchScreen("live");
  }
  if (
    !session &&
    activeSessionId &&
    lastSummary?.client_session_id === activeSessionId
  ) {
    activeSessionId = null;
    notice();
    switchScreen("summary");
    loadSessions();
    speak("Session finished. Your results have been saved on this station.");
  }
  $("fps").textContent = `${state.fps} FPS · pose ${state.pose_ms} ms`;
  if (!session) {
    $("preview-view").textContent = state.exercise.camera_view;
    $("instructions").replaceChildren(
      ...(state.exercise.instructions || []).map((text) => {
        const li = document.createElement("li");
        li.textContent = text;
        return li;
      }),
    );
  }
  if (session || screen === "live") {
    $("live-title").textContent =
      `${state.exercise.name} · ${titleCase(state.side)} leg`;
    $("live-patient").textContent =
      session?.patient?.full_name || "Avatar calibration preview";
    $("phase").textContent = titleCase(state.phase);
    $("camera-view").textContent = state.exercise.camera_view;
    $("camera-error").hidden = !state.camera_error && !cameraStreamFailed;
    $("camera-error").textContent = state.camera_error
      ? `Camera unavailable: ${state.camera_error}. Stop moving and ask staff to check the camera.`
      : cameraStreamFailed
        ? "Camera preview unavailable. Stop moving and ask staff to check the station camera."
        : "";
    const target = count(session?.repetitions_target);
    const valid = count(ev?.valid);
    $("reps-left").textContent = session ? Math.max(0, target - valid) : "—";
    $("rep-detail").textContent = session
      ? `${valid} of ${target} valid reps`
      : "Calibration preview";
    $("rep-progress").style.setProperty(
      "--progress",
      `${target ? Math.min(100, (valid / target) * 100) : 0}%`,
    );
    $("rep-progress").setAttribute("aria-valuemax", String(target || 1));
    $("rep-progress").setAttribute(
      "aria-valuenow",
      String(Math.min(valid, target || 1)),
    );
    $("rep-progress").setAttribute(
      "aria-valuetext",
      `${valid} valid repetitions completed; ${Math.max(0, target - valid)} remaining`,
    );
    $("timer").textContent = session
      ? fmtTime(session.duration_limit_seconds - session.elapsed_seconds)
      : "—:—";
    const paused = state.phase === "paused";
    $("pause-text").textContent = paused ? "Resume" : "Pause";
    $("pause-icon").textContent = paused ? "▶" : "Ⅱ";
    $("pause").setAttribute(
      "aria-label",
      paused ? "Resume exercise session" : "Pause exercise session",
    );
    if (paused)
      coaching("Session paused. Rest, then select Resume.", "warning");
    else if (state.camera_error || cameraStreamFailed)
      coaching(
        "Camera unavailable. Stop moving and ask staff for help.",
        "error",
      );
    else if (ev?.prompt) {
      const key = `${session?.client_session_id}:${ev.prompt.seq}`;
      coaching(ev.prompt.text, ev.prompt.level);
      if (lastPromptKey !== key) {
        lastPromptKey = key;
        speak(ev.prompt.text);
      }
    }
    const [lo, hi] = state.exercise.rom_standard_deg || [];
    $("live-arom").textContent =
      `Reference ROM: ${lo ?? "—"}–${hi ?? "—"}° · Session median peak: ${degrees(ev?.session_peak_deg)}`;
    renderJoints(state, jointStatus(state));
  }
  if (screen === "summary") renderSummary();
  updateControls();
}
function renderSummary() {
  const s = lastSummary;
  $("summary-empty").hidden = Boolean(s);
  if (!s) return;
  $("summary-exercise").textContent =
    `${s.exercise_name || titleCase(s.exercise_key)} · ${titleCase(s.affected_side)} leg`;
  $("summary-status").textContent =
    {
      completed: "✓ Prescribed repetition target reached.",
      incomplete: "Session ended before the repetition target was reached.",
      cancelled: "Session stopped before a repetition was recorded.",
    }[s.status] || titleCase(s.status);
  $("summary-valid").textContent = s.valid_repetitions;
  $("summary-invalid").textContent = s.invalid_repetitions;
  $("summary-incomplete").textContent = s.incomplete_repetitions;
  $("summary-rom").textContent = degrees(s.peak_rom_degrees);
  $("summary-duration").textContent = fmtTime(s.duration_seconds);
  $("summary-arom").textContent =
    s.arom_classification || "Not enough movement recorded";
  const stored = sessions.find(
    (row) => row.client_session_id === s.client_session_id,
  );
  $("summary-sync").textContent = syncLabel(
    stored?.sync_status || s.sync_status,
  );
}
function syncLabel(value) {
  return (
    { synced: "✓ Synced", pending: "↻ Pending", failed: "! Sync failed" }[
      value
    ] || titleCase(value || "pending")
  );
}
async function loadSessions() {
  if (historyLoading) return;
  historyLoading = true;
  $("history-status").textContent = historyLoaded
    ? "Refreshing local sessions…"
    : "Loading local sessions…";
  try {
    sessions = await api("/api/sessions");
    historyLoaded = true;
    renderSessions();
    $("history-status").textContent =
      `${sessions.length} local session${sessions.length === 1 ? "" : "s"} loaded. Latest 50 records from this station.`;
    if (screen === "summary") renderSummary();
  } catch (error) {
    $("history-status").textContent =
      `Cannot load sessions: ${error.message}. Select Refresh to try again.`;
  } finally {
    historyLoading = false;
  }
}
function renderSessions() {
  const patientFilter = $("history-patient").value;
  const filtered = sessions.filter(
    (s) => patientFilter === "all" || String(s.patient_id) === patientFilter,
  );
  $("history-empty").hidden = filtered.length > 0;
  $("sessions").parentElement.hidden = filtered.length === 0;
  $("sessions").tBodies[0].replaceChildren(
    ...filtered.map((s) => {
      const row = document.createElement("tr");
      const date = new Date(s.device_recorded_at);
      const dateText = Number.isNaN(date.getTime())
        ? "Date unavailable"
        : date.toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
          });
      const p = patients.find(
        (patient) => String(patient.id) === String(s.patient_id),
      );
      const fields = [
        ["Date", dateText],
        [
          "Exercise",
          `${s.exercise_name || titleCase(s.exercise_key)} · ${titleCase(s.affected_side)}`,
        ],
        ["Valid", String(s.valid_repetitions)],
        [
          "Status",
          `${s.status === "completed" ? "✓ " : s.status === "cancelled" ? "■ " : "◷ "}${titleCase(s.status)}`,
        ],
        ["Synced", syncLabel(s.sync_status)],
      ];
      for (const [index, [label, text]] of fields.entries()) {
        const cell = document.createElement("td");
        cell.dataset.label = label;
        const span = document.createElement("span");
        span.textContent = text;
        if (index === 3)
          span.className = `status-badge ${["completed", "cancelled", "incomplete"].includes(s.status) ? s.status : ""}`;
        cell.append(span);
        if (index === 1) {
          const small = document.createElement("small");
          small.textContent = p?.full_name || `Patient #${s.patient_id}`;
          cell.append(small);
        }
        if (index === 2) {
          const small = document.createElement("small");
          small.textContent = `${s.invalid_repetitions} invalid · ${s.incomplete_repetitions} incomplete`;
          cell.append(small);
        }
        if (index === 4 && s.sync_status === "failed" && s.sync_error) {
          const small = document.createElement("small");
          small.textContent = s.sync_error;
          cell.append(small);
        }
        row.append(cell);
      }
      return row;
    }),
  );
}
async function refreshStatus() {
  if (statusLoading) return;
  statusLoading = true;
  try {
    const data = await api("/api/status");
    $("backend").textContent =
      `Backend: ${data.backend_online ? "online" : "offline"}`;
    $("sync").textContent =
      `Sync: ${count(data.sync?.pending)} pending, ${count(data.sync?.failed)} failed, ${count(data.sync?.synced)} synced`;
  } catch (error) {
    $("backend").textContent = `Backend status unavailable: ${error.message}`;
  } finally {
    statusLoading = false;
  }
}
async function syncNow() {
  $("sync-now").disabled = true;
  try {
    await api("/api/sync", { method: "POST" });
    $("history-status").textContent =
      "Sync requested. Records update after the backend confirms receipt.";
  } catch (error) {
    $("history-status").textContent = `Sync request failed: ${error.message}`;
  } finally {
    $("sync-now").disabled = false;
    refreshStatus();
  }
}
function connect() {
  socket = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/state`,
  );
  socket.onopen = () => {
    const reconnected = !connected && Boolean(latest);
    connected = true;
    if (reconnected) {
      notice();
      attachCamera();
    }
    $("connection").textContent = "Station connected";
    $("connection").className = "connection online";
    updateControls();
  };
  socket.onmessage = (event) => {
    try {
      render(JSON.parse(event.data));
    } catch (error) {
      console.warn("PD1 state:", error);
    }
  };
  socket.onclose = () => {
    connected = false;
    $("connection").textContent = "Station disconnected";
    $("connection").className = "connection offline";
    if (latest?.session) {
      coaching(
        "Connection lost. Stop moving and ask staff to check the station.",
        "error",
      );
      notice(
        "Live state is disconnected. The station may still be recording. Do not continue until the connection returns.",
        "error",
      );
    }
    updateControls();
    setTimeout(connect, 2000);
  };
  socket.onerror = () => socket.close();
}
function voiceChanged() {
  const enabled = $("audio").checked;
  $("voice-text").textContent = enabled ? "Voice on" : "Voice off";
  $("voice").setAttribute("aria-pressed", String(enabled));
  if (!enabled && "speechSynthesis" in window) window.speechSynthesis.cancel();
}
$("camera").addEventListener("error", () => {
  if (screen !== "live") return;
  cameraStreamFailed = true;
  coaching(
    "Camera preview unavailable. Stop moving and ask staff for help.",
    "error",
  );
  $("camera-error").hidden = false;
  $("camera-error").textContent =
    "Camera preview is not available. Stop moving and ask staff to check the station camera.";
});
$("patient").addEventListener("change", loadPrescriptions);
$("prescription").addEventListener("change", () => {
  updateSetup();
  updateControls();
  updatePreview();
});
for (const input of document.querySelectorAll('input[name="side"]'))
  input.addEventListener("change", updatePreview);
$("start-form").addEventListener("submit", (event) => {
  event.preventDefault();
  startSession();
});
$("stop").addEventListener("click", stopSession);
$("pause").addEventListener("click", togglePause);
$("audio").addEventListener("change", voiceChanged);
$("voice").addEventListener("click", () => {
  $("audio").checked = !$("audio").checked;
  voiceChanged();
});
$("open-history").addEventListener("click", () => switchScreen("sessions"));
$("summary-history").addEventListener("click", () => switchScreen("sessions"));
$("history-back").addEventListener("click", () => switchScreen(historyOrigin));
$("summary-home").addEventListener("click", () => switchScreen("start"));
$("empty-start").addEventListener("click", () => switchScreen("start"));
$("start-again").addEventListener("click", () => {
  switchScreen("start");
  notice(
    "Check your patient, prescription, and affected side, then select Start exercise.",
  );
});
$("refresh-sessions").addEventListener("click", loadSessions);
$("sync-now").addEventListener("click", syncNow);
$("history-patient").addEventListener("change", renderSessions);
$("reload-patients").addEventListener("click", () => {
  prescriptions = [];
  $("prescription").replaceChildren(option("", "Choose a patient first"));
  updateSetup();
  loadPatients();
});
for (const button of document.querySelectorAll("[data-joint]"))
  button.addEventListener("click", () => {
    selectedJoint = button.dataset.joint;
    for (const tab of document.querySelectorAll("[data-joint]"))
      tab.setAttribute("aria-pressed", String(tab === button));
    if (latest?.joints) renderJoints(latest, jointStatus(latest));
  });
window.addEventListener("hashchange", () =>
  switchScreen(location.hash.slice(1)),
);
let dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
function setTheme() {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("theme-toggle").textContent = dark ? "Light mode" : "Dark mode";
  $("theme-toggle").setAttribute("aria-pressed", String(dark));
  avatar?.setTheme?.(dark);
}
$("theme-toggle").addEventListener("click", () => {
  dark = !dark;
  setTheme();
});
if (calibrate) {
  $("calibration").hidden = false;
  const updateCalibration = () => {
    if (!avatar) return;
    const exercise = latest?.exercise || {
      posture: "supine",
      hip_motion: "flexion",
    };
    avatar.update(
      {
        hip: Number($("cal-hip").value),
        knee: Number($("cal-knee").value),
        ankle: Number($("cal-ankle").value),
      },
      { hip: "ok", knee: "ok", ankle: "ok" },
      exercise,
      side(),
    );
  };
  for (const id of ["cal-hip", "cal-knee", "cal-ankle"])
    $(id).addEventListener("input", updateCalibration);
}
setTheme();
voiceChanged();
switchScreen(calibrate ? "live" : location.hash.slice(1) || "start", false);
loadPatients();
refreshStatus();
connect();
pollTimer = setInterval(() => {
  refreshStatus();
  if (["sessions", "summary"].includes(screen)) loadSessions();
}, 5000);
window.addEventListener("pagehide", () => {
  clearInterval(pollTimer);
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
});
