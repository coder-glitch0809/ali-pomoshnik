// Renderer state checks without a browser or real AI/API calls.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function fixture() {
  let beams = 0;
  let frame;
  const context = new Proxy({
    createRadialGradient: () => ({ addColorStop() {} }),
    createLinearGradient: () => ({ addColorStop() {} }),
    clearRect() { beams = 0; },
    stroke() { if (this.lineWidth === 1.6) beams++; },
  }, { get: (target, key) => key in target ? target[key] : () => {} });
  class Element {
    constructor() {
      this.children = []; this.dataset = {}; this.attributes = {}; this.events = {};
      this.style = { setProperty() {} };
      this.classes = new Set();
      this.classList = { toggle: (key, value) => value ? this.classes.add(key) : this.classes.delete(key) };
      this.clientWidth = 950; this.clientHeight = 680;
    }
    append(...items) { items.forEach(item => { item.parent = this; this.children.push(item); }); }
    remove() { this.parent.children = this.parent.children.filter(x => x !== this); }
    querySelector(selector) { return this.children.find(x => x.className === selector.slice(1)); }
    setAttribute(k, v) { this.attributes[k] = v; }
    addEventListener(k, v) { this.events[k] = v; }
    dispatchEvent() {}
    getContext() { return context; }
  }
  const root = new Element();
  const ids = Object.fromEntries(['canvas', '#galaxyAgents', '#galaxyCore', '#galaxyMotion', '#galaxyConnection', '#galaxyCoreState', '#galaxySummary'].map(k => [k, new Element()]));
  root.querySelector = key => ids[key];
  const sandbox = {
    document: { querySelector: () => root, createElement: () => new Element(), addEventListener() {}, hidden: false },
    window: {}, matchMedia: () => ({ matches: false, addEventListener() {} }),
    ResizeObserver: class { constructor(cb) { this.cb = cb; } observe() { this.cb(); } },
    IntersectionObserver: class { constructor(cb) { this.cb = cb; } observe() { this.cb([{ isIntersecting: true }]); } },
    requestAnimationFrame: cb => { frame = cb; return 1; }, devicePixelRatio: 1,
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../web/monitor-galaxy.js'), 'utf8'), sandbox);
  return { api: sandbox.window.AliGalaxy, nodes: ids['#galaxyAgents'].children,
    root, ids, beams: () => beams, advance: stamp => frame(stamp) };
}
const keys = ['treyder', 'kontent', 'informatika', 'dasturchi'];
function snapshot(activeKeys = []) {
  return { agents: ['ali', ...keys].map(key => ({ key, name: key, status: activeKeys.includes(key) ? 'running' : 'idle' })),
    jobs: activeKeys.map(agent => ({ agent, status: 'running' })) };
}

test('idle stations have four robots and no fake task beams', () => {
  const f = fixture(); f.api.setOnline(true); f.api.update(snapshot());
  assert.equal(f.nodes.length, 4); assert.equal(f.beams(), 0);
});
test('robot stations stay fixed while light animation advances', () => {
  const f = fixture(); f.api.setOnline(true); f.api.update(snapshot(keys));
  const positions = () => f.nodes.map(n => [n.style.left, n.style.top]);
  const before = positions();
  f.advance(1000); f.advance(2000); f.advance(9000);
  assert.deepEqual(positions(), before);
  assert.equal(new Set(f.nodes.map(n => n.dataset.robot)).size, 4);
  assert.ok(f.nodes.every(n => !n.children[0].innerHTML.includes('<img')));
});
test('one assignment lights only the assigned robot', () => {
  const f = fixture(); f.api.setOnline(true); f.api.update(snapshot(['kontent']));
  assert.deepEqual(f.nodes.filter(n => n.classes.has('active')).map(n => n.dataset.key), ['kontent']);
  assert.equal(f.beams(), 1);
});
test('simultaneous assignments create equal beams to all four agents', () => {
  const f = fixture(); f.api.setOnline(true); f.api.update(snapshot(keys));
  assert.equal(f.beams(), 4); assert.equal(f.nodes.filter(n => n.classes.has('active')).length, 4);
  f.api.update(snapshot()); assert.equal(f.beams(), 0);
});
test('disconnect clears stale beams and reconnect restores current assignments', () => {
  const f = fixture(); f.api.setOnline(true); f.api.update(snapshot(keys));
  f.api.setOnline(false); assert.equal(f.beams(), 0);
  assert.equal(f.nodes.filter(n => n.classes.has('active')).length, 0);
  f.api.setOnline(true); assert.equal(f.beams(), 4);
});
test('selecting an agent highlights it without hiding other active links', () => {
  const f = fixture(); f.api.setOnline(true); f.api.update(snapshot(keys)); f.api.select('treyder');
  assert.equal(f.nodes.filter(n => n.classes.has('selected')).length, 1);
  assert.equal(f.beams(), 4);
});
