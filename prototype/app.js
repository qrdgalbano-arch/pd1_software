import { CONFIG } from "./config.js";
import { createAvatar } from "./avatar3d.js";
import { PoseLandmarker, FilesetResolver } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

const $ = (s) => document.querySelector(s);
const q = new URLSearchParams(location.search);
const C = { ...CONFIG, repsPerSet: +q.get("reps") || CONFIG.repsPerSet, restSeconds: +q.get("rest") || CONFIG.restSeconds };
const MODEL = "../PD1_Software_Design_C/models/pose_landmarker_full.task";
const SIDE = { left: [11, 23, 25, 27], right: [12, 24, 26, 28] };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const app = { pid: null, done: {}, skipped: {}, results: {}, ex: null, landmarker: null, S: null, av: null, use3d: false };

function show(id) { document.querySelectorAll(".screen").forEach((e) => e.classList.add("hidden")); $("#" + id).classList.remove("hidden"); }
function modal(html, bind) { $("#modalBox").innerHTML = html; $("#modal").classList.remove("hidden"); bind && bind(); }
function closeModal() { $("#modal").classList.add("hidden"); }

/* ---------- audio ---------- */
let actx;
function beep() { try { actx = actx || new AudioContext(); const o = actx.createOscillator(), g = actx.createGain(); o.frequency.value = 880; g.gain.value = 0.15; o.connect(g); g.connect(actx.destination); o.start(); o.stop(actx.currentTime + 0.15); } catch {} }
let lastSpoken = { t: 0, m: "" };
function say(m, force) {
  const now = performance.now();
  if (!force && (now - lastSpoken.t < 2500 || (m === lastSpoken.m && now - lastSpoken.t < 6000))) return;
  lastSpoken = { t: now, m };
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(m); u.rate = 0.9; u.pitch = 1; u.lang = "en-US";
  const v = speechSynthesis.getVoices().find((x) => x.lang.startsWith("en") && x.localService && /female|samantha|zira|aria|google us/i.test(x.name)) || speechSynthesis.getVoices().find((x) => x.lang.startsWith("en"));
  if (v) u.voice = v; speechSynthesis.speak(u);
}

/* ---------- login & list ---------- */
$("#who").textContent = `${C.patient.name} | ${C.patient.sex} | ${C.patient.age} y`;
$("#pidGo").onclick = () => {
  const v = $("#pid").value.trim();
  if (!/^\d{7}$/.test(v)) { $("#pidErr").textContent = "Enter exactly 7 digits."; return; }
  app.pid = v; renderList(); show("list");
};
function renderList() {
  $("#today").textContent = new Date().toLocaleDateString(undefined, { weekday: "long", month: "numeric", day: "numeric", year: "2-digit" });
  $("#exList").innerHTML = "";
  C.exercises.forEach((e, i) => {
    const st = app.done[i] ? '<span class="done">Done</span>' : app.skipped[i] ? `<span class="tag">Skipped: ${app.skipped[i]}</span>` : '<span class="tag">Not yet</span>';
    const d = document.createElement("div"); d.className = "ex";
    d.innerHTML = `<div class="num">${i + 1}</div><div class="t"><b>${e.name}</b><br><span class="tag">${e.prescription}</span></div>${st}<button>Record</button>`;
    d.querySelector("button").onclick = () => selectEx(i); $("#exList").appendChild(d);
  });
}
function selectEx(i) {
  const prev = i - 1;
  if (prev >= 0 && !app.done[prev] && !app.skipped[prev]) {
    modal(`<h3>Skip the ${C.exercises[prev].name}?</h3><button id="y">Yes</button> <button id="n" class="secondary">No</button>`, () => {
      $("#n").onclick = () => { closeModal(); show("list"); };
      $("#y").onclick = () => modal(`<h3>Choose a reason</h3>
        ${["Pain", "Fatigue", "Not enough time"].map((r) => `<label><input type="radio" name="rs" value="${r}"> ${r}</label><br>`).join("")}
        <label><input type="radio" name="rs" value="Others"> Others:</label> <input id="oth" placeholder="specify"><br><button id="ok">Confirm</button>`, () => {
        $("#ok").onclick = () => {
          const r = document.querySelector('input[name=rs]:checked'); if (!r) return;
          let reason = r.value; if (reason === "Others") { reason = $("#oth").value.trim(); if (!reason) return; }
          app.skipped[prev] = reason; closeModal(); openDetail(i);
        };
      });
    });
    return;
  }
  openDetail(i);
}
function openDetail(i) {
  const e = C.exercises[i]; app.ex = i;
  $("#dName").textContent = e.name; $("#dRx").textContent = e.prescription; $("#dFreq").textContent = e.frequency;
  $("#dIns").innerHTML = e.instructions.map((s) => `<li>${s}</li>`).join(""); $("#dCam").textContent = e.camera; show("detail");
}
$("#backList").onclick = () => { renderList(); show("list"); };
$("#finishAll").onclick = () => { renderSummary(); show("summary"); };
$("#toList").onclick = () => { renderList(); show("list"); };

