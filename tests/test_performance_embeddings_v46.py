"""Performance 4.6: reusable Ollama embedding connections, bounded and private."""
from __future__ import annotations

import asyncio
import httpx
import pytest

from aura.config import Settings
from aura.memory import MemoryEngine


class FakeClient:
    """One fake socket-based client for both single and batch embedding."""
    created = []
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.is_closed = False
        self.calls = []
        type(self).created.append(self)

    async def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        inputs = json["input"]
        vectors = [[1.0, 0.0]] if isinstance(inputs, str) else [
            [1.0, 0.0] for _ in inputs
        ]
        return httpx.Response(
            200,
            json={"embeddings": vectors},
            request=httpx.Request("POST", url),
        )

    async def aclose(self):
        self.is_closed = True


def test_embedding_connection_reused_across_multiple_queries(monkeypatch, tmp_path):
    FakeClient.created = []
    monkeypatch.setattr("aura.http_pool.httpx.AsyncClient", FakeClient)
    memory = MemoryEngine(Settings(
        data_dir=tmp_path, embedding_model="embedding-local"), object())

    async def run():
        before = memory.transport_status()
        assert before["created"] == 0 and before["active"] is False
        for _ in range(8):
            assert await memory._embed("O que é um vetor?") == [1.0, 0.0]
        assert len(FakeClient.created) == 1
        fake = FakeClient.created[0]
        assert len(fake.calls) == 8
        assert fake.kwargs["trust_env"] is False
        assert fake.kwargs["limits"].max_connections == 2
        assert all(c[2].read == 8.0 for c in fake.calls)
        assert memory.transport_status()["created"] == 1
        assert memory.transport_status()["private_content_stored"] is False
        assert "O que é um vetor?" not in str(memory.transport_status())
        await memory.close()
        assert fake.is_closed
        assert memory.transport_status()["active"] is False

    asyncio.run(run())


def test_batch_embedding_reuses_same_transport_as_query(monkeypatch, tmp_path):
    FakeClient.created = []
    monkeypatch.setattr("aura.http_pool.httpx.AsyncClient", FakeClient)

    class DB:
        def __init__(self):
            self.indexed = []
        def pending_episode_embeddings(self, model, months, limit):
            if self.indexed:
                return []
            return [{"id":"first","content":"Dado A"},
                    {"id":"second","content":"Dado B"}]
        def save_episode_vector(self, id, model, vector):
            self.indexed.append((id, model, vector))

    db = DB()
    memory = MemoryEngine(Settings(
        data_dir=tmp_path, embedding_model="embedding-local"), db)
    async def run():
        assert await memory._embed("pergunta") == [1.0, 0.0]
        result = await memory.index_episode_pending(limit=2)
        assert result["indexed"] == 2 and result["pending"] == 0
        assert len(FakeClient.created) == 1
        fake = FakeClient.created[0]
        assert len(fake.calls) == 2
        assert isinstance(fake.calls[1][1]["input"], list)
        assert fake.calls[1][2].read == 30.0
        assert db.indexed == [
            ("first", "embedding-local", [1.0,0.0]),
            ("second", "embedding-local", [1.0,0.0]),
        ]
        await memory.close()
        assert fake.is_closed
    asyncio.run(run())


def test_close_no_traffic_and_new_event_loop_recreates_client(monkeypatch, tmp_path):
    FakeClient.created = []
    monkeypatch.setattr("aura.http_pool.httpx.AsyncClient", FakeClient)
    memory = MemoryEngine(Settings(data_dir=tmp_path, embedding_model="test"), object())
    asyncio.run(memory.close())
    assert not FakeClient.created
    assert asyncio.run(memory._embed("primeiro")) == [1.0, 0.0]
    assert asyncio.run(memory._embed("segundo")) == [1.0, 0.0]
    assert len(FakeClient.created) == 2
    assert FakeClient.created[0].is_closed
    asyncio.run(memory.close())
    assert FakeClient.created[1].is_closed


def test_empty_model_never_allocates_an_http_client(monkeypatch, tmp_path):
    FakeClient.created = []
    monkeypatch.setattr("aura.http_pool.httpx.AsyncClient", FakeClient)
    memory = MemoryEngine(Settings(data_dir=tmp_path, embedding_model=""), object())
    assert asyncio.run(memory._embed("privado")) is None
    assert memory.transport_status()["created"] == 0
    asyncio.run(memory.close())
    assert FakeClient.created == []


def test_embedded_http_failure_preserves_lexical_fallback(monkeypatch,tmp_path):
    class FailureClient(FakeClient):
        async def post(self, url, *, json, timeout):
            raise httpx.ConnectError("offline")
    monkeypatch.setattr("aura.http_pool.httpx.AsyncClient", FailureClient)
    memory = MemoryEngine(Settings(data_dir=tmp_path,embedding_model="test"),object())

    async def run():
        assert await memory._embed("private question") is None
        assert memory.transport_status()["created"] == 1
        await memory.close()
    asyncio.run(run())


def test_application_shutdown_closes_activated_memory(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from aura.app import create_app

    observed = []
    close_original = MemoryEngine.close

    async def observed_close(self):
        observed.append(self)
        await close_original(self)

    monkeypatch.setattr(MemoryEngine, "close", observed_close)
    app = create_app(Settings(data_dir=tmp_path,
                              database_encryption_required=False,
                              embedding_model="test"))

    with TestClient(app) as client:
        response = client.get("/api/memory/search", params={"q":"processador"})
        assert response.status_code == 200

    assert len(observed) == 1
    assert observed[0].transport_status()["active"] is False
