"""Expecto voice: fail-closed local STT, no download, no persistent audio."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from aura.local_stt import LocalSpeech, STTUnavailable, STTInvalidAudio
from aura.config import Settings
from aura.app import create_app


def test_disabled_by_default(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    with TestClient(app) as client:
        d=client.get("/api/voice/diagnostics")
        assert d.status_code==200 and d.json()["configured"] is False
        assert client.post("/api/voice/transcribe",data=b'x'*150,
                           headers={"content-type":"audio/webm"}).status_code==503


def test_only_preinstalled_model_and_size_bounded(tmp_path):
    service=LocalSpeech(str(tmp_path/"absent"))
    assert service.status()["model_directory_exists"] is False
    with pytest.raises(STTUnavailable):
        service.transcribe(b"x"*150,"audio/webm")
    with pytest.raises(STTInvalidAudio):
        service.transcribe(b"x"*127,"audio/webm")
    with pytest.raises(STTInvalidAudio):
        service.transcribe(b"x"*150,"application/octet-stream")


def test_backend_is_lazy_and_transcript_bounded(tmp_path):
    created=[]
    class Segment:
        def __init__(self,text):self.text=text
    class Fake:
        def transcribe(self,file,**kwargs):
            assert kwargs["language"]=="pt"
            assert file.read()==b"x"*150
            return [Segment(" Olá "),Segment(" Expecto ")],None
    engine=LocalSpeech(str(tmp_path),backend_factory=lambda folder:created.append(folder) or Fake())
    assert not created
    assert engine.transcribe(b"x"*150,"audio/webm")=="Olá Expecto"
    assert len(created)==1
    assert engine.status()["model_loaded"]


def test_transcription_api_calls_offline_engine(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False,
                            local_stt_model_dir=str(tmp_path)))
    app.state.local_speech._backend_factory=lambda folder: type(
        "Fake",(),{"transcribe":lambda self,file,**kw: (
            [type("Segment",(),{"text":"Bom dia"})()],None)})()
    with TestClient(app) as client:
        res=client.post("/api/voice/transcribe",content=b"x"*150,
                        headers={"content-type":"audio/webm"})
        assert res.status_code==200 and res.json()["text"]=="Bom dia"
        assert res.json()["source"]=="local_offline"
        bad=client.post("/api/voice/transcribe",content=b"x"*150,
                        headers={"content-type":"application/json"})
        assert bad.status_code==415
        short=client.post("/api/voice/transcribe",content=b"x",
                          headers={"content-type":"audio/webm"})
        assert short.status_code==422
        hostile=client.post("/api/voice/transcribe",content=b"x"*150,
                            headers={"content-type":"audio/webm","origin":"https://evil.example"})
        assert hostile.status_code==403


def test_browser_source_has_no_infinite_network_retries():
    source=(Path(__file__).resolve().parent.parent/"web/app.js").read_text(encoding="utf-8")
    assert "voiceErrorMessage" in source
    assert "getUserMedia" in source
    assert "MediaRecorder" in source
    assert "/api/voice/diagnostics" in source
    assert "/api/voice/transcribe" in source
    assert "setInterval(()=>voice()" not in source