/* ---------- geometry ---------- */
function ang(a, b, c) {
  const v1 = [a.x - b.x, a.y - b.y], v2 = [c.x - b.x, c.y - b.y];
  const m = Math.hypot(...v1) * Math.hypot(...v2); if (!m) return 180;
  return (Math.acos(clamp((v1[0] * v2[0] + v1[1] * v2[1]) / m, -1, 1)) * 180) / Math.PI;
}
function sideMetrics(lm, side, W, H) {
  const [s, h, k, a] = SIDE[side].map((i) => ({ x: lm[i].x * W, y: lm[i].y * H, v: lm[i].visibility ?? 1 }));
  return { pts: { s, h, k, a }, vis: Math.min(s.v, h.v, k.v, a.v), hipFlex: 180 - ang(s, h, k), kneeFlex: 180 - ang(h, k, a),
    trunkTilt: (Math.atan2(Math.abs(h.y - s.y), Math.abs(h.x - s.x)) * 180) / Math.PI, dir: Math.sign(h.x - s.x) || 1 };
}
const primary = (ex, m) => (ex.id === "slr" ? m.hipFlex : m.kneeFlex);

/* ---------- session ---------- */
async function initPose() {
  if (app.landmarker) return;
  const fs = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  app.landmarker = await PoseLandmarker.createFromOptions(fs, { baseOptions: { modelAssetPath: MODEL }, runningMode: "VIDEO", numPoses: 1 });
}
async function initAvatar(exId) {
  try {
    if (!app.av) { setMsg("Loading 3D avatar (large file, please wait)..."); app.av = await createAvatar($("#twin3d"), q.get("flip") === "1" ? -1 : 1); }
    app.av.setExercise(exId); app.use3d = true;
  } catch (err) { console.warn("3D avatar unavailable, using 2D twin:", err); app.use3d = false; app.av = null; }
  $("#twin3d").style.display = app.use3d ? "block" : "none";
}
$("#startSession").onclick = async () => {
  show("record"); $("#msg").textContent = "Starting camera..."; $("#msg").className = "msg";
  try {
    await initPose();
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    $("#vid").srcObject = stream; await $("#vid").play();
  } catch (err) { $("#msg").textContent = "Camera/model error: " + err.message + " (serve over http://localhost)"; return; }
  const ex = C.exercises[app.ex];
  await initAvatar(ex.id);
  app.S = { ex, set: 1, legIdx: 0, reps: 0, phase: "POSITION", hold: null, peak: 0, viol: null, devT: {}, data: [], resume: 0, prevA: null, prevT: 0, sm: null, lost: false, running: true, guide: {} };
  $("#rTitle").textContent = ex.name; setMsg("Get into the starting position.");
  say(`Get into position. ${ex.id === "slr" ? "Lie on your back" : "Lie on your stomach"}, ${C.legs[0]} leg first.`, true);
  requestAnimationFrame(loop);
};
$("#stopRec").onclick = () => finishRec(false);
function setMsg(t, cls) { $("#msg").textContent = t; $("#msg").className = "msg " + (cls || ""); }
function curLeg() { return C.legs[app.S.legIdx]; }

