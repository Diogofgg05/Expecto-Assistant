# Expecto 6.1 — cancellable voice turns (foundation)

This module is a transport-agnostic voice coordinator, not a complete STT/TTS implementation. It adds bounded transcripts, explicit turn phases, generation tokens, stale-result rejection, and interruption semantics. There are no background threads, model downloads, microphone permissions, or network calls.

The intended next integration is: microphone -> VAD -> faster-whisper -> VoiceTurns -> existing Ollama -> Piper -> playback. All optional heavyweight backends should remain dormant until a user explicitly starts a voice session. Use an independent cancellable task per turn; on barge-in cancel pending work and stop playback immediately. The generation token is a second safety net against providers that do not respect cancellation.

This design is inspired by the cancellable pipeline patterns in open-source voice assistants. Do not claim voice latency or speech quality until testing with actual Portuguese audio, microphone, speakers, and installed models.

Run: `python -m pytest -q tests/test_voice_turns_v61.py`.
