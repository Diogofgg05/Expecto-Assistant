"""EXPECTO 7.8: memory, book QA and service architecture in one process.

No live model, external network, PDF download or destructive data migration.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from aura.book_reasoning import BookReasoningEngine, BookModelPort
from aura.command_memory import handle_memory_command
from aura.memory_commands import handle_memory_command as domain_handler
from aura.config import Settings
from aura.core.architecture import inspect_architecture
from aura.core.services import CoreServices
from aura.database import Database
from aura.engine import AuraEngine


QUOTE = "Os vetores têm magnitude e direção no espaço geométrico."


class SourceIndex:
    calls = 0

    def __init__(self, db):
        self.db = db

    async def search(self, question, **kwargs):
        self.calls += 1
        return [{"id": "sample", "passage_id": "sample", "book_id": "book",
                 "title": "Manual de vetores", "page": 7, "text": QUOTE}]


class SourceModel:
    model = "deterministic-integration"

    async def generate(self, task, payload):
        assert task == "answer"
        return {"answer": QUOTE, "abstain": False, "citations": [
            {"passage_id": payload["passages"][0]["passage_id"], "quote": QUOTE},
        ]}


def test_memory_privacy_and_book_pipeline_share_same_local_database(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    db = Database(tmp_path / "integrated.sqlite3", require_encryption=False)
    services = CoreServices(settings, db)
    engine = AuraEngine(settings, db, services=services)
    assert handle_memory_command is domain_handler

    async def exercise():
        created = await engine.command("Lembra-te de estudar vetores e matrizes")
        assert created["action"]["panel"] == "memory"
        assert len(db.memories()) == 1

        private = await engine.command("Ativa modo privado")
        assert "Modo privado" in private["text"]
        assert db.get_option("private_mode", "false") == "true"

        no_books = await engine.command("Segundo os livros, explica os vetores")
        assert "não tenho livros pdf" in no_books["text"].lower()
        assert "research" not in services.initialized
        assert db.get_option("private_mode", "false") == "true"

        book = BookReasoningEngine(db, semantic_index_factory=SourceIndex)
        answer = await book.answer("Que características têm os vetores?", SourceModel())
        assert not answer["abstained"]
        assert answer["citations"][0]["page"] == 7
        assert answer["status"] == "source_anchored_unverified"
        assert db.memories()[0]["content"] == "estudar vetores e matrizes"
        return answer

    assert asyncio.run(exercise())["answer"] == QUOTE


def test_integration_guard_covers_all_four_new_domains():
    root = Path(__file__).resolve().parents[1]
    report = inspect_architecture(root)
    names = {module.name for module in report.modules}
    assert {"aura.core.services", "aura.llm_pipeline.inference",
            "aura.memory_commands.policy",
            "aura.book_reasoning_components.study"} <= names
    assert report.ok, "\n".join(report.violations)
    assert report.governed_cycles == ()
    assert isinstance(SourceModel(), BookModelPort)