function loop() {
  const S = app.S; if (!S || !S.running) return;
  const v = $("#vid"); const ov = $("#ov");
  if (v.videoWidth) { ov.width = v.videoWidth; ov.height = v.videoHeight; }
  if (v.readyState >= 2 && v.videoWidth) {
    const res = app.landmarker.detectForVideo(v, performance.now());
    const lm = res.landmarks && res.landmarks[0];
    S.guide = {};
    if (S.phase === "REST") restTick();
    else if (lm) process(lm, v.videoWidth, v.videoHeight); else { S.lost = true; setMsg("I can't see you. Move into view.", "bad"); }
    draw(lm, ov);
    $("#rInfo").textContent = `Set ${S.set}/${C.sets} | ${curLeg()} leg | Valid ${S.reps}/${C.repsPerSet}`;
    $("#stat").textContent = S.resume ? `Resuming: ${C.resumeValidReps - S.resume}/${C.resumeValidReps} valid reps` : "";
  }
  requestAnimationFrame(loop);
}

function positionFailures(ex, m) {
  const f = [];
  if (m.vis < C.minVisibility) return [{ id: "vis", t: "Keep your whole leg in view." }];
  if (m.trunkTilt > 30) f.push({ id: "lie", t: "Lie flat on the mat.", dir: "down", j: "h" });
  if (ex.id === "slr") {
    if (m.hipFlex > ex.rest_max_deg) f.push({ id: "low", t: "Lower your leg to the mat.", dir: "down", j: "a" });
    if (m.kneeFlex > ex.knee_max_deg) f.push({ id: "knee", t: "Straighten your knee.", dir: "down", j: "k", red: "knee" });
  } else {
    if (m.hipFlex > ex.thigh_max_deg) f.push({ id: "thigh", t: "Keep your thigh flat on the mat.", dir: "down", j: "k", red: "thigh" });
    if (m.kneeFlex > ex.rest_max_deg) f.push({ id: "str", t: "Straighten your leg on the mat.", dir: "down", j: "a" });
  }
  return f;
}

