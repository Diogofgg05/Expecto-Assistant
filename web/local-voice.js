/* EXPECTO Local STT — microphone recording with bounded VAD, no cloud upload.
   Uses local HTTP /api/voice/transcribe only when whisper.cpp is configured. */
(() => {
  'use strict';
  const MAX_SECONDS = 15;
  const SILENCE_MS = 950;
  const MIN_VOICE_MS = 250;
  let current = null;
  let cached = null;

  async function capabilities() {
    if (cached !== null) return cached;
    try {
      const response = await fetch('/api/voice/capabilities', { cache: 'no-store' });
      cached = response.ok && !!(await response.json()).local_stt;
    } catch (_) { cached = false; }
    return cached;
  }

  function encodeWav(chunks, count, rate) {
    // Typed arrays avoid hundreds of thousands of boxed JS numbers.
    count = Math.min(Math.round(rate * MAX_SECONDS), count);
    const samples = new Float32Array(count);
    let offset = 0;
    for (const chunk of chunks) {
      const copy = Math.min(chunk.length, count - offset);
      if (copy <= 0) break;
      samples.set(chunk.subarray(0, copy), offset);
      offset += copy;
    }
    const ratio = rate / 16000;
    const len = Math.floor(count / ratio);
    const bytes = new ArrayBuffer(44 + len * 2);
    const view = new DataView(bytes);
    function str(at, s) {
      for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i));
    }
    str(0, 'RIFF'); view.setUint32(4, bytes.byteLength - 8, true);
    str(8, 'WAVE'); str(12, 'fmt '); view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, 16000, true); view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    str(36, 'data'); view.setUint32(40, len * 2, true);
    for (let i = 0; i < len; i++) {
      const from = Math.floor(i * ratio);
      const to = Math.max(from + 1, Math.floor((i + 1) * ratio));
      let avg = 0;
      for (let j = from; j < to && j < count; j++) avg += samples[j];
      avg /= Math.max(1, Math.min(to, count) - from);
      const v = Math.max(-1, Math.min(1, avg));
      view.setInt16(44 + 2 * i, v < 0 ? Math.round(v * 32768) : Math.round(v * 32767), true);
    }
    return new Blob([bytes], { type: 'audio/wav' });
  }

  async function stopSession(session, send) {
    if (session.done) return;
    session.done = true;
    try { session.processor?.disconnect(); } catch (_) {}
    try { session.source?.disconnect(); } catch (_) {}
    try { session.muted?.disconnect(); } catch (_) {}
    session.stream?.getTracks().forEach(track => track.stop());
    try { await session.context?.close(); } catch (_) {}
    if (current !== session) return;
    if (!send || !session.voiced) { current = null; session.onStatus?.('idle'); return; }
    session.onStatus?.('transcribing');
    const wav = encodeWav(session.chunks, session.sampleCount, session.rate);
    session.chunks = []; // Free source PCM before network transcription.
    const signal = session.abort.signal;
    try {
      const resp = await fetch('/api/voice/transcribe', {
        method: 'POST', headers: { 'Content-Type': 'audio/wav' },
        body: wav, signal
      });
      if (!resp.ok) throw new Error('Transcrição local HTTP ' + resp.status);
      const result = await resp.json();
      if (current === session && !signal.aborted) {
        current = null;
        session.onResult?.(String(result.text || '').trim());
      }
    } catch (err) {
      if (current === session) {
        current = null;
        if (!signal.aborted) session.onError?.(err);
      }
    }
  }
  async function start(callbacks = {}) {
    if (current) return false;
    if (!(await capabilities()) || !navigator.mediaDevices?.getUserMedia) return false;
    const session = {
      ...callbacks, abort: new AbortController(), done: false,
      stream: null, context: null, processor: null, source: null, muted: null,
      chunks: [], sampleCount: 0, voiced: false, voicedMs: 0, silenceSince: null,
      rate: 48000
    };
    current = session;
    try {
      session.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }
      });
      if (current !== session || session.done) {
        session.stream.getTracks().forEach(t => t.stop());
        return true;
      }
      const Context = window.AudioContext || window.webkitAudioContext;
      if (!Context) throw new Error('AudioContext indisponível.');
      session.context = new Context();
      session.rate = session.context.sampleRate;
      session.source = session.context.createMediaStreamSource(session.stream);
      // ScriptProcessor is a compatibility fallback; a dedicated AudioWorklet
      // can replace it later without changing the backend recording contract.
      session.processor = session.context.createScriptProcessor(2048, 1, 1);
      session.muted = session.context.createGain(); session.muted.gain.value = 0;
      session.source.connect(session.processor);
      session.processor.connect(session.muted);
      session.muted.connect(session.context.destination);
      session.onStatus?.('listening');
      let startedAt = performance.now();
      session.processor.onaudioprocess = event => {
        if (session.done) return;
        const chunk = event.inputBuffer.getChannelData(0);
        const limit = session.rate * MAX_SECONDS;
        const copy = Math.min(chunk.length, Math.max(0, limit - session.sampleCount));
        if (copy) session.chunks.push(chunk.slice(0, copy));
        session.sampleCount += copy;
        const now = performance.now();
        let energy = 0;
        for (const x of chunk) energy += x * x;
        const rms = Math.sqrt(energy / chunk.length);
        if (rms > 0.015) {
          session.voiced = true;
          session.voicedMs += (chunk.length / session.rate) * 1000;
          session.silenceSince = null;
        } else if (session.voiced && session.silenceSince === null) session.silenceSince = now;
        const longEnough = session.voicedMs >= MIN_VOICE_MS;
        if ((longEnough && session.silenceSince && now - session.silenceSince > SILENCE_MS) ||
            now - startedAt >= MAX_SECONDS * 1000 ||
            session.sampleCount >= session.rate * MAX_SECONDS) {
          void stopSession(session, longEnough);
        }
      };
      return true;
    } catch (err) {
      await stopSession(session, false);
      callbacks.onError?.(err);
      return true; // Started local path, do not start a second mic prompt.
    }
  }
  function cancel() {
    if (!current) return;
    const session = current;
    session.abort.abort();
    current = null;
    void stopSession(session, false);
  }
  window.ExpectoLocalSTT = {
    get active() { return !!current; },
    capabilities, start, cancel,
    stop() { if (current) void stopSession(current, true); }
  };
})();
