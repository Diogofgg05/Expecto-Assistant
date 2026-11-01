"""Local voice contracts: strict bounds and mocked binaries, no real models."""
from __future__ import annotations

import io
import wave

from fastapi.testclient import TestClient
from aura.app import create_app
from aura.config import Settings
from aura.local_voice import LocalVoice, VoiceInvalid, validate_wav


def wav_bytes(seconds=0.5):
    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\\x00\\x00' * round(16000 * seconds))
    return data.getvalue()


def test_wav_format_and_duration_guards():
    assert validate_wav(wav_bytes(.5)) == .5
    for data in [b'', b'invalid' * 150, wav_bytes(16), wav_bytes(.1)]:
        try:
            validate_wav(data)
        except VoiceInvalid:
            pass
        else:
            raise AssertionError('Invalid audio accepted')


def make_settings(tmp_path):
    whisper = tmp_path / 'whisper'
    piper = tmp_path / 'piper'
    whisper.write_text('#!/bin/sh\\nexit 0\\n')
    piper.write_text('#!/bin/sh\\nexit 0\\n')
    whisper.chmod(0o755)
    piper.chmod(0o755)
    model_stt = tmp_path / 'speech.bin'
    model_stt.write_bytes(b'model-placeholder')
    model_tts = tmp_path / 'voice.onnx'
    model_tts.write_bytes(b'model-placeholder')
    return Settings(
        data_dir=tmp_path / 'data',
        database_encryption_required=False,
        voice_whisper_binary=str(whisper), voice_whisper_model=str(model_stt),
        voice_piper_binary=str(piper), voice_piper_model=str(model_tts),
    )


def test_endpoints_unavailable_with_safe_default(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        capabilities = client.get('/api/voice/capabilities').json()
        assert capabilities['local_stt'] is False
        assert capabilities['local_tts'] is False
        assert client.post('/api/voice/transcribe', content=wav_bytes(.5),
                           headers={'Content-Type': 'audio/wav'}).status_code == 503
        assert client.post('/api/voice/synthesize', json={'text': 'Olá'}).status_code == 503


def test_local_stt_and_tts_mock(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    app = create_app(settings)
    async def fake_run(argv, *, input_bytes, timeout):
        from pathlib import Path
        if '-of' in argv:
            prefix = Path(argv[argv.index('-of') + 1])
            Path(str(prefix) + '.txt').write_text('Olá, Expecto.', encoding='utf-8')
        else:
            out = Path(argv[argv.index('--output_file') + 1])
            out.write_bytes(wav_bytes(.5))
    monkeypatch.setattr('aura.local_voice._run', fake_run)
    with TestClient(app) as client:
        caps = client.get('/api/voice/capabilities').json()
        assert caps['local_stt'] and caps['local_tts']
        res = client.post('/api/voice/transcribe', content=wav_bytes(.5),
                          headers={'Content-Type':'audio/wav'})
        assert res.status_code == 200
        assert res.json()['text'] == 'Olá, Expecto.'
        assert res.json()['processing_ms'] >= 0
        res = client.post('/api/voice/synthesize', json={'text':'Bom dia.'})
        assert res.status_code == 200
        assert res.headers['content-type'].startswith('audio/wav')
        assert res.content[:4] == b'RIFF'


def test_voice_rejects_unsupported_media_and_oversized_audio(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.post('/api/voice/transcribe', content=wav_bytes(.5),
                           headers={'Content-Type': 'application/json'}).status_code == 415
        assert client.post('/api/voice/transcribe', content=b'R' * (512 * 1024 + 1),
                           headers={'Content-Type': 'audio/wav'}).status_code == 413
        assert client.post('/api/voice/transcribe', content=wav_bytes(.1),
                           headers={'Content-Type':'audio/wav'}).status_code == 422
        assert client.post('/api/voice/synthesize', json={'text':'x'*241}).status_code == 422
