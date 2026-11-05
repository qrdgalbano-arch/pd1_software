import { CONFIG } from "./config.js";
import { createAvatar } from "./avatar3d.js";
import { PoseLandmarker, FilesetResolver } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

const $ = (s) => document.querySelector(s);
const q = new URLSearchParams(location.search);
const C = { ...CONFIG, repsPerSet: +q.get("reps") || CONFIG.repsPerSet, restSeconds: +q.get("rest") || CONFIG.restSeconds };
const MODEL = "../PD1_Software_Design_C/models/pose_landmarker_full.task";
const SIDE = { left: [11, 23, 25, 27], right: [12, 24, 26, 28] };
const PART = ["shoulder", "hip", "knee", "ankle"];
const KEYS = [11, 12, 23, 24, 25, 26, 27, 28];
const ROTS = [0, 90, -90];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const app = { pid: null, done: {}, skipped: {}, results: {}, ex: null, landmarker: null, S: null, av: null, use3d: false, rot: 0, rotMode: localStorage.getItem("rotMode") || "auto" };

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

/* ---------- pose estimation (full body, rotation for lying poses) ---------- */
async function initPose() {
  if (app.landmarker) return;
  const fs = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  app.landmarker = await PoseLandmarker.createFromOptions(fs, {
    baseOptions: { modelAssetPath: MODEL }, runningMode: "VIDEO", numPoses: 1,
    minPoseDetectionConfidence: 0.35, minPosePresenceConfidence: 0.35, minTrackingConfidence: 0.35
  });
}
const rc = document.createElement("canvas");
let lastTs = 0;
const nextTs = () => (lastTs = Math.max(lastTs + 1, performance.now()));
function runDetect(v, rot) {
  const W = v.videoWidth, H = v.videoHeight; let src = v;
  if (rot !== 0) {
    rc.width = H; rc.height = W; const c = rc.getContext("2d"); c.save();
    if (rot === 90) { c.translate(H, 0); c.rotate(Math.PI / 2); } else { c.translate(0, W); c.rotate(-Math.PI / 2); }
    c.drawImage(v, 0, 0); c.restore(); src = rc;
  }
  const r = app.landmarker.detectForVideo(src, nextTs());
  const raw = r.landmarks && r.landmarks[0]; if (!raw) return null;
  return raw.map((p) => rot === 0 ? { x: p.x, y: p.y, visibility: p.visibility ?? 0 } : rot === 90 ? { x: p.y, y: 1 - p.x, visibility: p.visibility ?? 0 } : { x: 1 - p.y, y: p.x, visibility: p.visibility ?? 0 });
}
// A confident skeleton is only trusted if the trunk lies roughly horizontal in the camera image (patient is lying, camera at the side).
function score(lm, W, H) {
  if (!lm) return 0;
  const v = KEYS.reduce((s, i) => s + lm[i].visibility, 0) / KEYS.length;
  const ms = [(lm[11].x + lm[12].x) / 2 * W, (lm[11].y + lm[12].y) / 2 * H], mh = [(lm[23].x + lm[24].x) / 2 * W, (lm[23].y + lm[24].y) / 2 * H];
  const tilt = (Math.atan2(Math.abs(mh[1] - ms[1]), Math.abs(mh[0] - ms[0])) * 180) / Math.PI;
  const inside = KEYS.every((i) => lm[i].x > -0.05 && lm[i].x < 1.05 && lm[i].y > -0.05 && lm[i].y < 1.05);
  return tilt <= 50 && inside ? v : v * 0.2;
}
function detect(v) {
  const W = v.videoWidth, H = v.videoHeight;
  if (app.rotMode !== "auto") { app.rot = +app.rotMode; return runDetect(v, app.rot); }
  let lm = runDetect(v, app.rot), sc = score(lm, W, H);
  if (sc < 0.5) {
    for (const alt of ROTS) {
      if (alt === app.rot) continue;
      const l2 = runDetect(v, alt), s2 = score(l2, W, H);
      if (s2 > sc + 0.1) { sc = s2; lm = l2; app.rot = alt; }
    }
  }
  return lm;
}
function smoothLm(prev, lm) { return prev ? lm.map((p, i) => ({ x: prev[i].x + 0.5 * (p.x - prev[i].x), y: prev[i].y + 0.5 * (p.y - prev[i].y), visibility: p.visibility })) : lm.map((p) => ({ ...p })); }

