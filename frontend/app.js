'use strict';
/* Dating Coach AI — web beta frontend. Vanilla JS, no build step. */

/* ================= helpers ================= */
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));
const LS_TOKEN = 'dca_token';

const state = {
  user: null,
  coaches: [],
  locked: [],
  dates: [],
  tab: 'practice'
};

function toast(msg, isErr) {
  const root = $('#toast-root');
  const el = document.createElement('div');
  el.className = 'toast' + (isErr ? ' error' : '');
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 2800);
  setTimeout(() => el.remove(), 3300);
}

function fmtTime(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  } catch (e) { return ''; }
}

function fmtVal(v) {
  if (v == null) return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(1);
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return String(v);
}

function prettyKey(k) {
  return String(k).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ================= API client ================= */
function token() { return localStorage.getItem(LS_TOKEN); }

function logout() {
  localStorage.removeItem(LS_TOKEN);
  state.user = null; state.coaches = []; state.dates = [];
  showView('auth');
}

async function api(path, opts) {
  opts = opts || {};
  const headers = { 'Content-Type': 'application/json' };
  if (token()) headers['Authorization'] = 'Bearer ' + token();
  const res = await fetch('/api' + path, {
    method: opts.method || 'GET',
    headers: headers,
    body: opts.body
  });
  if (res.status === 401) {
    logout();
    throw new Error('Signed out — log back in.');
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  if (!res.ok) {
    const msg = (data && (data.detail || data.error || data.message)) || ('Request failed (' + res.status + ')');
    throw new Error(msg);
  }
  return data || {};
}

/* ================= SSE streaming ================= */
async function streamSSE(path, body, cbs) {
  cbs = cbs || {};
  const headers = { 'Content-Type': 'application/json' };
  if (token()) headers['Authorization'] = 'Bearer ' + token();
  const ctrl = new AbortController();
  if (cbs.onController) cbs.onController(ctrl);
  const res = await fetch('/api' + path, {
    method: 'POST', headers: headers, body: JSON.stringify(body), signal: ctrl.signal
  });
  if (res.status === 401) { logout(); throw new Error('Signed out — log back in.'); }
  if (!res.ok) {
    let m = 'Request failed (' + res.status + ')';
    try { const d = await res.json(); m = d.detail || d.error || d.message || m; } catch (e) {}
    throw new Error(m);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  let sawDone = false;
  try {
    for (;;) {
      const step = await reader.read();
      if (step.done) break;
      buf += dec.decode(step.value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (line.slice(0, 5) !== 'data:') continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === '[DONE]') continue;
        try {
          const obj = JSON.parse(payload);
          if (obj.done) { sawDone = true; if (cbs.onDone) cbs.onDone(obj); }
          else if (typeof obj.delta === 'string' && obj.delta) { if (cbs.onDelta) cbs.onDelta(obj.delta); }
          else if (typeof obj.text === 'string' && obj.text) { if (cbs.onDelta) cbs.onDelta(obj.text); }
        } catch (e) { /* partial chunk */ }
      }
    }
  } catch (e) {
    if (e && e.name === 'AbortError') {
      if (cbs.onAbort) cbs.onAbort();
    } else { throw e; }
  } finally {
    try { reader.releaseLock(); } catch (e) {}
  }
  // process any trailing line without a newline terminator
  const tail = buf.trim();
  if (tail.slice(0, 5) === 'data:') {
    try {
      const obj = JSON.parse(tail.slice(5).trim());
      if (obj.done) { sawDone = true; if (cbs.onDone) cbs.onDone(obj); }
      else if (typeof obj.delta === 'string' && obj.delta) { if (cbs.onDelta) cbs.onDelta(obj.delta); }
    } catch (e) {}
  }
  if (!sawDone && cbs.onEnd) cbs.onEnd();
}

/* ================= tiny markdown ================= */
function md(src) {
  const lines = esc(src || '').split('\n');
  let html = '', inUl = false, inOl = false;
  const close = () => {
    if (inUl) { html += '</ul>'; inUl = false; }
    if (inOl) { html += '</ol>'; inOl = false; }
  };
  const inline = (t) => t
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|\W)\*([^*\n]+?)\*/g, '$1<em>$2</em>');
  lines.forEach((raw) => {
    const line = raw.trim();
    let m;
    if ((m = line.match(/^###\s+(.*)/))) { close(); html += '<h3>' + inline(m[1]) + '</h3>'; }
    else if ((m = line.match(/^##\s+(.*)/))) { close(); html += '<h2>' + inline(m[1]) + '</h2>'; }
    else if ((m = line.match(/^#\s+(.*)/))) { close(); html += '<h1>' + inline(m[1]) + '</h1>'; }
    else if ((m = line.match(/^&gt;\s?(.*)/))) { close(); html += '<blockquote>' + inline(m[1]) + '</blockquote>'; }
    else if ((m = line.match(/^[-*•]\s+(.*)/))) {
      if (inOl) { html += '</ol>'; inOl = false; }
      if (!inUl) { html += '<ul>'; inUl = true; }
      html += '<li>' + inline(m[1]) + '</li>';
    }
    else if ((m = line.match(/^\d+[.)]\s+(.*)/))) {
      if (inUl) { html += '</ul>'; inUl = false; }
      if (!inOl) { html += '<ol>'; inOl = true; }
      html += '<li>' + inline(m[1]) + '</li>';
    }
    else if (line === '') { close(); }
    else { close(); html += '<p>' + inline(line) + '</p>'; }
  });
  close();
  return html || '<p class="muted">—</p>';
}

/* ================= portraits (graceful fallback) ================= */
function portraitHTML(src, name, cls) {
  const nm = String(name || '?').trim();
  const initials = esc((nm.split(/\s+/).map((w) => w[0]).join('').slice(0, 2) || '?').toUpperCase());
  const img = src
    ? '<img src="' + esc(src) + '" alt="' + esc(nm) + '" loading="lazy" onerror="this.remove()">'
    : '';
  return '<div class="portrait ' + (cls || '') + '">' + img +
    '<span class="portrait-fallback">' + initials + '</span></div>';
}

/* ================= modal ================= */
function openModal(html) {
  const root = $('#modal-root');
  root.innerHTML = '<div class="modal-overlay"><div class="modal" role="dialog" aria-modal="true">' + html + '</div></div>';
  const ov = root.firstElementChild;
  ov.addEventListener('click', (e) => { if (e.target === ov) closeModal(); });
}
function closeModal() { $('#modal-root').innerHTML = ''; }

/* ================= THEME (dark-first, 2026 apps have a toggle) ================= */
const THEME_SVGS = {
  dark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
  light: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
};

function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

function paintThemeBtn() {
  const btn = $('#btn-theme');
  if (!btn) return;
  // show the icon of what you'll switch TO
  btn.innerHTML = currentTheme() === 'dark' ? THEME_SVGS.light : THEME_SVGS.dark;
  btn.setAttribute('aria-label', currentTheme() === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
}

function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem('dca_theme', t); } catch (e) {}
  const m = $('#meta-theme');
  if (m) m.setAttribute('content', t === 'light' ? '#f4f5f8' : '#0a0c11');
  paintThemeBtn();
}

function initTheme() {
  paintThemeBtn();
  const btn = $('#btn-theme');
  if (btn) btn.addEventListener('click', () => setTheme(currentTheme() === 'dark' ? 'light' : 'dark'));
}

/* ================= router ================= */
function showView(name) {
  $$('.view').forEach((v) => v.classList.remove('active'));
  const el = $('#view-' + name);
  if (el) el.classList.add('active');
  window.scrollTo(0, 0);
}

function setTab(name) {
  state.tab = name;
  $$('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
  $$('#view-main .tab').forEach((t) => t.classList.toggle('active', t.id === 'tab-' + name));
  if (name === 'patterns') loadPatterns();
}

/* ================= chat surface factory =================
   Hard requirements live here:
   - user message echoes INSTANTLY
   - typing indicator while the AI responds
   - token-by-token streaming
   - send button morphs to spinner/stop while busy, reverts after */
const PLANE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/></svg>';

function chatSurface(cfg) {
  const list = $(cfg.list), form = $(cfg.form), input = $(cfg.input), sendBtn = $(cfg.sendBtn);
  let busy = false, ctrl = null;
  sendBtn.innerHTML = PLANE_SVG;

  function setBusy(b) {
    busy = b;
    sendBtn.classList.toggle('is-busy', b);
    sendBtn.setAttribute('aria-label', b ? 'Stop generating' : 'Send');
    sendBtn.title = b ? 'Stop' : 'Send';
    sendBtn.innerHTML = b
      ? '<span class="spinner"></span><span class="stop"></span>'
      : PLANE_SVG;
  }
  function scrollBottom() {
    requestAnimationFrame(() => { list.scrollTop = list.scrollHeight; });
  }
  function aiName() {
    return (typeof cfg.aiName === 'function') ? cfg.aiName() : (cfg.aiName || null);
  }
  function addUser(text) {
    const el = document.createElement('div');
    el.className = 'msg user';
    const b = document.createElement('div');
    b.className = 'bubble';
    b.textContent = text;
    el.appendChild(b);
    list.appendChild(el);
    scrollBottom();
    return el;
  }
  function addAI(text) {
    const el = document.createElement('div');
    el.className = 'msg ai';
    const who = aiName();
    if (who) {
      const w = document.createElement('div');
      w.className = 'who';
      w.textContent = who;
      el.appendChild(w);
    }
    const b = document.createElement('div');
    b.className = 'bubble';
    if (text != null) b.textContent = text;
    el.appendChild(b);
    list.appendChild(el);
    scrollBottom();
    return { el: el, bubble: b };
  }
  function addTyping() {
    const el = document.createElement('div');
    el.className = 'msg ai';
    el.setAttribute('data-typing', '1');
    el.innerHTML = '<div class="bubble typing"><span></span><span></span><span></span></div>';
    list.appendChild(el);
    scrollBottom();
    return el;
  }
  function removeTyping() {
    const t = list.querySelector('[data-typing]');
    if (t) t.remove();
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    if (busy) { if (ctrl) ctrl.abort(); return; } // STOP button
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.focus();
    addUser(text); // instant echo — no waiting on the network
    setBusy(true);
    addTyping();
    let streamed = false, bubble = null;
    const finish = () => { removeTyping(); if (bubble) bubble.classList.remove('streaming'); scrollBottom(); };
    Promise.resolve().then(() => cfg.onSend(text, {
      controller: (c) => { ctrl = c; },
      delta: (chunk) => {
        if (!streamed) {
          streamed = true;
          removeTyping();
          const a = addAI(null);
          bubble = a.bubble;
          bubble.classList.add('streaming');
        }
        bubble.textContent += chunk;
        scrollBottom();
      },
      done: finish,
      abort: () => { removeTyping(); if (bubble) bubble.classList.remove('streaming'); scrollBottom(); }
    })).catch((err) => {
      removeTyping();
      toast((err && err.message) || 'Something went wrong', true);
    }).then(() => { ctrl = null; setBusy(false); });
  });

  return {
    addUser: addUser, addAI: addAI, addTyping: addTyping, removeTyping: removeTyping,
    setBusy: setBusy, scrollBottom: scrollBottom, listEl: list,
    clear: () => { list.innerHTML = ''; },
    isBusy: () => busy
  };
}

let coachSurface = null;
let simSurface = null;

/* ================= AUTH ================= */
let authMode = 'login';

function setAuthMode(mode) {
  authMode = mode;
  $('#tab-login').classList.toggle('active', mode === 'login');
  $('#tab-signup').classList.toggle('active', mode === 'signup');
  $('#field-name').classList.toggle('hidden', mode === 'login');
  $('#btn-auth-submit').textContent = mode === 'signup' ? 'Create account' : 'Log in';
  $('#auth-password').setAttribute('autocomplete', mode === 'signup' ? 'new-password' : 'current-password');
  hideAuthErr();
}

function showAuthErr(msg) {
  const el = $('#auth-error');
  el.textContent = msg;
  el.classList.remove('hidden');
}
function hideAuthErr() { $('#auth-error').classList.add('hidden'); }

function saveSession(r) {
  if (r && r.token) localStorage.setItem(LS_TOKEN, r.token);
  if (r && r.user) state.user = r.user;
}

function initAuth() {
  $('#tab-login').addEventListener('click', () => setAuthMode('login'));
  $('#tab-signup').addEventListener('click', () => setAuthMode('signup'));
  $('#form-auth').addEventListener('submit', (e) => {
    e.preventDefault();
    const email = $('#auth-email').value.trim();
    const password = $('#auth-password').value;
    hideAuthErr();
    if (!email || !password) { showAuthErr('Enter your email and password.'); return; }
    const btn = $('#btn-auth-submit');
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = 'One sec…';
    const run = async () => {
      if (authMode === 'signup') {
        const display_name = $('#auth-name').value.trim();
        const tz = (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone;
        const payload = { email: email, password: password, timezone: tz };
        if (display_name) payload.display_name = display_name;
        saveSession(await api('/auth/signup', { method: 'POST', body: JSON.stringify(payload) }));
      } else {
        saveSession(await api('/auth/login', { method: 'POST', body: JSON.stringify({ email: email, password: password }) }));
      }
      await bootAfterAuth();
    };
    run().catch((err) => showAuthErr(err.message || 'Something went wrong'))
      .then(() => { btn.disabled = false; btn.textContent = label; });
  });
}

async function bootAfterAuth() {
  const me = await api('/me');
  state.user = me.user || me;
  setHearts(state.user.hearts || 0);
  if (!state.user.onboarding_done) {
    showView('onboarding');
    renderOnboarding();
  } else if (!state.user.coach_id) {
    await openPicker(false);
  } else {
    await enterMain('practice');
  }
}

/* ================= ONBOARDING =================
   Deep first-date interview. No timers, no required fields —
   Continue always works; answers save at the end. */
const OB_STEPS = [
  { title: 'The basics', qs: [
    { id: 'display_name', q: 'What should your coach call you?', type: 'text', hint: 'First name is plenty.', ph: 'Your name' },
    { id: 'about_me', q: 'Who are you when you\u2019re not thinking about dating?', type: 'area', hint: 'A few honest sentences — work, life, what fills your week.', ph: 'Tell me about yourself\u2026' },
    { id: 'daily_life', q: 'What does your life look like right now?', type: 'area', hint: 'City, work, routine — the backdrop your dating life plays out against.', ph: 'A snapshot of your week\u2026' }
  ]},
  { title: 'What you want', qs: [
    { id: 'looking_for', q: 'Describe the relationship you\u2019re actually looking for.', type: 'area', hint: 'Not the r\u00e9sum\u00e9 version — the real one.', ph: 'Be honest, nobody\u2019s grading this\u2026' },
    { id: 'ideal_partner', q: 'Paint the picture: your ideal partner on a random Tuesday night.', type: 'area', hint: 'Who are they? What are they like to be around?', ph: 'What does a good Tuesday look like?\u2026' },
    { id: 'celebrity_type', q: 'If your \u201ctype\u201d had a celebrity face, whose would it be?', type: 'text', optional: true, hint: 'Optional — shorthand helps your coach calibrate fast.', ph: 'e.g. \u2026' }
  ]},
  { title: 'Your patterns', qs: [
    { id: 'dating_history', q: 'Give me the honest two-minute version of your dating history.', type: 'area', hint: 'The patterns matter more than the play-by-play.', ph: 'Where have you been with this?\u2026' },
    { id: 'communication_style', q: 'When something bothers you with someone you\u2019re seeing — what do you actually do?', type: 'area', hint: 'Bring it up? Sit on it? Pull away?', ph: 'Your real move, not the ideal one\u2026' },
    { id: 'attachment', q: 'When things get tense or uncertain, what\u2019s your move?', type: 'area', hint: 'Lean in and talk it out — or go quiet and create distance?', ph: '\u2026' }
  ]},
  { title: 'The work', qs: [
    { id: 'dealbreakers', q: 'What are your non-negotiable dealbreakers?', type: 'area', hint: 'The things that end it, no debate.', ph: 'Name them plainly\u2026' },
    { id: 'pattern_to_break', q: 'What\u2019s the one pattern in your dating life you most want to break?', type: 'area', hint: 'Be blunt. Your coach has heard it all.', ph: 'The loop you keep ending up in\u2026' },
    { id: 'goals', q: 'What do you most want to get better at — and anything else your coach should know going in?', type: 'area', hint: 'Skills, blind spots, context. All of it helps.', ph: 'Last one \u2014 lay it out\u2026' }
  ]},
  { title: 'The hard questions', qs: [
    { id: 'dx_crazy', q: 'Be straight: is there anything a little crazy about how you date?', type: 'area', hint: 'No judgment — your coach needs the real material to work with.', ph: 'The pattern you\u2019d never admit on a date\u2026' },
    { id: 'dx_cheated', q: 'Have you ever cheated — or come close? What happened?', type: 'area', hint: 'Yours or theirs. The trust stuff matters.', ph: '\u2026' },
    { id: 'dx_last_why', q: 'Why didn\u2019t your last relationship work? The real reason, not the polite one.', type: 'area', hint: 'Say the quiet part.', ph: '\u2026' },
    { id: 'dx_hurt', q: 'Who hurt you — and what did it leave behind?', type: 'area', hint: 'Name it so it stops driving.', ph: '\u2026' },
    { id: 'dx_alone', q: 'What drove you to be alone instead of being with someone?', type: 'area', hint: 'Protection? Peace? Habit?', ph: '\u2026' },
    { id: 'dx_expect', q: 'What are you actually expecting from having a man or woman in your life?', type: 'area', hint: 'The honest job description.', ph: '\u2026' },
    { id: 'dx_missing', q: 'What did the last person not do for you?', type: 'area', hint: 'The unmet need.', ph: '\u2026' },
    { id: 'dx_money', q: 'How important is money to you in a relationship?', type: 'text', hint: 'A number or a sentence.', ph: 'e.g. 8/10 \u2014 security matters' },
    { id: 'dx_jealousy', q: 'How important is jealousy to you?', type: 'text', hint: 'Do you need it to feel wanted, or does it poison things?', ph: '\u2026' },
    { id: 'dx_sex', q: 'How important is sex to you in a relationship?', type: 'text', hint: 'Straight answer, no shame.', ph: '\u2026' },
    { id: 'dx_fam_close', q: 'Who are you closest to — family or friend — and WHY?', type: 'area', hint: 'The person whose opinion actually moves you.', ph: 'Name them and say why\u2026' },
    { id: 'dx_parents_together', q: 'Are your parents together or divorced?', type: 'text', hint: 'One line is fine.', ph: 'Together / divorced / it\u2019s complicated\u2026' },
    { id: 'dx_dad_rel', q: 'Do you have a good relationship with your dad?', type: 'text', hint: 'Honest yes, no, or somewhere between.', ph: '\u2026' },
    { id: 'dx_mom_rel', q: 'Do you have a good relationship with your mom?', type: 'text', hint: 'Honest yes, no, or somewhere between.', ph: '\u2026' },
    { id: 'dx_parents_rel', q: 'Do your parents have a good relationship with each other?', type: 'area', hint: 'What did love look like growing up in your house?', ph: 'What did you see between them\u2026' },
    { id: 'dx_advice_from', q: 'Who do you normally get your dating advice from — and WHY do you value their opinion?', type: 'area', hint: 'Whose voice is already in your head when you date?', ph: 'Name them and say why you listen\u2026' },
    { id: 'dx_advice_single', q: 'Is that person single themselves?', type: 'text', hint: 'Yes / no / it\u2019s complicated.', ph: '\u2026' },
    { id: 'dx_advice_divorced', q: 'Are they divorced?', type: 'text', hint: 'Track record matters — even for wisdom about what NOT to do.', ph: '\u2026' },
    { id: 'dx_talk_parents', q: 'Do you talk to your parents?', type: 'text', hint: 'Regularly, rarely, or not at all.', ph: '\u2026' },
    { id: 'dx_model_who', q: 'Who has the relationship you actually want — your parents? A friend? Someone real? Or does it only exist in movies?', type: 'area', hint: 'Name the model. If no one real has it, say so.', ph: 'Who\u2019s living the thing you want\u2026' }
  ]}
];

let obStep = 0;
const obAnswers = {};

function renderOnboarding() {
  obStep = 0;
  Object.keys(obAnswers).forEach((k) => delete obAnswers[k]);
  renderObStep();
}

function renderObStep() {
  const step = OB_STEPS[obStep];
  $('#ob-step-label').textContent = 'Step ' + (obStep + 1) + ' of ' + OB_STEPS.length + ' · ' + step.title;
  $('#ob-progress').style.width = Math.round(((obStep + 1) / OB_STEPS.length) * 100) + '%';
  $('#ob-questions').innerHTML = step.qs.map((q) => {
    const val = esc(obAnswers[q.id] || '');
    const field = q.type === 'text'
      ? '<input type="text" id="ob-' + q.id + '" value="' + val + '" placeholder="' + esc(q.ph || '') + '" autocomplete="off">'
      : '<textarea id="ob-' + q.id + '" rows="4" placeholder="' + esc(q.ph || '') + '">' + val + '</textarea>';
    return '<div class="ob-q"><label>' + esc(q.q) +
      (q.optional ? ' <span class="muted sm">(optional)</span>' : '') +
      '</label><div class="q-hint">' + esc(q.hint || '') + '</div>' + field + '</div>';
  }).join('');
  $('#btn-ob-back').style.visibility = obStep === 0 ? 'hidden' : 'visible';
  $('#btn-ob-next').textContent = obStep === OB_STEPS.length - 1 ? 'Meet my coaches →' : 'Continue';
}

function collectObStep() {
  OB_STEPS[obStep].qs.forEach((q) => {
    const el = $('#ob-' + q.id);
    if (el) obAnswers[q.id] = el.value.trim();
  });
}

function initOnboarding() {
  $('#btn-ob-back').addEventListener('click', () => {
    collectObStep();
    if (obStep > 0) { obStep -= 1; renderObStep(); window.scrollTo(0, 0); }
  });
  $('#btn-ob-next').addEventListener('click', () => {
    collectObStep();
    const btn = $('#btn-ob-next');
    if (obStep < OB_STEPS.length - 1) {
      obStep += 1;
      renderObStep();
      window.scrollTo(0, 0);
      return;
    }
    // Final step: save, then advance to the coach picker.
    btn.disabled = true;
    const label = btn.textContent;
    btn.textContent = 'Saving…';
    api('/onboarding', { method: 'POST', body: JSON.stringify({ answers: obAnswers }) })
      .then(() => api('/me'))
      .then((me) => {
        state.user = me.user || me;
        return openPicker(false);
      })
      .catch((err) => {
        // Even if the save hiccups, never trap the user — surface it and let them retry.
        toast(err.message || 'Couldn\u2019t save — try again', true);
      })
      .then(() => { btn.disabled = false; btn.textContent = label; });
  });
}

/* ================= COACH PICKER ================= */
function currentCoach() {
  if (!state.user || !state.user.coach_id) return null;
  return state.coaches.find((c) => String(c.id) === String(state.user.coach_id)) || null;
}

async function ensureCoaches() {
  if (!state.coaches.length) {
    try {
      const r = await api('/coaches');
      state.coaches = r.coaches || [];
      state.locked = r.locked || [];
    } catch (e) { /* handled by callers */ }
  }
}

async function openPicker(fromSwitch) {
  showView('pick');
  const box = $('#coach-cards');
  box.innerHTML = '<div class="skel-cards"><div class="skel-card"></div><div class="skel-card"></div><div class="skel-card"></div></div>';
  $('#locked-slot').innerHTML = '';
  await ensureCoaches();
  if (!state.coaches.length) {
    box.innerHTML = '<div class="empty">Couldn\u2019t load coaches. Check your connection and try again.</div>';
    return;
  }
  renderCoachCards(fromSwitch);
}

function renderCoachCards(fromSwitch) {
  const box = $('#coach-cards');
  const cur = state.user && state.user.coach_id;
  box.innerHTML = state.coaches.map((c) => {
    const isCur = String(c.id) === String(cur);
    return '<div class="coach-card' + (isCur ? ' current' : '') + '" data-id="' + esc(c.id) + '">' +
      '<div class="coach-card-main">' +
        portraitHTML(c.img || ('/assets/coaches/' + c.id + '.webp'), c.name, 'lg') +
        '<div class="coach-card-info">' +
          '<div class="coach-name-row"><h3>' + esc(c.name) + ', ' + esc(c.age) + '</h3>' +
            (isCur ? '<span class="current-badge">YOUR COACH</span>' : '') + '</div>' +
          '<div class="coach-tagline">' + esc(c.tagline || '') + '</div>' +
          '<p class="coach-bio">' + esc(c.bio || '') + '</p>' +
          (c.lane ? '<span class="lane">' + esc(c.lane) + '</span>' : '') +
        '</div>' +
      '</div>' +
      '<button class="btn ' + (isCur ? 'btn-ghost' : 'btn-primary') + ' coach-pick-btn" data-id="' + esc(c.id) + '" type="button">' +
        (isCur ? 'Current coach' : 'Choose ' + esc(c.name)) +
      '</button>' +
    '</div>';
  }).join('');

  let locked = state.locked.slice();
  if (!locked.length) {
    locked = [{ name: 'Millionaire Matchmaker', note: 'Premium coach — coming soon' }];
  }
  $('#locked-slot').innerHTML = locked.map((l) =>
    '<div class="locked-card"><span class="lock-ico">🔒</span><b>' + esc(l.name) + '</b><br>' +
    '<span class="sm">' + esc(l.note || 'Coming soon') + '</span></div>'
  ).join('');

  $$('#coach-cards .coach-card').forEach((card) => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.coach-pick-btn')) return;
      pickCoach(card.dataset.id, fromSwitch);
    });
  });
  $$('#coach-cards .coach-pick-btn').forEach((b) => {
    b.addEventListener('click', (e) => { e.stopPropagation(); pickCoach(b.dataset.id, fromSwitch); });
  });
}

function pickCoach(id, fromSwitch) {
  const btns = $$('#coach-cards [data-id="' + id + '"] .coach-pick-btn, #coach-cards .coach-pick-btn[data-id="' + id + '"]');
  btns.forEach((b) => { b.disabled = true; });
  api('/coach-pick', { method: 'POST', body: JSON.stringify({ coach_id: id }) })
    .then(() => api('/me'))
    .then((me) => {
      state.user = me.user || me;
      setHearts(state.user.hearts || 0);
      toast('Coach picked. Let\u2019s get to work.');
      return enterMain(fromSwitch ? 'coaches' : 'practice');
    })
    .catch((err) => {
      toast(err.message || 'Couldn\u2019t pick coach', true);
      btns.forEach((b) => { b.disabled = false; });
    });
}

/* ================= MAIN SHELL ================= */
function setHearts(n) {
  const prev = state.user ? state.user.hearts : null;
  if (state.user) state.user.hearts = n;
  const h = $('#hearts-count');
  if (h) h.textContent = (n == null ? 0 : n);
  const ph = $('#profile-hearts');
  if (ph) ph.textContent = (n == null ? 0 : n);
  if (prev != null && n !== prev) {
    const pill = $('#hearts-pill');
    if (pill) { pill.classList.remove('pop'); void pill.offsetWidth; pill.classList.add('pop'); }
  }
}

async function enterMain(tab) {
  showView('main');
  setTab(tab || 'practice');
  await ensureCoaches();
  loadCheckins();
  initPractice();
  initCoachChat();
  loadProfile();
}

/* ================= CHECK-INS ================= */
let checkins = [];

function loadCheckins() {
  api('/checkins').then((r) => {
    checkins = (r && r.checkins) || [];
    renderCheckinBanner();
    renderProfileCheckins();
  }).catch(() => { /* quiet — check-ins are a bonus, not a blocker */ });
}

function renderCheckinBanner() {
  const area = $('#checkin-area');
  if (!area) return;
  const unseen = checkins.filter((c) => !c.seen);
  if (!unseen.length) { area.innerHTML = ''; return; }
  const c = unseen[0];
  const ico = c.kind === 'evening' ? '🌙' : '☀️';
  area.innerHTML =
    '<div class="checkin-banner"><span class="ci-ico">' + ico + '</span>' +
    '<div class="ci-body"><div class="ci-kind">' + esc(c.kind || 'check-in') + '</div>' +
    '<p>' + esc(c.text) + '</p></div>' +
    '<button class="ci-dismiss" type="button">Got it</button></div>';
  area.querySelector('.ci-dismiss').addEventListener('click', () => {
    api('/checkins/seen', { method: 'POST', body: JSON.stringify({ id: c.id }) }).catch(() => {});
    checkins = checkins.map((x) => (x.id === c.id ? Object.assign({}, x, { seen: true }) : x));
    renderCheckinBanner();
    renderProfileCheckins();
  });
}

function renderProfileCheckins() {
  const box = $('#profile-checkins');
  if (!box) return;
  if (!checkins.length) { box.innerHTML = '<div class="empty">No check-ins yet.</div>'; return; }
  box.innerHTML = checkins.slice(0, 10).map((c) =>
    '<div class="checkin-item' + (c.seen ? ' seen' : '') + '">' +
    '<div class="ci-kind">' + esc(c.kind || 'check-in') + '</div>' +
    '<div>' + esc(c.text) + '</div></div>'
  ).join('');
}

/* ================= PRACTICE TAB ================= */
function initPractice() {
  const box = $('#date-cards');
  box.innerHTML = '<div class="skel-cards"><div class="skel-card"></div><div class="skel-card"></div></div>';
  api('/dates').then((r) => {
    state.dates = (r && r.dates) || [];
    if (!state.dates.length) {
      box.innerHTML = '<div class="empty">No practice dates right now — check back soon.</div>';
      return;
    }
    box.innerHTML = state.dates.map((d, i) =>
      '<div class="date-card">' +
        '<div class="date-media">' +
          portraitHTML(d.img || ('/assets/dates/date' + (i + 1) + '.webp'), d.name, 'xl') +
          '<div class="date-chip">' + esc(d.name) + (d.age ? '<span class="date-age">' + esc(d.age) + '</span>' : '') + '</div>' +
        '</div>' +
        '<div class="date-card-body">' +
          (d.tagline ? '<div class="date-tagline">' + esc(d.tagline) + '</div>' : '') +
          (d.personality ? '<div class="date-personality">' + esc(d.personality) + '</div>' : '') +
          '<button class="btn btn-primary btn-block" data-date="' + esc(d.id) + '" type="button">Start date</button>' +
        '</div>' +
      '</div>'
    ).join('');
    $$('#date-cards [data-date]').forEach((b) =>
      b.addEventListener('click', () => startSim(b.dataset.date, null)));
  }).catch(() => {
    box.innerHTML = '<div class="empty">Couldn\u2019t load dates. Pull to retry by reopening the tab.</div>';
  });
  loadRecentSims();
}

function loadRecentSims() {
  const box = $('#recent-sims');
  if (!box) return;
  api('/sim/history').then((r) => {
    const sims = (r && r.sims) || [];
    if (!sims.length) { box.innerHTML = ''; return; }
    box.innerHTML = '<div class="recent-sims"><h3>Recent sessions</h3>' +
      sims.slice(0, 5).map((s) => {
        const hd = s.hearts_delta;
        const heartsHtml = (hd != null)
          ? ' <span class="rs-hearts ' + (hd >= 0 ? 'up' : 'down') + '">' + (hd >= 0 ? '+' : '') + hd + ' ♥</span>'
          : '';
        return '<div class="recent-sim"><div class="rs-body">' +
        '<div class="rs-name">' + esc(s.date_name || s.name || 'Practice date') + '</div>' +
        '<div class="rs-sub">' + esc(fmtTime(s.created_at || s.ended_at)) + '</div></div>' +
        heartsHtml + '</div>';
      }).join('') + '</div>';
  }).catch(() => {});
}

/* ---------- custom date builder ---------- */
function openCustomDate() {
  openModal(
    '<h3>Build a custom date</h3>' +
    '<p class="muted sm">Describe who you want to practice with. Your coach supervises the whole thing — and the red flags are always on.</p>' +
    '<div class="field"><label for="cd-name">Name <span class="muted">(optional)</span></label>' +
      '<input id="cd-name" type="text" placeholder="e.g. Jordan" autocomplete="off"></div>' +
    '<div class="field"><label for="cd-personality">Personality</label>' +
      '<input id="cd-personality" type="text" placeholder="e.g. confident, a little guarded, dry humor" autocomplete="off"></div>' +
    '<div class="field"><label for="cd-ethnicity">Ethnicity</label>' +
      '<input id="cd-ethnicity" type="text" placeholder="e.g. Korean-American" autocomplete="off"></div>' +
    '<div class="field"><label for="cd-vibe">Vibe</label>' +
      '<select id="cd-vibe"><option>Down-to-earth</option><option>Playful</option><option>Mysterious</option>' +
      '<option>Ambitious</option><option>Sweet</option><option>Confident</option><option>Chaotic</option></select></div>' +
    '<div class="field"><label for="cd-celebrity">Celebrity type <span class="muted">(optional)</span></label>' +
      '<input id="cd-celebrity" type="text" placeholder="e.g. gives off young Rihanna energy" autocomplete="off"></div>' +
    '<div class="modal-actions">' +
      '<button class="btn btn-primary" id="cd-go" type="button">Start practice date</button>' +
      '<button class="btn btn-ghost" id="cd-cancel" type="button">Cancel</button>' +
    '</div>'
  );
  $('#cd-cancel').addEventListener('click', closeModal);
  $('#cd-go').addEventListener('click', () => {
    const personality = $('#cd-personality').value.trim();
    if (!personality) { toast('Give your date a personality first.', true); return; }
    const payload = {
      personality: personality,
      ethnicity: $('#cd-ethnicity').value.trim(),
      vibe: $('#cd-vibe').value,
      celebrity_type: $('#cd-celebrity').value.trim()
    };
    const name = $('#cd-name').value.trim();
    if (name) payload.name = name;
    const btn = $('#cd-go');
    btn.disabled = true;
    btn.textContent = 'Building…';
    api('/dates/custom', { method: 'POST', body: JSON.stringify(payload) })
      .then((r) => { closeModal(); startSim(r.date.id, r.date); })
      .catch((err) => { toast(err.message || 'Couldn\u2019t build that date', true); btn.disabled = false; btn.textContent = 'Start practice date'; });
  });
}

/* ================= PRACTICE DATE SIM ================= */
let sim = null; // { id, date }

function startSim(dateId, dateObj) {
  const date = dateObj || state.dates.find((d) => String(d.id) === String(dateId)) || {};
  showView('sim');
  simSurface.clear();
  const lt = $('#lifeline-thread');
  if (lt) lt.innerHTML = '';
  closeLifeline();
  const head = $('#sim-id');
  head.innerHTML = portraitHTML(date.img, date.name || 'Date', 'sm') +
    '<div>' + esc(date.name || 'Your date') + '<span class="sim-tag">practice date · no clock, your pace</span></div>';
  const endBtn = $('#btn-end-date');
  endBtn.classList.remove('armed');
  endBtn.textContent = 'End date';
  api('/sim/start', { method: 'POST', body: JSON.stringify({ date_id: dateId }) })
    .then((r) => {
      sim = { id: r.simulation_id, date: date };
      if (r.opening && r.opening.text) {
        simSurface.addAI(r.opening.text);
        simSurface.scrollBottom();
      }
    })
    .catch((err) => {
      toast(err.message || 'Couldn\u2019t start the date', true);
      sim = null;
      enterMain('practice');
    });
}

function armEndDate() {
  const btn = $('#btn-end-date');
  if (!btn.classList.contains('armed')) {
    btn.classList.add('armed');
    btn.textContent = 'Tap again to end';
    setTimeout(() => {
      if (btn.classList.contains('armed')) { btn.classList.remove('armed'); btn.textContent = 'End date'; }
    }, 4000);
    return;
  }
  btn.classList.remove('armed');
  btn.textContent = 'End date';
  endSim();
}

function endSim() {
  if (!sim || !sim.id) { enterMain('practice'); return; }
  const id = sim.id;
  sim = null;
  closeLifeline();
  api('/sim/end', { method: 'POST', body: JSON.stringify({ simulation_id: id }) })
    .then((r) => showFeedback(r))
    .catch((err) => { toast(err.message || 'Couldn\u2019t end the date', true); enterMain('practice'); });
}

/* ================= ASK COACH LIFELINE =================
   Mid-date lifeline: ping your coach without leaving the sim.
   The date conversation stays visible underneath the slide-over. */
function openLifeline() {
  const c = currentCoach();
  const name = c ? c.name : 'Coach';
  const img = c ? (c.img || ('/assets/coaches/' + c.id + '.webp')) : '/assets/coaches/nia.webp';
  $('#lifeline-coach').innerHTML = portraitHTML(img, name, 'sm') +
    '<div><div class="ll-name">' + esc(name) + '</div>' +
    '<div class="ll-sub muted sm">mid-date lifeline</div></div>';
  $('#lifeline-panel').classList.remove('hidden');
  $('#lifeline-input').focus();
}

function closeLifeline() {
  const p = $('#lifeline-panel');
  if (p) p.classList.add('hidden');
}

function lifelineMsg(who, text, cls) {
  const thread = $('#lifeline-thread');
  const el = document.createElement('div');
  el.className = 'll-msg ' + (cls || '');
  const w = document.createElement('div');
  w.className = 'll-who';
  w.textContent = who;
  const b = document.createElement('div');
  b.className = 'll-text';
  b.textContent = text;
  el.appendChild(w);
  el.appendChild(b);
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
}

function askCoach(text) {
  if (!sim || !sim.id) { toast('Start a date first.', true); return; }
  const btn = $('#lifeline-send');
  if (btn.classList.contains('is-busy')) return;
  btn.classList.add('is-busy');
  btn.innerHTML = '<span class="spinner"></span>';
  lifelineMsg('You', text, 'you');
  const typing = document.createElement('div');
  typing.className = 'll-msg coach';
  typing.innerHTML = '<div class="bubble typing"><span></span><span></span><span></span></div>';
  const thread = $('#lifeline-thread');
  thread.appendChild(typing);
  thread.scrollTop = thread.scrollHeight;
  api('/sim/ask-coach', { method: 'POST', body: JSON.stringify({ simulation_id: sim.id, question: text }) })
    .then((r) => {
      typing.remove();
      lifelineMsg(r.coach_name || 'Coach', r.advice || 'No advice came back.', 'coach');
    })
    .catch((err) => {
      typing.remove();
      toast(err.message || 'Coach is unreachable right now', true);
    })
    .finally(() => {
      btn.classList.remove('is-busy');
      btn.innerHTML = PLANE_SVG;
    });
}

function initLifeline() {
  const sendBtn = $('#lifeline-send');
  if (sendBtn) sendBtn.innerHTML = PLANE_SVG;
  $('#btn-ask-coach').addEventListener('click', () => {
    if (!sim || !sim.id) { toast('Start a date first.', true); return; }
    const p = $('#lifeline-panel');
    if (p.classList.contains('hidden')) { openLifeline(); } else { closeLifeline(); }
  });
  $('#btn-lifeline-close').addEventListener('click', closeLifeline);
  $('#lifeline-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const input = $('#lifeline-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    askCoach(text);
  });
}

/* ================= YOUR PATTERNS (living mirror) ================= */
function loadPatterns() {
  const box = $('#patterns-body');
  if (!box) return;
  box.innerHTML = '<div class="skel">Reading your file…</div>';
  api('/patterns').then((r) => {
    const g = r.grouped_patterns || { dating: [], family: [], needs: [] };
    const sec = (title, items) => {
      if (!items || !items.length) return '';
      return '<div class="card"><h3>' + esc(title) + '</h3><ul class="pattern-list">' +
        items.map((p) => '<li>' + esc(p) + '</li>').join('') + '</ul></div>';
    };
    let html = '<div class="card mirror-card"><h3>Your mirror</h3>' +
      '<div class="mirror-coach muted sm">' + esc(r.coach_name || 'Coach') + ' sees you like this:</div>' +
      '<p class="mirror-text">' + esc(r.mirror || '') + '</p></div>';
    if (r.diagnosis_summary) html += '<p class="muted sm">' + esc(r.diagnosis_summary) + '</p>';
    html += sec('Dating patterns', g.dating);
    html += sec('Family dynamics shaping your dating', g.family);
    html += sec('Needs & drivers', g.needs);
    const exposed = r.exposed_in_sims || [];
    if (exposed.length) {
      html += '<div class="card"><h3>What your dates exposed</h3>' +
        exposed.map((e) => '<div class="exposed-row"><div class="ex-name">' + esc(e.date_name || 'Date') +
          ' <span class="muted sm">· score ' + esc(e.score) + '</span></div>' +
          (e.notes ? '<div class="muted sm">' + esc(e.notes) + '</div>' : '') + '</div>').join('') + '</div>';
    }
    const themes = r.lifeline_themes || [];
    if (themes.length) {
      html += '<div class="card"><h3>What you\u2019ve asked your coach mid-date</h3><ul class="pattern-list">' +
        themes.map((t) => '<li>\u201c' + esc(t.question) + '\u201d</li>').join('') + '</ul></div>';
    }
    if (!g.dating.length && !g.family.length && !g.needs.length && !exposed.length) {
      html += '<div class="empty">Nothing on file yet — answer the hard questions in onboarding and run a practice date. The mirror fills in as you train.</div>';
    }
    box.innerHTML = html;
  }).catch(() => {
    box.innerHTML = '<div class="empty">Couldn\u2019t load your patterns. Try again.</div>';
  });
}

/* ================= FEEDBACK ================= */
function scorecardRows(sc) {
  if (!sc) return '<div class="empty">No scorecard returned.</div>';
  const entries = Array.isArray(sc)
    ? sc.map((x, i) => ['Point ' + (i + 1), x])
    : Object.keys(sc).filter((k) => k !== 'feedback').map((k) => [k, sc[k]]);
  if (!entries.length) return '<div class="empty">No scorecard returned.</div>';
  return entries.map((pair) => {
    const v = pair[1];
    const val = (v && typeof v === 'object') ? JSON.stringify(v) : fmtVal(v);
    return '<div class="scorecard-row"><span class="k">' + esc(prettyKey(pair[0])) + '</span>' +
      '<span class="v">' + esc(val) + '</span></div>';
  }).join('');
}

function showFeedback(r) {
  showView('feedback');
  const d = (r && typeof r.hearts_delta === 'number') ? r.hearts_delta : 0;
  const sign = d > 0 ? '+' : '';
  const total = (r && typeof r.new_hearts === 'number') ? r.new_hearts : (state.user ? state.user.hearts : 0);
  $('#fb-hearts').innerHTML =
    '<div class="burst"><span class="heart">♥</span> ' + sign + d +
    '<small>' + (d > 0 ? 'hearts earned' : d < 0 ? 'hearts lost' : 'no change') +
    (total != null ? ' · ' + total + ' total' : '') + '</small></div>';
  $('#fb-feedback').innerHTML = md((r && r.feedback) || 'No feedback came back for this one.');
  $('#fb-scorecard').innerHTML = scorecardRows(r && r.scorecard);
  if (r && typeof r.new_hearts === 'number') setHearts(r.new_hearts);
  loadProfile();
}

/* ================= COACH CHAT TAB ================= */
const coachHist = { before: null, hasMore: false };

function greetingFor(c) {
  return 'Hey — ' + c.name + ' here. What\u2019s on your mind: a situation you\u2019re dealing with, or something you want to practice?';
}

function renderCoachHead() {
  const head = $('#coach-chat-head');
  const c = currentCoach();
  if (!c) {
    head.innerHTML = '<div class="cc-info"><div class="cc-name">No coach yet</div>' +
      '<div class="cc-sub">Pick the voice you want in your corner.</div></div>' +
      '<button class="btn btn-primary btn-sm" id="btn-pick-coach" type="button">Pick</button>';
    $('#btn-pick-coach').addEventListener('click', () => openPicker(true));
    return;
  }
  head.innerHTML =
    portraitHTML(c.img || ('/assets/coaches/' + c.id + '.webp'), c.name, 'sm') +
    '<div class="cc-info"><div class="cc-name">' + esc(c.name) + '</div>' +
    '<div class="cc-sub">' + esc(c.tagline || c.style || '') + '</div></div>' +
    '<button class="btn btn-ghost btn-sm" id="btn-pick-coach" type="button">Switch</button>';
  $('#btn-pick-coach').addEventListener('click', () => openPicker(true));
}

function initCoachChat() {
  renderCoachHead();
  coachSurface.clear();
  coachHist.before = null;
  coachHist.hasMore = false;
  loadCoachHistory(false);
}

function loadCoachHistory(older) {
  const c = currentCoach();
  const olderBox = $('#coach-load-older');
  if (!c) { olderBox.classList.add('hidden'); return; }
  const q = 'coach_id=' + encodeURIComponent(c.id) + '&limit=50' +
    (older && coachHist.before ? '&before=' + encodeURIComponent(coachHist.before) : '');
  api('/chat/history?' + q).then((r) => {
    const msgs = (r && r.messages) || [];
    coachHist.hasMore = !!(r && r.has_more);
    if (msgs.length) coachHist.before = msgs[0].id;
    const list = coachSurface.listEl;
    const nodes = msgs.map((m) => {
      const el = document.createElement('div');
      el.className = 'msg ' + (m.role === 'user' ? 'user' : 'ai');
      const b = document.createElement('div');
      b.className = 'bubble';
      b.textContent = m.text || '';
      el.appendChild(b);
      return el;
    });
    if (older) {
      const prevH = list.scrollHeight;
      // insert oldest-first: iterate in reverse so order is preserved
      for (let k = nodes.length - 1; k >= 0; k--) list.insertBefore(nodes[k], list.firstChild);
      list.scrollTop = list.scrollHeight - prevH;
    } else {
      list.innerHTML = '';
      nodes.forEach((n) => list.appendChild(n));
      if (!msgs.length) coachSurface.addAI(greetingFor(c));
      list.scrollTop = list.scrollHeight;
    }
    olderBox.classList.toggle('hidden', !coachHist.hasMore);
  }).catch((err) => toast(err.message || 'Couldn\u2019t load messages', true));
}

/* ================= TOOLS ================= */
function toolButton(sel, fn) {
  const btn = $(sel);
  btn.addEventListener('click', () => {
    if (btn.classList.contains('is-loading')) return; // already working — ignore taps
    btn.classList.add('is-loading');
    btn.disabled = true;
    Promise.resolve()
      .then(fn)
      .catch((err) => toast((err && err.message) || 'Something went wrong', true))
      .then(() => { btn.classList.remove('is-loading'); btn.disabled = false; });
  });
}

function initTools() {
  toolButton('#btn-tool-reply', async () => {
    const conv = $('#tool-reply-input').value.trim();
    if (!conv) { toast('Paste a conversation first.'); return; }
    const out = $('#tool-reply-out');
    out.innerHTML = '<div class="tool-loading"><span class="spinner"></span>Reading the room…</div>';
    const r = await api('/tools/reply', { method: 'POST', body: JSON.stringify({ conversation: conv }) });
    const opts = (r && r.options) || [];
    if (!opts.length) { out.innerHTML = '<div class="empty">No replies came back — try again.</div>'; return; }
    out.innerHTML = '';
    opts.forEach((o) => {
      const card = document.createElement('div');
      card.className = 'reply-opt';
      const t = document.createElement('div');
      t.className = 'ro-text';
      t.textContent = o.reply;
      const s = document.createElement('div');
      s.className = 'ro-strategy';
      const b = document.createElement('b');
      b.textContent = 'Strategy: ';
      s.appendChild(b);
      s.appendChild(document.createTextNode(o.strategy || ''));
      const copy = document.createElement('button');
      copy.className = 'copy-btn';
      copy.type = 'button';
      copy.textContent = 'Copy reply';
      copy.addEventListener('click', () => {
        const done = () => toast('Copied — make it yours.');
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(o.reply).then(done).catch(() => toast('Copy failed', true));
        } else { toast('Copy not supported here', true); }
      });
      card.appendChild(t); card.appendChild(s); card.appendChild(copy);
      out.appendChild(card);
    });
  });

  toolButton('#btn-tool-decode', async () => {
    const msg = $('#tool-decode-input').value.trim();
    if (!msg) { toast('Paste their message first.'); return; }
    const out = $('#tool-decode-out');
    out.innerHTML = '<div class="tool-loading"><span class="spinner"></span>Decoding…</div>';
    const r = await api('/tools/decode', { method: 'POST', body: JSON.stringify({ message: msg }) });
    const flags = (r && r.red_flags) || [];
    let html = '<div class="decode-block"><h4>Subtext</h4><p>' + esc(r.subtext || '—') + '</p></div>' +
      '<div class="decode-block"><h4>Tone read</h4><p>' + esc(r.tone || '—') + '</p></div>' +
      '<div class="decode-block"><h4>Red flags</h4>';
    if (flags.length) {
      html += flags.map((f) =>
        '<div class="redflag"><b>🚩 ' + esc(f.flag) + '</b><p>' + esc(f.explanation) + '</p></div>'
      ).join('');
    } else {
      html += '<p class="muted">None spotted in this one.</p>';
    }
    html += '</div>';
    out.innerHTML = html;
  });
}

/* ================= PROFILE ================= */
function loadProfile() {
  const u = state.user;
  if (!u) return;
  $('#profile-name').textContent = u.display_name || '—';
  $('#profile-email').textContent = u.email || '';
  setHearts(u.hearts || 0);
  const c = currentCoach();
  $('#btn-switch-coach').textContent = c ? c.name + ' →' : 'Pick a coach';
  renderProfileCheckins();
  api('/history').then((r) => {
    renderStats(r && r.stats);
    renderScorecards(r && r.scorecards);
  }).catch(() => {
    renderStats(null);
    renderScorecards(null);
  });
}

function renderStats(stats) {
  const box = $('#profile-stats');
  if (!stats || !Object.keys(stats).length) {
    box.innerHTML = '<div class="empty" style="grid-column:1/-1">No stats yet — run a practice date.</div>';
    return;
  }
  box.innerHTML = Object.keys(stats).map((k) =>
    '<div class="stat"><div class="sv">' + esc(fmtVal(stats[k])) + '</div>' +
    '<div class="sk">' + esc(prettyKey(k)) + '</div></div>'
  ).join('');
}

function renderScorecards(scorecards) {
  const box = $('#profile-scorecards');
  if (!scorecards || !scorecards.length) {
    box.innerHTML = '<div class="empty">No debriefs yet — your practice dates land here.</div>';
    return;
  }
  box.innerHTML = scorecards.slice(0, 20).map((s) => {
    const title = s.date_name || s.name || s.title || 'Practice date';
    const when = fmtTime(s.created_at || s.ended_at || s.date);
    let detail = '';
    if (s.score != null) detail += 'Score ' + esc(fmtVal(s.score));
    if (s.texting_score != null) detail += (detail ? ' · ' : '') + 'Texting ' + esc(fmtVal(s.texting_score));
    if (s.red_flag_score != null) detail += (detail ? ' · ' : '') + 'Red flags ' + esc(fmtVal(s.red_flag_score));
    if (s.hearts_delta != null) detail += (detail ? ' · ' : '') + (s.hearts_delta >= 0 ? '+' : '') + s.hearts_delta + ' ♥';
    if (!detail && s.summary) detail = String(s.summary).slice(0, 140);
    return '<div class="scorecard-item"><div class="sc-top"><b>' + esc(title) + '</b>' +
      '<span class="sc-date">' + esc(when) + '</span></div>' +
      (detail ? '<div class="sc-detail">' + esc(detail) + '</div>' : '') + '</div>';
  }).join('');
}

function initProfile() {
  $('#btn-switch-coach').addEventListener('click', () => openPicker(true));

  $('#btn-edit-name').addEventListener('click', () => {
    openModal(
      '<h3>Display name</h3>' +
      '<div class="field"><input id="en-input" type="text" maxlength="40" value="' +
        esc(state.user ? state.user.display_name || '' : '') + '" autocomplete="off"></div>' +
      '<div class="modal-actions">' +
        '<button class="btn btn-primary" id="en-go" type="button">Save</button>' +
        '<button class="btn btn-ghost" id="en-cancel" type="button">Cancel</button>' +
      '</div>'
    );
    $('#en-cancel').addEventListener('click', closeModal);
    $('#en-go').addEventListener('click', () => {
      const name = $('#en-input').value.trim();
      const btn = $('#en-go');
      btn.disabled = true;
      api('/me', { method: 'PUT', body: JSON.stringify({ display_name: name }) })
        .then((r) => {
          state.user = (r && r.user) || Object.assign({}, state.user, { display_name: name });
          closeModal();
          loadProfile();
          toast('Saved.');
        })
        .catch((err) => { toast(err.message || 'Couldn\u2019t save', true); btn.disabled = false; });
    });
  });

  $('#btn-fresh-restart').addEventListener('click', () => {
    openModal(
      '<h3>Fresh restart?</h3>' +
      '<p class="muted">This resets your <b style="color:var(--text)">hearts</b> and <b style="color:var(--text)">stats</b> ' +
      'to zero so you can climb again. Your history and debriefs stay put.</p>' +
      '<p class="muted sm">Type <b>RESTART</b> to confirm. This can\u2019t be undone.</p>' +
      '<div class="field"><input id="fr-input" class="type-confirm" type="text" placeholder="RESTART" autocomplete="off"></div>' +
      '<div class="modal-actions">' +
        '<button class="btn btn-danger" id="fr-go" type="button" disabled>Wipe it and restart</button>' +
        '<button class="btn btn-ghost" id="fr-cancel" type="button">Keep my progress</button>' +
      '</div>'
    );
    const inp = $('#fr-input'), go = $('#fr-go');
    inp.addEventListener('input', () => { go.disabled = inp.value.trim().toUpperCase() !== 'RESTART'; });
    $('#fr-cancel').addEventListener('click', closeModal);
    go.addEventListener('click', () => {
      go.disabled = true;
      go.textContent = 'Restarting…';
      api('/fresh-restart', { method: 'POST', body: JSON.stringify({ confirm: true }) })
        .then((r) => {
          closeModal();
          setHearts((r && typeof r.hearts === 'number') ? r.hearts : 0);
          toast('Fresh start. Make it count.');
          loadProfile();
        })
        .catch((err) => {
          toast(err.message || 'Couldn\u2019t restart', true);
          go.disabled = false;
          go.textContent = 'Wipe it and restart';
        });
    });
  });

  $('#btn-logout').addEventListener('click', () => {
    logout();
    toast('Logged out.');
  });
}

/* ================= BOOT ================= */
function init() {
  initTheme();
  initAuth();
  initOnboarding();
  initTools();
  initProfile();
  initLifeline();

  coachSurface = chatSurface({
    list: '#coach-chat-list', form: '#coach-composer', input: '#coach-input', sendBtn: '#coach-send',
    aiName: () => { const c = currentCoach(); return c ? c.name : null; },
    onSend: (text, hooks) => {
      const c = currentCoach();
      if (!c) return Promise.reject(new Error('Pick a coach first.'));
      return streamSSE('/chat', { coach_id: c.id, message: text }, {
        onController: hooks.controller, onDelta: hooks.delta,
        onDone: hooks.done, onAbort: hooks.abort, onEnd: hooks.done
      });
    }
  });

  simSurface = chatSurface({
    list: '#sim-chat-list', form: '#sim-composer', input: '#sim-input', sendBtn: '#sim-send',
    aiName: () => (sim && sim.date && sim.date.name) ? sim.date.name : null,
    onSend: (text, hooks) => {
      if (!sim || !sim.id) return Promise.reject(new Error('No active date.'));
      return streamSSE('/sim/message', { simulation_id: sim.id, message: text }, {
        onController: hooks.controller, onDelta: hooks.delta,
        onDone: hooks.done, onAbort: hooks.abort, onEnd: hooks.done
      });
    }
  });

  $$('.tab-btn').forEach((b) => b.addEventListener('click', () => setTab(b.dataset.tab)));
  $('#btn-custom-date').addEventListener('click', openCustomDate);
  $('#btn-end-date').addEventListener('click', armEndDate);
  $('#btn-load-older').addEventListener('click', () => loadCoachHistory(true));
  $('#btn-fb-practice').addEventListener('click', () => { showView('main'); setTab('practice'); });
  $('#btn-fb-coach').addEventListener('click', () => { showView('main'); setTab('coaches'); });
  $('#hearts-pill').addEventListener('click', () => setTab('profile'));

  if (token()) {
    bootAfterAuth().catch(() => showView('auth'));
  } else {
    showView('auth');
  }
}

document.addEventListener('DOMContentLoaded', init);
