/* Ali — veb interfeys */
(() => {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const isPhone = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  const DEVICE = isPhone ? 'phone' : 'desktop';

  const el = {
    stage: $('#stage'), feed: $('#feed'), state: $('#stateLabel'), live: $('#liveTranscript'),
    input: $('#input'), composer: $('#composer'), mic: $('#micBtn'), file: $('#fileInput'),
    attachments: $('#attachments'), drawer: $('#drawer'), scrim: $('#scrim'), stats: $('#stats'),
    sheet: $('#confirmSheet'), toast: $('#toast'), player: $('#player'), geo: $('#geoToggle'),
  };

  // ---------- Saqlanadigan sozlamalar ----------
  const store = {
    get(k, d) { try { const v = localStorage.getItem('ali.' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('ali.' + k, JSON.stringify(v)); } catch { /* yo'q */ } },
  };
  const modes = { deep: store.get('deep', false), super: store.get('super', false), voice: store.get('voice', true), wake: false };

  let status = { wake_words: ['ali'], stt_language: 'uz-UZ', server_stt: false, assistant: 'Ali', user: '' };
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
      return (state === 'thinking' || state === 'working') ? `rgba(255,181,71,${a})`
        : state === 'offline' ? `rgba(110,140,160,${a})` : `rgba(0,229,255,${a})`;
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

    // Brauzer tanimasa: yozib, serverga (OpenAI) yuborish
    async function startServerRecording() {
      if (!status.server_stt) { toast('Ovozni tanish uchun Chrome yoki OPENAI_API_KEY kerak'); return; }
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
    web_search: 'Internetdan qidirish', consult_experts: 'GPT + Gemini maslahati', run_powershell: 'PowerShell',
    take_screenshot: 'Ekran rasmi', get_weather: 'Ob-havo', get_my_location: 'Joylashuv', open_application: 'Ilova ochish',
    open_website: 'Sayt ochish', instagram_analytics: 'Instagram analitika', instagram_competitor: 'Raqobatchi tahlili',
    instagram_comments: 'Izohlar', save_knowledge: 'Bilimni saqlash', search_knowledge: 'Bilimlar bazasi',
    remember_fact: 'Eslab qolish', set_reminder: 'Eslatma', phone_open_url: 'Telefonda ochish', phone_notify: 'Telefonga xabar',
    system_status: 'Tizim holati', get_datetime: 'Vaqt',
  };

  function scrollDown() { requestAnimationFrame(() => { el.stage.scrollTop = el.stage.scrollHeight; }); }
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

  function addTurn(id) {
    const div = document.createElement('div');
    div.className = 'msg ai';
    div.innerHTML = `
      <div class="card">
        <div class="card-head">${esc(status.assistant || 'Ali')}<span class="spinner"></span></div>
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
    ws.onopen = () => { retry = 0; idleState(); loadStatus(); sendLocationNow(); };
    ws.onclose = (e) => {
      if (e.code === 4401) { location.href = '/login'; return; }
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
      case 'devices': loadStatus(); break;
      case 'user':
        if (m.from === myDeviceId) break; // o'zimizniki allaqachon ko'rsatilgan
        addUser(m.text, m.images || [], false, m.from);
        addTurn(m.id);
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
    if (!wsSend({ type: 'ask', id, text, images, deep: modes.deep, super: modes.super })) { toast('Server bilan aloqa yo‘q'); return; }
    busy = true;
    addUser(text, attachments.map((a) => a.src), true);
    addTurn(id);
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
      const labels = { deep: ['Chuqur fikrlash yoqildi', 'Tezkor rejim'], super: ['Super miya: Claude + GPT + Gemini', 'Faqat Claude'],
        voice: ['Javoblar ovoz bilan o‘qiladi', 'Ovoz o‘chirildi'], wake: [`“${status.wake_words[0]}” deb chaqiring`, 'Doimiy tinglash o‘chdi'] };
      toast(labels[name][modes[name] ? 0 : 1]);
      if (name === 'voice' && !modes.voice) stopSpeaking();
    });
  });

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

  // ---------- Menyu ----------
  function openDrawer(open) {
    el.drawer.classList.toggle('open', open); el.scrim.classList.toggle('show', open);
    el.drawer.setAttribute('aria-hidden', String(!open));
    if (open) loadStatus();
  }
  $('#menuBtn').onclick = () => openDrawer(true);
  $('#closeDrawer').onclick = () => openDrawer(false);
  el.scrim.onclick = () => openDrawer(false);
  $('#newSession').onclick = () => { wsSend({ type: 'new_session' }); openDrawer(false); };

  async function loadStatus() {
    try {
      const res = await fetch('/api/status');
      if (res.status === 401) { location.href = '/login'; return; }
      status = await res.json();
    } catch { return; }
    $('#brandName').textContent = (status.assistant || 'Ali').toUpperCase();
    document.title = status.assistant || 'Ali';
    for (const [k, v] of Object.entries(status.models)) document.querySelector(`.pill[data-model="${k}"]`)?.classList.toggle('on', !!v);
    const d = status.devices || {};
    el.stats.innerHTML = `
      <div class="stat"><b>${d.phone || 0}</b><span>Telefon ulangan</span></div>
      <div class="stat"><b>${d.desktop || 0}</b><span>Kompyuter ulangan</span></div>
      <div class="stat"><b>${status.facts}</b><span>Eslab qolingan fakt</span></div>
      <div class="stat"><b>${status.knowledge}</b><span>O‘rganilgan mavzu</span></div>
      <div class="stat wide"><span>Asosiy miya</span><b>${esc(status.models.claude)}</b></div>
      <div class="stat wide"><span>Maslahatchilar</span><b>${esc([status.models.openai, status.models.gemini].filter(Boolean).join(' · ') || 'ulanmagan')}</b></div>
      <div class="stat wide"><span>Telegram bot</span><b>${status.telegram ? 'ulangan' : 'ulanmagan'}</b></div>
      <div class="stat wide"><span>Ovoz</span><b>${esc(status.voice || '')}</b></div>
      <div class="stat wide"><span>Instagram</span><b>${esc(status.instagram.join(', ') || 'ulanmagan')}</b></div>`;
    if (state === 'offline') idleState();
  }

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

  connect();
})();
