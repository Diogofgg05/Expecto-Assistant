/* EXPECTO Local STT — microphone recording with bounded VAD, no cloud upload.
   Uses local HTTP /api/voice/transcribe only when whisper.cpp is configured. */
(() => {
  'use strict';
  const MAX_SECONDS = 15;
  const CONNECT_TIMEOUT_MS = 5000;
  const TRANSCRIPTION_TIMEOUT_MS = 30000;
  const SILENCE_MS = 950;
  const MIN_VOICE_MS = 250;
  let current = null;
  let cached = null;
  let persistent = false;

  async function capabilities() {
    if (cached !== null) return cached;
    try {
      const response = await fetch('/api/voice/capabilities', { cache: 'no-store' });
      const details = response.ok ? await response.json() : {};
      persistent = !!details.persistent_stt;
      cached = !!(details.local_stt || persistent);
    } catch (_) { cached = false; }
    return cached;
  }

  function clearDeadlines(session) {
    if (session.connectDeadline !== null) clearTimeout(session.connectDeadline);
    if (session.finalDeadline !== null) clearTimeout(session.finalDeadline);
    session.connectDeadline = null;
    session.finalDeadline = null;
  }
  function failSession(session, message) {
    if (current !== session || session.failed) return;
    session.failed = true;
    clearDeadlines(session);
    session.abort.abort();
    const socket = session.socket;
    session.socket = null;
    current = null;
    try { socket?.close(); } catch (_) {}
    // stopSession also closes audio tracks and the AudioContext if recording.
    void stopSession(session, false);
    session.onError?.(new Error(message));
  }
  function awaitFinal(session) {
    if (session.finalDeadline !== null) clearTimeout(session.finalDeadline);
    session.finalDeadline = setTimeout(() => {
      failSession(session, 'Whisper local não respondeu à transcrição dentro do prazo.');
    }, TRANSCRIPTION_TIMEOUT_MS);
  }
  function microphoneMessage(err) {
    if (err?.name === 'NotAllowedError' || err?.name === 'PermissionDeniedError')
      return 'Acesso ao microfone recusado. Ativa a permissão do navegador.';
    if (err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError')
      return 'Não foi detetado nenhum microfone. Verifica o dispositivo de entrada.';
    if (err?.name === 'NotReadableError' || err?.name === 'TrackStartError')
      return 'Microfone ocupado ou indisponível. Fecha outras aplicações de áudio.';
    if (err?.name === 'SecurityError')
      return 'Microfone bloqueado. Usa localhost ou uma origem HTTPS autorizada.';
    return String(err?.message || 'Falha ao iniciar o microfone local.');
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

  function sendPCM(session, block){
    if(!session.socket || session.socket.readyState!==WebSocket.OPEN)return;
    if(session.resampler){const output=session.resampler.push(block);if(output.length&&session.socket.bufferedAmount<=128*1024)session.socket.send(output.buffer);return;}
    const rate=session.rate, ratio=rate/16000, len=Math.floor(block.length/ratio);
    const output=new Int16Array(len);
    for(let i=0;i<len;i++){
      const sample=Math.max(-1,Math.min(1,block[Math.min(block.length-1,Math.floor(i*ratio))]));
      output[i]=sample<0?Math.round(sample*32768):Math.round(sample*32767);
    }
    if(session.socket.bufferedAmount>128*1024)return;
    session.socket.send(output.buffer);
  }
  async function stopSession(session, send) {
    if (session.done) return;
    session.done = true;
    if (!send) clearDeadlines(session);
    try { session.processor?.disconnect(); } catch (_) {}
    try { session.source?.disconnect(); } catch (_) {}
    try { session.muted?.disconnect(); } catch (_) {}
    session.stream?.getTracks().forEach(track => track.stop());
    try { await session.context?.close(); } catch (_) {}
    if (current !== session) return;
    if (!send || !session.voiced) {
      clearDeadlines(session);
      if (session.socket) session.socket.close();
      current = null; session.onStatus?.('idle'); return;
    }
    session.onStatus?.('transcribing');
    if(session.socket){
      if(session.socket.readyState === WebSocket.OPEN){
        try {
          session.socket.send(JSON.stringify({type:'flush'}));
          awaitFinal(session);
        } catch (_) {
          failSession(session, 'Não consegui finalizar a gravação local.');
        }
        return;
      }
      if(session.socket.readyState === WebSocket.CONNECTING){
        // The recording may end before the WebSocket handshake finishes.
        // Keep recorded PCM until onopen, then flush exactly once.
        session.flushWhenOpen=true;
        return;
      }
      failSession(session, 'Canal Whisper local interrompido.');
      return;
    }
    const wav = encodeWav(session.chunks, session.sampleCount, session.rate);
    session.chunks = []; // Free source PCM before network transcription.
    const signal = session.abort.signal;
    let timedOut = false;
    const deadline = setTimeout(() => {
      timedOut = true;
      session.abort.abort();
    }, TRANSCRIPTION_TIMEOUT_MS);
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
        session.onError?.(timedOut
          ? new Error('Whisper local excedeu o tempo de transcrição.')
          : err);
      }
    } finally {
      clearTimeout(deadline);
    }
  }
  async function start(callbacks = {}) {
    if (current) return false;
    if (!(await capabilities()) || !navigator.mediaDevices?.getUserMedia) return false;
    const session = {
      ...callbacks, abort: new AbortController(), done: false,
      stream: null, context: null, processor: null, source: null, muted: null,
      chunks: [], sampleCount: 0, voiced: false, voicedMs: 0, silenceSince: null,
      socket: null, resampler:null, gate:null, flushWhenOpen:false, rate: 48000,
      connectDeadline:null, finalDeadline:null, failed:false
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
      const DSP=window.ExpectoAudioDSP;
      if(DSP){
        session.resampler=new DSP.PCM16Resampler(session.rate);
        session.gate=new DSP.VoiceGate(session.rate);
      }
      session.muted=session.context.createGain();session.muted.gain.value=0;
      let workletReady=false;
      if(session.context.audioWorklet && window.AudioWorkletNode){
        try{
          await session.context.audioWorklet.addModule('/static/capture-worklet.js');
          if(current!==session || session.done)return true;
          session.processor=new AudioWorkletNode(session.context,'expecto-capture');
          session.processor.port.onmessage=(event)=>consume(event.data);
          workletReady=true;
        }catch(_){/* Compatibility fallback for unsupported worklets. */}
      }
      if(!workletReady){
        session.processor=session.context.createScriptProcessor(2048,1,1);
        session.processor.onaudioprocess=event=>consume(event.inputBuffer.getChannelData(0));
      }
      session.source.connect(session.processor);
      session.processor.connect(session.muted);
      session.muted.connect(session.context.destination);
      if(persistent && typeof WebSocket !== 'undefined'){
        const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socket = new WebSocket(scheme + '//' + location.host + '/api/voice/continuous');
        session.socket = socket;
        session.connectDeadline = setTimeout(() => {
          failSession(session, 'Whisper local não estabeleceu ligação. Verifica o servidor.');
        }, CONNECT_TIMEOUT_MS);
        socket.onmessage = event => {
          if(current !== session || session.abort.signal.aborted)return;
          try{
            if(typeof event.data !== 'string' || event.data.length > 65536)
              throw new Error('Resposta do Whisper inválida.');
            const data=JSON.parse(event.data);
            if(data.type==='partial')session.onPartial?.(String(data.text||''));
            else if(data.type==='final'){
              clearDeadlines(session);
              session.socket=null;current=null;
              try { socket.close(); } catch (_) {}
              session.onResult?.(String(data.text||'').trim());
            }else if(data.type==='error'){
              failSession(session, 'Whisper local: '+String(data.reason||'falha de transcrição'));
            }else{
              throw new Error('Resposta do Whisper desconhecida.');
            }
          }catch(_){
            failSession(session, 'Resposta inválida do Whisper local.');
          }
        };
        socket.onerror=()=>failSession(session, 'Falha da ligação Whisper local.');
        socket.onclose=()=>failSession(session, 'Canal Whisper local encerrado inesperadamente.');
        socket.onopen=()=>{
          if(current!==session){socket.close();return;}
          if(session.connectDeadline !== null) clearTimeout(session.connectDeadline);
          session.connectDeadline=null;
          for(const block of session.chunks)sendPCM(session,block);
          session.chunks=[];
          if(session.flushWhenOpen){
            session.flushWhenOpen=false;
            try {
              socket.send(JSON.stringify({type:'flush'}));
              awaitFinal(session);
            } catch (_) {
              failSession(session, 'Não consegui finalizar a gravação local.');
            }
          }
        };
      }
      session.onStatus?.('listening');
      const startedAt=performance.now();
      function consume(chunk){
        if(session.done || current!==session)return;
        const limit=session.rate*MAX_SECONDS;
        const copy=Math.min(chunk.length,Math.max(0,limit-session.sampleCount));
        if(copy){
          const block=chunk.slice(0,copy);
          if(session.socket?.readyState===WebSocket.OPEN)sendPCM(session,block);
          else session.chunks.push(block);
        }
        session.sampleCount+=copy;
        const now=performance.now();
        let decision;
        if(session.gate)decision=session.gate.update(chunk,now);
        else{
          let energy=0;for(const x of chunk)energy+=x*x;
          const rms=Math.sqrt(energy/chunk.length);
          if(rms>0.015){session.voiced=true;session.voicedMs+=chunk.length/session.rate*1000;session.silenceSince=null;}
          else if(session.voiced&&session.silenceSince===null)session.silenceSince=now;
          decision={voiced:session.voicedMs>=MIN_VOICE_MS,
                    end:session.voicedMs>=MIN_VOICE_MS&&session.silenceSince!==null&&now-session.silenceSince>SILENCE_MS,
                    max:now-startedAt>=MAX_SECONDS*1000};
        }
        session.voiced ||= decision.voiced;
        if(decision.end||decision.max||session.sampleCount>=limit)void stopSession(session,decision.voiced);
      }
      return true;
    } catch (err) {
      await stopSession(session, false);
      callbacks.onError?.(new Error(microphoneMessage(err)));
      return true; // Started local path, do not start a second mic prompt.
    }
  }
  function cancel() {
    if (!current) return;
    const session = current;
    session.abort.abort();
    clearDeadlines(session);
    if(session.socket){try{session.socket.close();}catch(_){}}
    current = null;
    void stopSession(session, false);
  }
  window.ExpectoLocalSTT = {
    get active() { return !!current; },
    capabilities, start, cancel,
    stop() { if (current) void stopSession(current, true); }
  };
})();
