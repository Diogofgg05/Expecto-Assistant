/* Voice 5.6: real prefetch/cancellation contracts with fully mocked audio.
 * Run: node --test tests/test_voice_prefetch_v56.cjs
 */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const settle = async () => {
  for (let i = 0; i < 12; i++) await Promise.resolve();
};

function harness() {
  const calls = [], players = [], events = [], revoked = [];
  class Utterance { constructor(text) { this.text = text; } }
  class Audio {
    constructor(uri) { this.uri = uri; this.paused = false; players.push(this); }
    async play() { this.onplay?.(); }
    pause() { this.paused = true; }
  }
  const synth = {
    getVoices() { return [{ lang: 'pt-PT' }]; },
    cancel() {},
    speak(u) { u.onstart?.(); }
  };
  let urlCounter = 0;
  const win = {
    speechSynthesis: synth,
    SpeechSynthesisUtterance: Utterance,
    performance: {now() { return 1000; }},
    dispatchEvent(e) { events.push(e.detail); }
  };
  const context = {
    window: win,
    Audio, Blob, AbortController,
    URL: {
      createObjectURL() { return 'blob:' + ++urlCounter; },
      revokeObjectURL(uri) { revoked.push(uri); }
    },
    fetch: (url, options) => {
      calls.push({url, options});
      return Promise.resolve({
        ok: true,
        blob: async () => new Blob([new Uint8Array([82,73,70,70])])
      });
    },
    SpeechSynthesisUtterance: Utterance,
    CustomEvent: class { constructor(_type, options) { this.detail = options.detail; } },
  };
  vm.runInNewContext(
    fs.readFileSync(path.resolve(__dirname, '../web/voice.js'), 'utf8'),
    context,
    {filename:'voice.js'}
  );
  return {voice:win.ExpectoVoice, calls, players, events, revoked};
}

test('preloads one segment and reuses audio without duplicate synthesis', async () => {
  const h = harness();
  h.voice.configure({localTTS:true});
  assert.equal(h.voice.start(),true);
  h.voice.feed('Primeira frase. Segunda frase. Terceira frase.');
  h.voice.finish();
  await settle();
  assert.equal(h.calls.length, 2); // first playback + exactly one prepared segment
  assert.equal(h.players.length, 1);
  h.players[0].onended();
  await settle();
  assert.equal(h.calls.length, 3); // prefetch third as second starts
  assert.equal(h.players.length, 2);
  h.players[1].onended();
  await settle();
  assert.equal(h.calls.length, 3); // no extra request for third
  assert.equal(h.players.length, 3);
  h.players[2].onended();
  await settle();
  assert.equal(h.voice.active,false);
  assert.equal(h.events.filter(e=>e.type==='start'&&e.engine==='piper').length,3);
  assert.equal(h.events.filter(e=>e.type==='start'&&e.preloaded).length,2);
  assert.equal(h.revoked.length,3);
});

test('interrupt cancels current and preloaded Piper requests', async () => {
  const h = harness();
  h.voice.configure({localTTS:true});
  h.voice.speak('A primeira frase. A segunda frase.');
  await settle();
  assert.equal(h.calls.length,2);
  const active = h.players[0];
  h.voice.cancel();
  assert.equal(active.paused,true);
  assert.equal(h.calls.every(c=>c.options.signal.aborted),true);
  active.onended?.(); // old completion must not restart playback
  await settle();
  assert.equal(h.players.length,1);
  assert.equal(h.voice.active,false);
});

test('browser TTS still works without configured Piper', async () => {
  const h=harness();
  h.voice.speak('Olá, estou disponível.');
  await settle();
  assert.equal(h.calls.length,0);
  assert.equal(h.events.some(e=>e.type==='start'&&e.engine==='browser'),true);
});
