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


def test_planning_has_smaller_generation_budget(monkeypatch):
    budgets = []
    class FakeClient:
        def __init__(self, **kwargs):
            pass
        async def post(self, url, json):
            budgets.append(json["options"]["num_predict"])
            return httpx.Response(200, json={"message":{"content":'{}'}},
                                  request=httpx.Request("POST", url))
        async def aclose(self):
            pass
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    async def run():
        adapter = OllamaMultiLayerAdapter("http://127.0.0.1:11434", "test")
        async with adapter:
            await adapter.plan("plan")
            await adapter("answer")
    asyncio.run(run())
    assert budgets == [192, 950]


def test_ollama_metrics_are_converted_from_nanoseconds(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def post(self, url, json):
            return httpx.Response(200, json={
                "message": {"content": "{}"},
                "total_duration": 80000000, "load_duration": 10000000,
                "prompt_eval_duration": 20000000,
                "eval_duration": 40000000, "eval_count": 4
            }, request=httpx.Request("POST", url))
        async def aclose(self): pass
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    adapter = OllamaMultiLayerAdapter("http://127.0.0.1:11434", "test")
    asyncio.run(adapter("metrics"))
    metrics = adapter.last_metrics
    assert metrics["total_ms"] == 80.0
    assert metrics["load_ms"] == 10.0
    assert metrics["prompt_eval_ms"] == 20.0
    assert metrics["generation_ms"] == 40.0
    assert metrics["tokens_per_second"] == 100.0
    assert metrics["generated_tokens"] == 4
    assert metrics["elapsed_ms"] >= 0
    assert metrics["ttft_ms"] is None