/* ---------- geometry ---------- */
function ang(a, b, c) {
  const v1 = [a.x - b.x, a.y - b.y], v2 = [c.x - b.x, c.y - b.y];
  const m = Math.hypot(...v1) * Math.hypot(...v2); if (!m) return 180;
  return (Math.acos(clamp((v1[0] * v2[0] + v1[1] * v2[1]) / m, -1, 1)) * 180) / Math.PI;
}
function sideMetrics(lm, side, W, H) {
  const [s, h, k, a] = SIDE[side].map((i) => ({ x: lm[i].x * W, y: lm[i].y * H, v: lm[i].visibility }));
  return { pts: { s, h, k, a }, hipFlex: 180 - ang(s, h, k), kneeFlex: 180 - ang(h, k, a) };
}
const primary = (ex, m) => (ex.id === "slr" ? m.hipFlex : m.kneeFlex);
const moving = (ex, m) => (ex.id === "slr" ? m.hipFlex > ex.rep_start_deg && m.kneeFlex <= 25 : m.kneeFlex > ex.rep_start_deg && m.hipFlex <= ex.thigh_max_deg + 10);

function avatarDirs(lm, W, H, prone, headDir) {
  const d = {}, f = prone ? headDir : -headDir;
  const seg = (id, a, b) => {
    if (lm[a].visibility < 0.35 || lm[b].visibility < 0.35) return;
    const dx = (lm[b].x - lm[a].x) * W, dy = (lm[b].y - lm[a].y) * H;
    if (Math.hypot(dx, dy) < 4) return; d[id] = [0, -dy, f * dx];
  };
  seg("left_thigh", 23, 25); seg("left_shin", 25, 27); seg("right_thigh", 24, 26); seg("right_shin", 26, 28);
  seg("left_uarm", 11, 13); seg("left_farm", 13, 15); seg("right_uarm", 12, 14); seg("right_farm", 14, 16);
  return d;
}

/* ---------- session ---------- */
async function initAvatar(exId) {
  try {
    if (!app.av) { setMsg("Loading 3D avatar (large file, please wait)..."); app.av = await createAvatar($("#twin3d")); }
    app.av.setExercise(exId); app.use3d = true;
  } catch (err) { console.warn("3D avatar unavailable, using 2D twin:", err); app.use3d = false; app.av = null; }
  $("#twin3d").style.display = app.use3d ? "block" : "none";
}
$("#rotSel").value = app.rotMode;
$("#rotSel").onchange = (e) => { app.rotMode = e.target.value; localStorage.setItem("rotMode", app.rotMode); if (app.S) app.S.lmS = null; };
$("#startSession").onclick = async () => {
  show("record"); $("#msg").textContent = "Starting camera..."; $("#msg").className = "msg";
  try {
    await initPose();
    const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
    $("#vid").srcObject = stream; await $("#vid").play();
    $(".cam").style.aspectRatio = `${$("#vid").videoWidth} / ${$("#vid").videoHeight}`;
  } catch (err) { $("#msg").textContent = "Camera/model error: " + err.message + " (serve over http://localhost)"; return; }
  const ex = C.exercises[app.ex];
  await initAvatar(ex.id);
  app.S = { ex, set: 1, leg: null, legsDone: [], reps: 0, phase: "POSITION", hold: null, peak: 0, viol: null, devT: {}, data: [], resume: 0, prevA: null, prevT: 0, lmS: null, M: null, m: null, running: true, guide: {}, nvis: 0, sv: { left: 0, right: 0 } };
  $("#rTitle").textContent = ex.name; setMsg("Get into the position shown by the green target.");
  say(`Get into position like the green target. ${ex.id === "slr" ? "Lie on your back" : "Lie on your stomach"}.`, true);
  requestAnimationFrame(loop);
};
$("#stopRec").onclick = () => finishRec(false);
function setMsg(t, cls) { $("#msg").textContent = t; $("#msg").className = "msg " + (cls || ""); }
const other = (s) => (s === "left" ? "right" : "left");

