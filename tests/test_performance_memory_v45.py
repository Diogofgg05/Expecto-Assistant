"""Performance Engine 4.5: concurrent per-request semantic snapshot regression.

No personal text leaves the process and no vector is cached between requests.
"""
from __future__ import annotations

import asyncio
import json
import threading

from aura.config import Settings
from aura.memory import MemoryEngine


class FakeDatabase:
    def __init__(self):
        self.calls = {"notes": 0, "episodes": 0, "vectors": 0, "episode_vectors": 0}
        self.semantic_notes = [
            {"id": "n-semantic", "content": "Holograma azul", "importance": 5,
             "category": "note", "created_at": "2026-01-01", "vector_json": json.dumps([1., 0.])},
        ]
        self.semantic_episodes = [
            {"id": "e-semantic", "content": "Explicação do holograma", "role": "user",
             "created_at": "2026-03-01T00:00:00Z", "vector_json": json.dumps([1., 0.])},
        ]

    def search_memories(self, question, limit):
        self.calls["notes"] += 1
        return []

    def search_episodes(self, question, months, limit):
        self.calls["episodes"] += 1
        return []

    def vectors(self, model, limit):
        self.calls["vectors"] += 1
        return [dict(item) for item in self.semantic_notes]

    def episode_vectors_in_window(self, model, months):
        self.calls["episode_vectors"] += 1
        return [dict(item) for item in self.semantic_episodes]


def test_recalls_both_semantic_categories_from_one_snapshot(tmp_path):
    db = FakeDatabase()
    memory = MemoryEngine(Settings(data_dir=tmp_path, embedding_model="test"), db)
    embeddings = []
    async def embed(text):
        embeddings.append(text)
        return [1., 0.]
    memory._embed = embed

    notes, episodes = asyncio.run(memory.recall_pair("holograma", months=6))
    assert [item["id"] for item in notes] == ["n-semantic"]
    assert [item["id"] for item in episodes] == ["e-semantic"]
    assert db.calls == {"notes": 1, "episodes": 1, "vectors": 1, "episode_vectors": 1}
    assert embeddings == ["holograma"]

    # A subsequent request re-reads DB, never returns a stale semantic cache.
    db.semantic_notes[0]["vector_json"] = json.dumps([0., 1.])
    later_notes, later_episodes = asyncio.run(memory.recall_pair("holograma"))
    assert later_notes == []
    assert [item["id"] for item in later_episodes] == ["e-semantic"]
    assert db.calls["vectors"] == 2 and len(embeddings) == 2


def test_vector_prefetch_starts_before_embedding_finishes(tmp_path):
    marker = threading.Event()
    db = FakeDatabase()
    original = db.vectors
    def delayed_vector_fetch(model, limit):
        marker.set()
        return original(model, limit)
    db.vectors = delayed_vector_fetch
    memory = MemoryEngine(Settings(data_dir=tmp_path, embedding_model="test"), db)

    async def embed(text):
        # This assertion would fail in 4.4 (vectors were fetched after embed).
        ready = await asyncio.to_thread(marker.wait, 2.)
        assert ready, "Vector lookup did not start concurrently with embedding"
        return [1., 0.]
    memory._embed = embed
    notes, episodes = asyncio.run(asyncio.wait_for(
        memory.recall_pair("holograma"), timeout=3.))
    assert [x["id"] for x in notes] == ["n-semantic"]
    assert [x["id"] for x in episodes] == ["e-semantic"]


def test_failed_embedding_falls_back_to_lexical_and_does_not_retry(tmp_path):
    db = FakeDatabase()
    db.search_memories = lambda question, limit: [{
        "id": "lexical", "content": "CPU", "importance": 4,
        "category": "note", "created_at": "2026-01-01"}]
    memory = MemoryEngine(Settings(data_dir=tmp_path, embedding_model="test"), db)
    calls = [0]
    async def embed(text):
        calls[0] += 1
        return None
    memory._embed = embed
    notes, episodes = asyncio.run(memory.recall_pair("CPU"))
    assert [x["id"] for x in notes] == ["lexical"]
    assert episodes == []
    assert calls == [1]


def test_direct_recall_methods_remain_compatible(tmp_path):
    db = FakeDatabase()
    memory = MemoryEngine(Settings(data_dir=tmp_path, embedding_model="test"), db)
    async def embed(text):
        return [1., 0.]
    memory._embed = embed
    async def run():
        notes = await memory.recall("holograma")
        episodes = await memory.recall_episodes("holograma")
        assert [x["id"] for x in notes] == ["n-semantic"]
        assert [x["id"] for x in episodes] == ["e-semantic"]
    asyncio.run(run())
