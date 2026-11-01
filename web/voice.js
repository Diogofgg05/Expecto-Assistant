/* EXPECTO voice 5.6 — progressive sentence TTS and reliable interruption.
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
  let prefetched = null, lastPlaybackEnd = 0;
  const now = () => window.performance?.now?.() ?? Date.now();
  // One speculative Piper request at most. The backend serializes model work.
  function requestWav(text) {
    const controller = new AbortController();
    const begun = now();
    const promise = fetch('/api/voice/synthesize', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text}), signal: controller.signal
    }).then(response => {
      if (!response.ok) throw new Error('Local voice synthesis failed');
      return response.blob();
    }).then(blob => ({blob, synthesisMs: Math.round(now() - begun)}));
    return {text, controller, promise};
  }
  function preloadNext() {
    if (!localTTS || !active || !queue.length || prefetched) return;
    // Preserve order: at most one cached segment is prepared ahead.
    const text = queue[0];
    prefetched = requestWav(text);
    prefetched.promise.catch(() => {}); // Failure is handled by playback fallback.
    report('prefetch', {characters: text.length});
  }


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
    prefetched?.controller.abort(); prefetched = null;
    lastPlaybackEnd = 0;
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
    if (localTTS) {
      // If it was prepared while the previous segment was playing, reuse it.
      const ready = prefetched?.text === text ? prefetched : null;
      if (ready) prefetched = null;
      void speakLocal(text, token, ready);
      preloadNext();
      return;
    }
    speakBrowser(text, token);
  }
  async function speakLocal(text, token, ready = null) {
    uttering = true;
    // A previously started request can be reused instead of being duplicated.
    const operation = ready || requestWav(text);
    const controller = operation.controller;
    localAbort = controller;
    try {
      const {blob, synthesisMs} = await operation.promise;
      if (token !== epoch || !active || controller.signal.aborted) return;
      localURL = URL.createObjectURL(blob);
      const audio = new Audio(localURL);
      localAudio = audio;
      audio.onplay = () => {
        if (token !== epoch || !active) return;
        if (!started) { started = true; handlers.onStart?.(); }
        report('start', {
          text, engine:'piper', synthesisMs,
          gapMs:lastPlaybackEnd ? Math.round(now() - lastPlaybackEnd) : null,
          preloaded: !!ready
        });
        preloadNext();
      };
      let completed = false;
      function complete() {
        if (completed || token !== epoch || !active) return;
        completed = true;
        localAudio = null;
        if(localURL){URL.revokeObjectURL(localURL);localURL='';}
        localAbort = null;
        uttering = false; spoken += text.length;
        lastPlaybackEnd = now();
        report('segment_end',{text,engine:'piper'});
        pump(token);
      }
      audio.onended = complete;
      audio.onerror = () => {
        if (completed || token !== epoch || !active) return;
        completed = true;
        localAudio = null;
        if(localURL){URL.revokeObjectURL(localURL);localURL='';}
        localAbort = null; uttering = false;
        // A failed or unplayable WAV must not block the rest of the answer.
        speakBrowser(text, token);
      };
      await audio.play();
    } catch (err) {
      if(token !== epoch || !active || controller.signal.aborted) return;
      if(localURL){URL.revokeObjectURL(localURL);localURL='';}
      localAudio = null;localAbort = null;uttering = false;
      // No speech server / blocked autoplay: use the browser as fallback.
      if (synth) speakBrowser(text,token);
      else {spoken += text.length; pump(token);}
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
    // Speak the FIRST complete sentence; picking the last punctuation
    // caused whole paragraphs to become a single blocking TTS request.
    const first = marks.exec(chunk);
    if (first) return first.index + 1;
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
    if (uttering) preloadNext();
    pump(epoch);
  }
  const api = {
    get supported() { return (!!synth && !!window.SpeechSynthesisUtterance) || localTTS; },
    configure(options = {}) {
      const enabled = !!options.localTTS;
      if (enabled !== localTTS) {
        prefetched?.controller.abort(); prefetched = null;
      }
      localTTS = enabled;
      if (active && uttering) preloadNext();
    },
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
