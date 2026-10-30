"""Deterministic percentile and benchmark orchestration tests."""
import asyncio
from aura.ollama_benchmark import percentile, summarize, benchmark


def test_percentile_interpolation():
    assert percentile([], 95) is None
    assert percentile([10, 20, 30, 40, 50], 50) == 30
    assert percentile([10, 20, 30, 40, 50], 95) == 48
    assert percentile([10, 20, 30, 40, 50], 99) == 49.6


def test_summary_preserves_missing_ttft():
    result = summarize([{"elapsed_ms": 10, "ttft_ms": None},
                        {"elapsed_ms": 30, "ttft_ms": None}])
    assert result["elapsed_ms"]["p50"] == 20
    assert result["ttft_ms"]["samples"] == 0
    assert result["ttft_ms"]["p95"] is None


def test_benchmark_excludes_warmups(monkeypatch):
    calls = []
    class Adapter:
        def __init__(self, *args):
            self.last_metrics = None
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def __call__(self, prompt):
            calls.append(prompt)
            self.last_metrics = {"elapsed_ms": len(calls), "ttft_ms": None}
    monkeypatch.setattr("aura.ollama_benchmark.OllamaMultiLayerAdapter", Adapter)
    async def identity(url, model):
        return {"schema_version": 2, "model_digest": "a" * 64,
                "workload_sha256": "b" * 64, "hardware": {"cpu_model": "test"}}
    monkeypatch.setattr("aura.ollama_benchmark.collect_identity", identity)
    result = asyncio.run(benchmark("test","http://localhost:11434",3,2,False))
    assert len(calls) == 5
    assert [item["elapsed_ms"] for item in result["samples"]] == [3,4,5]
    assert result["summary"]["elapsed_ms"]["p50"] == 4

    assert result["model_digest"] == "a" * 64
    assert result["schema_version"] == 2
