"""Benchmark identity contract tests; no live Ollama needed."""
import asyncio
import json
import httpx
import pytest

from aura import benchmark_identity as identity


def test_model_digest_from_ollama_tags(monkeypatch):
    actual = httpx.AsyncClient
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [
            {"name": "qwen3:latest", "digest": "a" * 64}]})
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: actual(transport=httpx.MockTransport(handler), **kw))
    result = asyncio.run(identity.fetch_model_digest("http://127.0.0.1:11434", "qwen3"))
    assert result == "a" * 64


def test_unknown_model_is_rejected(monkeypatch):
    actual = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: actual(transport=httpx.MockTransport(
                            lambda req: httpx.Response(200, json={"models": []})), **kw))
    with pytest.raises(ValueError, match="not found"):
        asyncio.run(identity.fetch_model_digest("http://127.0.0.1:11434", "unknown"))


def test_invalid_digest_rejected(monkeypatch):
    actual = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: actual(transport=httpx.MockTransport(
                            lambda req: httpx.Response(200, json={"models": [
                                {"name":"qwen3:latest","digest":"untrusted"}]})), **kw))
    with pytest.raises(ValueError, match="digest"):
        asyncio.run(identity.fetch_model_digest("http://127.0.0.1:11434", "qwen3"))


def test_collect_identity_contains_workload_hash(monkeypatch):
    async def digest(url, model):
        return "a" * 64
    monkeypatch.setattr(identity, "fetch_model_digest", digest)
    monkeypatch.setattr(identity, "hardware_profile",
        lambda: {"system": "Linux", "architecture": "x86_64",
                 "cpu_model": "test", "logical_cpus": 4,
                 "physical_ram_bytes": 8192})
    result = asyncio.run(identity.collect_identity("http://localhost:11434", "qwen3"))
    assert result["schema_version"] == 2
    assert len(result["workload_sha256"]) == 64
    assert result["hardware"]["cpu_model"] == "test"


def test_missing_hardware_prevents_comparison(monkeypatch):
    monkeypatch.setattr(identity, "hardware_profile",
        lambda: {"cpu_model": None, "logical_cpus": 4,
                 "physical_ram_bytes": 8192})
    with pytest.raises(RuntimeError, match="CPU/RAM"):
        asyncio.run(identity.collect_identity("http://localhost:11434", "qwen3"))
