"""Deterministic architectural and transport regression tests for 7.6."""
import asyncio
import json
import httpx

from aura.config import Settings
from aura.database import Database
from aura.llm import Ollama, SYSTEM
from aura.llm_pipeline.prompt import compose_messages
from aura.llm_pipeline.context import collect_context
from aura.performance import FAST
from aura.nanomemory import NanoMemoryEngine


def test_prompt_preserves_system_and_bounded_history(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    turns = [{"role": "user", "content": "OLD " * 1000}] + [
        {"role": "assistant", "content": "recent"} for _ in range(9)]
    msg = compose_messages(settings, "Define compilador", turns, FAST, "", SYSTEM)
    assert msg[0]["role"] == "system"
    assert "Nunca afirmes" in msg[0]["content"]
    assert msg[-1] == {"role": "user", "content": "Define compilador"}
    assert len(msg) <= 10
    assert "OLD OLD" not in str(msg)


def test_fast_context_never_reads_private_notes(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    db = Database(tmp_path / "test.sqlite3", require_encryption=False)
    class NoPrivateRead:
        async def recall(self, *args, **kwargs):
            raise AssertionError("private memory accessed")
        async def recall_episodes(self, *args, **kwargs):
            raise AssertionError("private episodes accessed")
        def query_scope(self):
            raise AssertionError("private embeddings accessed")
    policy = NanoMemoryEngine(settings).decide("fast", prediction=FAST.max_predict)
    result = asyncio.run(collect_context(
        settings, db, NoPrivateRead(), "O que é Python?", FAST, policy))
    assert result == ("", 0, 0)


def test_http_fallback_and_metrics_are_anonymous(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        ollama_model="base:latest", ollama_fast_model="missing:latest")
    llm = Ollama(settings, Database(tmp_path / "fallback.sqlite3", require_encryption=False))
    original = httpx.AsyncClient
    requested = []
    def response(request):
        model = json.loads(request.content)["model"]
        requested.append(model)
        if model == "missing:latest":
            return httpx.Response(404)
        return httpx.Response(200, json={"message": {"content": "Resposta correta"}})
    monkeypatch.setattr("aura.llm.httpx.AsyncClient",
        lambda *a, **kw: original(*a, transport=httpx.MockTransport(response),
                                 **{k:v for k,v in kw.items() if k != "transport"}))
    assert asyncio.run(llm.reply("Define compilador")) == "Resposta correta"
    assert requested == ["missing:latest", "base:latest"]
    assert asyncio.run(llm.reply("Define compilador")) == "Resposta correta"
    assert requested[-1] == "base:latest"
    assert llm.metrics.summary()["failed_requests"] == 0
    assert "Define compilador" not in json.dumps(llm.metrics.summary())


def test_ndjson_stream_chunks_and_metrics(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    llm = Ollama(settings, Database(tmp_path / "stream.sqlite3", require_encryption=False))
    original = httpx.AsyncClient
    def response(_request):
        return httpx.Response(200, text=(
            '{"message":{"content":"Olá "},"done":false}\n'
            '{"message":{"content":"mundo"},"done":false}\n'
            '{"done":true,"eval_count":2,"eval_duration":1000000000}\n'))
    monkeypatch.setattr("aura.llm.httpx.AsyncClient",
        lambda *a, **kw: original(*a, transport=httpx.MockTransport(response),
                                 **{k:v for k,v in kw.items() if k != "transport"}))
    async def exercise():
        pieces = []
        async def callback(piece):
            pieces.append(piece)
        return await llm.reply("Define compilador", on_token=callback), pieces
    answer, pieces = asyncio.run(exercise())
    assert answer == "Olá mundo"
    assert pieces == ["Olá ", "mundo"]
    assert llm.metrics.summary()["failed_requests"] == 0
