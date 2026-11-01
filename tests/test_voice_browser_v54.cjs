/* Execute with: node --test tests/test_voice_browser_v54.cjs
   Uses fake browser primitives, no microphone or external services. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness() {
  const spoken = [];
  const events = [];
  class Utterance {
    constructor(text) { this.text = text; }
  }
  const synth = {
    cancelCalls: 0,
    getVoices() { return [{ name: 'Português', lang: 'pt-PT' }]; },
    cancel() { this.cancelCalls += 1; },
    speak(utterance) {
      spoken.push(utterance);
      utterance.onstart?.();
    },
  };
  const win = {
    speechSynthesis: synth,
    SpeechSynthesisUtterance: Utterance,
    dispatchEvent(e) { events.push(e.detail); },
  };
  const context = {
    window: win,
    SpeechSynthesisUtterance: Utterance,
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
  };
  vm.runInNewContext(
    fs.readFileSync(path.resolve(__dirname, '../web/voice.js'), 'utf8'),
    context,
    { filename: 'voice.js' }
  );
  return { voice: win.ExpectoVoice, spoken, events, synth };
}

test('starts speaking after first sentence, before the model ends', () => {
  const { voice, spoken } = harness();
  let begins = 0, ends = 0;
  assert.equal(voice.start({ onStart() { begins++; }, onEnd() { ends++; } }), true);
  voice.feed('Olá. ');
  assert.equal(spoken.length, 1);
  assert.equal(spoken[0].text, 'Olá.');
  assert.equal(begins, 1);
  voice.feed('Como estás? ');
  voice.finish();
  spoken[0].onend();
  assert.equal(spoken.length, 2);
  assert.equal(spoken[1].text, 'Como estás?');
  spoken[1].onend();
  assert.equal(ends, 1);
  assert.equal(voice.active, false);
});

test('speaks a long unpunctuated thought before all tokens arrive', () => {
  const { voice, spoken } = harness();
  voice.start();
  voice.feed('Esta é uma resposta longa sobre a tecnologia e o raciocínio, com várias palavras e explicações que continuam mais adiante.');
  assert.ok(spoken.length >= 1);
  assert.ok(spoken[0].text.length >= 36);
  voice.finish();
  while (voice.active) spoken.at(-1).onend();
});

test('interrupting cancels playback and ignores stale utterance events', () => {
  const { voice, spoken, synth } = harness();
  let oldEnd = 0;
  voice.speak('Resposta antiga.', { onEnd() { oldEnd++; } });
  const old = spoken[0];
  voice.cancel();
  voice.speak('Resposta nova.');
  old.onend();
  assert.equal(oldEnd, 0);
  assert.equal(spoken.length, 2);
  assert.equal(spoken[1].text, 'Resposta nova.');
  assert.ok(synth.cancelCalls >= 2);
});

test('respects total speech budget and reports boundaries', () => {
  const { voice, spoken, events } = harness();
  let boundary = -1;
  voice.speak('Primeiro segmento. ', { onBoundary(index) { boundary = index; } });
  spoken[0].onboundary({ charIndex: 3 });
  assert.equal(boundary, 3);
  assert.ok(events.some(event => event.type === 'boundary'));
  voice.cancel();
  voice.start();
  voice.feed('A'.repeat(6000));
  voice.finish();
  let output = '';
  while (voice.active) {
    const last = spoken.at(-1);
    output += last.text;
    last.onend();
  }
  assert.ok(output.length <= 2700);
});
