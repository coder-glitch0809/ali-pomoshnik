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
})();
