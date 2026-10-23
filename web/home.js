(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const key = 'ali.home.notes.v1';
  const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tashkent', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  let notes = [];
  try { const saved = JSON.parse(localStorage.getItem(key) || '[]'); if (Array.isArray(saved)) notes = saved.filter(n => n && typeof n.id === 'string' && typeof n.text === 'string' && [0,1,2,3].includes(n.priority)); } catch {}
  function save(next) {
    try { localStorage.setItem(key, JSON.stringify(next)); notes = next; render(); return true; }
    catch { $('noteFeedback').textContent = 'Saqlanmadi. Brauzer xotirasi mavjud emas yoki to‘lgan.'; return false; }
  }
  const ask = text => window.dispatchEvent(new CustomEvent('ali-home-ask', { detail: text }));
  function render() {
    const day = today(), plan = notes.filter(n => n.day === day);
    $('homeDate').textContent = new Intl.DateTimeFormat('uz-UZ', { timeZone: 'Asia/Tashkent', weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }).format(new Date());
    $('dayCount').textContent = `${plan.filter(n => n.done).length}/${plan.length}`;
    $('inboxCount').textContent = notes.filter(n => !n.done).length;
    $('inboxHint').textContent = `${notes.filter(n => !n.done).length} ta yozuv`;
    $('planList').replaceChildren(); $('noteList').replaceChildren();
    if (!plan.length) {
      const empty = document.createElement('div'); empty.className = 'home-empty';
      const title = document.createElement('strong'); title.textContent = 'Bugun uchun reja hali yo‘q';
      const desc = document.createElement('p'); desc.textContent = 'Yozuv qo‘shing. Muhimligiga qarab 3 ta vazifani kun rejasiga tanlaymiz.';
      const button = document.createElement('button'); button.className = 'btn primary'; button.textContent = 'Reja tuzish'; button.onclick = makePlan;
      empty.append(title, desc, button); $('planList').append(empty);
    }
    for (const note of plan) {
      const label = document.createElement('label'); label.className = 'home-task';
      const check = document.createElement('input'); check.type = 'checkbox'; check.checked = !!note.done;
      check.onchange = () => { if (!save(notes.map(n => n.id === note.id ? {...n, done: check.checked} : n))) check.checked = !!note.done; };
      const text = document.createElement('span'); text.textContent = note.text;
      label.append(check, text); $('planList').append(label);
    }
    for (const note of notes.filter(n => !n.done).sort((a,b) => a.priority - b.priority)) {
      const row = document.createElement('div'); row.className = 'home-note';
      const text = document.createElement('span'); text.textContent = note.text;
      const priority = document.createElement('small'); priority.textContent = `P${note.priority}`;
      const remove = document.createElement('button'); remove.textContent = '×'; remove.setAttribute('aria-label', `Yozuvni o‘chirish: ${note.text}`); remove.onclick = () => save(notes.filter(n => n.id !== note.id));
      row.append(text, priority, remove); $('noteList').append(row);
    }
  }
  function makePlan() {
    const day = today(), existing = notes.filter(n => n.day === day).length;
    const candidates = notes.filter(n => !n.done && n.day !== day).sort((a,b) => a.priority - b.priority).slice(0, Math.max(0, 3 - existing));
    if (!candidates.length) { $('noteFeedback').textContent = existing ? 'Bugungi reja tayyor. Vazifalarni belgilab boring.' : 'Avval reja uchun yozuv kiriting.'; $('noteText').focus(); return; }
    const ids = new Set(candidates.map(n => n.id)); save(notes.map(n => ids.has(n.id) ? {...n, day} : n));
  }
  $('noteForm').addEventListener('submit', event => {
    event.preventDefault(); const text = $('noteText').value.trim(); if (!text) return;
    if (save([...notes, {id: crypto.randomUUID(), text, priority: Number(new FormData(event.target).get('priority')), done: false}])) { $('noteText').value = ''; $('noteFeedback').textContent = 'Shu brauzerda saqlandi.'; }
  });
  $('dayPlan').onclick = makePlan;
  $('planWithAli').onclick = () => ask('Kunimni rejalashtirishga yordam ber.' + (notes.some(n => !n.done) ? '\nMening yozuvlarim:\n' + notes.filter(n => !n.done).map(n => `P${n.priority}: ${n.text}`).join('\n') : ' Avval maqsadlarimni so‘ra.'));
  $('openInbox').onclick = () => $('noteText').focus();
  document.querySelectorAll('[data-home-ask]').forEach(button => button.onclick = () => ask(button.dataset.homeAsk));
  window.AliHome = { update(status, mon) { if (status && Number.isFinite(status.facts)) $('memoryCount').textContent = status.facts; if (mon) $('activeCount').textContent = mon.agents.filter(a => a.status === 'running').length; } };
  render(); document.addEventListener('visibilitychange', () => { if (!document.hidden) render(); });

  // ---------- Bugun dunyoda: ob-havo, kripto, bozorlar, yangiliklar ----------
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const body = (id) => document.querySelector(`#${id} .world-body`);
  const fmt = (n, d = 2) => Number(n).toLocaleString('en-US', { maximumFractionDigits: n >= 1000 ? 0 : n >= 1 ? d : 4 });
  const pct = (c) => { const e = el('em', c >= 0 ? 'up' : 'down', `${c >= 0 ? '▲' : '▼'} ${Math.abs(c).toFixed(2)}%`); return e; };
  let world = null, newsTab = 'uzbekiston';

  function renderWeather(w) {
    const b = body('worldWeather'); b.replaceChildren();
    if (!w) { b.textContent = 'Ob-havo ma’lumoti olinmadi'; return; }
    const now = el('div', 'w-now'); now.append(el('span', 'ico', w.icon));
    const t = el('div'); t.append(el('b', '', `${w.temp}°`), el('p', '', `${w.place} · ${w.text}`), el('p', '', `His qilinadi ${w.feels}° · shamol ${w.wind} km/s · namlik ${w.humidity}%`));
    now.append(t);
    const days = el('div', 'w-days');
    w.days.forEach((d, i) => { const c = el('div'); c.append(el('small', '', i ? new Date(d.date).toLocaleDateString('uz-UZ', { weekday: 'short' }) : 'Bugun'), el('span', '', `${d.icon} ${d.max}°/${d.min}°`), el('small', '', `💧${d.rain ?? 0}%`)); days.append(c); });
    b.append(now, days);
  }
  function renderTicks(id, rows, label) {
    const b = body(id); b.replaceChildren();
    if (!rows.length) { b.textContent = 'Ma’lumot olinmadi'; return; }
    for (const r of rows) { const row = el('div', 'tick'); const name = el('div'); name.append(el('div', '', label(r)[0]), el('span', '', label(r)[1])); row.append(name, el('b', '', fmt(r.price)), pct(r.change)); b.append(row); }
  }
  function renderNews() {
    const b = body('worldNews'); b.replaceChildren();
    const items = world?.news?.[newsTab] || [];
    if (!items.length) { b.textContent = 'Yangiliklar olinmadi'; return; }
    for (const n of items) {
      const a = el('a', 'news-item', n.title); a.href = n.link; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.append(el('small', '', `${n.source}${n.ts ? ' · ' + new Date(n.ts * 1000).toLocaleString('uz-UZ', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' }) : ''}`));
      b.append(a);
    }
  }
  async function loadWorld(force) {
    try { const r = await fetch('/api/dashboard' + (force ? '?refresh=1' : '')); if (!r.ok) return; world = await r.json(); } catch { return; }
    $('worldUpdated').textContent = 'Yangilandi: ' + new Date(world.updated * 1000).toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' });
    renderWeather(world.weather);
    renderTicks('worldCrypto', world.crypto, (r) => [r.symbol, 'USDT']);
    renderTicks('worldMarkets', world.markets, (r) => [r.name, r.kind]);
    renderNews();
  }
  document.querySelectorAll('.news-tabs button').forEach((b) => b.onclick = () => {
    newsTab = b.dataset.news; document.querySelectorAll('.news-tabs button').forEach((x) => x.classList.toggle('on', x === b)); renderNews();
  });
  $('worldRefresh').onclick = () => loadWorld(true);

  // ---------- Ali xotirasi: nima va qayerda saqlanadi ----------
  async function loadMemory() {
    let m; try { const r = await fetch('/api/memory-info'); if (!r.ok) return; m = await r.json(); } catch { return; }
    const b = body('homeMemory'); b.replaceChildren();
    const grid = el('div', 'mem-grid');
    [[m.messages, 'yozishma'], [m.agent_tasks, 'agent ishi'], [m.facts, 'fakt'], [m.knowledge, 'o‘rganilgan bilim']].forEach(([n, t]) => { const c = el('div'); c.append(el('b', '', n), el('span', '', t)); grid.append(c); });
    const paths = el('div', 'mem-paths');
    [['Asl xotira (baza):', m.db], ['O‘qiladigan nusxa (har kun Markdown):', m.journal], ['Agentlar va ularning tajribasi:', m.agents_dir], ...(m.obsidian ? [['Obsidian ombori:', m.obsidian]] : [])].forEach(([t, p]) => { const line = el('div'); line.append(el('b', '', t + ' '), document.createTextNode(p)); paths.append(line); });
    const team = el('div', 'mem-team');
    for (const a of m.team) team.append(el('span', '', `${a.icon} ${a.name}: ${a.lessons} saboq · ${a.knowledge} bilim`));
    b.append(grid, paths, team);
    $('memoryOpen').hidden = !m.local;
    if (m.obsidian_uri) {  // Obsidian'da ochish: ilova o'zi ochiladi
      const ob = el('a', 'link', 'Obsidian’da ochish →'); ob.href = m.obsidian_uri; ob.style.marginLeft = '12px';
      $('memoryOpen').parentElement.querySelector('.obsidian-link')?.remove(); ob.classList.add('obsidian-link');
      $('memoryOpen').after(ob);
    }
  }
  $('memoryOpen').onclick = () => fetch('/api/memory-open', { method: 'POST' });

  const refreshHome = () => { if (!document.getElementById('view-home').hidden) { loadWorld(); loadMemory(); } };
  loadWorld(); loadMemory();  // birinchi ochilishda doim (bo'lim hali ko'rsatilmagan bo'lishi mumkin)
  setInterval(refreshHome, 10 * 60 * 1000);
  window.addEventListener('hashchange', () => { if (location.hash === '#home') refreshHome(); });
})();
