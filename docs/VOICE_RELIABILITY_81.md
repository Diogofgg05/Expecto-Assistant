# EXPECTO 8.1 — Reliable Local Microphone Lifecycle

**Status:** feature PR, not integrated into `main`.

## Problems addressed

The persistent Whisper WebSocket previously had no connection timeout, so
an indefinitely pending handshake could leave the microphone session stuck.
Unexpected WebSocket errors could clear the user-visible status without
closing the recording tracks. Waiting indefinitely for a final transcription
could likewise prevent a new voice session from starting.

## Changes

- Timeout of 5 seconds for the local Whisper WebSocket handshake.
- Timeout of 30 seconds for a final Whisper transcription (HTTP/WS).
- Error and unexpected-close paths free the microphone track, AudioContext,
  socket and pending timers. Duplicate close/error callbacks are suppressed.
- Successful WebSocket results clear all deadlines and retain PT-PT text.
- Permission denied, no microphone, busy microphone and insecure-context
  errors show actionable local messages.
- Cancel remains silent and idempotent.
- Browser-based fallback remains unchanged; no automatic cloud upload or new
  network origin is introduced.

## Validation

```bash
node --check web/local-voice.js
node --test tests/test_local_voice_lifecycle_v81.cjs
node --test tests/test_voice_browser_v54.cjs tests/test_voice_prefetch_v56.cjs tests/test_audio_pipeline_v62.cjs
python -m pytest -q tests
```

The existing GitHub quality gate includes the new browser test.
These are deterministic simulated microphone/network failure tests, not a
claim that physical-device compatibility, live Whisper accuracy or speech
latency has been measured on Windows, Linux or mobile.

This PR targets the 8.0 feature branch to avoid modifying `main` or
merging unreviewed ancestry automatically.
