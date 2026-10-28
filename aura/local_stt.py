"""Optional, strictly local faster-whisper transcription; no model downloads.

The browser captures audio after explicit user interaction. This service accepts
bounded media bytes and transcribes with an already-installed model directory.
It does not persist recordings, call the network or modify the encrypted DB.
"""
from __future__ import annotations

import io
import threading
from pathlib import Path


class STTUnavailable(RuntimeError):
    """The optional local speech engine cannot run on this installation."""


class STTInvalidAudio(ValueError):
    """An audio payload is empty, unsupported or could not be decoded."""


class LocalSpeech:
    """Lazily loaded offline speech engine; one inference at a time."""

    MAX_AUDIO_BYTES = 8 * 1024 * 1024
    ALLOWED_TYPES = frozenset({
        "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav",
        "audio/mp4", "audio/mpeg", "video/webm"
    })

    def __init__(self, model_dir: str = "", *, backend_factory=None):
        self.model_dir = model_dir.strip()
        self._backend = None
        self._lock = threading.Lock()
        self._backend_factory = backend_factory

    @property
    def configured(self) -> bool:
        return bool(self.model_dir)

    def status(self) -> dict:
        p = Path(self.model_dir).expanduser() if self.configured else None
        return {
            "configured": self.configured,
            "model_directory_exists": bool(p and p.is_dir()),
            "engine": "faster-whisper-local-optional",
            "model_loaded": self._backend is not None,
            "network_downloads": False,
            "max_audio_bytes": self.MAX_AUDIO_BYTES,
            "languages": ["pt"],
        }

    def _model(self):
        if not self.configured:
            raise STTUnavailable("O motor local não está configurado.")
        folder = Path(self.model_dir).expanduser()
        if not folder.is_dir():
            raise STTUnavailable("A pasta do modelo local não existe.")
        if self._backend is None:
            try:
                if self._backend_factory is not None:
                    backend = self._backend_factory(folder)
                else:
                    from faster_whisper import WhisperModel
                    backend = WhisperModel(str(folder), device="cpu",
                                           compute_type="int8", local_files_only=True)
            except (ImportError, RuntimeError, ValueError, OSError) as exc:
                raise STTUnavailable("O motor faster-whisper local está indisponível.") from exc
            self._backend = backend
        return self._backend

    def transcribe(self, audio: bytes, mime_type: str) -> str:
        """Synchronous worker entrypoint; call with asyncio.to_thread from FastAPI."""
        if not isinstance(audio, bytes) or not 128 <= len(audio) <= self.MAX_AUDIO_BYTES:
            raise STTInvalidAudio("O áudio está vazio ou excede o limite de 8 MB.")
        mime = mime_type.lower().split(";", 1)[0].strip()
        if mime not in self.ALLOWED_TYPES:
            raise STTInvalidAudio("Formato de áudio não suportado.")
        with self._lock:
            model = self._model()
            try:
                segments, _ = model.transcribe(
                    io.BytesIO(audio), language="pt", beam_size=1, vad_filter=True
                )
                out = []
                size = 0
                for segment in segments:
                    value = str(segment.text).strip()
                    if value:
                        out.append(value)
                        size += len(value)
                        if size >= 4000:
                            break
                return " ".join(out)[:4000].strip()
            except (RuntimeError, ValueError, OSError, EOFError) as exc:
                raise STTInvalidAudio("Não foi possível descodificar ou transcrever o áudio.") from exc
