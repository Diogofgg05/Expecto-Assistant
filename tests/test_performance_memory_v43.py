"""Performance 4.3 memory hot path: top-k and overlapping lexical I/O.

All tests are offline. The ordering and semantic threshold must match 4.1.
"""
from __future__ import annotations

import asyncio
import math
import threading

from aura.config import Settings
from aura.memory import MemoryEngine, cosine


def test_query_cosine_norm_reuse_identical_result():
    query = [0.1, -0.2, 0.3, 0.0]
    query_norm = math.sqrt(sum(x * x for x in query))
    for candidate in ([0.1,-0.2,0.3,0.0], [0,1,0,0], [0,0,0,0],
                      [1,0,-1,0], [1,0,0]):
        expected = cosine(query, candidate)
        result = cosine(query, candidate, left_norm=query_norm)
        assert math.isclose(result, expected, rel_tol=1e-12, abs_tol=1e-12)


def test_semantic_top50_preserves_stable_tie_order(tmp_path):
    class FakeDB:
        def search_episodes(self, question, months, limit):
            return []
        def episode_vectors_in_window(self, model, months):
            return [
                dict(id=str(i), vector_json="[1.0,0.0]", content="texto")
                for i in range(100)
            ]
    settings = Settings(data_dir=tmp_path, embedding_model="test")
    mem = MemoryEngine(settings, FakeDB())
    async def no_embed(*args):
        raise AssertionError("An explicit vector should be used")
    mem._embed = no_embed
    results = asyncio.run(mem.recall_episodes(
        "teste", query_vector=[1.0,0.0], limit=30))
    assert [x["id"] for x in results] == [str(i) for i in range(30)]


def test_lexical_lookup_overlaps_network_embedding(tmp_path):
    marker = threading.Event()
    class FakeDB:
        def search_memories(self, question, limit):
            marker.set()
            return []
        def search_episodes(self, question, months, limit):
            return []
        def vectors(self, model, limit):
            return []
        def episode_vectors_in_window(self, model, months):
            return []
    mem = MemoryEngine(Settings(data_dir=tmp_path,embedding_model="test"),FakeDB())
    calls = [0]
    async def slow_embed(question):
        calls[0] += 1
        # Requires lexical DB search to start before the embedding returns.
        assert await asyncio.to_thread(marker.wait, 2.0)
        return [1.0,0.0]
    mem._embed=slow_embed
    notes, episodes = asyncio.run(asyncio.wait_for(
        mem.recall_pair("Pergunta de teste"), timeout=3.0))
    assert notes == [] and episodes == []
    assert calls[0] == 1


def test_without_embedding_model_never_calls_ollama(tmp_path):
    class FakeDB:
        def search_memories(self, question, limit):
            return []
        def search_episodes(self, question, months, limit):
            return []
    mem = MemoryEngine(Settings(data_dir=tmp_path,embedding_model=""),FakeDB())
    async def fail(*args):
        raise AssertionError("Must not request an embedding")
    mem._embed=fail
    assert asyncio.run(mem.recall_pair("Sem embeddings")) == [[], []]