function loop() {
  const S = app.S; if (!S || !S.running) return;
  const v = $("#vid"), ov = $("#ov");
  if (v.videoWidth && (ov.width !== v.videoWidth || ov.height !== v.videoHeight)) { ov.width = v.videoWidth; ov.height = v.videoHeight; }
  if (v.readyState >= 2 && v.videoWidth) {
    const W = v.videoWidth, H = v.videoHeight, lm = detect(v);
    S.guide = {};
    if (lm) {
      S.lmS = smoothLm(S.lmS, lm); S.nvis = S.lmS.filter((p) => p.visibility >= 0.5).length;
      ingest(W, H);
      if (S.phase === "REST") restTick(); else if (S.allVisible) process(W, H);
      else if (S.phase !== "REST") { setMsg(S.visMsg, "bad"); say(S.visMsg); }
    } else { S.lmS = null; S.allVisible = false; S.nvis = 0; if (S.phase === "REST") restTick(); else setMsg("I can't see you. Lie in view of the camera.", "bad"); }
    draw(ov, W, H);
    $("#rInfo").textContent = `Set ${S.set}/${C.sets} | ${S.leg ? S.leg + " leg" : "choose a leg"} | Valid ${S.reps}/${C.repsPerSet}`;
    $("#stat").textContent = `Landmarks ${S.nvis}/33 | rotation ${app.rot} deg (${app.rotMode})` + (S.resume ? ` | Resuming: ${C.resumeValidReps - S.resume}/${C.resumeValidReps} valid reps` : "");
  }
  requestAnimationFrame(loop);
}

function ingest(W, H) {
  const S = app.S, lm = S.lmS;
  S.M = { left: sideMetrics(lm, "left", W, H), right: sideMetrics(lm, "right", W, H) };
  const sv = (side) => Math.min(...SIDE[side].map((i) => lm[i].visibility));
  S.sv = { left: sv("left"), right: sv("right") };
  // Side-view rule: the camera-side leg must be clear; the far-side leg may be partly hidden.
  const best = S.sv.left >= S.sv.right ? "left" : "right", far = other(best);
  S.allVisible = S.sv[best] >= C.minVisibility && S.sv[far] >= 0.15;
  if (!S.allVisible) {
    const side = S.sv[best] < C.minVisibility ? best : far;
    const idx = SIDE[side].map((i, k) => [lm[i].visibility, k]).sort((a, b) => a[0] - b[0])[0][1];
    S.visMsg = `I can't see your ${side} ${PART[idx]} clearly. Adjust the camera or your position.`;
  }
  const ms = { x: (lm[11].x + lm[12].x) / 2 * W, y: (lm[11].y + lm[12].y) / 2 * H }, mh = { x: (lm[23].x + lm[24].x) / 2 * W, y: (lm[23].y + lm[24].y) / 2 * H };
  S.trunkTilt = (Math.atan2(Math.abs(mh.y - ms.y), Math.abs(mh.x - ms.x)) * 180) / Math.PI;
  S.headDir = Math.sign(ms.x - mh.x) || -1;
  const side = S.leg || best;
  S.m = S.M[side]; S.mSide = side;
}

function positionFailures(ex, S) {
  const f = [], M = S.M;
  if (S.trunkTilt > 30) f.push({ id: "lie", t: "Lie flat on the mat.", dir: "down", j: "h" });
  const ok = (s) => S.sv[s] < 0.3 || (ex.id === "slr" ? M[s].hipFlex <= ex.rest_max_deg && M[s].kneeFlex <= ex.knee_max_deg : M[s].kneeFlex <= ex.rest_max_deg && M[s].hipFlex <= ex.thigh_max_deg);
  if (S.leg) {
    const m = M[S.leg];
    if (ex.id === "slr") {
      if (m.hipFlex > ex.rest_max_deg) f.push({ id: "low", t: "Lower your leg to the mat.", dir: "down", j: "a" });
      if (m.kneeFlex > ex.knee_max_deg) f.push({ id: "knee", t: "Straighten your knee.", dir: "down", j: "k", red: "knee" });
    } else {
      if (m.hipFlex > ex.thigh_max_deg) f.push({ id: "thigh", t: "Keep your thigh flat on the mat.", dir: "down", j: "k", red: "thigh" });
      if (m.kneeFlex > ex.rest_max_deg) f.push({ id: "str", t: "Straighten your leg on the mat.", dir: "down", j: "a" });
    }
  } else if (ex.id === "slr") { if (!ok("left") && !ok("right")) f.push({ id: "low", t: "Lower and straighten one leg on the mat.", dir: "down", j: "a" }); }
  else if (!ok("left") || !ok("right")) f.push({ id: "str", t: "Lie on your stomach with both legs straight.", dir: "down", j: "a" });
  return f;
}

