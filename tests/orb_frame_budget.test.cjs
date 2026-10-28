/* Offline canvas simulator: test redraw budgets, not visual fidelity or watts. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../web/orb.js'), 'utf8');

function simulate({mode = 'idle', reduced = false, hidden = false} = {}) {
  const pending = [];
  let redraws = 0;
  const noop = () => {};
  const ctx = {
    setTransform: noop, save: noop, restore: noop, translate: noop,
    rotate: noop, scale: noop, beginPath: noop, arc: noop,
    stroke: noop, fill: noop, moveTo: noop, lineTo: noop,
    setLineDash: noop, clearRect: () => { redraws += 1; },
    createRadialGradient: () => ({addColorStop: noop})
  };
  const canvas = {
    getContext: () => ctx,
    getBoundingClientRect: () => ({width: 500, height: 500})
  };
  const document = {hidden, getElementById: () => canvas};
  const window = {
    devicePixelRatio: 1,
    matchMedia: () => ({matches: reduced})
  };
  class ResizeObserver {
    observe() {}
  }
  vm.runInNewContext(source, {
    document, window, ResizeObserver,
    requestAnimationFrame: fn => pending.push(fn),
    Math
  }, {timeout: 1000});
  window.AuraOrb.setMode(mode);
  // Simulate two seconds of callbacks at 60Hz; canvas only repaints as needed.
  for (let i = 1; i <= 120; i++) {
    assert.ok(pending.length, 'animation should have a scheduled callback');
    pending.shift()(i * 1000 / 60);
  }
  return redraws;
}

test('idle animation draws fewer frames than active voice states', () => {
  const idle = simulate({mode:'idle'});
  const thinking = simulate({mode:'thinking'});
  const listening = simulate({mode:'listening'});
  assert.ok(idle >= 20 && idle <= 40, 'idle should use about 20 fps');
  assert.ok(thinking > idle);
  assert.ok(listening > thinking);
});

test('hidden tab does not draw hologram', () => {
  assert.equal(simulate({hidden:true}), 0);
});

test('reduced-motion animation remains visible but redraws sparingly', () => {
  const lowMotion = simulate({reduced:true});
  assert.ok(lowMotion >= 1 && lowMotion <= 5);
});