function process(lm, W, H) {
  const S = app.S, ex = S.ex, now = performance.now() / 1000, side = curLeg();
  const other = side === "left" ? "right" : "left";
  const raw = sideMetrics(lm, side, W, H), oth = sideMetrics(lm, other, W, H);
  const k = 0.45;
  S.sm = S.sm ? { hipFlex: S.sm.hipFlex + k * (raw.hipFlex - S.sm.hipFlex), kneeFlex: S.sm.kneeFlex + k * (raw.kneeFlex - S.sm.kneeFlex) } : { hipFlex: raw.hipFlex, kneeFlex: raw.kneeFlex };
  const m = { ...raw, hipFlex: S.sm.hipFlex, kneeFlex: S.sm.kneeFlex }; S.m = m; S.oth = oth;
  const a = primary(ex, m);

  if (raw.vis < C.minVisibility) { S.lost = true; setMsg("Keep your whole leg in view.", "bad"); say("Keep your whole leg in view."); return; }
  S.lost = false;

  if (S.phase === "POSITION") {
    const f = positionFailures(ex, m);
    if (f.length) {
      S.hold = null; setMsg(f[0].t, "bad"); say(f[0].t); S.guide = { dir: f[0].dir, j: f[0].j, red: f[0].red };
    } else {
      S.hold = S.hold || now; setMsg("Hold still...");
      if (now - S.hold >= C.holdReadySeconds) { S.phase = "READY"; S.hold = null; setMsg("Position ready. Begin the exercise.", "good"); say("Position ready. Begin.", true); }
    }
    return;
  }
  if (S.phase === "READY") {
    const f = positionFailures(ex, m).filter((x) => x.id !== "vis");
    if (primary(ex, oth) > ex.rep_start_deg && a < ex.rest_max_deg) { setMsg(`Wrong leg. Use your ${side} leg.`, "bad"); say(`Wrong leg. Use your ${side} leg.`); S.guide = { red: "other" }; return; }
    if (a > ex.rep_start_deg) { S.phase = "MOVING"; S.peak = a; S.viol = null; S.devT = {}; S.prevA = a; S.prevT = now; return; }
    if (f.length && a <= ex.rest_max_deg) { S.hold = S.hold || now; if (now - S.hold > 1.5) { S.phase = "POSITION"; S.hold = null; } } else S.hold = null;
    setMsg(`Raise your ${ex.motion === "hip flexion" ? "leg" : "heel"} slowly.`); S.guide = { dir: "up", j: "a" };
    return;
  }
  if (S.phase === "MOVING") {
    S.peak = Math.max(S.peak, a);
    const speed = S.prevA == null ? 0 : Math.abs(a - S.prevA) / Math.max(now - S.prevT, 0.016);
    S.prevA = a; S.prevT = now;
    const dev = [];
    if (ex.id === "slr" && m.kneeFlex > ex.knee_max_deg) dev.push({ id: "knee", t: "Keep your knee straight.", red: "knee" });
    if (ex.id === "plf" && m.hipFlex > ex.thigh_max_deg) dev.push({ id: "thigh", t: "Keep your thigh flat on the mat.", red: "thigh" });
    if (speed > ex.max_speed_dps) dev.push({ id: "fast", t: "Slow down.", red: "leg" });
    S.activeDev = null;
    for (const d of dev) {
      S.devT[d.id] = S.devT[d.id] || now;
      if (now - S.devT[d.id] >= C.deviationConfirmSeconds) { S.viol = S.viol || d; S.activeDev = d; }
    }
    ["knee", "thigh", "fast"].forEach((id) => { if (!dev.find((d) => d.id === id)) delete S.devT[id]; });
    if (S.activeDev) { setMsg(S.activeDev.t, "bad"); say(S.activeDev.t); S.guide = { dir: "down", j: "k", red: S.activeDev.red }; }
    else if (S.peak >= ex.target_deg) { setMsg("Good. Now lower slowly.", "good"); S.guide = { dir: "down", j: "a" }; }
    else { setMsg("Keep going. Lift higher.", ""); S.guide = { dir: "up", j: "a" }; }
    if (a < ex.rest_max_deg) completeRep(m);
    return;
  }
}

