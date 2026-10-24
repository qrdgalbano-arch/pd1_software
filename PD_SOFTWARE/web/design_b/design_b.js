(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const LIVE = new URLSearchParams(location.search).has('live');

  // Target angles are placeholders until clinical staff confirm them.
  // stationKey/joint link to the existing station pipeline (live mode only).
  const EXERCISES = [
    {
      key: 'straight_leg_raise',
      stationKey: 'straight_leg_raising',
      joint: 'hip',
      name: 'Straight Leg Raise',
      sets: 3, reps: 10, target: 60, rest: 10, frequency: 'Daily',
      steps: [
        'Lie down flat on your back with one knee bent and the other leg kept completely straight.',
        'Tighten your thigh muscle on the straight leg and slowly lift it about 12 inches.',
        'Hold for 3 seconds, then slowly lower the straight leg back to the floor.',
      ],
    },
    {
      key: 'prone_leg_flexion',
      stationKey: 'prone_leg_flexion',
      joint: 'knee',
      name: 'Prone Leg Flexion',
      sets: 3, reps: 10, target: 90, rest: 20, frequency: 'Daily',
      steps: [
        'Lie face down on a firm surface with both legs straight.',
        'Keep your thigh on the surface and slowly bend the knee, bringing your heel toward you.',
        'Hold for 3 seconds, then slowly lower your foot back down.',
      ],
    },
    {
      key: 'ankle_pump',
      stationKey: null,
      joint: null,
      name: 'Ankle Pump',
      sets: 3, reps: 10, target: 30, rest: 5, frequency: 'Daily',
      steps: [
        'Lie or sit with your legs straight and relaxed.',
        'Point your toes away from you as far as is comfortable, then pull them back toward your shin.',
        'Move smoothly and repeat without rushing.',
      ],
    },
  ];

  const KEY_S = 'pdb_sessions_v1';
  const KEY_L = 'pdb_last_synced_v1';
  const PERIOD = 4;

  function loadSessions() {
    try { return JSON.parse(localStorage.getItem(KEY_S) || '[]'); }
    catch (e) { return []; }
  }
  const state = {
    patientId: null,
    patientName: null,
    sessions: loadSessions(),
    lastSynced: localStorage.getItem(KEY_L),
    syncing: false,
  };
  function save() {
    localStorage.setItem(KEY_S, JSON.stringify(state.sessions));
    if (state.lastSynced) localStorage.setItem(KEY_L, state.lastSynced);
  }

  const pad = (n) => String(n).padStart(2, '0');
  const mmss = (s) => pad(Math.floor(s / 60)) + ':' + pad(s % 60);
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const clock = (d) => {
    const h = d.getHours() % 12 || 12;
    return h + ':' + pad(d.getMinutes()) + ' ' + (d.getHours() >= 12 ? 'PM' : 'AM');
  };
  const dateText = (d) =>
    d.toLocaleDateString(undefined, { weekday: 'long', month: 'numeric', day: 'numeric', year: '2-digit' });

  function pending() { return state.sessions.filter((s) => !s.synced); }

  function completedToday() {
    const map = {};
    const now = new Date();
    for (const s of state.sessions) {
      if (!s.completed || s.patientId !== state.patientId) continue;
      const d = new Date(s.recordedAt);
      if (d.toDateString() !== now.toDateString()) continue;
      if (!map[s.exerciseKey] || d > map[s.exerciseKey]) map[s.exerciseKey] = d;
    }
    return map;
  }
  function nextIndex() {
    const done = completedToday();
    const i = EXERCISES.findIndex((e) => !done[e.key]);
    return i < 0 ? EXERCISES.length : i;
  }

  // ---------------------------------------------------------- navigation
  const SCREENS = ['patient', 'list', 'instr', 'rec', 'done', 'sync'];
  let current = 'patient';
  let syncBack = 'list';

  function show(name) {
    current = name;
    for (const s of SCREENS) $('s-' + s).hidden = s !== name;
    $('who').hidden = !state.patientId;
    $('btn-sync-top').hidden = !state.patientId;
    const h = document.querySelector('#s-' + name + ' h1');
    if (h) h.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }
  function notice(msg, level) {
    const el = $('notice');
    el.textContent = msg || '';
    el.className = 'notice ' + (level || 'info');
    el.hidden = !msg;
  }
  function updateTop() {
    $('pending-count').textContent = String(pending().length);
    if (state.patientId) {
      $('who').textContent = state.patientName
        ? state.patientName + ' (ID ' + state.patientId + ')'
        : 'ID ' + state.patientId;
    }
  }

  // ---------------------------------------------------------- 1. patient ID
  async function lookupPatients() {
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 3000);
    try {
      const r = await fetch('/api/patients', { signal: c.signal });
      if (!r.ok) return null;
      const b = await r.json();
      return Array.isArray(b.patients) ? b.patients : null;
    } catch (e) {
      return null;
    } finally {
      clearTimeout(t);
    }
  }

  $('f-patient').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = $('in-patient').value.trim().toUpperCase();
    const err = $('err-patient');
    err.hidden = true;
    if (!/^[A-Z0-9-]{1,20}$/.test(id)) {
      err.textContent = 'Enter a valid Patient ID (letters, numbers, or dashes).';
      err.hidden = false;
      return;
    }
    const list = await lookupPatients();
    let name = null;
    if (list && list.length) {
      const p = list.find((x) => String(x.id).toUpperCase() === id);
      if (!p) {
        err.textContent = 'Patient ID not found on this station.';
        err.hidden = false;
        return;
      }
      name = p.full_name || null;
      notice();
    } else {
      notice('Station patient list unavailable. The ID format was accepted but not verified.', 'warn');
    }
    state.patientId = id;
    state.patientName = name;
    updateTop();
    renderList();
    show('list');
  });

  // ---------------------------------------------------------- 2. exercise list
  function renderList() {
    $('t-list').textContent = dateText(new Date());
    $('list-sub').textContent =
      'Patient ' + state.patientId + (state.patientName ? ' - ' + state.patientName : '');
    const done = completedToday();
    const next = nextIndex();
    const ol = $('list');
    ol.replaceChildren();
    EXERCISES.forEach((ex, i) => {
      const isDone = !!done[ex.key];
      const active = i === next;
      const locked = !isDone && !active;
      const li = document.createElement('li');
      li.className = 'item' + (locked ? ' locked' : '') + (active ? ' active' : '');
      const num = document.createElement('span');
      num.className = 'num';
      num.textContent = String(i + 1);
      const body = document.createElement('div');
      body.className = 'grow';
      const b = document.createElement('b');
      b.textContent = ex.name;
      const small = document.createElement('small');
      small.textContent = ex.sets + ' sets × ' + ex.reps + ' reps' +
        (locked ? ' - Locked: finish the previous exercise first' : '');
      body.append(b, small);
      li.append(num, body);
      if (isDone) {
        const s = document.createElement('span');
        s.className = 'done';
        s.textContent = '✓ ' + clock(done[ex.key]);
        li.append(s);
      } else if (active) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn primary small';
        btn.textContent = 'Record';
        btn.setAttribute('aria-label', 'Record ' + ex.name);
        btn.addEventListener('click', () => openInstr(ex));
        li.append(btn);
      } else {
        const s = document.createElement('span');
        s.className = 'dash';
        s.textContent = '—';
        s.setAttribute('aria-label', 'Not done');
        li.append(s);
      }
      ol.append(li);
    });
    $('list-done').hidden = next < EXERCISES.length;
  }

  // ---------------------------------------------------------- 3. instructions
  function openInstr(ex) {
    $('t-instr').textContent = ex.name;
    $('i-presc').textContent = ex.sets + ' Sets × ' + ex.reps + ' Reps';
    $('i-freq').textContent = ex.frequency;
    $('i-steps').replaceChildren(
      ...ex.steps.map((t) => {
        const li = document.createElement('li');
        li.textContent = t;
        return li;
      })
    );
    $('btn-start').onclick = () => startRecording(ex);
    show('instr');
  }
  $('instr-back').addEventListener('click', () => show('list'));

  // ---------------------------------------------------------- 4. recording
  let rec = null;
  let rafId = null;
  let lastT = 0;
  const live = { joints: null };

  function setPreview() {
    if (!LIVE || !rec || !rec.ex.stationKey) return;
    fetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exercise_key: rec.ex.stationKey, side: rec.side }),
    }).catch(() => {});
  }

  function startRecording(ex) {
    rec = {
      ex, side: 'left', set: 1, reps: 0, total: 0, setsDone: 0,
      cycle: 0, elapsed: 0, paused: false, prompting: false,
      up: false, angle: 0, reached: false, source: 'sim',
    };
    setPreview();
    $('t-rec').textContent = ex.name;
    $('btn-pause').textContent = 'Pause';
    updateHud();
    show('rec');
    lastT = performance.now();
    cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(loop);
  }

  function repDone() {
    rec.reps += 1;
    rec.total += 1;
    if (rec.reps >= rec.ex.reps) setComplete();
  }

  function loop(now) {
    if (!rec) return;
    const dt = Math.min(0.1, (now - lastT) / 1000);
    lastT = now;
    if (!rec.paused && !rec.prompting) {
      rec.elapsed += dt;
      const jt = LIVE && rec.ex.joint && live.joints ? live.joints[rec.ex.joint] : null;
      if (jt && jt.tracked && typeof jt.angle === 'number') {
        rec.source = 'live';
        rec.angle = Math.max(0, jt.angle);
        if (rec.angle >= rec.ex.target * 0.85) {
          rec.up = true;
        } else if (rec.up && rec.angle <= rec.ex.rest) {
          rec.up = false;
          repDone();
        }
      } else {
        rec.source = 'sim';
        rec.cycle += dt;
        if (rec.cycle >= PERIOD) {
          rec.cycle -= PERIOD;
          repDone();
        }
        if (rec) {
          const peak = rec.ex.target * (1 + 0.04 * Math.sin(rec.reps * 1.7));
          rec.angle = peak * (0.5 - 0.5 * Math.cos((2 * Math.PI * rec.cycle) / PERIOD));
        }
      }
      if (rec) rec.reached = rec.angle >= rec.ex.target * 0.9;
    }
    if (!rec) return;
    draw();
    updateHud();
    rafId = requestAnimationFrame(loop);
  }

  function updateHud() {
    const ex = rec.ex;
    $('r-side').textContent = cap(rec.side) + ' leg';
    $('r-set').textContent = rec.set + ' of ' + ex.sets;
    $('r-time').textContent = mmss(Math.round(rec.elapsed));
    $('r-angle').textContent = Math.round(rec.angle) + '°';
    $('r-state').textContent = rec.reached ? 'Target reached' : 'Keep moving';
    $('r-reps').textContent = 'Rep ' + rec.reps + ' / ' + ex.reps;
    $('r-fill').style.width = (rec.reps / ex.reps) * 100 + '%';
    $('r-bar').setAttribute('aria-valuemax', String(ex.reps));
    $('r-bar').setAttribute('aria-valuenow', String(rec.reps));
    const isLive = rec.source === 'live';
    $('r-source').textContent = isLive ? 'LIVE STATION DATA' : 'SIMULATED DATA';
    $('r-source').className = 'badge ' + (isLive ? 'ok' : 'warn');
  }

  // Digital twin: draws ONLY the active leg (left or right).
  function pose(deg) {
    const dir = rec.side === 'left' ? 1 : -1;
    const hip = { x: dir > 0 ? 80 : 520, y: 270 };
    const th = 130, sh = 120, ft = 40;
    const r = (deg * Math.PI) / 180;
    const unit = (a) => ({ x: dir * Math.cos(a), y: -Math.sin(a) });
    const perp = (d) => ({ x: dir * d.y, y: -dir * d.x });
    const add = (p, d, l) => ({ x: p.x + d.x * l, y: p.y + d.y * l });
    const flat = { x: dir, y: 0 };
    let knee, ankle, toe;
    if (rec.ex.key === 'straight_leg_raise') {
      const d = unit(r);
      knee = add(hip, d, th);
      ankle = add(knee, d, sh);
      toe = add(ankle, perp(d), ft);
    } else if (rec.ex.key === 'prone_leg_flexion') {
      knee = add(hip, flat, th);
      const d = unit(r);
      ankle = add(knee, d, sh);
      toe = add(ankle, perp(d), ft);
    } else {
      knee = add(hip, flat, th);
      ankle = add(knee, flat, sh);
      const p = perp(flat);
      const fd = { x: p.x * Math.cos(r) + flat.x * Math.sin(r), y: p.y * Math.cos(r) + flat.y * Math.sin(r) };
      toe = add(ankle, fd, ft);
    }
    return { hip, knee, ankle, toe };
  }
  function seg(a, b, color, w) {
    return "<line x1='" + a.x + "' y1='" + a.y + "' x2='" + b.x + "' y2='" + b.y +
      "' stroke='" + color + "' stroke-width='" + w + "' stroke-linecap='round'/>";
  }
  function draw() {
    const g = pose(rec.ex.target);
    const p = pose(rec.angle);
    const col = rec.reached ? '#2e7d4f' : '#f2b632';
    let h = "<rect x='20' y='292' width='560' height='10' rx='5' fill='#bddcce'/>";
    h += seg(g.hip, g.knee, '#bddcce', 8) + seg(g.knee, g.ankle, '#bddcce', 8) + seg(g.ankle, g.toe, '#bddcce', 8);
    h += seg(p.hip, p.knee, '#0f4c3a', 12) + seg(p.knee, p.ankle, '#0f4c3a', 12) + seg(p.ankle, p.toe, '#0f4c3a', 8);
    const joints = [['hip', p.hip], ['knee', p.knee], ['ankle', p.ankle]];
    for (const [n, j] of joints) {
      h += "<circle cx='" + j.x + "' cy='" + j.y + "' r='14' fill='#fff'/>" +
        "<circle cx='" + j.x + "' cy='" + j.y + "' r='10' fill='" + col + "'/>" +
        "<text x='" + j.x + "' y='" + (j.y + 30) + "' text-anchor='middle' font-size='13' fill='#5e7a6f'>" + n + '</text>';
    }
    $('twin').innerHTML = h;
  }

  // ---------------------------------------------------------- 5. prompts
  function modal(opts) {
    return new Promise((resolve) => {
      $('m-title').textContent = opts.title;
      $('m-body').textContent = opts.body;
      $('m-ok').textContent = opts.ok;
      const c = $('m-cancel');
      c.hidden = !opts.cancel;
      if (opts.cancel) c.textContent = opts.cancel;
      const overlay = $('modal');
      overlay.hidden = false;
      $('m-ok').focus();
      const close = (v) => {
        overlay.hidden = true;
        $('m-ok').onclick = null;
        c.onclick = null;
        resolve(v);
      };
      $('m-ok').onclick = () => close(true);
      c.onclick = () => close(false);
    });
  }

  async function setComplete() {
    const r = rec;
    const ex = r.ex;
    const last = r.set >= ex.sets;
    const isFinal = last && r.side === 'right';
    r.prompting = true;
    r.setsDone += 1;
    if (isFinal) {
      finish(true);
      return;
    }
    await modal(
      last
        ? { title: cap(r.side) + ' Leg Complete!', body: 'Rest, then switch to your right leg.', ok: 'Start Right Leg' }
        : {
            title: 'Set ' + r.set + ' Complete!',
            body: ex.reps + ' / ' + ex.reps + ' reps on the ' + r.side + ' leg. Rest before beginning your next set.',
            ok: 'Start Set ' + (r.set + 1),
          }
    );
    if (rec !== r) return;
    if (last) {
      r.side = 'right';
      r.set = 1;
      setPreview();
    } else {
      r.set += 1;
    }
    r.reps = 0;
    r.cycle = 0;
    r.up = false;
    r.prompting = false;
    lastT = performance.now();
  }

  $('btn-pause').addEventListener('click', () => {
    if (!rec || rec.prompting) return;
    rec.paused = !rec.paused;
    $('btn-pause').textContent = rec.paused ? 'Resume' : 'Pause';
    lastT = performance.now();
  });

  $('btn-end').addEventListener('click', async () => {
    if (!rec || rec.prompting) return;
    const r = rec;
    const was = r.paused;
    r.paused = true;
    const ok = await modal({
      title: 'End session?',
      body: 'Your progress will be saved, but this exercise will stay marked as not done.',
      ok: 'End session',
      cancel: 'Keep going',
    });
    if (rec !== r) return;
    if (ok) finish(false);
    else r.paused = was;
  });

  // ---------------------------------------------------------- 6. session complete
  function finish(completed) {
    const r = rec;
    cancelAnimationFrame(rafId);
    rec = null;
    const record = {
      id: 'pdb-' + Date.now(),
      patientId: state.patientId,
      exerciseKey: r.ex.key,
      exerciseName: r.ex.name,
      setsCompleted: r.setsDone,
      setsTotal: r.ex.sets * 2,
      totalReps: r.total,
      repsTotal: r.ex.reps * r.ex.sets * 2,
      durationSeconds: Math.round(r.elapsed),
      recordedAt: new Date().toISOString(),
      completed,
      synced: false,
    };
    state.sessions.unshift(record);
    save();
    updateTop();
    $('t-done').textContent = completed ? 'Session Complete!' : 'Session Ended Early';
    $('d-icon').textContent = completed ? '✓' : '!';
    $('d-icon').className = 'big-icon' + (completed ? '' : ' warn');
    $('d-sets').textContent = record.setsCompleted + ' / ' + record.setsTotal + ' sets';
    $('d-reps').textContent = record.totalReps + ' / ' + record.repsTotal + ' reps';
    $('d-dur').textContent = mmss(record.durationSeconds);
    show('done');
  }
  $('btn-finish').addEventListener('click', () => {
    renderList();
    show('list');
  });

  // ---------------------------------------------------------- 7. sync status
  async function stationStatus() {
    try {
      const r = await fetch('/api/status');
      if (!r.ok) return 'unknown';
      const b = await r.json();
      return b.backend_online ? 'online' : 'offline';
    } catch (e) {
      return 'station not reachable';
    }
  }

  async function renderSync() {
    const p = pending();
    const all = p.length === 0;
    $('y-icon').textContent = all ? '✓' : '!';
    $('y-icon').className = 'big-icon' + (all ? '' : ' warn');
    $('y-title').textContent = all ? 'All sessions synced' : p.length + ' session(s) waiting to sync';
    $('y-last').textContent = state.lastSynced
      ? 'Last synced: ' + dateText(new Date(state.lastSynced)) + ', ' + clock(new Date(state.lastSynced))
      : 'Not synced yet';
    const all_btn = $('btn-sync-all');
    all_btn.hidden = all;
    all_btn.disabled = state.syncing;
    all_btn.textContent = state.syncing ? 'Syncing...' : 'Sync all';
    const ul = $('y-list');
    ul.replaceChildren();
    if (all) {
      const li = document.createElement('li');
      li.className = 'muted';
      li.textContent = 'Nothing pending.';
      ul.append(li);
    }
    for (const s of p) {
      const li = document.createElement('li');
      const body = document.createElement('div');
      body.className = 'grow';
      const b = document.createElement('b');
      b.textContent = s.exerciseName;
      const small = document.createElement('small');
      small.textContent = s.setsCompleted + ' sets · ' + s.totalReps + ' reps · ' + mmss(s.durationSeconds);
      body.append(b, small);
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn small';
      btn.textContent = 'Sync';
      btn.disabled = state.syncing;
      btn.addEventListener('click', () => doSync([s.id]));
      li.append(body, btn);
      ul.append(li);
    }
    $('y-station').textContent = 'Station backend: ' + (await stationStatus());
  }

  // Simulated upload: no data is sent anywhere in this build.
  async function doSync(ids) {
    if (state.syncing) return;
    state.syncing = true;
    renderSync();
    await new Promise((r) => setTimeout(r, ids ? 800 : 1200));
    for (const s of state.sessions) {
      if (!ids || ids.includes(s.id)) s.synced = true;
    }
    state.lastSynced = new Date().toISOString();
    state.syncing = false;
    save();
    updateTop();
    renderSync();
  }

  $('btn-sync-top').addEventListener('click', () => {
    if (current === 'rec' || current === 'sync') return;
    syncBack = current;
    renderSync();
    show('sync');
  });
  $('sync-back').addEventListener('click', () => {
    if (syncBack === 'list') renderList();
    show(syncBack === 'rec' ? 'list' : syncBack);
  });
  $('btn-sync-all').addEventListener('click', () => doSync(null));

  // ---------------------------------------------------------- live station link
  function connect() {
    const ws = new WebSocket((location.protocol === 'https:' ? 'wss' : 'ws') + '://' + location.host + '/ws/state');
    ws.onmessage = (e) => {
      try { live.joints = JSON.parse(e.data).joints || null; } catch (_) { /* ignore */ }
    };
    ws.onclose = () => {
      live.joints = null;
      setTimeout(connect, 2000);
    };
    ws.onerror = () => ws.close();
  }
  if (LIVE) {
    $('mode').textContent = 'Station live (hip/knee exercises)';
    $('mode').className = 'badge ok';
    connect();
  }

  updateTop();
  show('patient');
  $('in-patient').focus();
})();
