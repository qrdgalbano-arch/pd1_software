// Design B working prototype: talks to the real station API (no simulation).
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);

  // The prescription has no 'sets' field, so sets per leg is set here.
  // Each set is one real station session (one prescription, one leg).
  const SETS_PER_SIDE = 3;
  const ORDER = ['straight_leg_raising', 'prone_leg_flexion', 'ankle_pump'];
  const SCREENS = ['patient', 'list', 'instr', 'rec', 'done', 'sync'];

  const S = {
    patient: null,
    prescriptions: {},
    exercises: {},
    sessions: [],
    latest: null,
    connected: false,
    flow: null,
    avatar: null,
    avatarLoading: false,
    voice: true,
    lastPromptKey: '',
    cameraFailed: false,
  };
  let current = 'patient';
  let syncBack = 'list';

  // ---------------------------------------------------------- helpers
  const pad = (n) => String(n).padStart(2, '0');
  const mmss = (s) => {
    const t = Math.max(0, Math.floor(Number(s) || 0));
    return pad(Math.floor(t / 60)) + ':' + pad(t % 60);
  };
  const cap = (s) => String(s || '').charAt(0).toUpperCase() + String(s || '').slice(1);
  const titleCase = (v) => String(v || '').split('_').map(cap).join(' ');
  const clock = (d) => {
    const h = d.getHours() % 12 || 12;
    return h + ':' + pad(d.getMinutes()) + ' ' + (d.getHours() >= 12 ? 'PM' : 'AM');
  };
  const dateText = (d) =>
    d.toLocaleDateString(undefined, { weekday: 'long', month: 'numeric', day: 'numeric', year: '2-digit' });
  const deg = (v) => (typeof v === 'number' && Number.isFinite(v) ? Math.round(v) + '°' : '—');
  const exName = (k) => (S.exercises[k] && S.exercises[k].display_name) || titleCase(k);

  async function api(path, options) {
    const opts = options || {};
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 15000);
    try {
      const r = await fetch(path, {
        ...opts,
        headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
        signal: c.signal,
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        throw new Error(typeof body.detail === 'string' ? body.detail : r.status + ' ' + r.statusText);
      }
      return body;
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('The station took too long to respond.');
      throw e;
    } finally {
      clearTimeout(t);
    }
  }

  function notice(msg, level) {
    const el = $('notice');
    el.textContent = msg || '';
    el.className = 'notice ' + (level || 'info');
    el.hidden = !msg;
  }

  function speak(text) {
    if (!S.voice || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.9;
    window.speechSynthesis.speak(u);
  }

  function coaching(text, level) {
    const lv = ['info', 'success', 'warning', 'error'].includes(level) ? level : 'info';
    $('prompt').className = 'prompt ' + lv;
    $('prompt-symbol').textContent = { success: '✓', warning: '!', error: '!', info: '●' }[lv];
    if ($('prompt-text').textContent !== text) $('prompt-text').textContent = text;
  }

  function show(name) {
    current = name;
    for (const s of SCREENS) $('s-' + s).hidden = s !== name;
    $('who').hidden = !S.patient;
    $('btn-sync-top').hidden = !S.patient;
    if (name === 'rec') {
      S.cameraFailed = false;
      $('camera').src = '/video.mjpg?view=' + Date.now();
      initAvatar();
    } else {
      $('camera').removeAttribute('src');
    }
    const h = document.querySelector('#s-' + name + ' h1');
    if (h) h.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }

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

  // ---------------------------------------------------------- 3D digital twin (avatar.js)
  async function initAvatar() {
    if (S.avatar) {
      S.avatar.resize();
      return;
    }
    if (S.avatarLoading) return;
    S.avatarLoading = true;
    try {
      const mod = await import('/static/avatar.js');
      const a = new mod.TwinAvatar($('avatar'));
      await a.load();
      a.resize();
      a.setTheme(false);
      S.avatar = a;
      $('avatar-error').hidden = true;
    } catch (e) {
      $('avatar-error').hidden = false;
      console.warn('PD1 avatar:', e);
    } finally {
      S.avatarLoading = false;
    }
  }

  // ---------------------------------------------------------- station data
  async function loadExercises() {
    try {
      S.exercises = await api('/api/exercises');
    } catch (e) {
      S.exercises = {};
    }
  }
  async function refreshSessions() {
    try {
      S.sessions = await api('/api/sessions?limit=200');
    } catch (e) {
      /* keep previous list */
    }
  }

  // Progress today for this patient, from the station's saved sessions.
  function progress(key) {
    const out = { left: 0, right: 0 };
    const today = new Date().toDateString();
    for (const s of S.sessions) {
      if (String(s.patient_id) !== String(S.patient.id)) continue;
      if (s.exercise_key !== key || s.status !== 'completed') continue;
      if (new Date(s.device_recorded_at).toDateString() !== today) continue;
      if (out[s.affected_side] !== undefined) out[s.affected_side] += 1;
    }
    return out;
  }
  function isDone(key) {
    const p = progress(key);
    return p.left >= SETS_PER_SIDE && p.right >= SETS_PER_SIDE;
  }
  function doneAt(key) {
    let latest = null;
    const today = new Date().toDateString();
    for (const s of S.sessions) {
      if (String(s.patient_id) !== String(S.patient.id)) continue;
      if (s.exercise_key !== key || s.status !== 'completed') continue;
      const d = new Date(s.device_recorded_at);
      if (d.toDateString() !== today) continue;
      if (!latest || d > latest) latest = d;
    }
    return latest;
  }
  function nextKey() {
    for (const k of ORDER) {
      if (!S.prescriptions[k]) continue;
      if (!isDone(k)) return k;
    }
    return null;
  }

  // ---------------------------------------------------------- 1. patient ID
  $('f-patient').addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = $('err-patient');
    err.hidden = true;
    const id = $('in-patient').value.trim();
    if (!/^[0-9]+$/.test(id)) {
      err.textContent = 'Enter your numeric Patient ID.';
      err.hidden = false;
      return;
    }
    $('btn-patient').disabled = true;
    try {
      const data = await api('/api/patients');
      const p = (data.patients || []).find((x) => String(x.id) === id);
      if (!p) {
        err.textContent = 'Patient ID not found on this station.';
        err.hidden = false;
        return;
      }
      const pr = await api('/api/patients/' + encodeURIComponent(id) + '/prescriptions');
      S.prescriptions = {};
      for (const item of pr.prescriptions || []) {
        if (!S.prescriptions[item.exercise_key]) S.prescriptions[item.exercise_key] = item;
      }
      S.patient = p;
      const cached = data.source === 'cache' || pr.source === 'cache';
      notice(cached ? 'Backend unavailable. Using the station cached patients and prescriptions.' : '', 'warn');
      await refreshSessions();
      updateWho();
      renderList();
      show('list');
    } catch (ex) {
      err.textContent = 'Cannot load this patient: ' + ex.message;
      err.hidden = false;
    } finally {
      $('btn-patient').disabled = false;
    }
  });

  function updateWho() {
    if (!S.patient) return;
    $('who').textContent = (S.patient.full_name || 'Patient') + ' (ID ' + S.patient.id + ')';
  }

  // ---------------------------------------------------------- 2. exercise list
  function renderList() {
    $('t-list').textContent = dateText(new Date());
    $('list-sub').textContent = (S.patient.full_name || 'Patient') + ' - ID ' + S.patient.id;
    const next = nextKey();
    const ol = $('list');
    ol.replaceChildren();
    ORDER.forEach((key, i) => {
      const p = S.prescriptions[key];
      const done = p && isDone(key);
      const active = key === next;
      const prog = progress(key);
      const li = document.createElement('li');
      li.className = 'item' + (!p || (!done && !active) ? ' locked' : '') + (active ? ' active' : '');
      const num = document.createElement('span');
      num.className = 'num';
      num.textContent = String(i + 1);
      const body = document.createElement('div');
      body.className = 'grow';
      const b = document.createElement('b');
      b.textContent = exName(key);
      const small = document.createElement('small');
      if (!p) {
        small.textContent = 'Not prescribed. Ask staff to prescribe it.';
      } else {
        let t = SETS_PER_SIDE + ' sets × ' + p.repetitions_target + ' reps per leg';
        if (!done && (prog.left > 0 || prog.right > 0)) {
          t += ' - progress: left ' + Math.min(prog.left, SETS_PER_SIDE) + '/' + SETS_PER_SIDE +
            ', right ' + Math.min(prog.right, SETS_PER_SIDE) + '/' + SETS_PER_SIDE;
        }
        if (!done && !active) t += ' - Locked: finish the previous exercise first';
        small.textContent = t;
      }
      body.append(b, small);
      li.append(num, body);
      if (done) {
        const s = document.createElement('span');
        s.className = 'done';
        const d = doneAt(key);
        s.textContent = '✓ ' + (d ? clock(d) : '');
        li.append(s);
      } else if (active) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn primary small';
        btn.textContent = 'Record';
        btn.setAttribute('aria-label', 'Record ' + exName(key));
        btn.addEventListener('click', () => openInstr(key));
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
    $('list-done').hidden = next !== null || !ORDER.some((k) => S.prescriptions[k]);
  }

  // ---------------------------------------------------------- 3. instructions
  function openInstr(key) {
    const p = S.prescriptions[key];
    const cfg = S.exercises[key] || {};
    $('t-instr').textContent = exName(key);
    $('i-presc').textContent = SETS_PER_SIDE + ' Sets × ' + p.repetitions_target + ' Reps';
    $('i-time').textContent = mmss(p.duration_limit_seconds);
    $('i-freq').textContent = p.frequency || 'Daily';
    $('i-view').textContent = cfg.camera_view || '';
    $('i-steps').replaceChildren(
      ...(cfg.instructions || []).map((t) => {
        const li = document.createElement('li');
        li.textContent = t;
        return li;
      })
    );
    $('btn-start').onclick = () => beginExercise(key);
    show('instr');
  }
  $('instr-back').addEventListener('click', () => show('list'));

  // ---------------------------------------------------------- 4. recording (real sessions)
  function beginExercise(key) {
    const p = S.prescriptions[key];
    const prog = progress(key);
    const f = {
      key, p, side: 'left', set: 1, results: [],
      sessionId: null, handling: false, userEnded: false,
    };
    if (prog.left < SETS_PER_SIDE) {
      f.side = 'left';
      f.set = prog.left + 1;
    } else {
      f.side = 'right';
      f.set = prog.right + 1;
    }
    S.flow = f;
    startSet(true);
  }

  async function startSet(first) {
    const f = S.flow;
    f.handling = false;
    f.userEnded = false;
    S.lastPromptKey = '';
    try {
      const r = await api('/api/session/start', {
        method: 'POST',
        body: JSON.stringify({
          patient_id: Number(S.patient.id),
          prescription_id: Number(f.p.id),
          side: f.side,
        }),
      });
      f.sessionId = r.client_session_id;
      notice('');
      coaching('Hold still in the starting position.', 'info');
      show('rec');
      if (S.latest) renderRec(S.latest);
    } catch (e) {
      notice('Cannot start the set: ' + e.message, 'error');
      if (first) {
        S.flow = null;
        show('instr');
      } else {
        await refreshSessions();
        renderList();
        S.flow = null;
        show('list');
      }
    }
  }

  function renderRec(s) {
    const f = S.flow;
    if (!f) return;
    const ex = s.exercise;
    const sess = s.session;
    const ev = s.evaluation;
    const cfg = S.exercises[f.key] || {};
    $('t-rec').textContent = ex.name;
    $('r-side').textContent = cap(f.side) + ' leg';
    $('r-leg').textContent = cap(f.side) + ' leg';
    $('r-set').textContent = f.set + ' of ' + SETS_PER_SIDE;
    $('r-phase').textContent = titleCase(s.phase);

    const target = sess ? Number(sess.repetitions_target) || 0 : Number(f.p.repetitions_target) || 0;
    const valid = Number(ev && ev.valid) || 0;
    $('r-reps').textContent = 'Valid reps ' + Math.min(valid, target) + ' / ' + target;
    $('r-fill').style.width = (target ? Math.min(100, (valid / target) * 100) : 0) + '%';
    $('r-bar').setAttribute('aria-valuemax', String(target || 1));
    $('r-bar').setAttribute('aria-valuenow', String(Math.min(valid, target || 1)));
    $('r-time').textContent = sess ? mmss(sess.duration_limit_seconds - sess.elapsed_seconds) : '--:--';

    const paused = s.phase === 'paused';
    $('btn-pause').textContent = paused ? 'Resume' : 'Pause';
    $('btn-pause').disabled = !sess;
    $('btn-stop').disabled = !sess;

    const camMsg = s.camera_error
      ? 'Camera unavailable: ' + s.camera_error + '. Stop moving and ask staff to check the camera.'
      : S.cameraFailed
        ? 'Camera preview unavailable. Ask staff to check the station camera.'
        : '';
    $('camera-error').hidden = !camMsg;
    $('camera-error').textContent = camMsg;

    if (paused) {
      coaching('Set paused. Rest, then select Resume.', 'warning');
    } else if (camMsg) {
      coaching('Camera unavailable. Stop moving and ask staff for help.', 'error');
    } else if (ev && ev.prompt) {
      const key = f.sessionId + ':' + ev.prompt.seq;
      coaching(ev.prompt.text, ev.prompt.level);
      if (S.lastPromptKey !== key) {
        S.lastPromptKey = key;
        speak(ev.prompt.text);
      }
    }

    const joints = s.joints;
    const active = new Set((ev && ev.active_deviations) || []);
    const devJoints = new Set(
      (cfg.deviations || []).filter((d) => active.has(d.id)).map((d) => d.joint)
    );
    const statuses = {};
    for (const [name, j] of Object.entries(joints)) {
      statuses[name] = !j.tracked ? 'lost' : devJoints.has(name) ? 'deviation' : 'ok';
    }
    $('joint-chips').replaceChildren(
      ...['hip', 'knee', 'ankle'].map((name) => {
        const j = joints[name];
        const span = document.createElement('span');
        span.className = 'jchip ' + (statuses[name] || 'lost');
        span.textContent = titleCase(name);
        const b = document.createElement('b');
        b.textContent = j && j.tracked ? deg(j.angle) : 'Lost';
        span.append(b);
        return span;
      })
    );
    const primary = joints[ex.primary_joint];
    const rom = ex.rom_standard_deg || [];
    $('r-angle').textContent =
      titleCase(ex.primary_joint) + ' angle: ' + (primary && primary.tracked ? deg(primary.angle) : 'not tracked') +
      ' - reference ROM ' + (rom[0] != null ? rom[0] : '-') + ' to ' + (rom[1] != null ? rom[1] : '-') + '°';

    if (S.avatar) {
      S.avatar.update(
        Object.fromEntries(
          Object.entries(joints).map(([n, j]) => [n, j.tracked ? j.angle : null])
        ),
        statuses,
        s.exercise,
        s.side
      );
    }
  }

  $('camera').addEventListener('error', () => {
    if (current !== 'rec') return;
    S.cameraFailed = true;
    if (S.latest) renderRec(S.latest);
  });

  $('btn-pause').addEventListener('click', async () => {
    const s = S.latest;
    if (!s || !s.session) return;
    const resume = s.phase === 'paused';
    try {
      await api('/api/session/' + (resume ? 'resume' : 'pause'), { method: 'POST' });
      if (!resume && 'speechSynthesis' in window) window.speechSynthesis.cancel();
    } catch (e) {
      notice('Cannot ' + (resume ? 'resume' : 'pause') + ': ' + e.message, 'error');
    }
  });

  $('btn-stop').addEventListener('click', async () => {
    const f = S.flow;
    if (!f || !S.latest || !S.latest.session) return;
    const ok = await modal({
      title: 'End session?',
      body: 'Your progress for this set is saved, but this exercise stays marked as not done.',
      ok: 'End session',
      cancel: 'Keep going',
    });
    if (!ok) return;
    f.userEnded = true;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    try {
      const sum = await api('/api/session/stop', { method: 'POST' });
      handleEnd(sum);
    } catch (e) {
      if (S.latest && S.latest.session) {
        f.userEnded = false;
        notice('Cannot stop: ' + e.message, 'error');
      }
    }
  });

  $('btn-stop-stray').addEventListener('click', async () => {
    try {
      await api('/api/session/stop', { method: 'POST' });
      notice('');
    } catch (e) {
      notice('Cannot stop the running session: ' + e.message, 'error');
    }
  });

  // ---------------------------------------------------------- 5. set / leg prompts
  function handleEnd(sum) {
    const f = S.flow;
    if (!f || f.handling) return;
    f.handling = true;
    onSetEnded(sum);
  }

  async function onSetEnded(sum) {
    const f = S.flow;
    f.results.push(sum);
    await refreshSessions();
    if (f.userEnded) {
      finishExercise();
      return;
    }
    if (sum.status === 'completed') {
      const last = f.set >= SETS_PER_SIDE;
      const isFinal = last && f.side === 'right';
      if (isFinal) {
        finishExercise();
        return;
      }
      await modal(
        last
          ? {
              title: cap(f.side) + ' Leg Complete!',
              body: sum.valid_repetitions + ' valid reps. Rest, then switch to your right leg.',
              ok: 'Start Right Leg',
            }
          : {
              title: 'Set ' + f.set + ' Complete!',
              body: sum.valid_repetitions + ' valid reps on the ' + f.side + ' leg. Rest before beginning your next set.',
              ok: 'Start Set ' + (f.set + 1),
            }
      );
      if (S.flow !== f) return;
      if (last) {
        f.side = 'right';
        f.set = 1;
      } else {
        f.set += 1;
      }
      startSet(false);
    } else {
      const again = await modal({
        title: 'Set ' + f.set + ' not completed',
        body: sum.valid_repetitions + ' of ' + f.p.repetitions_target + ' valid reps before the set ended.',
        ok: 'Repeat this set',
        cancel: 'End exercise',
      });
      if (S.flow !== f) return;
      if (again) startSet(false);
      else finishExercise();
    }
  }

  // ---------------------------------------------------------- 6. session complete
  function finishExercise() {
    const f = S.flow;
    S.flow = null;
    const prog = progress(f.key);
    const complete = isDone(f.key);
    let valid = 0;
    let invalid = 0;
    let duration = 0;
    const lastBySide = {};
    for (const r of f.results) {
      valid += r.valid_repetitions || 0;
      invalid += r.invalid_repetitions || 0;
      duration += r.duration_seconds || 0;
      lastBySide[r.affected_side] = r;
    }
    $('t-done').textContent = complete ? 'Session Complete!' : 'Session Ended Early';
    $('d-icon').textContent = complete ? '✓' : '!';
    $('d-icon').className = 'big-icon' + (complete ? '' : ' warn');
    $('d-sets').textContent =
      Math.min(prog.left, SETS_PER_SIDE) + Math.min(prog.right, SETS_PER_SIDE) + ' / ' + SETS_PER_SIDE * 2 + ' sets';
    $('d-reps').textContent = valid + ' valid, ' + invalid + ' invalid';
    $('d-dur').textContent = mmss(duration);
    $('d-rom').textContent =
      Object.entries(lastBySide)
        .map(([sd, r]) => cap(sd) + ': ' + (r.arom_classification || 'n/a') + (r.peak_rom_degrees != null ? ' (' + deg(r.peak_rom_degrees) + ')' : ''))
        .join('; ') || '—';
    refreshStatus();
    show('done');
  }
  $('btn-finish').addEventListener('click', () => {
    renderList();
    show('list');
  });

  // ---------------------------------------------------------- 7. sync status (real)
  const syncLabel = (v) => ({ synced: 'Synced', pending: 'Pending', failed: 'Failed' }[v] || titleCase(v || 'pending'));

  async function renderSync() {
    const [st, rows] = await Promise.all([
      api('/api/status').catch(() => null),
      api('/api/sessions?limit=200').catch(() => null),
    ]);
    if (current !== 'sync') return;
    const pending = rows ? rows.filter((r) => r.sync_status !== 'synced') : [];
    const all = rows !== null && pending.length === 0;
    $('y-icon').textContent = all ? '✓' : '!';
    $('y-icon').className = 'big-icon' + (all ? '' : ' warn');
    $('y-title').textContent =
      rows === null ? 'Station not reachable' : all ? 'All sessions synced' : pending.length + ' session(s) waiting to sync';
    let line = st ? 'Backend: ' + (st.backend_online ? 'online' : 'offline') : 'Backend status unavailable';
    if (st && st.sync) {
      line += ' - ' + (st.sync.synced || 0) + ' synced, ' + (st.sync.pending || 0) + ' pending, ' + (st.sync.failed || 0) + ' failed';
    }
    if (st && st.last_sync_error) line += ' - last error: ' + st.last_sync_error;
    $('y-station').textContent = line;
    $('btn-sync-all').hidden = all || rows === null;
    const ul = $('y-list');
    ul.replaceChildren();
    if (all) {
      const li = document.createElement('li');
      li.className = 'muted';
      li.textContent = 'Nothing pending.';
      ul.append(li);
    }
    for (const r of pending) {
      const li = document.createElement('li');
      const body = document.createElement('div');
      body.className = 'grow';
      const b = document.createElement('b');
      b.textContent = (r.exercise_name || titleCase(r.exercise_key)) + ' - ' + cap(r.affected_side) + ' leg';
      const small = document.createElement('small');
      small.textContent = r.valid_repetitions + ' valid reps - ' + mmss(r.duration_seconds) +
        (r.sync_status === 'failed' && r.sync_error ? ' - ' + r.sync_error : '');
      body.append(b, small);
      const badge = document.createElement('span');
      badge.className = 'badge ' + (r.sync_status === 'failed' ? 'danger' : 'warn');
      badge.textContent = syncLabel(r.sync_status);
      li.append(body, badge);
      ul.append(li);
    }
  }

  async function syncNow() {
    $('btn-sync-all').disabled = true;
    try {
      await api('/api/sync', { method: 'POST' });
    } catch (e) {
      notice('Sync request failed: ' + e.message, 'error');
    }
    for (let i = 0; i < 5 && current === 'sync'; i += 1) {
      await new Promise((r) => setTimeout(r, 2000));
      await renderSync();
    }
    $('btn-sync-all').disabled = false;
    refreshStatus();
  }

  async function refreshStatus() {
    try {
      const st = await api('/api/status');
      const n = (Number(st.sync && st.sync.pending) || 0) + (Number(st.sync && st.sync.failed) || 0);
      $('pending-count').textContent = String(n);
    } catch (e) {
      /* station unreachable */
    }
  }

  $('btn-sync-top').addEventListener('click', () => {
    if (current === 'rec' || current === 'sync') return;
    syncBack = current;
    show('sync');
    renderSync();
  });
  $('sync-back').addEventListener('click', () => {
    if (syncBack === 'list' && S.patient) renderList();
    show(syncBack === 'rec' || syncBack === 'sync' ? 'list' : syncBack);
  });
  $('btn-sync-all').addEventListener('click', syncNow);

  // ---------------------------------------------------------- live station link
  function setConn() {
    const el = $('conn');
    el.textContent = S.connected ? 'Station connected' : 'Station disconnected';
    el.className = 'badge ' + (S.connected ? 'ok' : 'danger');
    if (!S.connected && S.flow && current === 'rec') {
      coaching('Connection lost. Stop moving and ask staff to check the station.', 'error');
    }
  }

  function onState(s) {
    if (!s || !s.exercise || !s.joints) return;
    S.latest = s;
    const f = S.flow;
    const stray = Boolean(s.session) && !(f && f.sessionId === s.session.client_session_id);
    $('btn-stop-stray').hidden = !stray;
    if (
      f && f.sessionId && !s.session && s.last_summary &&
      s.last_summary.client_session_id === f.sessionId
    ) {
      handleEnd(s.last_summary);
    }
    if (current === 'rec') renderRec(s);
  }

  function connectSocket() {
    const ws = new WebSocket((location.protocol === 'https:' ? 'wss' : 'ws') + '://' + location.host + '/ws/state');
    ws.onopen = () => {
      S.connected = true;
      setConn();
    };
    ws.onmessage = (e) => {
      try {
        onState(JSON.parse(e.data));
      } catch (err) {
        console.warn('PD1 state:', err);
      }
    };
    ws.onclose = () => {
      S.connected = false;
      setConn();
      setTimeout(connectSocket, 2000);
    };
    ws.onerror = () => ws.close();
  }

  $('btn-voice').addEventListener('click', () => {
    S.voice = !S.voice;
    $('btn-voice').textContent = S.voice ? 'Voice on' : 'Voice off';
    $('btn-voice').setAttribute('aria-pressed', String(S.voice));
    if (!S.voice && 'speechSynthesis' in window) window.speechSynthesis.cancel();
  });

  // ---------------------------------------------------------- start
  loadExercises();
  connectSocket();
  refreshStatus();
  setInterval(refreshStatus, 5000);
  show('patient');
  $('in-patient').focus();
})();