function process(W, H) {
  const S = app.S, ex = S.ex, now = performance.now() / 1000, M = S.M;
  if (S.phase === "POSITION") {
    const f = positionFailures(ex, S);
    if (f.length) { S.hold = null; setMsg(f[0].t, "bad"); say(f[0].t); S.guide = { dir: f[0].dir, j: f[0].j, red: f[0].red }; }
    else {
      S.hold = S.hold || now; setMsg("Hold still...");
      if (now - S.hold >= C.holdReadySeconds) { S.phase = "READY"; S.hold = null; setMsg(S.leg ? `Position ready. Begin with your ${S.leg} leg.` : "Position ready. Raise the leg you want to exercise first.", "good"); say(S.leg ? `Position ready. Use your ${S.leg} leg.` : "Position ready. Raise one leg to begin.", true); }
    }
    return;
  }
  if (S.phase === "READY") {
    if (!S.leg) {
      const c = ["left", "right"].filter((s) => S.sv[s] >= 0.3 && moving(ex, M[s]));
      if (!c.length) { setMsg("Raise the leg you want to exercise first."); S.guide = { dir: "up", j: "a" }; return; }
      S.leg = c.sort((a, b) => primary(ex, M[b]) - primary(ex, M[a]))[0];
      say(`Using your ${S.leg} leg.`, true);
    }
    const m = M[S.leg], o = M[other(S.leg)];
    if (S.sv[other(S.leg)] >= 0.3 && moving(ex, o) && primary(ex, m) < ex.rest_max_deg) { setMsg(`Wrong leg. Use your ${S.leg} leg.`, "bad"); say(`Wrong leg. Use your ${S.leg} leg.`); S.guide = { red: "other" }; return; }
    if (primary(ex, m) > ex.rep_start_deg) { S.phase = "MOVING"; S.peak = primary(ex, m); S.viol = null; S.devT = {}; S.prevA = S.peak; S.prevT = now; return; }
    const f = positionFailures(ex, S).filter((x) => x.id !== "lie");
    if (f.length && primary(ex, m) <= ex.rest_max_deg) { S.hold = S.hold || now; if (now - S.hold > 1.5) { S.phase = "POSITION"; S.hold = null; } } else S.hold = null;
    setMsg(`Raise your ${ex.motion === "hip flexion" ? "leg" : "heel"} slowly.`); S.guide = { dir: "up", j: "a" };
    return;
  }
  if (S.phase === "MOVING") {
    const m = M[S.leg], a = primary(ex, m);
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
  }
}

