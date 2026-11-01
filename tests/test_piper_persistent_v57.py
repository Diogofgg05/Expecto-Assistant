"""Persistent Piper integration tests, using fake ONNX model (no real audio packages)."""
from __future__ import annotations

import asyncio
import sys
import types
import wave
import io

import pytest
from aura.config import Settings
from aura.local_voice import LocalVoice, VoiceUnavailable


def config(tmp_path, *, cli=False):
    model = tmp_path / 'pt_PT-voice.onnx'
    model.write_bytes(b'fake-model')
    (tmp_path / 'pt_PT-voice.onnx.json').write_text('{}', encoding='utf-8')
    binary = tmp_path / 'piper'
    if cli:
        binary.write_bytes(b'fake-binary')
        binary.chmod(0o755)
    return Settings(
        data_dir=tmp_path,
        database_encryption_required=False,
        voice_piper_inprocess=True,
        voice_piper_model=str(model),
        voice_piper_binary=str(binary) if cli else '',
    )


def fake_piper(monkeypatch, *, fail_load=False):
    counts = {'loads': 0, 'syntheses': 0}
    class FakeVoice:
        @classmethod
        def load(cls, path):
            counts['loads'] += 1
            if fail_load:
                raise RuntimeError('Invalid ONNX')
            return cls()

        def synthesize_wav(self, text, wav):
            counts['syntheses'] += 1
            wav.setframerate(22050)
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.writeframes(bytes(2205 * 2))
    monkeypatch.setitem(sys.modules, 'piper', types.SimpleNamespace(PiperVoice=FakeVoice))
    return counts


def test_model_loads_once_and_reuses_same_session(tmp_path, monkeypatch):
    counts = fake_piper(monkeypatch)
    voice = LocalVoice(config(tmp_path))
    assert voice.capabilities()['tts_mode'] == 'persistent'
    assert voice.capabilities()['tts_model_loaded'] is False

    async def run():
        return await asyncio.gather(*(voice.synthesize('Uma frase.') for _ in range(4)))

    outputs = asyncio.run(run())
    assert len(outputs) == 4
    assert all(b.startswith(b'RIFF') for b in outputs)
    assert counts == {'loads': 1, 'syntheses': 4}
    assert voice.capabilities()['tts_model_loaded'] is True


def test_loading_failure_disables_persistent_without_retry(tmp_path, monkeypatch):
    counts = fake_piper(monkeypatch, fail_load=True)
    voice = LocalVoice(config(tmp_path))
    async def run():
        with pytest.raises(VoiceUnavailable):
            await voice.synthesize('Olá.')
        assert voice.capabilities()['tts_mode'] == 'disabled'
        with pytest.raises(VoiceUnavailable):
            await voice.synthesize('Outra.')
    asyncio.run(run())
    assert counts['loads'] == 1


def test_python_dependency_absent_retains_cli_fallback(tmp_path, monkeypatch):
    # A module without PiperVoice behaves the same as a missing optional dependency.
    monkeypatch.setitem(sys.modules, 'piper', types.SimpleNamespace())
    voice = LocalVoice(config(tmp_path, cli=True))
    assert voice.capabilities()['tts_mode'] == 'cli'
    assert voice.tts_available


def test_missing_config_disables_persistent_voice(tmp_path, monkeypatch):
    fake_piper(monkeypatch)
    settings = config(tmp_path)
    (tmp_path / 'pt_PT-voice.onnx.json').unlink()
    voice = LocalVoice(settings)
    assert voice.capabilities()['tts_mode'] == 'disabled'
    assert not voice.tts_available


def test_persistent_voice_rejects_text_too_long(tmp_path, monkeypatch):
    fake_piper(monkeypatch)
    voice = LocalVoice(config(tmp_path))
    from aura.local_voice import VoiceInvalid
    async def run():
        with pytest.raises(VoiceInvalid):
            await voice.synthesize('a' * 300)
    asyncio.run(run())
