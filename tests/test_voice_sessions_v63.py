"""Offline regression tests for voice session API and stale-result protection."""
import pytest
from fastapi.testclient import TestClient
from aura.voice_sessions import VoiceCapacityError, VoiceSessions
from aura.app import create_app
from aura.config import Settings

def test_barge_in_rejects_stale_transcript():
    sessions = VoiceSessions()
    first = sessions.listen()
    second = sessions.listen(first["session_id"])
    sid = first["session_id"]
    assert sessions.transcript(sid, first["generation"], "stale")["kind"] == "stale"
    assert sessions.transcript(sid, second["generation"], "new")["kind"] == "request_llm"

def test_expired_session_and_capacity_recovers():
    now = [1.0]
    sessions = VoiceSessions(max_sessions=1, idle_ttl=10, clock=lambda: now[0])
    first = sessions.listen()
    with pytest.raises(VoiceCapacityError):
        sessions.listen()
    now[0] = 11.0
    second = sessions.listen()
    assert first["session_id"] != second["session_id"]
    with pytest.raises(KeyError):
        sessions.status(first["session_id"])

def test_isolated_sessions():
    sessions = VoiceSessions()
    a = sessions.listen()
    b = sessions.listen()
    assert a["session_id"] != b["session_id"]
    assert sessions.transcript(a["session_id"], a["generation"], "hello")["kind"] == "request_llm"
    assert sessions.status(b["session_id"])["phase"] == "listening"

def test_stop_invalidates_session():
    sessions = VoiceSessions()
    start = sessions.listen()
    assert sessions.stop(start["session_id"])["kind"] == "cancel_previous"
    with pytest.raises(KeyError):
        sessions.answer(start["session_id"], start["generation"], "no")

def test_invalid_session_limits():
    with pytest.raises(ValueError):
        VoiceSessions(max_sessions=0)
    with pytest.raises(ValueError):
        VoiceSessions(idle_ttl=0)

def test_http_voice_end_to_end(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        start = client.post("/api/voice/listen", json={})
        assert start.status_code == 200
        sid, generation = start.json()["session_id"], start.json()["generation"]
        transcript = client.post("/api/voice/transcript", json={"session_id":sid, "generation":generation, "text":"Olá, Expecto"})
        assert transcript.status_code == 200
        assert transcript.json()["kind"] == "request_llm"
        answer = client.post("/api/voice/answer", json={"session_id":sid, "generation":generation, "text":"Olá!"})
        assert answer.json()["kind"] == "request_tts"
        finished = client.post("/api/voice/finished", json={"session_id":sid, "generation":generation})
        assert finished.json()["kind"] == "idle"
        assert client.post("/api/voice/stop", json={"session_id":sid}).status_code == 200
        assert client.get("/api/voice/status/" + sid).status_code == 404

def test_http_stale_generation_and_bad_payload(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        start = client.post("/api/voice/listen", json={}).json()
        sid, old = start["session_id"], start["generation"]
        later = client.post("/api/voice/listen", json={"session_id":sid}).json()
        assert later["generation"] > old
        response = client.post("/api/voice/transcript", json={"session_id":sid, "generation":old, "text":"comando antigo"})
        assert response.json()["kind"] == "stale"
        assert client.post("/api/voice/transcript", json={"session_id":sid, "generation":later["generation"], "text":""}).status_code == 422
        assert client.post("/api/voice/answer", json={"session_id":"invalid", "generation":1, "text":"x"}).status_code == 422

def test_http_rejects_cross_origin(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        result = client.post("/api/voice/listen", json={}, headers={"origin":"https://evil.example"})
        assert result.status_code == 403
