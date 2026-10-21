/* Monitoring-only renderer. Activity comes from /api/monitor, never demo timers. */
(() => {
  'use strict';
  const root = document.querySelector('#galaxyMonitor');
  if (!root) return;
  const canvas = root.querySelector('canvas'), ctx = canvas.getContext('2d');
  if (!ctx) return;
  const layer = root.querySelector('#galaxyAgents');
  const core = root.querySelector('#galaxyCore');
  const motion = root.querySelector('#galaxyMotion');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const nodes = new Map();
  let members = [], active = new Set(), selected = '', online = false;
  // Agent answered: the beam stays a moment longer and energy flows back to Ali.
  const RETURN_MS = 3200, returning = new Map();
  let runningJobs = new Map();
  let w = 1, h = 1, time = 0, previous = 0, raf = 0, visible = false, paused = reduced.matches;
  let seed = 3125;
  function random() { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }
  const stars = Array.from({ length: 180 }, () => ({ x: random(), y: random(), r: .3 + random(), a: .15 + random() * .55, phase: random() * 7 }));

  // Static galaxy texture; only starlight and task signals animate.
  const nebula = document.createElement('canvas');
  nebula.width = nebula.height = 1100;
  const g = nebula.getContext('2d');
  g.translate(550, 550);
  const mist = g.createRadialGradient(0, 0, 5, 0, 0, 500);
  mist.addColorStop(0, '#d4b77740'); mist.addColorStop(.16, '#7a8cb845'); mist.addColorStop(.55, '#4a689426'); mist.addColorStop(1, '#17284700');
  g.fillStyle = mist; g.fillRect(-550, -550, 1100, 1100);
  g.globalCompositeOperation = 'screen';
  for (let i = 0; i < 15500; i++) {
    const radius = 25 + Math.pow(random(), .65) * 460;
    const arm = i % 3;
    const angle = arm * Math.PI * 2 / 3 + radius * .014 + (random() - .5) * (.3 + radius / 1000);
    const scatter = (random() + random() - 1) * 28;
    const x = Math.cos(angle) * radius + scatter, y = Math.sin(angle) * radius + scatter;
    const warm = radius < 100;
    const size = .4 + random() * 1.5;
    g.fillStyle = warm ? `rgba(255,222,157,${.1 + random() * .45})` : `rgba(${160 + Math.floor(random() * 65)},${180 + Math.floor(random() * 55)},255,${.06 + random() * .38})`;
    g.beginPath(); g.arc(x, y, size, 0, Math.PI * 2); g.fill();
    if (i % 45 === 0) {
      g.fillStyle = '#b3cfff08'; g.beginPath(); g.arc(x, y, 12 + random() * 20, 0, Math.PI * 2); g.fill();
    }
  }
  const gold = g.createRadialGradient(0, 0, 0, 0, 0, 110);
  gold.addColorStop(0, '#fff6c8ee'); gold.addColorStop(.25, '#f3d5a477'); gold.addColorStop(1, '#f3d5a400');
  g.scale(1.25, .65); g.fillStyle = gold; g.fillRect(-120, -120, 240, 240);

  function resize() {
    w = root.clientWidth; h = root.clientHeight;
    if (!w || !h) return;
    fitAgents();
    const dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }
  // Agents sit on a ring (ellipse) around Ali, evenly spaced, starting at the top.
  // Many agents (more than 10) use two rings, alternating inner and outer.
  function ring(count) {
    const card = w < 700 ? 64 : 92;
    const rx = Math.max(140, w / 2 - card - 20), ry = Math.max(150, h / 2 - card - (w < 700 ? 60 : 30));
    const two = count > 10;
    return { rx, ry, two, inner: two ? .62 : 1 };
  }
  function fitAgents() {
    root.style.minHeight = `${members.length > 10 ? 760 : 600}px`;
  }
  function position(index, count) {
    const { rx, ry, two, inner } = ring(count);
    const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, count);
    const k = two && index % 2 ? inner : 1;
    return { x: w / 2 + Math.cos(angle) * rx * k, y: h / 2 + 12 + Math.sin(angle) * ry * k };
  }
  // Energy link Ali -> agent while the agent's task is running: glowing conduit, crackling
  // lightning, energy packets flowing towards the agent and a pulsing impact at the agent.
  const BOT_COLORS = { coder: '#79dfff', creator: '#d0a3ff', mentor: '#7ce5bc', analyst: '#ffc880' };
  function noise(n) { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
  function bolt(x, y, ex, ey, jitter, key) {
    const dx = ex - x, dy = ey - y, len = Math.hypot(dx, dy) || 1, nx = -dy / len, ny = dx / len;
    const steps = Math.max(6, Math.round(len / 34)), frame = Math.floor(time * 14);
    ctx.beginPath(); ctx.moveTo(x, y);
    for (let i = 1; i < steps; i++) {
      const t = i / steps, off = (noise(frame * 31 + i * 7 + key) - .5) * jitter * Math.sin(t * Math.PI);
      ctx.lineTo(x + dx * t + nx * off, y + dy * t + ny * off);
    }
    ctx.lineTo(ex, ey); ctx.stroke();
  }
  function beam(p, color, key, back = false) {
    const x = w / 2, y = h / 2;
    const pulse = .75 + .25 * Math.sin(time * 6 + key);
    const grad = ctx.createLinearGradient(x, y, p.x, p.y);
    grad.addColorStop(0, '#ffe7a8'); grad.addColorStop(.45, '#bdf3ff'); grad.addColorStop(1, color);
    ctx.save(); ctx.globalCompositeOperation = 'screen'; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    // 1. Wide glowing conduit
    ctx.strokeStyle = grad; ctx.shadowColor = color; ctx.shadowBlur = 28;
    ctx.lineWidth = 16; ctx.globalAlpha = .12 * pulse; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(p.x, p.y); ctx.stroke();
    ctx.lineWidth = 6; ctx.globalAlpha = .28 * pulse; ctx.stroke();
    // 2. Bright core line
    ctx.lineWidth = 1.6; ctx.globalAlpha = .95; ctx.stroke();
    // 3. Crackling lightning around the core
    ctx.shadowBlur = 14; ctx.strokeStyle = '#eafcff';
    ctx.lineWidth = 1.3; ctx.globalAlpha = .75; bolt(x, y, p.x, p.y, 26, key);
    ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.globalAlpha = .55; bolt(x, y, p.x, p.y, 40, key + 50);
    // 4. Energy packets: Ali -> agent while working, agent -> Ali while the answer returns
    for (let i = 0; i < 5; i++) {
      const t = (time * (back ? .9 : .45) + i / 5) % 1, k = back ? 1 - t : t;
      const px = x + (p.x - x) * k, py = y + (p.y - y) * k;
      const r = 2.5 + 2.5 * Math.sin(t * Math.PI);
      const glow = ctx.createRadialGradient(px, py, 0, px, py, r * 4);
      glow.addColorStop(0, '#ffffff'); glow.addColorStop(.3, color); glow.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.globalAlpha = .9 * Math.sin(t * Math.PI); ctx.fillStyle = glow; ctx.shadowBlur = 0;
      ctx.beginPath(); ctx.arc(px, py, r * 4, 0, Math.PI * 2); ctx.fill();
    }
    // 5. Impact: at the agent while working, at Ali while the answer arrives
    const ix = back ? x : p.x, iy = back ? y : p.y;
    const halo = ctx.createRadialGradient(ix, iy, 10, ix, iy, 95);
    halo.addColorStop(0, color); halo.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.globalAlpha = .22 * pulse; ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(ix, iy, 95, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = color; ctx.shadowColor = color; ctx.shadowBlur = 12;
    for (let i = 0; i < 2; i++) {
      const t = (time * .8 + i / 2) % 1;
      ctx.globalAlpha = (1 - t) * .7; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(ix, iy, 55 + t * 45, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
  }
  function draw() {
    if (!w || !h) return;
    ctx.clearRect(0, 0, w, h);
    for (const s of stars) {
      ctx.fillStyle = `rgba(192,217,255,${s.a * (.75 + .25 * Math.sin(time * .6 + s.phase))})`;
      ctx.beginPath(); ctx.arc(s.x * w, s.y * h, s.r, 0, Math.PI * 2); ctx.fill();
    }
    ctx.save(); ctx.translate(w / 2, h / 2); ctx.rotate(-.5);
    const size = Math.max(470, Math.min(w * .94, h * 1.2));
    ctx.globalAlpha = .68 + .035 * Math.sin(time * .45); ctx.drawImage(nebula, -size / 2, -size / 2, size, size); ctx.restore();
    members.forEach((a, index) => {
      const p = position(index, members.length), node = nodes.get(a.key);
      node.style.left = `${p.x}px`; node.style.top = `${p.y}px`;
      const color = BOT_COLORS[node.dataset.robot] || '#79dfff';
      if (active.has(a.key) && online) beam(p, color, index * 13.7);
      else if (returning.has(a.key) && online) {
        const left = 1 - (Date.now() - returning.get(a.key)) / RETURN_MS;
        if (left <= 0) { returning.delete(a.key); node.classList.remove('active'); setTimeout(refreshStatus, 0); }
        else { ctx.save(); ctx.globalAlpha = Math.min(1, left * 2); beam(p, color, index * 13.7, true); ctx.restore(); }
      }
    });
  }
  function tick(stamp) {
    raf = 0;
    if (!visible || document.hidden) { previous = 0; return; }
    if (!paused) time += previous ? Math.min((stamp - previous) / 1000, .05) : 0;
    previous = stamp; draw();
    if (!paused) raf = requestAnimationFrame(tick);
  }
  function schedule() { if (visible && !document.hidden && !raf) raf = requestAnimationFrame(tick); }
  function motionState() {
    root.classList.toggle('paused', paused || !visible || document.hidden);
    motion.setAttribute('aria-pressed', String(paused));
    motion.setAttribute('aria-label', paused ? 'Animatsiyani davom ettirish' : 'Animatsiyani to‘xtatish');
    motion.textContent = paused ? '▷' : 'Ⅱ';
    previous = 0; schedule();
  }
  motion.addEventListener('click', () => { paused = !paused; motionState(); });
  reduced.addEventListener('change', () => { paused = reduced.matches; motionState(); });
  new ResizeObserver(resize).observe(root);
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; motionState(); }, { threshold: .05 }).observe(root);
  document.addEventListener('visibilitychange', motionState);

  function choose(key) {
    root.dispatchEvent(new CustomEvent('galaxy-select', { bubbles: true, detail: { key } }));
  }
  core.addEventListener('click', () => choose('ali'));
  function select(key) {
    selected = key;
    nodes.forEach((node, id) => { node.classList.toggle('selected', selected === id); node.setAttribute('aria-pressed', String(selected === id)); });
  }
  function update(snapshot) {
    members = (snapshot.agents || []).filter(a => a.key !== 'ali');
    fitAgents();
    root.classList.toggle('many-agents', members.length > 4);
    active = new Set((snapshot.jobs || []).filter(j => j.status === 'running').map(j => j.agent));
    // A job that was running and is now finished: show the answer travelling back to Ali.
    const nowRunning = new Map((snapshot.jobs || []).filter(j => j.status === 'running').map(j => [j.id, j.agent]));
    for (const job of snapshot.jobs || []) {
      if (runningJobs.has(job.id) && job.status !== 'running' && job.agent !== 'ali') returning.set(job.agent, Date.now());
    }
    runningJobs = nowRunning;
    // Running agent state also covers snapshots with a truncated job list.
    for (const a of snapshot.agents || []) if (a.status === 'running') active.add(a.key);
    for (const [key, node] of nodes) if (!members.some(a => a.key === key)) { node.remove(); nodes.delete(key); }
    for (const [i, a] of members.entries()) {
      let node = nodes.get(a.key);
      if (!node) {
        node = document.createElement('button'); node.type = 'button'; node.className = 'galaxy-agent';
        node.dataset.key = a.key;
        const variants = { dasturchi: 'coder', kontent: 'creator', informatika: 'mentor', treyder: 'analyst' };
        node.dataset.robot = variants[a.key] || ['coder', 'creator', 'mentor', 'analyst'][i % 4];
        node.style.setProperty('--blink-delay', `${-i * 1.7}s`);
        const figure = document.createElement('span'); figure.className = 'galaxy-agent-figure';
        figure.setAttribute('aria-hidden', 'true');
        figure.innerHTML = '<span class="bot-antenna"></span><span class="bot-ear left"></span><span class="bot-ear right"></span><span class="bot-shell"><span class="bot-visor"><span class="bot-eye left"></span><span class="bot-eye right"></span><span class="bot-mouth"></span></span><span class="bot-detail"></span></span><span class="bot-neck"></span><span class="bot-base"></span>';
        const name = document.createElement('span'); name.className = 'galaxy-agent-label';
        const state = document.createElement('span'); state.className = 'galaxy-agent-status';
        node.append(figure, name, state); node.addEventListener('click', () => choose(a.key));
        layer.append(node); nodes.set(a.key, node);
      }
      const working = active.has(a.key) && online, answering = !working && returning.has(a.key) && online;
      node.classList.toggle('active', working || answering);
      node.querySelector('.galaxy-agent-label').textContent = a.name;
      node.querySelector('.galaxy-agent-status').textContent = !online ? 'Aloqa yo‘q' : working ? '● ISHLAYAPTI' : answering ? '● JAVOB BERDI' : 'KUTMOQDA';
      node.title = `${a.name} · ${working ? a.current || 'Vazifa bajarilmoqda' : 'Vazifalarni ko‘rish'}`;
      node.setAttribute('aria-label', `${a.name}: ${working ? 'ishlayapti' : 'kutmoqda'}. Vazifalarni ko‘rish`);
    }
    core.classList.toggle('working', active.size > 0 && online);
    root.querySelector('#galaxyCoreState').textContent = !online ? 'Aloqa yo‘q' : active.size ? 'Vazifa bajarilmoqda' : 'Markaziy ong';
    const n = members.filter(a => active.has(a.key) || returning.has(a.key)).length;
    root.querySelector('#galaxySummary').textContent = !online ? 'Jonli aloqa uzilgan' : `${members.length} agent tayyor · ${n} faol aloqa`;
    select(selected); draw(); schedule();
  }
  function refreshStatus() { update(latest); }
  let latest = { agents: [], jobs: [] };
  window.AliGalaxy = {
    update(snapshot) { latest = snapshot; update(snapshot); },
    select,
    setOnline(value) {
      online = value;
      const label = root.querySelector('#galaxyConnection');
      label.textContent = online ? '● JONLI ALOQA' : '○ ALOQA YO‘Q'; label.classList.toggle('online', online);
      update(latest);
    },
  };
  motionState();
})();
