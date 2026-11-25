(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const idea = $('creativeIdea'), result = $('creativeResult'), button = $('creativePlan');
  if (!idea || !result || !button) return;
  let timer = 0, active = false, shownStory = '';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function render(job) {
    const story = job.story;
    const key = JSON.stringify(story || null);
    if (story && shownStory !== key) {
      shownStory = key;
      result.innerHTML = `<div class="creative-story-head"><div><span class="creative-kicker">${esc(story.style || 'AI video')} · ${story.scenes.length} SAHNA</span><h2>${esc(story.title || 'Ssenariyingiz')}</h2><p>${esc(story.hook || '')}</p></div>${job.character ? `<img class="creative-character" src="${esc(job.character)}" alt="Yaratilgan qahramon">` : ''}</div><div class="creative-scenes">${story.scenes.map((scene, i) => `<article class="creative-scene"><span class="creative-scene-no">${String(i + 1).padStart(2, '0')}</span><div><b>${esc(scene.big || `Sahna ${i + 1}`)}</b><p>${esc(scene.voice || '')}</p></div></article>`).join('')}</div><div class="creative-progress" role="status"><span class="creative-spinner"></span><span id="creativeMessage">${esc(job.message)}</span></div><div id="creativeVideo"></div>`;
    } else {
      const msg = $('creativeMessage'); if (msg) msg.textContent = job.message || '';
      const portrait = result.querySelector('.creative-character');
      if (portrait && job.character && portrait.getAttribute('src') !== job.character) portrait.src = job.character;
      if (!portrait && job.character) {
        const head = result.querySelector('.creative-story-head');
        if (head) head.insertAdjacentHTML('beforeend', `<img class="creative-character" src="${esc(job.character)}" alt="Yaratilgan qahramon">`);
      }
    }
    if (job.status === 'done') {
      result.querySelector('.creative-progress')?.remove();
      const box = $('creativeVideo');
      if (box && !box.dataset.ready) {
        box.dataset.ready = 'yes';
        const url = '/api/outbox/' + encodeURIComponent(job.video);
        box.innerHTML = `<div class="creative-done"><b>✓ Video tayyor</b><a class="creative-download" href="${url}" download>⬇ Yuklab olish</a></div><video class="creative-player" controls playsinline src="${url}"></video>`;
      }
    }
    if (job.status === 'error') {
      const progress = result.querySelector('.creative-progress');
      if (progress) progress.outerHTML = `<div class="creative-error" role="alert">${esc(job.message || 'Video yaratishda xatolik yuz berdi')}</div>`;
    }
  }
  async function poll(id) {
    if (!active) return;
    try {
      const response = await fetch('/api/creative-video/' + encodeURIComponent(id));
      const job = await response.json();
      if (!response.ok) throw new Error(job.error || 'Ish holatini olib bo‘lmadi');
      render(job);
      if (job.status === 'done' || job.status === 'error') { active = false; button.disabled = false; button.textContent = '✦ Yana video yaratish'; return; }
    } catch (error) {
      result.innerHTML = `<div class="creative-error" role="alert">${esc(error.message)}</div>`;
      active = false; button.disabled = false; button.textContent = '✦ Qayta urinish'; return;
    }
    timer = window.setTimeout(() => poll(id), 1800);
  }
  button.addEventListener('click', async () => {
    if (active) return;
    if (!idea.value.trim()) { idea.focus(); return; }
    clearTimeout(timer); active = true; shownStory = '';
    button.disabled = true; button.textContent = 'Ali g‘oyani tushunyapti…';
    result.innerHTML = '<div class="creative-empty"><span class="creative-spinner"></span><h2>Ali hikoyangizni rejalashtiryapti</h2><p>Ssenariy va qahramonlar tayyorlanmoqda…</p></div>';
    try {
      const response = await fetch('/api/creative-video', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idea: idea.value.trim(), style: $('creativeStyle').value, format: $('creativeFormat').value }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Video yaratishni boshlash imkoni bo‘lmadi');
      button.textContent = 'Video tayyorlanmoqda…'; poll(data.id);
    } catch (error) {
      result.innerHTML = `<div class="creative-error" role="alert">${esc(error.message)}</div>`;
      active = false; button.disabled = false; button.textContent = '✦ Qayta urinish';
    }
  });
})();
