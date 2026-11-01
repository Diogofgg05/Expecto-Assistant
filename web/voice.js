/* EXPECTO voice 5.4 — progressive sentence TTS and reliable interruption.
   Browser Web Speech is a fallback, not a local neural TTS engine. */
(() => {
  'use strict';
  const synth = window.speechSynthesis;
  const MAX_TOTAL = 2700;
  const MAX_CHUNK = 170;
  const SOFT_SPLIT = 100;
  let epoch = 0;
  let active = false, finished = false, uttering = false, started = false;
  let pending = '', accepted = 0, spoken = 0;
  let queue = [], handlers = {};
  let localTTS = false, localAbort = null, localAudio = null, localURL = '';

  function report(type, details = {}) {
    try {
      window.dispatchEvent(new CustomEvent('expecto:voice', {
        detail: { type, ...details }
      }));
    } catch (_) { /* Works without CustomEvent on older clients. */ }
  }
  function chooseVoice() {
    const list = synth?.getVoices() || [];
    return list.find(v => v.lang.toLowerCase() === 'pt-pt') ||
           list.find(v => v.lang.toLowerCase().startsWith('pt')) || null;
  }
  function cancel() {
    epoch += 1;
    localAbort?.abort(); localAbort = null;
    if(localAudio){localAudio.pause();localAudio.src='';localAudio=null;}
    if(localURL){URL.revokeObjectURL(localURL);localURL='';}
    active = false; finished = false; uttering = false; started = false;
    pending = ''; accepted = 0; spoken = 0; queue = [];
    handlers = {};
    try { synth?.cancel(); } catch (_) {}
    report('cancel');
  }
  function pump(token) {
    if (token !== epoch || !active || uttering) return;
    if (!queue.length) {
      if (finished) {
        active = false;
        report('done', { spokenCharacters: spoken });
        handlers.onEnd?.();
      }
      return;
    }
    const text = queue.shift();
    if (localTTS) { void speakLocal(text, token); return; }
    speakBrowser(text, token);
  }
  async function speakLocal(text, token) {
    uttering = true;
    const controller = new AbortController();localAbort = controller;
    try {
      const response = await fetch('/api/voice/synthesize', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text}), signal: controller.signal
      });
      if (!response.ok) throw new Error('Local voice synthesis failed');
      const audioBlob = await response.blob();
      if (token !== epoch || !active) return;
      localURL = URL.createObjectURL(audioBlob);
      const audio = new Audio(localURL);
      localAudio = audio;
      audio.onplay = () => {
        if (token !== epoch || !active) return;
        if (!started) { started = true; handlers.onStart?.(); }
        report('start', {text, engine:'piper'});
      };
      let completed = false;
      function finishSegment() {
        if (completed || token !== epoch || !active) return;
        completed = true;
        localAudio = null;
        if(localURL){URL.revokeObjectURL(localURL);localURL='';}
        localAbort = null;
        uttering = false; spoken += text.length;
        report('segment_end',{text,engine:'piper'});
        pump(token);
      }
      audio.onended = finishSegment;
      audio.onerror = () => {
        if(token !== epoch || !active) return;
        localAudio = null;
        if(localURL){URL.revokeObjectURL(localURL);localURL='';}
        localAbort = null; uttering = false;
        speakBrowser(text, token);
      };
      await audio.play();
    } catch (err) {
      if(token !== epoch || !active || controller.signal.aborted) return;
      // Browser autoplay restrictions and Piper failures retain Web Speech.
      if(localURL){URL.revokeObjectURL(localURL);localURL='';}
      localAudio = null;localAbort = null;uttering = false;
      speakBrowser(text,token);
    }
  }
  function speakBrowser(text, token) {
    if (token !== epoch || !active) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'pt-PT';
    utterance.rate = 1.04; utterance.pitch = .95;
    const selected = chooseVoice();
    if (selected) utterance.voice = selected;
    uttering = true;
    utterance.onstart = () => {
      if (token !== epoch || !active) return;
      if (!started) { started = true; handlers.onStart?.(); }
      report('start', { text, engine:'browser' });
    };
    utterance.onboundary = event => {
      if (token !== epoch || !active) return;
      const index = Number.isFinite(event.charIndex) ? event.charIndex : 0;
      report('boundary', { index, text });
      handlers.onBoundary?.(index, text);
    };
    function next() {
      if (token !== epoch || !active) return;
      uttering = false;
      spoken += text.length;
      report('segment_end', { text, engine:'browser' });
      pump(token);
    }
    utterance.onend = next;
    utterance.onerror = next;
    try { synth.speak(utterance); }
    catch (_) { next(); }
  }
  function takeBoundary(force) {
    if (!pending) return 0;
    const limit = Math.min(MAX_CHUNK, pending.length);
    const chunk = pending.slice(0, limit);
    // Only complete sentences: don't split decimal numbers such as 3.14.
    const marks = /[.!?;:\n](?=\s|$)/g;
    let match, last = 0;
    while ((match = marks.exec(chunk))) last = match.index + 1;
    if (last) return last;
    if (pending.length >= SOFT_SPLIT || force) {
      const space = chunk.lastIndexOf(' ');
      return space > 36 ? space : (force || pending.length >= MAX_CHUNK ? limit : 0);
    }
    return 0;
  }
  function flush(force) {
    while (pending) {
      const count = takeBoundary(force);
      if (!count) break;
      const segment = pending.slice(0, count).trim();
      pending = pending.slice(count).trimStart();
      if (segment) queue.push(segment);
    }
    pump(epoch);
  }
  const api = {
    get supported() { return (!!synth && !!window.SpeechSynthesisUtterance) || localTTS; },
    configure(options = {}) { localTTS = !!options.localTTS; },
    get active() { return active; },
    get queuedSegments() { return queue.length; },
    start(callbacks = {}) {
      cancel();
      if (!api.supported) return false;
      handlers = callbacks;
      active = true;
      report('ready');
      return true;
    },
    feed(piece) {
      if (!active || finished || !piece) return;
      const room = MAX_TOTAL - accepted;
      if (room <= 0) return;
      const text = String(piece).slice(0, room);
      accepted += text.length;
      pending += text;
      flush(false);
    },
    finish() {
      if (!active || finished) return;
      finished = true;
      flush(true);
    },
    speak(text, callbacks = {}) {
      if (!api.start(callbacks)) return false;
      api.feed(text);
      api.finish();
      return true;
    },
    cancel,
  };
  window.ExpectoVoice = api;
})();
