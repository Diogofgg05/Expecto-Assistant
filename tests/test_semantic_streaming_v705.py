"""7.0.5: streaming vectors keep exact semantic + lexical retrieval behavior."""
import asyncio
import json
import math
import random
from datetime import datetime, timezone, timedelta

from aura.config import Settings
from aura.database import Database
from aura.db_shared import now, months_before
from aura.memory import MemoryEngine, cosine, top_semantic


def test_top_k_matches_full_sort_and_handles_invalid_vectors():
    rng = random.Random(705)
    query = [1.0, .2, -.1]
    vectors = [(f"m{i}", json.dumps([rng.uniform(-1, 1) for _ in range(3)]))
               for i in range(500)]
    vectors.extend([("invalid", "{not-json"), ("bad-dims", "[1,2]"),
                    ("NaN", "[NaN,1,1]")])
    full = []
    for i, (key, raw) in enumerate(vectors):
        try:
            similarity = cosine(query, json.loads(raw))
        except ValueError:
            continue
        if similarity >= .39 and math.isfinite(similarity):
            full.append((key, similarity, i))
    full.sort(key=lambda item: item[1], reverse=True)
    found, _ = top_semantic(query, iter(vectors), threshold=.39, limit=17)
    assert [(k, i) for k, _, i in found] == [(k, i) for k, _, i in full[:17]]


def test_ties_follow_original_sql_scan_order():
    vectors = [(f"m{i}", "[1,0]") for i in range(140)]
    best, _ = top_semantic([1, 0], iter(vectors), threshold=.39, limit=9)
    assert [k for k, _, _ in best] == [f"m{i}" for i in range(9)]


def test_streaming_db_batches_keep_bounded_rows_and_date_filter(tmp_path):
    db = Database(tmp_path / "db.sqlite3")
    stamp = now()
    with db.connect() as con:
        con.executemany(
            "INSERT INTO memories(id,content,created_at,updated_at,category,topic,source,status,importance) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            [(f"m{i:04}", f"Nota n{i}", stamp, stamp, 'note', '', 'explicit_user', 'active', 3)
             for i in range(330)])
        con.executemany(
            "INSERT INTO memory_vectors(memory_id,model,vector_json,updated_at) VALUES(?,?,?,?)",
            [(f"m{i:04}", "embed", json.dumps([float(i % 3), 1.0]), stamp)
             for i in range(330)])
        con.executemany(
            "INSERT INTO conversation_episodes(id,session_id,role,content,created_at) "
            "VALUES(?,?,?,?,?)",
            [(f"e{i:04}", "session", "user", f"Conversa {i}", stamp)
             for i in range(330)])
        con.executemany(
            "INSERT INTO episode_vectors(episode_id,model,vector_json,created_at) VALUES(?,?,?,?)",
            [(f"e{i:04}", "embed", json.dumps([1.0, float(i % 3)]), stamp)
             for i in range(330)])
    assert db.has_memory_vectors("embed")
    assert db.has_episode_vectors("embed", 6)
    assert list(db.iter_memory_vectors("embed", batch_size=17)) == [
        (row["id"], row["vector_json"]) for row in db.vectors("embed")]
    assert list(db.iter_episode_vectors("embed", batch_size=21)) == [
        (row["id"], row["vector_json"]) for row in db.episode_vectors_in_window("embed")]
    assert len(db.memory_rows_by_ids(["m0001", "m0001", "m0002"])) == 2
    assert len(db.episode_rows_by_ids(["e0001", "e0002"], 6)) == 2
    assert db.memory_rows_by_ids([]) == []
    assert db.episode_rows_by_ids([], 6) == []

    old = (datetime.fromisoformat(months_before(6)) - timedelta(days=2)).isoformat()
    with db.connect() as con:
        con.execute("UPDATE conversation_episodes SET created_at=? WHERE id=?", (old, "e0001"))
    assert "e0001" not in [ident for ident, _ in db.iter_episode_vectors("embed")]
    assert db.episode_rows_by_ids(["e0001"], 6) == []


def test_real_note_recall_fuses_lexical_and_semantic(tmp_path, monkeypatch):
    db = Database(tmp_path / "notes.sqlite3")
    a = db.add_memory("Trabalho no projeto Python com sensores industriais", importance=5)
    b = db.add_memory("Comi fruta e bolachas", importance=1)
    c = db.add_memory("Dispositivos aeronáuticos autónomos", importance=3)
    db.set_vector(a["id"], "embed", [1.0, .0])
    db.set_vector(b["id"], "embed", [.0, 1.0])
    db.set_vector(c["id"], "embed", [1.0, .0])
    engine = MemoryEngine(Settings(data_dir=tmp_path, embedding_model="embed"), db)
    async def fake_embed(_):
        return [1.0, 0.0]
    monkeypatch.setattr(engine, "_embed", fake_embed)
    results = asyncio.run(engine.recall("Python", limit=3))
    assert results[0]["id"] == a["id"]
    assert c["id"] in [n["id"] for n in results]
    assert b["id"] not in [n["id"] for n in results]
    assert all("vector_json" not in r for r in results)


def test_no_index_skips_outbound_embeddings(tmp_path, monkeypatch):
    db = Database(tmp_path / "empty.sqlite3")
    engine = MemoryEngine(Settings(data_dir=tmp_path, embedding_model="embed"), db)
    async def must_not_embed(_):
        raise AssertionError("Do not call Ollama without indexed vectors")
    monkeypatch.setattr(engine, "_embed", must_not_embed)
    assert asyncio.run(engine.recall("algo")) == []
    assert asyncio.run(engine.recall_episodes("algo")) == []


def test_episodic_semantic_recall_no_lexical_overlap(tmp_path, monkeypatch):
    db = Database(tmp_path / "episodes.sqlite3")
    old = db.record_exchange("s1", "Projeto com drones", "Resposta sobre drones")
    db.record_exchange("s2", "Uma receita de sopa", "Receita de legumes")
    db.save_episode_vector(old[0]["id"], "embed", [1.0, 0.0])
    db.save_episode_vector(old[1]["id"], "embed", [0.9, 0.1])
    engine = MemoryEngine(Settings(data_dir=tmp_path, embedding_model="embed"), db)
    async def fake_embed(_):
        return [1.0, 0.0]
    monkeypatch.setattr(engine, "_embed", fake_embed)
    results = asyncio.run(engine.recall_episodes("Aeronaves autónomas", 6))
    assert results[0]["id"] == old[0]["id"]
    assert results[0]["semantic_score"] == 1.0
    assert all("vector_json" not in r for r in results)
