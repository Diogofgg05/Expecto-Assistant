"""Offline API contract tests for the real SSE command transport."""
import json
from fastapi.testclient import TestClient
from aura.app import create_app
from aura.config import Settings


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


def test_streamed_tokens_are_provisional_and_final_is_authoritative(tmp_path, monkeypatch):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    engine=app.state.engine
    async def fake_reply(question, history=None, *, on_token=None):
        assert on_token is not None
        await on_token("2 + 2 ")
        await on_token("= 5")
        return "2 + 2 = 5"
    reviews=[]
    async def review(prompt):
        reviews.append(prompt)
        if len(reviews)==1:
            return json.dumps({"needs_revision":True,"issues":["erro aritmético"]})
        return "2 + 2 = 4"
    monkeypatch.setattr(engine.llm,"reply",fake_reply)
    monkeypatch.setattr(engine.llm,"review_text",review)
    with TestClient(app) as client:
        response=client.post("/api/command/stream",
            json={"message":"Calcula e explica a soma",
                  "session_id":"case-test","history":[]})
        assert response.status_code==200
        assert "text/event-stream" in response.headers["content-type"]
        frames=events(response)
        assert [x["type"] for x in frames]==["token","token","final"]
        assert "".join(x["text"] for x in frames[:2])=="2 + 2 = 5"
        assert frames[-1]["payload"]["text"]=="2 + 2 = 4"
        assert "capture" not in frames[-1]["payload"]


def test_non_llm_command_uses_existing_router_without_tokens(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    with TestClient(app) as client:
        response=client.post("/api/command/stream",json={"message":"Abre a memória"})
        assert response.status_code==200
        items=events(response)
        assert len(items)==1 and items[0]["type"]=="final"
        assert items[0]["payload"]["action"]["panel"]=="memory"


def test_streaming_same_origin_enforcement(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    with TestClient(app) as client:
        response=client.post("/api/command/stream",json={"message":"Abre a memória"},
                             headers={"origin":"https://hostile.example"})
        assert response.status_code==403


def test_streaming_ui_has_cancellation_and_draft_label():
    from pathlib import Path
    script=(Path(__file__).resolve().parent.parent/"web/app.js").read_text(encoding="utf-8")
    assert "/api/command/stream" in script
    assert "RASCUNHO" in script
    assert "abortController?.abort()" in script
    assert "new TextDecoder()" in script
