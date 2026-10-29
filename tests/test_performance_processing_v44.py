"""Expecto 4.4 deterministic processing regressions -- no live Ollama.

Always verify functional equivalence before claiming performance.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

import pytest

from aura.config import Settings
from aura.llm import Ollama
from aura.memory import cosine
from aura.ollama_resilience import OllamaCircuitBreaker


def test_native_cosine_matches_python_reference_over_varied_dimensions():
    def reference(left, right):
        if not left or len(left) != len(right):
            return 0.
        dot = sum(a * b for a, b in zip(left, right))
        denom = (math.sqrt(sum(x*x for x in left))
                 * math.sqrt(sum(y*y for y in right)))
        return dot / denom if denom else 0.
    for size in [0, 1, 2, 32, 384, 768]:
        left = [(i % 11 - 5) / 6 for i in range(size)]
        right = [(i % 17 - 9) / 7 for i in range(size)]
        want = reference(left, right)
        got = cosine(left, right)
        assert math.isclose(got, want, rel_tol=1e-12, abs_tol=1e-12)
        precomputed = math.sqrt(math.sumprod(left, left))
        assert math.isclose(cosine(left, right, left_norm=precomputed),
                            want, rel_tol=1e-12, abs_tol=1e-12)


def test_open_circuit_skips_all_expensive_context_work(tmp_path):
    llm = Ollama(Settings(data_dir=tmp_path,
                          database_encryption_required=False), object(), object())
    llm._circuit = OllamaCircuitBreaker(threshold=1, cooldown_s=300)
    llm._circuit.failure()
    attempted = [0]

    async def forbidden(question):
        attempted[0] += 1
        raise AssertionError("No DB or embedding retrieval while breaker is open")

    llm._personal_context = forbidden
    async def check():
        result = await llm.reply("O que é o meu projeto?")
        assert "O Ollama está temporariamente indisponível" in result
        assert attempted[0] == 0
        assert llm._circuit.status().rejected >= 1
        assert llm.performance.status()["requests"] == 1
    asyncio.run(check())


def test_context_exception_releases_half_open_probe(tmp_path):
    llm = Ollama(Settings(data_dir=tmp_path,
                          database_encryption_required=False), object(), object())
    now = [0.]
    llm._circuit = OllamaCircuitBreaker(
        threshold=1, cooldown_s=0.1, clock=lambda: now[0])
    llm._circuit.failure()
    now[0] += 0.2

    async def fail(question):
        raise RuntimeError("Malformed local DB")

    llm._personal_context = fail
    async def check():
        with pytest.raises(RuntimeError, match="Malformed"):
            await llm.reply("Qual era o meu projeto?")
        # Probe must be released, otherwise every subsequent request is rejected.
        assert llm._circuit.allow()
        llm._circuit.release_probe()
    asyncio.run(check())


def test_lexical_context_skips_thread_dispatch_when_no_embedding(tmp_path, monkeypatch):
    class StubMemory:
        model = ""
        async def recall(self, question, limit):
            return []
        async def recall_episodes(self, question, months, limit):
            return []

    llm = Ollama(Settings(data_dir=tmp_path,
                          database_encryption_required=False),
                 object(), StubMemory())

    async def forbidden_thread(*args, **kwargs):
        raise AssertionError("No asyncio.to_thread for lexical-only path")
    monkeypatch.setattr("aura.llm.asyncio.to_thread", forbidden_thread)
    fetched = []
    def local(question):
        fetched.append(question)
        return [], [], [], [], [], "", ""
    llm._local_context_parts = local
    async def check():
        context, continuity, reflection = await llm._personal_context(
            "Recordas a minha memória?")
        assert "Memórias do utilizador" in context
        assert continuity == reflection == ""
        assert fetched == ["Recordas a minha memória?"]
    asyncio.run(check())


def test_semantic_context_still_overlaps_local_lookup(tmp_path):
    import threading
    marker = threading.Event()
    class StubMemory:
        model = "local-embeddings"
        async def recall_pair(self, question, **kwargs):
            assert await asyncio.to_thread(marker.wait, 2)
            return [], []

    llm = Ollama(Settings(data_dir=tmp_path,
                          database_encryption_required=False),
                 object(), StubMemory())

    def local(question):
        marker.set()
        return [], [], [], [], [], "", ""
    llm._local_context_parts = local
    async def check():
        result = await llm._personal_context("Qual era o meu projeto?")
        assert "Memórias do utilizador" in result[0]
    asyncio.run(asyncio.wait_for(check(), timeout=3))