function completeRep(m) {
  const S = app.S, ex = S.ex;
  const reasonLow = S.peak < ex.target_deg, valid = !reasonLow && !S.viol;
  S.data.push({ set: S.set, leg: S.leg, peak: +S.peak.toFixed(1), rom: +(S.peak - Math.min(primary(ex, m), ex.rest_max_deg)).toFixed(1), valid, reason: valid ? null : reasonLow ? "Below target range" : S.viol.id });
  S.phase = "READY"; S.hold = null;
  if (valid) {
    beep(); S.reps++; if (S.resume > 0) S.resume--;
    setMsg(`Rep ${S.reps} counted.`, "good");
    if (S.reps >= C.repsPerSet) return legDone();
  } else { const t = reasonLow ? "Not counted. Lift a little higher." : "Not counted. " + S.viol.t; setMsg(t, "bad"); say(t, true); }
}
function legDone() {
  const S = app.S;
  S.legsDone.push(S.leg);
  if (S.legsDone.length < C.legs.length) {
    S.leg = other(S.leg); S.reps = 0; S.phase = "POSITION"; S.hold = null;
    setMsg(`Leg done. Now your ${S.leg} leg.`, "good"); say(`Leg done. Now your ${S.leg} leg.`, true); return;
  }
  if (S.set < C.sets) { S.phase = "REST"; S.restEnd = performance.now() / 1000 + C.restSeconds; $("#rest").classList.remove("hidden"); setMsg("Set complete. Rest.", "good"); say("Set complete. Rest.", true); return; }
  finishRec(true);
}
function restTick() {
  const S = app.S, left = Math.ceil(S.restEnd - performance.now() / 1000);
  $("#restClock").textContent = `${String(Math.floor(Math.max(left, 0) / 60)).padStart(2, "0")}:${String(Math.max(left, 0) % 60).padStart(2, "0")}`;
  if (left <= 0) {
    $("#rest").classList.add("hidden"); S.set++; S.leg = null; S.legsDone = []; S.reps = 0; S.phase = "POSITION"; S.hold = null; S.resume = C.resumeValidReps;
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
function draw(ov, W, H) {
  const S = app.S, ctx = ov.getContext("2d"); ctx.clearRect(0, 0, ov.width, ov.height);
  const lm = S.lmS;
  if (lm) {
    const lw = Math.max(2, W / 320);
    ctx.lineWidth = lw; ctx.strokeStyle = "rgba(255,255,255,0.7)";
    for (const c of PoseLandmarker.POSE_CONNECTIONS) {
      const a = lm[c.start], b = lm[c.end]; if (a.visibility < 0.3 || b.visibility < 0.3) continue;
      ctx.beginPath(); ctx.moveTo(a.x * W, a.y * H); ctx.lineTo(b.x * W, b.y * H); ctx.stroke();
    }
    lm.forEach((p) => { ctx.fillStyle = p.visibility >= 0.5 ? "#2dff8a" : "#ffb300"; ctx.beginPath(); ctx.arc(p.x * W, p.y * H, lw * 1.6, 0, 7); ctx.fill(); });
    if (S.m) {
      const p = S.m.pts, red = S.guide.red;
      const seg = (a, b, bad) => { ctx.strokeStyle = bad ? "#ff2d2d" : "#00e5ff"; ctx.lineWidth = lw * 2; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); };
      seg(p.s, p.h, false); seg(p.h, p.k, red === "thigh" || red === "leg" || red === "knee"); seg(p.k, p.a, red === "knee" || red === "leg");
      if (S.guide.dir && S.guide.j) arrow(ctx, p[S.guide.j].x + 30, p[S.guide.j].y - (S.guide.dir === "up" ? 10 : 70), S.guide.dir, 55, "#ffd400");
    }
  }
  drawTwin(W, H);
}
function drawTwin(W, H) {
  const S = app.S, c = $("#twin"), ctx = c.getContext("2d"), ex = S.ex; ctx.clearRect(0, 0, c.width, c.height);
  const g = S.guide || {}, showLive = S.phase !== "POSITION" && !!S.lmS;
  const gh = S.phase === "MOVING" || (S.phase === "READY" && S.leg) ? ex.ghost_deg : 0;
  const ghostLegs = gh && S.leg ? [{ side: S.leg, hip: ex.id === "slr" ? gh : 0, knee: ex.id === "plf" ? gh : 0 }] : [];
  if (app.use3d) {
    try {
      const dirs = showLive ? avatarDirs(S.lmS, W, H, ex.id === "plf", S.headDir) : {};
      app.av.update({ showLive, dirs, ghostLegs, red: g.red, side: S.leg });
    } catch (err) { console.warn("3D update failed, switching to 2D twin:", err); app.use3d = false; $("#twin3d").style.display = "none"; }
  }
  if (!app.use3d) {
    const ox = 170, oy = 210, m = S.m || { hipFlex: 0, kneeFlex: 0 };
    ctx.fillStyle = "#cfd8dc"; ctx.fillRect(20, oy + 18, 380, 8);
    skeleton(ctx, ox, oy, ex, ex.id === "slr" ? gh : 0, ex.id === "plf" ? gh : 0, showLive ? 0.3 : 0.8, showLive ? "#1565c0" : "#2e7d32", null);
    if (showLive) skeleton(ctx, ox, oy, ex, m.hipFlex, m.kneeFlex, 1, "#00796b", g.red);
  }
  ctx.fillStyle = "#333"; ctx.font = "bold 14px system-ui"; ctx.fillText(showLive ? "You (solid) / target (faded blue)" : "TARGET POSITION - match this", 10, 20);
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
