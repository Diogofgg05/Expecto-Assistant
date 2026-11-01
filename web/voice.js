/* EXPECTO Voice Pipeline — browser TTS, sentence buffering and barge-in.
   No remote scripts or cloud voice APIs are added by this file. */
(() => {
  'use strict';
  const synth = window.speechSynthesis;
  let epoch = 0, active = false, uttering = false, finished = false;
  let pending = '', spokenChars = 0, queue = [];
  let callbacks = {};
  const LIMIT = 2700;
  const voice = () => {
    const list = synth?.getVoices() || [];
    return list.find(v => v.lang.toLowerCase() === 'pt-pt') ||
           list.find(v => v.lang.toLowerCase().startsWith('pt')) || null;
  };
  function stop() {
    epoch++;
    active = false; uttering = false; finished = false;
    pending = ''; queue = []; callbacks = {}; spokenChars = 0;
    try { synth?.cancel(); } catch (_) {}
  }
  function pump(token) {
    if (!active || token !== epoch || uttering) return;
    if (!queue.length) {
      if (finished) {
        active = false;
        callbacks.onEnd?.();
      }
      return;
    }
    if (!synth) { stop(); return; }
    const text = queue.shift();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'pt-PT'; u.rate = 1.05; u.pitch = .94;
    const found = voice(); if (found) u.voice = found;
    uttering = true;
    u.onstart = () => { if (active && token === epoch) callbacks.onStart?.(); };
    u.onboundary = e => {
      if (active && token === epoch) callbacks.onBoundary?.(e.charIndex || 0);
    };
    u.onend = () => { if (token !== epoch) return; uttering = false; pump(token); };
    u.onerror = () => { if (token !== epoch) return; uttering = false; pump(token); };
    try { synth.speak(u); } catch (_) { uttering = false; stop(); }
  }
  function enqueue(soft = false) {
    while (pending.length) {
      const max = Math.min(pending.length, 175);
      const candidate = pending.slice(0, max);
      const matches = [...candidate.matchAll(/[.!?;:\n](?:\s|$)/g)];
      let cut = matches.length ? matches[matches.length - 1].index + 1 : 0;
      if (cut < 22 && pending.length >= 175) {
        cut = candidate.lastIndexOf(' ');
        if (cut < 40) cut = 175;
      }
      if (!cut && soft) cut = Math.min(pending.length, 175);
      if (!cut) break;
      let part = pending.slice(0, cut).trim();
      pending = pending.slice(cut).trimStart();
      if (part) {
        queue.push(part);
        spokenChars += part.length;
      }
    }
    pump(epoch);
  }
  const api = {
    get supported() { return !!synth && !!window.SpeechSynthesisUtterance; },
    get active() { return active; },
    start(next = {}) {
      stop();
      if (!api.supported) return false;
      callbacks = next; active = true;
      return true;
    },
    feed(piece) {
      if (!active || finished || !piece) return;
      const available = LIMIT - spokenChars - pending.length;
      if (available <= 0) return;
      pending += String(piece).slice(0, available);
      enqueue(false);
    },
    finish() {
      if (!active) return;
      finished = true; enqueue(true);
      pump(epoch);
    },
    speak(text, next = {}) {
      if (!api.start(next)) return false;
      api.feed(text); api.finish(); return true;
    },
    cancel: stop,
  };
  window.ExpectoVoice = api;
})();