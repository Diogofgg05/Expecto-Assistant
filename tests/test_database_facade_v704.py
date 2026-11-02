"""EXPECTO 7.0.4: preserve the old Database API and SQLite schema contract.

The public class remains importable from aura.database. Regression tests
exercise a legacy file, idempotent migrations, backups and cross-domain calls.
"""
from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

from aura.database import Database, now, months_before
from aura.db_notes import NotesMixin
from aura.db_episodes import EpisodesMixin
from aura.db_temporal import TemporalMixin
from aura.db_extractions import ExtractionsMixin
from aura.db_schema import SchemaMixin
from aura.db_settings import SettingsMixin
from aura.db_research import ResearchMixin


METHODS = {
    "add_memory", "memory_count", "memories", "get_memory", "update_memory",
    "delete_memory", "_terms", "search_memories", "set_vector", "vectors",
    "pending_embeddings", "export_memories", "backup",
    "pending_episode_embeddings", "save_episode_vector",
    "episode_vectors_in_window", "episode_vector_count",
    "record_exchange", "recent_episodes", "episodes_months_ago",
    "search_episodes", "delete_episode", "erase_episodes", "episode_count",
    "set_temporal_fact", "observe_temporal_episode", "temporal_current",
    "temporal_history", "temporal_as_of", "erase_temporal_subject",
    "temporal_count", "export_temporal_history",
    "unprocessed_user_episodes", "extracted_count", "save_extractions",
    "_remove_orphan_auto_memories", "get_option", "set_option",
    "capture_enabled", "export_full_memory", "backup_if_due",
    "combined_memory_panel", "remember_document", "documents",
    "create_job", "jobs", "disable_job", "job_result", "due_jobs",
    "_migrate_memories", "_migrate_episodes", "_migrate_cognitive_memory",
    "_migrate_temporal_memory",
}


def test_facade_preserves_all_original_methods_and_signatures():
    assert METHODS <= set(dir(Database))
    assert Database.add_memory is NotesMixin.add_memory
    assert Database.record_exchange is EpisodesMixin.record_exchange
    assert Database.temporal_current is TemporalMixin.temporal_current
    assert Database.save_extractions is ExtractionsMixin.save_extractions
    assert Database._migrate_episodes is SchemaMixin._migrate_episodes
    assert Database.get_option is SettingsMixin.get_option
    assert Database.remember_document is ResearchMixin.remember_document
    assert tuple(inspect.signature(Database.__init__).parameters) == (
        "self", "path", "passphrase", "require_encryption")
    assert tuple(inspect.signature(Database.add_memory).parameters) == (
        "self", "content", "category", "topic", "importance")
    assert callable(now) and callable(months_before)


def test_legacy_plaintext_schema_migrates_without_losing_notes(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, content TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO memories VALUES (?, ?, ?)",
                     ("old001", "Memória antiga sobre Python", "2025-01-01T00:00:00+00:00"))
    db = Database(path)
    old = db.get_memory("old001")
    assert old is not None and old["content"] == "Memória antiga sobre Python"
    assert len(db.search_memories("Python")) == 1
    assert db.memory_count() == 1

    # Running the entire idempotent migration a second time does not
    # rewrite, remove or rename the existing SQLite schema.
    def snapshot():
        with db.connect() as conn:
            return conn.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
                "ORDER BY type, name").fetchall()

    baseline = [tuple(row) for row in snapshot()]
    reopened = Database(path)
    assert [tuple(row) for row in snapshot()] == baseline
    assert reopened.get_memory("old001")["content"] == old["content"]


def test_same_facade_cross_domain_calls_and_backup(tmp_path):
    db = Database(tmp_path / "aura.sqlite3")
    note = db.add_memory("Memória de teste Python")
    assert db.get_memory(note["id"])["content"] == "Memória de teste Python"
    db.set_option("test_facade_704", "enabled")
    assert db.get_option("test_facade_704") == "enabled"
    assert db.due_jobs() == []
    created = db.create_job("Tópico de pesquisa", 24)
    assert created["topic"] == "Tópico de pesquisa"
    assert len(db.due_jobs()) == 1

    db.remember_document("Python", "Manual de Python", "Introdução à linguagem",
                         "https://example.org/manual", "documentation", "single_source")
    assert db.documents("Python")[0]["title"] == "Manual de Python"

    backup = db.backup(tmp_path / "backup")
    with sqlite3.connect(backup) as conn:
        rows = conn.execute("SELECT content FROM memories WHERE id=?", (note["id"],)).fetchall()
    assert rows == [("Memória de teste Python",)]
    assert db.memory_count() == 1
