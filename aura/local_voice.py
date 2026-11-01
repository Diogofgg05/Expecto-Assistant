"""Optional local speech engine. No cloud speech requests, no shell commands.

Whisper.cpp receives 16 kHz mono PCM WAV, Piper returns a WAV file per
short sentence. Temporary audio is erased on completion or failure.
"""
from __future__ import annotations

import asyncio
import io
import os
import tempfile
import time
import wave
from pathlib import Path


MAX_WAV_BYTES = 512 * 1024
MAX_TEXT = 240
MAX_SECONDS = 15.0
MIN_SECONDS = 0.25


class VoiceUnavailable(RuntimeError):
    pass


class VoiceInvalid(ValueError):
    pass


def _resolve_binary(name: str) -> Path | None:
    if not name.strip():
        return None
    path = Path(name).expanduser().resolve()
    if not path.is_file():
        return None
    if os.name != 'nt' and not os.access(path, os.X_OK):
        return None
    return path


def _resolve_model(name: str, extension: str | None = None) -> Path | None:
    if not name.strip():
        return None
    path = Path(name).expanduser().resolve()
    return path if path.is_file() and (extension is None or path.suffix == extension) else None


def validate_wav(raw: bytes) -> float:
    """Reject compressed/incorrect audio before launching a local model."""
    if not isinstance(raw, bytes) or not 1000 <= len(raw) <= MAX_WAV_BYTES:
        raise VoiceInvalid('O áudio excede o tamanho permitido ou está vazio.')
    try:
        with wave.open(io.BytesIO(raw), 'rb') as wav:
            if (wav.getnchannels() != 1 or wav.getsampwidth() != 2 or
                    wav.getframerate() != 16000 or wav.getcomptype() != 'NONE'):
                raise VoiceInvalid('Áudio obrigatório: WAV PCM16, mono, 16 kHz.')
            seconds = wav.getnframes() / wav.getframerate()
            if not MIN_SECONDS <= seconds <= MAX_SECONDS:
                raise VoiceInvalid('A gravação deve ter entre 0,25 e 15 segundos.')
            if len(raw) < 44 + wav.getnframes() * 2:
                raise VoiceInvalid('Gravação truncada.')
            return seconds
    except (EOFError, wave.Error) as exc:
        raise VoiceInvalid('Ficheiro WAV inválido.') from exc


async def _run(argv: list[str], *, input_bytes: bytes | None, timeout: float) -> None:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if input_bytes is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(process.communicate(input=input_bytes), timeout=timeout)
        if process.returncode != 0:
            raise VoiceUnavailable('O motor local de voz terminou com erro.')
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise


class LocalVoice:
    def __init__(self, settings):
        self.stt_bin = _resolve_binary(settings.voice_whisper_binary)
        self.stt_model = _resolve_model(settings.voice_whisper_model, '.bin')
        self.tts_bin = _resolve_binary(settings.voice_piper_binary)
        self.tts_model = _resolve_model(settings.voice_piper_model, '.onnx')
        # Keep local speech bounded on older machines.
        self._stt_lock = asyncio.Semaphore(1)
        self._tts_lock = asyncio.Semaphore(1)

    @property
    def stt_available(self) -> bool:
        return bool(self.stt_bin and self.stt_model)

    @property
    def tts_available(self) -> bool:
        return bool(self.tts_bin and self.tts_model)

    def capabilities(self) -> dict:
        return {
            'local_stt': self.stt_available,
            'local_tts': self.tts_available,
            'audio': 'wav/pcm16/mono/16000',
            'max_recording_seconds': MAX_SECONDS,
        }

    async def transcribe(self, wav_data: bytes) -> dict:
        if not self.stt_available:
            raise VoiceUnavailable('Whisper local não está configurado.')
        duration = validate_wav(wav_data)
        async with self._stt_lock:
            started = time.perf_counter()
            with tempfile.TemporaryDirectory(prefix='expecto-stt-') as folder:
                path = Path(folder)
                sound = path / 'recording.wav'
                prefix = path / 'transcript'
                sound.write_bytes(wav_data)
                command = [
                    str(self.stt_bin), '-m', str(self.stt_model),
                    '-f', str(sound), '-l', 'pt', '-nt',
                    '-otxt', '-of', str(prefix),
                    '-t', '4',
                ]
                try:
                    await _run(command, input_bytes=None, timeout=40)
                except asyncio.TimeoutError as exc:
                    raise VoiceUnavailable('O reconhecimento local excedeu 40 segundos.') from exc
                textfile = Path(str(prefix) + '.txt')
                if not textfile.exists():
                    raise VoiceUnavailable('O Whisper não produziu transcrição.')
                spoken = textfile.read_text(encoding='utf-8').strip()[:2000]
                return {
                    'text': spoken,
                    'duration_s': round(duration, 2),
                    'processing_ms': round((time.perf_counter() - started) * 1000, 1),
                }

    async def synthesize(self, text: str) -> bytes:
        if not self.tts_available:
            raise VoiceUnavailable('Piper local não está configurado.')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= MAX_TEXT:
            raise VoiceInvalid('O texto para voz deve conter entre 1 e 240 caracteres.')
        # One sentence per call: the caller can pipeline synthesis and playback.
        async with self._tts_lock:
            with tempfile.TemporaryDirectory(prefix='expecto-tts-') as folder:
                output = Path(folder) / 'speech.wav'
                cmd = [str(self.tts_bin), '--model', str(self.tts_model),
                       '--output_file', str(output)]
                try:
                    await _run(cmd, input_bytes=(text.strip() + '\n').encode('utf-8'), timeout=30)
                except asyncio.TimeoutError as exc:
                    raise VoiceUnavailable('A síntese local excedeu 30 segundos.') from exc
                if not output.exists() or output.stat().st_size > 4 * 1024 * 1024:
                    raise VoiceUnavailable('O sintetizador não produziu áudio válido.')
                raw = output.read_bytes()
                if not raw.startswith(b'RIFF') or raw[8:12] != b'WAVE':
                    raise VoiceUnavailable('Formato de áudio Piper inválido.')
                return raw