function completeRep(m) {
  const S = app.S, ex = S.ex;
  const reasonLow = S.peak < ex.target_deg;
  const valid = !reasonLow && !S.viol;
  const rec = { set: S.set, leg: curLeg(), peak: +S.peak.toFixed(1), rom: +(S.peak - Math.min(primary(ex, m), ex.rest_max_deg)).toFixed(1), valid, reason: valid ? null : reasonLow ? "Below target range" : S.viol.id };
  S.data.push(rec);
  S.phase = "READY"; S.hold = null; S.sm = null;
  if (valid) {
    beep(); S.reps++; if (S.resume > 0) S.resume--;
    setMsg(`Rep ${S.reps} counted.`, "good");
    if (S.reps >= C.repsPerSet) return legDone();
  } else { const t = reasonLow ? "Not counted. Lift a little higher." : "Not counted. " + S.viol.t; setMsg(t, "bad"); say(t, true); }
}
function legDone() {
  const S = app.S;
  if (S.legIdx < C.legs.length - 1) { S.legIdx++; S.reps = 0; S.phase = "POSITION"; setMsg(`Leg done. Switch to your ${curLeg()} leg.`, "good"); say(`Leg done. Switch to your ${curLeg()} leg.`, true); return; }
  if (S.set < C.sets) { S.phase = "REST"; S.restEnd = performance.now() / 1000 + C.restSeconds; $("#rest").classList.remove("hidden"); setMsg("Set complete. Rest.", "good"); say("Set complete. Rest.", true); return; }
  finishRec(true);
}
function restTick() {
  const S = app.S, left = Math.ceil(S.restEnd - performance.now() / 1000);
  $("#restClock").textContent = `${String(Math.floor(Math.max(left, 0) / 60)).padStart(2, "0")}:${String(Math.max(left, 0) % 60).padStart(2, "0")}`;
  if (left <= 0) {
    $("#rest").classList.add("hidden"); S.set++; S.legIdx = 0; S.reps = 0; S.phase = "POSITION"; S.resume = C.resumeValidReps; S.sm = null;
    setMsg(`Rest finished. Get ready for set ${S.set}.`); say(`Rest finished. Set ${S.set}. Get into position.`, true);
  }
}
$("#extend").onclick = () => { if (app.S) app.S.restEnd += C.restExtendSeconds; };

function finishRec(complete) {
  const S = app.S; S.running = false;
  const st = $("#vid").srcObject; st && st.getTracks().forEach((t) => t.stop());
  $("#rest").classList.add("hidden"); speechSynthesis.cancel();
  app.results[app.ex] = { ex: S.ex, data: S.data, completed: complete };
  if (complete) app.done[app.ex] = true;
  renderSummary(); show("summary"); if (complete) say("Exercise complete.", true);
}

