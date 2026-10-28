# Expecto 6.7 — Local microphone recovery (P0)

This is an incremental implementation of P0 from the Evolution 3.0 request.
It does not pretend to complete Three.js, WebGL, streaming inference, math typography,
or end-to-end voice hardware tests.

## Root cause

`web/app.js` previously used only `SpeechRecognition` (Web Speech API).
Some browser implementations use a remote recognizer, so error `network`
can occur even when getUserMedia and microphone permissions work.
CORS/WebSocket errors are not established as the cause in this repo: there
was no WebSocket STT transport. A browser error alone cannot distinguish
browser service reachability from microphone problems.

## Offline-first alternative

- Install optional `faster-whisper` in the active Python 3.12 venv:
  `.venv\\Scripts\\python.exe -m pip install faster-whisper`.
- Obtain a **licensed faster-whisper/CTranslate2 model** independently and
  store it in a local directory containing its files. No model is downloaded
  by Expecto. Validate its model provenance before use.
- Add `AURA_LOCAL_STT_MODEL_DIR=C:\\models\\faster-whisper-small` to `.env`
  (replace with the real full path to the prepared local model directory).
- Restart Expecto and open `http://127.0.0.1:8000`. Allow microphone access.
- Press `V` to record. Press `V` again to stop, or wait up to 14 seconds.
  Expecto sends only the recording to its **same-origin local API**,
  converts it to words on the CPU, and never persists the raw audio.
- `GET /api/voice/diagnostics` indicates whether a local model is configured
  and whether the directory exists. It never lists microphone devices.
- If the model is not configured, the older browser SpeechRecognition remains
  a fallback and now distinguishes `network`, permissions and missing device.

**Operational limitations:** On Windows, faster-whisper usually requires a
working FFmpeg/PyAV decoding stack; the optional dependency must be installed
and tested locally. The new endpoint uses an 8 MB payload limit, a server-side
75-second timeout and a maximum 4000-character transcript. CPU transcription
performance and microphone functionality have NOT been measured on the user's
actual machine. Simultaneous transcriptions are serialized by a lock.

The current voice route is **record then transcribe**, not real-time partial
speech streaming or bidirectional interruptible TTS. Repeated remote STT
fallbacks are not automatic. No app menus or visible buttons were added.

## Validation

```bat
.venv\\Scripts\\python.exe -m pytest -q tests/test_local_stt_v67.py
.venv\\Scripts\\python.exe -m pytest -q tests
```

The GitHub Actions suite validates API shape and synthetic fake STT adapters,
not true microphone hardware or measured voice accuracy. Real audio validation
with Portuguese-European speech remains required before claiming P0 complete.

## Next milestones

P1: cancellable Ollama token streaming with measured first-token latency.
P2: local KaTeX/MathJax with source review and strict CSP.
P3: honest backend event-driven hologram states, reduced motion and frame budgets.
P4: hardware measurements, adaptive inference, profiler and real-model benchmarks.
