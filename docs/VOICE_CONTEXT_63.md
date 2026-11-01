# EXPECTO 6.3 — Whisper final VAD, reliability, and context correctness

Three focused changes built on 6.2:

1. The offline faster-whisper backend enables its built-in Silero VAD
   for **completed utterances**. Intermediate provisional recognitions skip
   this extra preprocessing to retain lower-latency feedback. The VAD is
   not a separate audio listener and does not enable always-on recording.
2. If a short microphone capture finishes while the local WebSocket is
   still connecting, its PCM samples are kept until the connection opens.
   The client then transmits the samples and explicitly flushes the turn.
3. The FAST inference path no longer skips personal retrieval when an
   earlier conversation is supplied. Context-dependent definitions now
   use STANDARD, protecting the meaning of follow-up questions.

The existing AudioWorklet + adaptive energy gate remains the primary
client-side speech end detector. Silero VAD is applied within final
Whisper inference, not directly in that real-time callback.

## Tests
- `tests/test_whisper_continuous_v61.py`: provisional `vad_filter=False`,
  final `vad_filter=True`, model loaded once, WebSocket limits.
- `tests/test_performance_engine_v60.py`: FAST disabled when conversation
  history exists.

No real CPU, RAM, accuracy or Portuguese speech timing improvement has been
measured on the user's hardware. The changes remain on a stacked draft PR,
not on the repository's main branch.
