"""Private, opt-in persistent Whisper worker for streaming PCM16 recognition.

Uses local CTranslate2 faster-whisper model directories and never downloads
model weights. No audio or transcripts are retained after an utterance.
"""
from __future__ import annotations

import asyncio
import importlib
import threading
import time
from pathlib import Path
from .nanomemory import NanoMemoryEngine

SAMPLE_RATE = 16_000
MAX_SECONDS = 15
MAX_PCM_BYTES = SAMPLE_RATE * MAX_SECONDS * 2
MIN_PCM_BYTES = SAMPLE_RATE // 2  # 250 ms
MAX_PARTIAL_CHARS = 1200


class WhisperOfflineError(RuntimeError):
    pass


class PersistentWhisper:
    def __init__(self, settings):
        raw = getattr(settings, 'voice_whisper_persistent_model', '').strip()
        self.model_dir = Path(raw).expanduser().resolve() if raw else None
        self._memory = NanoMemoryEngine(settings)
        self._model_type = None
        self._model = None
        self._lock = threading.Lock()
        self._async_gate = asyncio.Semaphore(1)
        self.loads = 0
        self.utterances = 0
        self.failures = 0
        self.last_ms = None
        self._partial_skipped = 0
        # Require a local CTranslate2 model. A whisper.cpp ggml .bin is not
        # interchangeable with a faster-whisper directory.
        if (self.model_dir and self.model_dir.is_dir() and
                (self.model_dir / 'model.bin').is_file()):
            try:
                self._model_type = importlib.import_module('faster_whisper').WhisperModel
            except (ImportError, AttributeError):
                pass

    @property
    def available(self) -> bool:
        return self._model_type is not None

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def capabilities(self) -> dict:
        return {
            'persistent_stt': self.available,
            'persistent_stt_loaded': self.loaded,
            'input': 'pcm_s16le/mono/16000',
            'streaming_transport': 'websocket',
            'partial_transcripts': True,
            'max_segment_seconds': MAX_SECONDS,
            'engine': 'faster-whisper' if self.available else 'unavailable',
            'final_vad': 'silero' if self.available else 'disabled',
        }

    def _infer(self, pcm: bytes, *, partial: bool = False) -> str:
        # Threads may still run after the outer coroutine is cancelled.
        # A thread lock prevents simultaneous use of one model/ONNX session.
        with self._lock:
            if self._model is None:
                self._model = self._model_type(
                    str(self.model_dir), device='cpu', compute_type='int8',
                    cpu_threads=(2 if self._memory.decide('standard').effective == 'eco'
                                 else 4), num_workers=1, local_files_only=True,
                )
                self.loads += 1
            import numpy as np
            audio = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
            segments, _ = self._model.transcribe(
                audio, language='pt', beam_size=1,
                condition_on_previous_text=False,
                # faster-whisper bundles Silero VAD. Use it for finalized
                # turns only; partial 2–5 s windows must remain responsive.
                vad_filter=not partial,
                vad_parameters={'min_silence_duration_ms': 500, 'speech_pad_ms': 180}
                if not partial else None,
            )
            # Iteration actually runs the inference (segments is a generator).
            return ' '.join(segment.text.strip() for segment in segments
                            if getattr(segment, 'text', '').strip()).strip()[:2000]

    async def transcribe_pcm(self, pcm: bytes, *, partial: bool = False) -> dict:
        if not self.available:
            raise WhisperOfflineError('Modelo Whisper persistente indisponível.')
        if not isinstance(pcm, bytes) or len(pcm) % 2 or not MIN_PCM_BYTES <= len(pcm) <= MAX_PCM_BYTES:
            raise ValueError('Segmento PCM16 fora dos limites permitidos.')
        started = time.perf_counter()
        async with self._async_gate:
            try:
                text = await asyncio.wait_for(asyncio.to_thread(self._infer, pcm, partial=partial), timeout=45)
            except asyncio.TimeoutError as exc:
                self.failures += 1
                raise WhisperOfflineError('Whisper persistente excedeu 45 segundos.') from exc
            except Exception as exc:
                self.failures += 1
                raise WhisperOfflineError('Falha no reconhecimento local.') from exc
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        if not partial:
            self.utterances += 1
            self.last_ms = elapsed
        return {
            'text': text[:MAX_PARTIAL_CHARS] if partial else text,
            'processing_ms': elapsed,
            'partial': partial,
        }
