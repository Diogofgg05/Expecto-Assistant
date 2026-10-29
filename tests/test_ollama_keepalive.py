"""Tests for scoped Ollama HTTP client lifetime, no live server required."""
import asyncio
import httpx
from aura.multilayer_reasoning import OllamaMultiLayerAdapter


def test_ollama_adapter_reuses_client_inside_context(monkeypatch):
    created = []
    class FakeClient:
        def __init__(self, **kwargs):
            self.calls = 0
            self.closed = False
            created.append(self)
        async def post(self, url, json):
            self.calls += 1
            return httpx.Response(200, json={"message": {"content": '{"ok":true}' }},
                                  request=httpx.Request("POST", url))
        async def aclose(self):
            self.closed = True
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    async def exercise():
        adapter = OllamaMultiLayerAdapter("http://127.0.0.1:11434", "test")
        async with adapter:
            assert (await adapter("first"))["ok"] is True
            assert (await adapter("second"))["ok"] is True
            assert len(created) == 1
            assert created[0].calls == 2
            assert not created[0].closed
        assert created[0].closed
    asyncio.run(exercise())


def test_ollama_adapter_one_shot_closes_client(monkeypatch):
    created = []
    class FakeClient:
        def __init__(self, **kwargs):
            self.closed = False
            created.append(self)
        async def post(self, url, json):
            return httpx.Response(200, json={"message":{"content":'{}'}},
                                  request=httpx.Request("POST", url))
        async def aclose(self):
            self.closed = True
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    adapter = OllamaMultiLayerAdapter("http://127.0.0.1:11434", "test")
    asyncio.run(adapter("one-shot"))
    assert len(created) == 1 and created[0].closed
