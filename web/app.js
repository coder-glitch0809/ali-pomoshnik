/* Ali — veb interfeys */
(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const isPhone = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  const DEVICE = isPhone ? 'phone' : 'desktop';

  const el = {
    stage: $('#stage'), feed: $('#feed'), state: $('#stateLabel'), live: $('#liveTranscript'),
    input: $('#input'), composer: $('#composer'), mic: $('#micBtn'), file: $('#fileInput'),
    attachments: $('#attachments'), sidebar: $('#sidebar'), scrim: $('#scrim'),
    sheet: $('#confirmSheet'), toast: $('#toast'), player: $('#player'), geo: $('#geoToggle'),
  };

  // ---------- Saqlanadigan sozlamalar ----------
  const store = {
    get(k, d) { try { const v = localStorage.getItem('ali.' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('ali.' + k, JSON.stringify(v)); } catch { /* yo'q */ } },
  };
  const modes = { deep: store.get('deep', false), super: true, voice: store.get('voice', true), wake: false };

  let agent = '';
  store.set('agent', ''); store.set('super', true); // tanlangan agent kaliti ('' = oddiy Ali)

  let status = { wake_words: ['ali'], stt_language: 'uz-UZ', server_stt: false, assistant: 'Ali', user: '', agents: [] };
  let myDeviceId = null;
  let attachments = [];
  let busy = false;

  // ---------- Holat ----------
  const STATES = {
    idle: 'Tayyor', listening: 'Tinglayapman', thinking: 'Fikrlayapman',
    working: 'Bajaryapman', speaking: 'Gapiryapman', offline: 'Aloqa yo‘q', wake: 'Kutyapman',
  };
  let state = 'offline';
  function setState(s, sub) {
    state = s;
    $('#sidebarVoice').classList.toggle('listening', s === 'listening');
    $('#sidebarVoice').setAttribute('aria-pressed', String(s === 'listening'));
    $('#sidebarVoiceLabel').textContent = s === 'listening' ? 'Tinglashni to‘xtatish' : 'Ovozli suhbat';
    el.state.textContent = STATES[s] || s;
    if (sub !== undefined) el.live.textContent = sub;
  }
  function idleState() { setState(modes.wake ? 'wake' : 'idle', modes.wake ? `“${status.wake_words[0]}” deb chaqiring` : ''); }

  function toast(text, ms = 2600) {
    el.toast.textContent = text;
    el.toast.classList.add('show');
    clearTimeout(toast.t);
    toast.t = setTimeout(() => el.toast.classList.remove('show'), ms);
  }

  // ---------- Reaktor (animatsiya) ----------
  const reactor = (() => {
    const c = $('#reactor'), ctx = c.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = c.height = 400 * dpr;
    ctx.scale(dpr, dpr);
    let level = 0, target = 0, t = 0;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

    function color(a) {
      return (state === 'thinking' || state === 'working') ? `rgba(245,165,36,${a})`
        : state === 'offline' ? `rgba(120,130,150,${a})` : `rgba(91,140,255,${a})`;
    }
    function arc(r, start, len, w, a) {
      ctx.beginPath(); ctx.arc(200, 200, r, start, start + len);
      ctx.strokeStyle = color(a); ctx.lineWidth = w; ctx.stroke();
    }
    function frame() {
      const speed = state === 'thinking' || state === 'working' ? 3 : state === 'listening' || state === 'speaking' ? 1.6 : 0.6;
      t += reduce ? 0 : 0.008 * speed;
      level += (target - level) * 0.25;
      ctx.clearRect(0, 0, 400, 400);

      // tashqi shkala
      for (let i = 0; i < 72; i++) {
        const a = (i / 72) * Math.PI * 2 + t * 0.2;
        const r1 = 180, r2 = i % 6 === 0 ? 168 : 174;
        ctx.beginPath();
        ctx.moveTo(200 + Math.cos(a) * r1, 200 + Math.sin(a) * r1);
        ctx.lineTo(200 + Math.cos(a) * r2, 200 + Math.sin(a) * r2);
        ctx.strokeStyle = color(i % 6 === 0 ? 0.55 : 0.2); ctx.lineWidth = 1.5; ctx.stroke();
      }
      // aylanuvchi segmentlar
      for (let i = 0; i < 3; i++) arc(150, t * 1.3 + i * 2.094, 1.4, 3, 0.75);
      for (let i = 0; i < 8; i++) arc(128, -t * 2 + i * 0.785, 0.5, 8, 0.35);
      arc(108, 0, Math.PI * 2, 1, 0.35);

      // ovoz to'lqini
      const amp = 6 + level * 46;
      ctx.beginPath();
      for (let i = 0; i <= 120; i++) {
        const a = (i / 120) * Math.PI * 2;
        const r = 86 + Math.sin(a * 6 + t * 6) * amp * 0.25 + Math.sin(a * 11 - t * 4) * amp * 0.15;
        const x = 200 + Math.cos(a) * r, y = 200 + Math.sin(a) * r;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.strokeStyle = color(0.6); ctx.lineWidth = 2; ctx.stroke();

      // yadro
      const pulse = 1 + Math.sin(t * 3) * 0.04 + level * 0.25;
      const g = ctx.createRadialGradient(200, 200, 0, 200, 200, 78 * pulse);
      g.addColorStop(0, 'rgba(235,253,255,1)');
      g.addColorStop(0.28, color(0.95));
      g.addColorStop(0.62, color(0.25));
      g.addColorStop(1, color(0));
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(200, 200, 78 * pulse, 0, Math.PI * 2); ctx.fill();

      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    return { setLevel(v) { target = Math.max(0, Math.min(1, v)); } };
  })();

  // ---------- Audio darajasi (orb uchun) ----------
  let audioCtx = null, analyser = null, levelTimer = null;
  function ensureAudioCtx() {
    if (!audioCtx) {
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        audioCtx.createMediaElementSource(el.player).connect(analyser);
        analyser.connect(audioCtx.destination);
      } catch { audioCtx = null; }
    }
    if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
  }
  function trackLevel(node) {
    clearInterval(levelTimer);
    if (!node) { reactor.setLevel(0); return; }
    const buf = new Uint8Array(node.frequencyBinCount);
    levelTimer = setInterval(() => {
      node.getByteFrequencyData(buf);
      let sum = 0; for (const v of buf) sum += v;
      reactor.setLevel(sum / buf.length / 110);
    }, 50);
  }

  // ---------- Gapirish (TTS) ----------
  let speaking = false;
  async function speak(text) {
    if (!text) return;
    try {
      const res = await fetch('/api/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
      if (!res.ok || res.status === 204) return;
      const url = URL.createObjectURL(await res.blob());
      ensureAudioCtx();
      speaking = true;
      recognizer.pause();
      setState('speaking');
      el.player.src = url;
      await el.player.play();
      trackLevel(analyser);
    } catch (e) {
      speaking = false;
      idleState();
      recognizer.resume();
    }
  }
  el.player.addEventListener('ended', () => {
    speaking = false; trackLevel(null); idleState(); recognizer.resume();
  });
  function stopSpeaking() {
    if (!speaking) return;
    el.player.pause(); speaking = false; trackLevel(null);
  }

  // ---------- Eshitish (STT) ----------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognizer = (() => {
    let rec = null, mode = null, paused = false, awaitingCommand = false;
    let mediaRec = null, chunks = [];

    function normalize(s) { return s.toLowerCase().replace(/[.,!?]/g, '').trim(); }
    function stripWake(text) {
      const n = normalize(text);
      for (const w of status.wake_words) {
        if (n === w) return '';
        if (n.startsWith(w + ' ')) return text.trim().slice(w.length).replace(/^[\s,.!?]+/, '');
      }
      return null;
    }

    function build(continuous) {
      const r = new SR();
      r.lang = status.stt_language || 'uz-UZ';
      r.interimResults = true;
      r.continuous = continuous;
      r.maxAlternatives = 1;
      return r;
    }

    // Bir martalik tinglash (mikrofon tugmasi)
    function startOnce() {
      if (!SR) return startServerRecording();
      stopWake();
      stopSpeaking();
      mode = 'once';
      rec = build(false);
      let finalText = '';
      rec.onresult = (e) => {
        let interim = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript;
        }
        el.live.textContent = finalText + interim;
      };
      rec.onerror = (e) => { if (e.error === 'not-allowed') toast('Mikrofonga ruxsat berilmagan (HTTPS kerak)'); };
      rec.onend = () => {
        el.mic.classList.remove('recording');
        mode = null;
        if (finalText.trim()) send(finalText.trim());
        else idleState();
        if (modes.wake) startWake();
      };
      el.mic.classList.add('recording');
      setState('listening', '');
      reactor.setLevel(0.5);
      try { rec.start(); } catch { /* allaqachon */ }
    }

    // Doim tinglash rejimi ("Ali, ...")
    function startWake() {
      if (!SR) { toast('Bu brauzerda doimiy tinglash yo‘q — Chrome ishlating'); setMode('wake', false); return; }
      if (mode === 'wake' || paused) return;
      mode = 'wake';
      rec = build(true);
      rec.onresult = (e) => {
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          const text = r[0].transcript;
          if (!r.isFinal) { if (awaitingCommand) el.live.textContent = text; continue; }
          if (awaitingCommand) { awaitingCommand = false; send(text.trim()); continue; }
          const cmd = stripWake(text);
          if (cmd === null) continue;
          if (cmd) send(cmd);
          else { awaitingCommand = true; setState('listening', 'Ha, ' + (status.user || 'ser') + '?'); speak('Ha, ' + (status.user || 'ser') + '?'); }
        }
      };
      rec.onerror = (e) => {
        if (e.error === 'not-allowed') { toast('Mikrofonga ruxsat yo‘q'); setMode('wake', false); }
      };
      rec.onend = () => { if (mode === 'wake') { mode = null; if (modes.wake && !paused) setTimeout(startWake, 300); } };
      try { rec.start(); idleState(); } catch { mode = null; }
    }
    function stopWake() { if (mode === 'wake' && rec) { mode = null; try { rec.abort(); } catch { /* */ } } }

    // Brauzer tanimasa: yozib, serverga (Gemini) yuborish
    async function startServerRecording() {
      if (!status.server_stt) { toast('Ovozni tanish uchun Chrome yoki GEMINI_API_KEY kerak'); return; }
      if (mediaRec) { mediaRec.stop(); return; }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRec = new MediaRecorder(stream);
        chunks = [];
        mediaRec.ondataavailable = (e) => chunks.push(e.data);
        mediaRec.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          el.mic.classList.remove('recording');
          mediaRec = null;
          setState('thinking', 'Ovoz matnga aylantirilmoqda…');
          const fd = new FormData();
          fd.append('file', new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' }), 'voice.webm');
          const res = await fetch('/api/transcribe', { method: 'POST', body: fd });
          const data = await res.json().catch(() => ({}));
          if (data.text) send(data.text); else { toast('Tushunilmadi'); idleState(); }
        };
        mediaRec.start();
        el.mic.classList.add('recording');
        setState('listening', 'Gapiring, tugatgach yana bosing');
      } catch { toast('Mikrofonga ruxsat yo‘q (HTTPS kerak)'); }
    }

    return {
      startOnce, startWake, stopWake,
      stopOnce() { if (mode === 'once' && rec) rec.stop(); },
      get active() { return mode === 'once' || !!mediaRec; },
      pause() { paused = true; stopWake(); },
      resume() { paused = false; if (modes.wake) startWake(); },
    };
  })();

  // ---------- Markdown ----------
  function esc(s) { return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function inline(s) {
    return s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }
  function md(src) {
    const parts = esc(src).split(/```(?:\w+)?\n?([\s\S]*?)(?:```|$)/);
    let html = '';
    parts.forEach((part, i) => {
      if (i % 2) { html += `<pre><code>${part}</code></pre>`; return; }
      let list = null;
      const close = () => { if (list) { html += `</${list}>`; list = null; } };
      let para = [];
      const flush = () => { if (para.length) { html += `<p>${inline(para.join('<br>'))}</p>`; para = []; } };
      for (const line of part.split('\n')) {
        let m;
        if ((m = line.match(/^(#{1,3})\s+(.*)/))) { flush(); close(); html += `<h3>${inline(m[2])}</h3>`; }
        else if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { flush(); if (list !== 'ul') { close(); html += '<ul>'; list = 'ul'; } html += `<li>${inline(m[1])}</li>`; }
        else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { flush(); if (list !== 'ol') { close(); html += '<ol>'; list = 'ol'; } html += `<li>${inline(m[1])}</li>`; }
        else if (!line.trim()) { flush(); close(); }
        else { close(); para.push(line); }
      }
      flush(); close();
    });
    return html;
  }

  // ---------- Suhbat lentasi ----------
  const turns = new Map();
  const TOOL_NAMES = {
    web_search: 'Internetdan qidirish', run_powershell: 'PowerShell',
    take_screenshot: 'Ekran rasmi', get_weather: 'Ob-havo', get_my_location: 'Joylashuv', open_application: 'Ilova ochish',
    open_website: 'Sayt ochish', instagram_analytics: 'Instagram analitika', instagram_competitor: 'Raqobatchi tahlili',
    instagram_comments: 'Izohlar', save_knowledge: 'Bilimni saqlash', search_knowledge: 'Bilimlar bazasi',
    remember_fact: 'Eslab qolish', set_reminder: 'Eslatma', phone_open_url: 'Telefonda ochish', phone_notify: 'Telefonga xabar',
    system_status: 'Tizim holati', get_datetime: 'Vaqt', ask_agent: 'Agentga topshiriq', market_data: 'Bozor ma’lumotlari',
    list_projects: 'Loyihalar', project_tree: 'Loyiha fayllari', read_project_file: 'Faylni o‘qish', search_projects: 'Kodda qidirish',
    project_git_status: 'Git holati', write_project_file: 'Faylga yozish', run_in_project: 'Loyihada buyruq', open_in_vscode: 'VS Code’da ochish',
    github_repos: 'GitHub repolar', github_repo: 'GitHub repo', github_read: 'GitHub fayl', github_issues: 'GitHub issue',
    github_create_issue: 'Issue ochish', github_clone: 'Repo klonlash', vercel_projects: 'Vercel loyihalar', vercel_deployments: 'Vercel deploylar',
    vercel_logs: 'Vercel loglar', vercel_redeploy: 'Qayta deploy', code_task: 'Claude Code', code_task_status: 'Kod vazifasi holati',
    coding_tools_status: 'Kod agentlari', create_agent: 'Agent yaratish', delete_agent: 'Agent o‘chirish', list_agents: 'Agentlar',
    list_available_tools: 'Vositalar ro‘yxati', learn_now: 'O‘z-o‘zini o‘qitish', check_trading_projects: 'Treyding loyihalari tekshiruvi',
    instagram_accounts: 'Instagram akkauntlar', list_knowledge_topics: 'Bilim mavzulari', list_facts: 'Faktlar', forget_fact: 'Unutish',
    list_reminders: 'Eslatmalar', cancel_reminder: 'Eslatmani bekor qilish',
  };
  const agentInfo = (key) => (status.agents || []).find((a) => a.key === key);

  function scrollDown() { requestAnimationFrame(() => { el.stage.scrollTop = el.stage.scrollHeight; el.feed.scrollTop = el.feed.scrollHeight; }); }
  function startChat() { el.stage.classList.add('chatting'); }

  function addUser(text, images, fromSelf, source) {
    startChat();
    const div = document.createElement('div');
    div.className = 'msg user';
    const label = source === 'telegram' ? 'Telegramdan' : (isPhone ? 'Boshqa qurilmadan' : 'Telefondan');
    div.innerHTML = (fromSelf ? '' : `<div class="from">${label}</div>`) +
      images.map((src) => `<img class="attached" src="${src}" alt="">`).join('') +
      (text ? `<div class="bubble">${esc(text)}</div>` : '');
    el.feed.appendChild(div);
  }

  function addTurn(id, agentKey) {
    const a = agentInfo(agentKey);
    const div = document.createElement('div');
    div.className = 'msg ai';
    div.innerHTML = `
      <div class="card">
        <div class="card-head">${a ? `${esc(a.icon)} ${esc(a.name)}` : esc(status.assistant || 'Ali')}<span class="spinner"></span></div>
        <details class="thinking" hidden><summary><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>Fikrlash jarayoni</summary><div class="think-body"></div></details>
        <div class="tools"></div>
        <div class="extra"></div>
        <div class="answer"></div>
      </div>`;
    el.feed.appendChild(div);
    const t = {
      root: div, think: div.querySelector('.thinking'), thinkBody: div.querySelector('.think-body'),
      tools: div.querySelector('.tools'), extra: div.querySelector('.extra'), answer: div.querySelector('.answer'),
      spinner: div.querySelector('.spinner'), text: '', raf: 0,
    };
    turns.set(id, t);
    scrollDown();
    return t;
  }

  function renderAnswer(t) {
    if (t.raf) return;
    t.raf = requestAnimationFrame(() => { t.raf = 0; t.answer.innerHTML = md(t.text); scrollDown(); });
  }

  function finishTurn(t, text, isError) {
    t.spinner?.remove();
    if (isError) { t.answer.classList.add('error'); t.answer.textContent = text; return; }
    if (text) t.text = text;
    cancelAnimationFrame(t.raf); t.raf = 0;
    t.answer.innerHTML = md(t.text);
    if (t.think.open) t.think.open = false;
    const actions = document.createElement('div');
    actions.className = 'card-actions';
    actions.innerHTML = `<button class="speak-btn"><svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9zM16 8.5a5 5 0 0 1 0 7"/></svg>O‘qib berish</button>
      <button class="speak-btn copy"><svg viewBox="0 0 24 24"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>Nusxa</button>`;
    actions.firstElementChild.onclick = () => speak(t.text);
    actions.lastElementChild.onclick = () => { navigator.clipboard?.writeText(t.text); toast('Nusxalandi'); };
    t.root.querySelector('.card').appendChild(actions);
    scrollDown();
  }

  // ---------- Aloqa (WebSocket) ----------
  let ws = null, retry = 0;
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws?device=${DEVICE}`);
    ws.onopen = () => { retry = 0; setLive(true); idleState(); loadStatus(); loadMonitor(); sendLocationNow(); };
    ws.onclose = (e) => {
      if (e.code === 4401) { location.href = '/login'; return; }
      setLive(false);
      setState('offline', 'Qayta ulanmoqda…');
      setTimeout(connect, Math.min(1000 * 2 ** retry++, 15000));
    };
    ws.onmessage = (e) => handle(JSON.parse(e.data));
  }
  function wsSend(obj) { if (ws && ws.readyState === 1) { ws.send(JSON.stringify(obj)); return true; } return false; }

  function handle(m) {
    const t = m.id ? turns.get(m.id) : null;
    switch (m.type) {
      case 'hello': myDeviceId = m.device_id; break;
      case 'history':
        if (!turns.size && !el.feed.children.length) {
          for (const row of m.messages || []) {
            if (row.role === 'user') addUser(row.content, [], false, 'history');
            else if (row.role === 'assistant') {
              finishTurn(addTurn(`history-${row.id}`), row.content, false);
            }
          }
        }
        break;
      case 'devices': loadStatus(); break;
      case 'user':
        if (m.from === myDeviceId) break; // o'zimizniki allaqachon ko'rsatilgan
        addUser(m.text, m.images || [], false, m.from);
        addTurn(m.id, m.agent);
        setState('thinking', '');
        break;
      case 'thinking': {
        const turn = t || addTurn(m.id);
        turn.think.hidden = false;
        turn.thinkBody.textContent += m.data;
        turn.thinkBody.scrollTop = turn.thinkBody.scrollHeight;
        if (state !== 'thinking') setState('thinking');
        break;
      }
      case 'text': {
        const turn = t || addTurn(m.id);
        turn.text += m.data;
        renderAnswer(turn);
        if (state !== 'speaking') setState('working', '');
        break;
      }
      case 'tool_start': {
        const turn = t || addTurn(m.id);
        const chip = document.createElement('span');
        chip.className = 'tool';
        chip.dataset.name = m.data.name;
        chip.innerHTML = `<span class="dot"></span>${esc(TOOL_NAMES[m.data.name] || m.data.name)}`;
        turn.tools.appendChild(chip);
        setState('working', TOOL_NAMES[m.data.name] || m.data.name);
        scrollDown();
        break;
      }
      case 'agent': {
        const turn = t || addTurn(m.id);
        const chip = document.createElement('span');
        chip.className = 'tool agent-chip';
        chip.textContent = `${m.data.icon} ${m.data.name} ishlayapti`;
        turn.tools.appendChild(chip);
        setState('working', `${m.data.icon} ${m.data.name}`);
        scrollDown();
        break;
      }
      case 'tool_end': {
        if (!t) break;
        const chip = [...t.tools.querySelectorAll(`.tool[data-name="${m.data.name}"]:not(.ok):not(.err)`)][0];
        if (chip) { chip.classList.add(m.data.error ? 'err' : 'ok'); chip.title = m.data.output; }
        break;
      }
      case 'image': {
        const turn = [...turns.values()].pop();
        if (turn) { turn.extra.insertAdjacentHTML('beforeend', `<img class="shot" src="${m.src}" alt="${esc(m.caption || '')}">`); scrollDown(); }
        break;
      }
      case 'files': {
        const turn = t || [...turns.values()].pop();
        if (turn) {
          turn.extra.insertAdjacentHTML('beforeend', m.files.map((f) =>
            `<a class="file-link" href="${esc(f.url)}" download="${esc(f.name)}">📎 ${esc(f.name)}</a>`).join(''));
          scrollDown();
        }
        break;
      }
      case 'done':
        busy = false;
        if (t) finishTurn(t, m.text, false);
        idleState();
        if (modes.voice && m.speak_on === myDeviceId) speak(m.text);
        break;
      case 'error':
        busy = false;
        if (t) finishTurn(t, m.text, true); else toast(m.text);
        idleState();
        break;
      case 'busy': busy = false; toast('Ali hozir boshqa vazifa ustida — biroz kuting'); idleState(); break;
      case 'confirm': openConfirm(m); break;
      case 'confirm_closed': if (el.sheet.dataset.id === m.id) closeConfirm(); break;
      case 'notify':
        toast(m.text, 6000);
        if (navigator.vibrate) navigator.vibrate([120, 60, 120]);
        if (modes.voice) speak(m.text);
        break;
      case 'action': handleAction(m); break;
      case 'monitor': loadMonitor(); break;
      case 'agents_changed': loadStatus(); loadMonitor(); break;
      case 'monitor_log': appendLog(m.entry); break;
      case 'session_reset': el.feed.innerHTML = ''; turns.clear(); el.stage.classList.remove('chatting'); toast('Yangi suhbat'); break;
    }
  }

  function handleAction(m) {
    startChat();
    const div = document.createElement('div');
    div.className = 'msg ai';
    if (m.action === 'open_url') {
      div.innerHTML = `<div class="card action-card"><div class="card-head">Telefonda ochish</div>
        <p>${esc(m.title || m.url)}</p><div class="card-actions"><a class="btn primary" style="text-align:center;text-decoration:none" href="${esc(m.url)}" target="_blank" rel="noopener">Ochish</a></div></div>`;
      window.open(m.url, '_blank'); // brauzer ruxsat bersa - darhol ochiladi
    } else if (m.action === 'notify') {
      div.innerHTML = `<div class="card action-card"><div class="card-head">Xabar</div><p>${esc(m.text)}</p></div>`;
      if (navigator.vibrate) navigator.vibrate([200, 80, 200]);
      if ('Notification' in window && Notification.permission === 'granted') new Notification('Ali', { body: m.text, icon: '/static/icon.svg' });
    }
    el.feed.appendChild(div);
    scrollDown();
  }

  // ---------- Yuborish ----------
  function send(text) {
    text = (text || '').trim();
    if (!text && !attachments.length) return;
    if (busy) { toast('Ali javob berayapti…'); return; }
    stopSpeaking();
    const id = Math.random().toString(36).slice(2, 10);
    const images = attachments.map((a) => ({ media_type: 'image/jpeg', data: a.data }));
    if (!wsSend({ type: 'ask', id, text, images, deep: modes.deep, super: modes.super, agent })) { toast('Server bilan aloqa yo‘q'); return; }
    busy = true;
    addUser(text, attachments.map((a) => a.src), true);
    addTurn(id, agent);
    attachments = []; renderAttachments();
    el.input.value = ''; autosize();
    setState('thinking', '');
  }

  // ---------- Rasm biriktirish ----------
  function renderAttachments() {
    el.attachments.innerHTML = '';
    attachments.forEach((a, i) => {
      const d = document.createElement('div');
      d.className = 'att';
      d.innerHTML = `<img src="${a.src}" alt=""><button type="button" aria-label="O‘chirish">×</button>`;
      d.querySelector('button').onclick = () => { attachments.splice(i, 1); renderAttachments(); updateComposer(); };
      el.attachments.appendChild(d);
    });
  }
  function resizeImage(file) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const k = Math.min(1, 1568 / Math.max(img.width, img.height));
        const c = document.createElement('canvas');
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        const src = c.toDataURL('image/jpeg', 0.85);
        URL.revokeObjectURL(img.src);
        resolve({ src, data: src.split(',')[1] });
      };
      img.onerror = reject;
      img.src = URL.createObjectURL(file);
    });
  }
  el.file.addEventListener('change', async () => {
    for (const f of [...el.file.files].slice(0, 4)) {
      try { attachments.push(await resizeImage(f)); } catch { toast('Rasmni o‘qib bo‘lmadi'); }
    }
    el.file.value = '';
    renderAttachments(); updateComposer();
  });

  // ---------- Kiritish maydoni ----------
  function autosize() { el.input.style.height = 'auto'; el.input.style.height = Math.min(el.input.scrollHeight, 160) + 'px'; updateComposer(); }
  function updateComposer() { el.composer.classList.toggle('has-text', !!el.input.value.trim() || attachments.length > 0); }
  el.input.addEventListener('input', autosize);
  el.input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !isPhone) { e.preventDefault(); send(el.input.value); }
  });
  el.composer.addEventListener('submit', (e) => { e.preventDefault(); send(el.input.value); });
  el.mic.addEventListener('click', () => {
    unlockAudio();
    if (el.composer.classList.contains('has-text')) { send(el.input.value); return; }
    if (recognizer.active) recognizer.stopOnce(); else recognizer.startOnce();
  });
  document.querySelectorAll('.suggestions button').forEach((b) => b.addEventListener('click', () => { unlockAudio(); send(b.textContent); }));

  // Mobil brauzerlarda ovozni birinchi teginishda "ochish" kerak
  function silentWav() {
    const rate = 8000, n = 800, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
    const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
    str(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); str(8, 'WAVEfmt ');
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    str(36, 'data'); v.setUint32(40, n * 2, true);
    return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
  }
  let unlocked = false;
  function unlockAudio() {
    if (unlocked) return;
    unlocked = true;
    ensureAudioCtx();
    if (!speaking) { el.player.src = silentWav(); el.player.play().catch(() => {}); }
  }
  document.addEventListener('pointerdown', unlockAudio, { once: true });

  // ---------- Rejim tugmalari ----------
  function setMode(name, on) {
    if (name === 'super') on = true;
    modes[name] = on;
    if (name !== 'wake') store.set(name, on);
    document.querySelector(`.mode[data-mode="${name}"]`)?.classList.toggle('on', on);
    if (name === 'wake') { on ? recognizer.startWake() : recognizer.stopWake(); idleState(); }
  }
  document.querySelectorAll('.mode').forEach((b) => {
    b.classList.toggle('on', !!modes[b.dataset.mode]);
    b.addEventListener('click', () => {
      unlockAudio();
      const name = b.dataset.mode;
      setMode(name, !modes[name]);
      const labels = { deep: ['Chuqur fikrlash yoqildi', 'Tezkor rejim'], super: ['Faqat Claude', 'Faqat Claude'],
        voice: ['Javoblar ovoz bilan o‘qiladi', 'Ovoz o‘chirildi'], wake: [`“${status.wake_words[0]}” deb chaqiring`, 'Doimiy tinglash o‘chdi'] };
      toast(labels[name][modes[name] ? 0 : 1]);
      if (name === 'voice' && !modes.voice) stopSpeaking();
    });
  });

  // ---------- Agentlar ----------
  function renderAgents() {
    el.input.placeholder = `${status.assistant || 'Ali'}ga yozing yoki gapiring…`;
  }
  function selectAgent(key, silent) {
    agent = '';
    store.set('agent', '');
    renderAgents();
    if (!silent) toast('Vazifani Aliga yozing — agentlarni Ali boshqaradi');
  }

  // ---------- Tasdiqlash ----------
  function openConfirm(m) {
    el.sheet.dataset.id = m.id;
    $('#confirmName').textContent = TOOL_NAMES[m.name] || m.name;
    $('#confirmArgs').textContent = m.args.command || JSON.stringify(m.args, null, 2);
    el.sheet.classList.add('show');
    el.sheet.setAttribute('aria-hidden', 'false');
    if (navigator.vibrate) navigator.vibrate(80);
    if (modes.voice) speak('Ruxsatingiz kerak');
  }
  function closeConfirm() { el.sheet.classList.remove('show'); el.sheet.setAttribute('aria-hidden', 'true'); delete el.sheet.dataset.id; }
  function answerConfirm(ok) { wsSend({ type: 'confirm', id: el.sheet.dataset.id, ok }); closeConfirm(); }
  $('#allowBtn').onclick = () => answerConfirm(true);
  $('#denyBtn').onclick = () => answerConfirm(false);

  // ---------- Kompyuterdagi AI ilovalariga ruxsat ----------
  // Saytga shu kompyuterdan (localhost) kirilganda so'raladi; ruxsat berilsa eslab qolinadi, rad etilsa keyingi kirishda yana so'raladi.
  const localSheet = $('#localSheet');
  let localAsked = false;
  async function checkLocalAccess() {
    if (localAsked) return;
    let info;
    try {
      const res = await fetch('/api/local-access');
      if (!res.ok) return;
      info = await res.json();
    } catch { return; }
    if (!info.local || info.allowed === true) return;
    localAsked = true;
    $('#localApps').innerHTML = info.apps.map((a) => `<li class="${a.ready ? 'ready' : ''}"><span>${esc(a.name)}</span><small>${a.connected ? 'Ulangan' : a.installed ? 'O‘rnatilgan' : 'O‘rnatilmagan'}</small></li>`).join('');
    localSheet.classList.add('show');
    localSheet.setAttribute('aria-hidden', 'false');
    $('#localAllow').focus();
  }
  async function answerLocal(allowed) {
    localSheet.classList.remove('show');
    localSheet.setAttribute('aria-hidden', 'true');
    try {
      const res = await fetch('/api/local-access', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ allowed }) });
      if (!res.ok) throw new Error();
      toast(allowed ? 'Ruxsat berildi: Ali kompyuterdagi AI ilovalaridan foydalanadi' : 'Rad etildi');
    } catch { toast('Ruxsat saqlanmadi'); }
  }
  $('#localAllow').onclick = () => answerLocal(true);
  $('#localDeny').onclick = () => answerLocal(false);

  // ---------- Bo'limlar va menyu ----------
  const VIEW_TITLES = { home: 'Bosh sahifa', chat: 'Chat', monitor: 'Monitoring', agents: 'Agentlar', vault: 'Vault · Xotira', permissions: 'Ruxsatlar' };
  let view = 'home';
  function showView(name) {
    if (!VIEW_TITLES[name]) name = 'home';
    view = name;
    if (name === 'vault') window.AliVault?.refresh();
    if (name === 'permissions') window.AliPermissions?.refresh();
    document.body.classList.toggle('home-dashboard', name === 'home');
    document.querySelectorAll('.view').forEach((v) => { v.hidden = v.id !== 'view-' + name; });
    document.querySelectorAll('.nav-item').forEach((b) => b.classList.toggle('on', b.dataset.view === name));
    $('#mobileTitle').textContent = name === 'chat' ? `${status.assistant || 'Ali'} Chat` : VIEW_TITLES[name];
    if (location.hash.slice(1) !== name) history.replaceState(null, '', '#' + name);
    openSidebar(false);
    if (name === 'monitor' || name === 'agents' || name === 'home') loadMonitor();
    if (name === 'chat') { scrollDown(); if (!isPhone) el.input.focus(); }
  }
  function openSidebar(open) { el.sidebar.classList.toggle('open', open); el.scrim.classList.toggle('show', open); }
  document.querySelectorAll('.nav-item').forEach((b) => b.addEventListener('click', () => showView(b.dataset.view)));
  document.querySelectorAll('[data-goto]').forEach((b) => b.addEventListener('click', () => showView(b.dataset.goto)));
  $('#menuBtn').onclick = () => openSidebar(true);
  el.scrim.onclick = () => openSidebar(false);
  window.addEventListener('hashchange', () => showView(location.hash.slice(1)));

  function newSession() { wsSend({ type: 'new_session' }); }
  $('#newSession').onclick = newSession;
  $('#homeNew').onclick = () => { newSession(); showView('chat'); };
  $('#homeChat').onclick = () => showView('chat');
  $('#sidebarVoice').onclick = () => {
    unlockAudio(); showView('chat'); setMode('voice', true);
    if (recognizer.active) recognizer.stopOnce(); else { stopSpeaking(); recognizer.startOnce(); }
  };
  window.addEventListener('ali-home-ask', (event) => {
    unlockAudio(); showView('chat');
    el.input.value = event.detail;
    el.input.dispatchEvent(new Event('input', { bubbles: true }));
    el.input.focus();
  });
  // Tez topshiriqlar: kerakli agentni tanlab, chatga o'tadi
  document.querySelectorAll('#quick button').forEach((b) => b.addEventListener('click', () => {
    unlockAudio();
    selectAgent(agentInfo(b.dataset.agent) ? b.dataset.agent : '', true);
    showView('chat');
    send(b.dataset.ask);
  }));

  // Mavzu (qorong'i / yorug')
  $('#themeBtn').onclick = () => {
    const cur = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
    const next = cur === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    store.set('theme', next);
    syncAppearance();
    document.querySelector('meta[name="theme-color"]').content = next === 'light' ? '#ffffff' : '#0b0f17';
  };
  function syncAppearance() {
    const light = document.documentElement.dataset.theme === 'light';
    const label = light ? 'Tun rejimiga o‘tish' : 'Kun rejimiga o‘tish';
    $('#themeBtn').setAttribute('aria-label', label); $('#themeBtn').title = label;
    $('#glassBtn').setAttribute('aria-pressed', String(document.documentElement.dataset.glass === 'on'));
  }
  $('#glassBtn').onclick = () => {
    const enabled = document.documentElement.dataset.glass !== 'on';
    document.documentElement.dataset.glass = enabled ? 'on' : 'off'; store.set('glass', enabled); syncAppearance();
  };
  syncAppearance();

  function setLive(on) {
    document.querySelectorAll('.live').forEach((d) => d.classList.toggle('on', on));
    window.AliGalaxy?.setOnline(on);
  }

  function greeting() {
    const h = new Date().getHours();
    const part = h < 5 ? 'Xayrli tun' : h < 12 ? 'Xayrli tong' : h < 18 ? 'Xayrli kun' : 'Xayrli kech';
    return `${part}${status.user ? ', ' + status.user : ''}!`;
  }

  async function loadStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.status === 401) { location.href = '/login'; return; }
      status = await res.json();
    } catch { return; }
    const name = status.assistant || 'Ali';
    $('#brandName').textContent = name.toUpperCase();
    $('#navChat').textContent = `${name} Chat`;
    document.title = name;
    $('#greeting').textContent = greeting();
    window.AliHome?.update(status);
    $('#homeSub').textContent = `${name} va ${(status.agents || []).length} ta agent xizmatingizda`;
    $('#sideMeta').textContent = status.models.claude;
    checkLocalAccess();
    for (const [k, v] of Object.entries(status.models)) document.querySelector(`.pill[data-model="${k}"]`)?.classList.toggle('on', !!v);
    renderAgents();
    const d = status.devices || {};
    const onOff = (v, on, off = 'ulanmagan') => `<b class="small ${v ? 'on' : 'off'}">${esc(v ? on : off)}</b>`;
    $('#tiles').innerHTML = `
      <div class="tile"><span>Telefon ulangan</span><b>${d.phone || 0}</b></div>
      <div class="tile"><span>Kompyuter ulangan</span><b>${d.desktop || 0}</b></div>
      <div class="tile"><span>Eslab qolingan fakt</span><b>${status.facts}</b></div>
      <div class="tile"><span>O‘rganilgan mavzu</span><b>${status.knowledge}</b></div>
      <div class="tile"><span>Asosiy miya</span><b class="small">${esc(status.models.claude)}</b></div>
      <div class="tile"><span>Gemini</span>${onOff(status.models.gemini, status.models.gemini)}</div>
      <div class="tile"><span>Telegram bot</span>${onOff(status.telegram, 'ulangan')}</div>
      <div class="tile"><span>Ovoz</span><b class="small">${esc(status.voice || '—')}</b></div>
      <div class="tile"><span>Instagram</span>${onOff(status.instagram.length, status.instagram.join(', '))}</div>`;
    if (state === 'offline') idleState();
  }

  // ---------- Monitoring va agentlar ----------
  let mon = { agents: [], jobs: [], feed: [] };
  const monFilter = $('#monFilter'), showThink = $('#showThink');
  showThink.checked = store.get('showThink', false);

  const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit', hour12: false });
  const fmtClock = (ts) => new Date(ts * 1000).toLocaleTimeString('uz-UZ', { hour12: false });
  function fmtDur(sec) {
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return `${sec}s`;
    const m = Math.floor(sec / 60);
    return m < 60 ? `${m}m ${sec % 60}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
  }
  const memberOf = (key) => mon.agents.find((a) => a.key === key) || { key, name: key, icon: '🤖' };

  let monTimer = 0;
  function loadMonitor() {
    clearTimeout(monTimer);
    monTimer = setTimeout(async () => {
      try {
        const res = await fetch('/api/monitor');
        if (!res.ok) return;
        mon = await res.json();
      } catch { return; }
      renderMonitor();
    }, 150);
  }

  function agentCard(a, opts = {}) {
    const running = a.status === 'running';
    const stateText = running ? `Ishlayapti · <span data-since="${a.since}">${fmtDur(Date.now() / 1000 - a.since)}</span>` : 'Bo‘sh';
    const last = running ? a.current : a.last;
    return `<div class="agent-card${running ? ' running' : ''}${opts.click ? ' clickable' : ''}" data-key="${esc(a.key)}">
      <div class="ac-head"><span class="ico">${esc(a.icon)}</span><span class="nm">${esc(a.name)}</span></div>
      <div class="ac-state"><i></i>${stateText}</div>
      <div class="ac-last">${last ? (running ? '' : 'Oxirgi: ') + esc(last) : 'Hali ish yo‘q'}</div>
      <div class="ac-stats"><span>Bugun: <b>${a.today}</b></span><span>Jami: <b>${a.total}</b></span></div>
    </div>`;
  }

  function renderMonitor() {
    window.AliHome?.update(null, mon);
    const running = mon.agents.filter((a) => a.status === 'running');
    const badge = $('#runBadge');
    badge.hidden = !running.length;
    badge.textContent = running.length;
    $('#monSub').textContent = running.length ? `${running.length} ta ish bajarilmoqda` : 'Hozir ish yo‘q — hamma bo‘sh';

    // filtr ro'yxati
    const sel = monFilter.value;
    monFilter.innerHTML = '<option value="">Barcha agentlar</option>' +
      mon.agents.map((a) => `<option value="${esc(a.key)}">${esc(a.icon)} ${esc(a.name)}</option>`).join('');
    monFilter.value = mon.agents.some((a) => a.key === sel) ? sel : '';

    window.AliGalaxy?.update(mon);
    window.AliGalaxy?.select(monFilter.value);
    $('#monAgents').innerHTML = mon.agents.map((a) => `<button type="button" class="galaxy-agent-chip${a.status === 'running' ? ' running' : ''}${monFilter.value === a.key ? ' selected' : ''}" data-key="${esc(a.key)}" aria-pressed="${monFilter.value === a.key}"><i></i><span>${esc(a.name)}</span><small>${a.status === 'running' ? 'Ishlayapti' : 'Kutmoqda'}</small></button>`).join('');
    $('#homeAgents').innerHTML = mon.agents.map((a) => agentCard(a, { click: true })).join('');
    renderJobs();
    renderLog();
    renderAgentCards();
  }

  function renderJobs() {
    const box = $('#jobs'), scroll = box.scrollTop;
    const f = monFilter.value;
    const jobs = mon.jobs.filter((j) => !f || j.agent === f);
    const active = jobs.filter((j) => j.status === 'running').length;
    $('#jobsCount').textContent = `${active} faol · ${jobs.length} jami`;
    $('#jobs').innerHTML = jobs.map((j) => {
      const a = memberOf(j.agent);
      const dur = j.status === 'running' ? `<span data-since="${j.start}">${fmtDur(Date.now() / 1000 - j.start)}</span>` : fmtDur((j.end || j.start) - j.start);
      const src = j.source === 'telegram' || j.source === 'avtopilot' ? j.source
        : memberOf(j.source).name !== j.source ? `${memberOf(j.source).name} topshirdi` : 'ilova';
      const jobState = j.status === 'running' ? 'Ishlayapti' : j.status === 'error' ? 'Xato' : 'Yakunlandi';
      return `<div class="job ${esc(j.status)}"><span class="bar" title="${jobState}" aria-label="${jobState}"></span><div class="job-main">
        <div class="job-top"><span>${esc(a.icon)}</span><b>${esc(a.name)}</b><span class="src">${esc(src)}</span><time>${fmtTime(j.start)} · ${dur}</time></div>
        <div class="job-text">${esc(j.text || '—')}${j.steps ? ` · ${j.steps} ta amal` : ''}</div></div></div>`;
    }).join('') || '<div class="empty">Hali ishlar yo‘q. Chatda biror narsa so‘rang.</div>';
    box.scrollTop = scroll;
  }

  function logRow(e) {
    const a = memberOf(e.agent);
    const who = e.kind === 'user' ? '👤 Siz' : `${a.icon} ${a.name}`;
    return `<div class="log ${e.kind}"><time>${fmtClock(e.t)}</time><div><span class="who">${esc(who)}</span> <span class="msg-t">${esc(e.text)}</span></div></div>`;
  }
  function visibleLog(e) { return (showThink.checked || e.kind !== 'think') && (!monFilter.value || e.agent === monFilter.value); }
  function renderLog() {
    const box = $('#liveLog');
    const scroll = box.scrollTop;
    const rows = mon.feed.filter(visibleLog).slice(-150).reverse();
    box.innerHTML = rows.map(logRow).join('') || '<div class="empty">Lenta bo‘sh. Ali ishlay boshlasa, shu yerda jonli ko‘rinadi.</div>';
    box.scrollTop = scroll;
  }
  function appendLog(e) {
    mon.feed.push(e);
    if (mon.feed.length > 400) mon.feed.shift();
    if (!visibleLog(e)) return;
    const box = $('#liveLog');
    const scroll = box.scrollTop, height = box.scrollHeight;
    box.querySelector('.empty')?.remove();
    box.insertAdjacentHTML('afterbegin', logRow(e));
    if (scroll < 8) box.firstElementChild.classList.add('log-new');
    else box.scrollTop = scroll + box.scrollHeight - height;
    while (box.children.length > 150) box.lastElementChild.remove();
  }
  function filterMonitoring(key) {
    monFilter.value = key;
    window.AliGalaxy?.select(key);
    $('#monAgents').querySelectorAll('[data-key]').forEach((b) => {
      b.classList.toggle('selected', b.dataset.key === key);
      b.setAttribute('aria-pressed', String(b.dataset.key === key));
    });
    renderJobs(); renderLog();
  }
  monFilter.addEventListener('change', () => filterMonitoring(monFilter.value));
  $('#galaxyMonitor').addEventListener('galaxy-select', (e) => filterMonitoring(monFilter.value === e.detail.key ? '' : e.detail.key));
  $('#monAgents').addEventListener('click', (e) => {
    const chip = e.target.closest('[data-key]');
    if (chip) filterMonitoring(monFilter.value === chip.dataset.key ? '' : chip.dataset.key);
  });
  setInterval(() => { if ((view === 'monitor' || view === 'agents') && !document.hidden) loadMonitor(); }, 4000);
  showThink.addEventListener('change', () => { store.set('showThink', showThink.checked); renderLog(); });

  function renderAgentCards() {
    const learning = mon.learning || { agents: {} };
    $('#learningState').textContent = learning.enabled ? `Har ${learning.interval_hours} soatda bilim yangilash` : 'Avtomatik o‘rganish o‘chiq';
    $('#learningInfo').textContent = learning.enabled ? 'Server ishlaganda tekshiradi · xatoda 1 soatdan keyin qayta urinadi · API sarfi mavjud' : 'Mavzularni agent sozlamalarida belgilash mumkin.';
    const learningMarkup = (a) => {
      if (a.key === 'ali') return `<div class="agent-learning"><b>Jamoaning markaziy yordamchisi</b><p>Vazifalarni taqsimlaydi va agentlar bilimidan foydalanadi.</p>${improveMarkup((learning.agents.ali || {}).improve)}</div>`;
      const l = learning.agents[a.key] || {}, k = l.knowledge || { count: 0, latest: [] };
      const date = t => t ? new Date(t * 1000).toLocaleString('uz-UZ', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) : 'Hali yo‘q';
      const labels = {running:'O‘rganmoqda',updated:'Bilim qo‘shildi',checked:'Tekshirildi',error:'O‘rganishda xato'};
      return `<div class="agent-learning ${l.status === 'error' ? 'has-error' : ''}"><b>${labels[l.status] || 'Navbat kutilmoqda'}</b><span>${k.count} ta bilim</span><p>Oxirgi tekshiruv: ${date(l.last_attempt)}</p><details><summary>Bilimlar va mavzular</summary><p>${esc((l.topics || []).join(' · '))}</p><p>Keyingi urinish: ${learning.enabled ? (l.next_at ? date(l.next_at) : 'Navbatdagi tekshiruvda') : 'O‘chirilgan'}</p>${k.latest.map(n => `<p class="knowledge-topic">${esc(n.topic)} <small>${esc(n.created_at.slice(0,10))}</small></p>`).join('')}${l.summary ? `<p>${esc(l.summary)}</p>` : ''}${improveMarkup(l.improve)}</details></div>`;
    };
    const improveMarkup = (im) => {
      if (!learning.self_improve || !im || im.score == null) return '';
      const st = {improved:'Rivojlantirildi',healthy:'Sog‘lom',checked:'Kamchilik bor',error:'Tahlilda xato'}[im.status] || '';
      return `<p><b>🌱 Rivojlanish: ${im.score}/100</b> · ${st}</p>${(im.fixed || []).map(f => `<p>✔ ${esc(f)}</p>`).join('')}${(im.issues || []).map(i => `<p>⚠ ${esc(i)}</p>`).join('')}${im.summary ? `<p>${esc(im.summary)}</p>` : ''}`;
    };
    const openKeys = new Set([...$('#agentCards').querySelectorAll('details[open]')].map(d => d.closest('[data-agent-card]').dataset.agentCard));
    $('#agentCards').innerHTML = mon.agents.map((a) => `
      <div class="agent-card${a.status === 'running' ? ' running' : ''}" data-agent-card="${esc(a.key)}">
        <div class="ac-head"><span class="ico">${esc(a.icon)}</span><div><div class="nm">${esc(a.name)}</div>
          <div class="ac-state"><i></i>${a.status === 'running' ? 'Ishlayapti' : 'Bo‘sh'} · bugun ${a.today}, jami ${a.total}</div></div></div>
        <div class="ac-desc">${esc(a.description || '')}</div>
        ${learningMarkup(a)}
        <div class="ac-actions">
          <button class="btn primary" data-chat="${esc(a.key)}">Ali orqali buyruq →</button>
          ${a.key !== 'ali' ? `<button class="btn ghost" data-edit="${esc(a.key)}">Tahrirlash</button>` : ''}
        </div>
      </div>`).join('');
    $('#agentCards').querySelectorAll('[data-agent-card]').forEach(card => { if (openKeys.has(card.dataset.agentCard) && card.querySelector('details')) card.querySelector('details').open = true; });
  }
  $('#agentCards').addEventListener('click', (e) => {
    const b = e.target.closest('[data-chat]');
    if (b) { selectAgent(b.dataset.chat === 'ali' ? '' : b.dataset.chat, true); showView('chat'); return; }
    const ed = e.target.closest('[data-edit]');
    if (ed) openAgentForm(ed.dataset.edit);
  });

  // ---------- Agent yaratish / tahrirlash ----------
  const agentSheet = $('#agentSheet'), agentForm = $('#agentForm');
  let editing = null;
  async function openAgentForm(key) {
    let data;
    try { data = await (await fetch('/api/agents')).json(); } catch { toast('Server bilan aloqa yo‘q'); return; }
    const a = key ? data.agents.find((x) => x.key === key) : null;
    editing = a ? a.key : null;
    $('#agentFormTitle').textContent = a ? `${a.icon} ${a.name} — tahrirlash` : 'Yangi agent';
    const f = agentForm.elements;
    f.icon.value = a?.icon || '🤖';
    f.name.value = a?.name || '';
    f.key.value = a?.key || '';
    f.key.disabled = !!a;
    f.description.value = a?.description || '';
    f.prompt.value = a?.prompt || '';
    f.learn.value = (a?.learn || []).join('\n');
    const chosen = new Set(a?.tools || ['web_search', 'search_knowledge', 'save_knowledge', 'get_datetime']);
    $('#toolPicks').innerHTML = data.tools.map((t) => `<label title="${esc(t.description)}">
      <input type="checkbox" value="${esc(t.name)}"${chosen.has(t.name) ? ' checked' : ''}>
      ${esc(TOOL_NAMES[t.name] || t.name)}${t.dangerous ? ' <span class="warn" title="Tasdiq so‘raladi">⚠</span>' : ''}</label>`).join('');
    $('#agentDelete').hidden = !a;
    agentSheet.classList.add('show');
    agentSheet.setAttribute('aria-hidden', 'false');
  }
  function closeAgentForm() { agentSheet.classList.remove('show'); agentSheet.setAttribute('aria-hidden', 'true'); }
  $('#newAgentBtn').onclick = () => openAgentForm(null);
  $('#agentFormClose').onclick = closeAgentForm;
  agentSheet.addEventListener('click', (e) => { if (e.target === agentSheet) closeAgentForm(); });
  agentForm.elements.name.addEventListener('input', (e) => {
    if (editing) return; // kalit faqat yangi agentda nomdan avtomatik yasaladi
    const map = { 'ʻ': '', "'": '', '‘': '', 'ʼ': '', ' ': '-' };
    agentForm.elements.key.value = e.target.value.toLowerCase().replace(/[ʻ'‘ʼ ]/g, (c) => map[c])
      .replace(/[^a-z0-9_-]/g, '').slice(0, 30);
  });
  agentForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = agentForm.elements;
    const body = {
      key: editing || f.key.value.trim(), icon: f.icon.value.trim(), name: f.name.value.trim(),
      description: f.description.value.trim(), prompt: f.prompt.value,
      learn: f.learn.value.split('\n').map((x) => x.trim()).filter(Boolean),
      tools: [...$('#toolPicks').querySelectorAll('input:checked')].map((i) => i.value),
    };
    const res = await fetch('/api/agents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const out = await res.json().catch(() => ({}));
    if (!res.ok) { toast(out.error || 'Saqlanmadi'); return; }
    closeAgentForm();
    toast(`${out.agent.icon} ${out.agent.name} saqlandi`);
  });
  $('#agentDelete').onclick = async () => {
    if (!editing || !confirm('Agent o‘chirilsinmi?')) return;
    await fetch('/api/agents/' + encodeURIComponent(editing), { method: 'DELETE' });
    closeAgentForm();
    toast('Agent o‘chirildi');
  };
  $('#homeAgents').addEventListener('click', (e) => {
    const c = e.target.closest('.agent-card');
    if (c) { selectAgent(c.dataset.key === 'ali' ? '' : c.dataset.key, true); showView('chat'); }
  });

  // ishlayotgan vaqtni har soniyada yangilash
  setInterval(() => {
    if (document.hidden) return;
    const now = Date.now() / 1000;
    document.querySelectorAll('[data-since]').forEach((s) => { s.textContent = fmtDur(now - Number(s.dataset.since)); });
  }, 1000);

  // ---------- Joylashuv ----------
  let geoWatch = null, lastGeoSent = 0, lastPos = null;
  function sendLocationNow() { if (lastPos) { wsSend({ type: 'location', ...lastPos }); lastGeoSent = Date.now(); } }
  function startGeo() {
    if (!('geolocation' in navigator)) { toast('Joylashuv qo‘llab-quvvatlanmaydi'); return; }
    geoWatch = navigator.geolocation.watchPosition((p) => {
      lastPos = { lat: p.coords.latitude, lon: p.coords.longitude, accuracy: Math.round(p.coords.accuracy) };
      if (Date.now() - lastGeoSent > 60000) sendLocationNow();
    }, (err) => { if (err.code === 1) { toast('Joylashuvga ruxsat berilmadi'); el.geo.checked = false; store.set('geo', false); } },
    { enableHighAccuracy: true, maximumAge: 30000 });
  }
  function stopGeo() { if (geoWatch !== null) navigator.geolocation.clearWatch(geoWatch); geoWatch = null; }
  el.geo.checked = store.get('geo', true);
  el.geo.addEventListener('change', () => { store.set('geo', el.geo.checked); el.geo.checked ? startGeo() : stopGeo(); });
  if (el.geo.checked) startGeo();

  if (isPhone && 'Notification' in window && Notification.permission === 'default') {
    document.addEventListener('pointerdown', () => Notification.requestPermission().catch(() => {}), { once: true });
  }

  if (!window.isSecureContext) {
    setTimeout(() => toast('Mikrofon va joylashuv uchun HTTPS kerak — tunnel.bat havolasidan oching', 6000), 1200);
  }

  showView(location.hash.slice(1) || 'home');
  connect();
})();