/* ---------- summary ---------- */
function stats(ex, rows) {
  const v = rows.filter((r) => r.valid); if (!v.length) return null;
  const avg = (k) => v.reduce((s, r) => s + r[k], 0) / v.length;
  return { n: v.length, bad: rows.length - v.length, rom: avg("rom"), peak: avg("peak"), wnl: avg("rom") >= ex.wnl_min_deg };
}
function renderSummary() {
  let h = `<p>Patient ID ${app.pid || "-"} | ${C.patient.name}, ${C.patient.sex}, ${C.patient.age}</p>`;
  Object.values(app.results).forEach((r) => {
    h += `<h3>${r.ex.name} (${r.ex.motion})</h3><p class="tag">Standard: ${r.ex.wnl_source}. WNL if average valid-rep ROM >= ${r.ex.wnl_min_deg} deg.</p>
    <table><tr><th>Leg</th><th>Valid reps</th><th>Not counted</th><th>Avg ROM (valid)</th><th>Classification</th></tr>`;
    C.legs.forEach((leg) => {
      const s = stats(r.ex, r.data.filter((d) => d.leg === leg));
      h += s ? `<tr><td>${leg}</td><td>${s.n}</td><td>${s.bad}</td><td>${s.rom.toFixed(1)} deg</td><td class="${s.wnl ? "wnl" : "low"}">${s.wnl ? "Within normal limits" : "Below normal limits"}</td></tr>`
             : `<tr><td>${leg}</td><td>0</td><td>-</td><td>n/a</td><td>Not assessed</td></tr>`;
    });
    h += "</table>";
  });
  Object.entries(app.skipped).forEach(([i, r]) => (h += `<p>Skipped: ${C.exercises[i].name} - ${r}</p>`));
  $("#sumBody").innerHTML = h || "<p>No exercises recorded yet.</p>";
}
$("#dl").onclick = () => {
  const blob = new Blob([JSON.stringify({ patientId: app.pid, patient: C.patient, skipped: app.skipped, results: app.results }, null, 2)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `session_${app.pid}.json`; a.click();
};

/* ---------- drawing ---------- */
function arrow(ctx, x, y, dir, len, col) {
  const dy = dir === "up" ? -1 : 1; ctx.strokeStyle = ctx.fillStyle = col; ctx.lineWidth = 6;
  ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + dy * len); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x - 12, y + dy * (len - 14)); ctx.lineTo(x, y + dy * (len + 8)); ctx.lineTo(x + 12, y + dy * (len - 14)); ctx.fill();
}
function draw(lm, ov) {
  const S = app.S, ctx = ov.getContext("2d"); ctx.clearRect(0, 0, ov.width, ov.height);
  if (lm && S.m) {
    const p = S.m.pts, red = S.guide.red;
    const seg = (a, b, bad) => { ctx.strokeStyle = bad ? "#ff2d2d" : "#2dff8a"; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); };
    seg(p.s, p.h, false); seg(p.h, p.k, red === "thigh" || red === "leg" || red === "knee"); seg(p.k, p.a, red === "knee" || red === "leg");
    if (S.guide.dir && S.guide.j) arrow(ctx, p[S.guide.j].x + 30, p[S.guide.j].y - (S.guide.dir === "up" ? 10 : 70), S.guide.dir, 55, "#ffd400");
  }
  drawTwin();
}
function drawTwin() {
  const S = app.S, c = $("#twin"), ctx = c.getContext("2d"), ex = S.ex; ctx.clearRect(0, 0, c.width, c.height);
  const m = S.m || { hipFlex: 0, kneeFlex: 0 }, g = S.guide || {};
  const gh = S.phase === "MOVING" || S.phase === "READY" ? ex.ghost_deg : 0;
  if (app.use3d) {
    try {
      app.av.update({ side: curLeg(), ex: ex.id, hip: m.hipFlex, knee: m.kneeFlex, ghostHip: ex.id === "slr" ? gh : 0, ghostKnee: ex.id === "plf" ? gh : 0, red: g.red });
    } catch (err) { console.warn("3D update failed, switching to 2D twin:", err); app.use3d = false; $("#twin3d").style.display = "none"; }
  }
  if (!app.use3d) {
    const ox = 170, oy = 210;
    ctx.fillStyle = "#cfd8dc"; ctx.fillRect(20, oy + 18, 380, 8);
    skeleton(ctx, ox, oy, ex, ex.id === "slr" ? gh : 0, ex.id === "plf" ? gh : 0, 0.3, "#1565c0", null);
    skeleton(ctx, ox, oy, ex, m.hipFlex, m.kneeFlex, 1, "#00796b", g.red);
  }
  if (g.dir) arrow(ctx, 340, g.dir === "up" ? 190 : 80, g.dir, 60, "#f9a825");
}
function skeleton(ctx, ox, oy, ex, hip, knee, alpha, col, red) {
  const T = 120, TH = 110, SH = 105, r = (d) => (d * Math.PI) / 180;
  const thA = r(hip), shA = ex.id === "slr" ? r(hip - knee) : r(hip + knee);
  const hx = ox, hy = oy, kx = hx + TH * Math.cos(thA), ky = hy - TH * Math.sin(thA), ax = kx + SH * Math.cos(shA), ay = ky - SH * Math.sin(shA);
  ctx.globalAlpha = alpha; ctx.lineCap = "round"; ctx.lineWidth = 10;
  const ln = (x1, y1, x2, y2, bad) => { ctx.strokeStyle = bad ? "#e53935" : col; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); };
  ln(hx - T, hy, hx, hy, false);
  ln(hx, hy, kx, ky, red === "thigh" || red === "leg" || red === "knee");
  ln(kx, ky, ax, ay, red === "knee" || red === "leg");
  ctx.fillStyle = col; ctx.beginPath(); ctx.arc(hx - T - 22, hy - 4, 16, 0, 7); ctx.fill();
  ctx.beginPath(); ctx.arc(hx, hy, 7, 0, 7); ctx.arc(kx, ky, 7, 0, 7); ctx.fill(); ctx.globalAlpha = 1;
}
