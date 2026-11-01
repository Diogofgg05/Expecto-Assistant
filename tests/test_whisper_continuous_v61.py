"""Whisper persistent loading and bounds: fake local model, no external download."""
from __future__ import annotations
import asyncio
import sys
import types
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from aura.app import create_app
from aura.config import Settings
from aura.persistent_whisper import PersistentWhisper, MAX_PCM_BYTES

def make_settings(tmp_path,monkeypatch):
    model=tmp_path/'whisper'; model.mkdir(); (model/'model.bin').write_bytes(b'fake')
    calls={'loads':0,'runs':0}
    class FakeSegment:
        text=' Olá Expecto '
    class FakeModel:
        def __init__(self,*args,**kwargs):
            assert kwargs.get('local_files_only') is True
            calls['loads']+=1
        def transcribe(self,*args,**kwargs):
            calls['runs']+=1
            return iter([FakeSegment()]),{}
    monkeypatch.setitem(sys.modules,'faster_whisper',types.SimpleNamespace(WhisperModel=FakeModel))
    return Settings(data_dir=tmp_path/'data',database_encryption_required=False,
                    voice_whisper_persistent_model=str(model)),calls

def test_load_once_across_transcriptions(tmp_path,monkeypatch):
    settings,calls=make_settings(tmp_path,monkeypatch)
    worker=PersistentWhisper(settings)
    async def work():
        pcm=bytes(32000)
        a=await worker.transcribe_pcm(pcm,partial=True)
        b=await worker.transcribe_pcm(pcm,partial=False)
        assert a['partial'] is True
        assert b['text']=='Olá Expecto'
    asyncio.run(work())
    assert calls=={'loads':1,'runs':2}
    assert worker.loaded

def test_bounds_and_local_capabilities(tmp_path,monkeypatch):
    settings,_=make_settings(tmp_path,monkeypatch)
    worker=PersistentWhisper(settings)
    assert worker.capabilities()['persistent_stt']
    async def work():
        for data in (b'',b'1',bytes(MAX_PCM_BYTES+2)):
            with pytest.raises(ValueError):
                await worker.transcribe_pcm(data)
    asyncio.run(work())
    app=create_app(settings)
    with TestClient(app) as client:
        d=client.get('/api/voice/capabilities').json()
        assert d['persistent_stt'] is True
        assert d['streaming_transport']=='websocket'

def test_websocket_final_and_partial(tmp_path,monkeypatch):
    settings,calls=make_settings(tmp_path,monkeypatch)
    app=create_app(settings)
    with TestClient(app) as client:
        with client.websocket_connect('/api/voice/continuous') as ws:
            ws.send_bytes(bytes(64000))
            ws.send_text('{"type":"flush"}')
            event=ws.receive_json()
            assert event['type']=='final'
            assert event['text']=='Olá Expecto'
            ws.send_bytes(bytes(16000))
            ws.send_text('{"type":"flush"}')
            assert ws.receive_json()['type']=='final'
    assert calls['loads']==1


def test_final_turn_uses_silero_but_partial_remains_fast(tmp_path, monkeypatch):
    settings, counts = make_settings(tmp_path, monkeypatch)
    import sys
    module = sys.modules['faster_whisper']
    original_model = module.WhisperModel
    modes = []
    class CaptureModel(original_model):
        def transcribe(self, *args, **kwargs):
            modes.append(kwargs['vad_filter'])
            return super().transcribe(*args, **kwargs)
    module.WhisperModel = CaptureModel
    worker = PersistentWhisper(settings)
    async def exercise():
        await worker.transcribe_pcm(bytes(32000), partial=True)
        await worker.transcribe_pcm(bytes(32000), partial=False)
    asyncio.run(exercise())
    assert modes == [False, True]
    assert worker.capabilities()['final_vad'] == 'silero'
