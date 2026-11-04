"""Component boundaries and public API compatibility for EXPECTO 7.4."""
import ast
import asyncio
from pathlib import Path

from aura.book_reasoning import (
    BookReasoningEngine, OllamaBookModel, BookModelPort,
    _normal, _tokens, _quote_valid, _plausible,
)
from aura.database import Database


class StubModel:
    model = "stub-model"

    async def generate(self, task, payload):
        assert task == "answer"
        passage = payload["passages"][0]
        quote = "Os vetores têm magnitude e direção no espaço geométrico."
        return {"answer": quote, "abstain": False,
                "citations": [{"passage_id": passage["passage_id"], "quote": quote}]}


class StubIndex:
    calls = 0

    def __init__(self, db):
        self.db = db

    async def search(self, question, **kwargs):
        type(self).calls += 1
        return [{"id": "p1", "passage_id": "p1", "book_id": "b1",
                 "title": "Livro de teste", "page": 4,
                 "text": "Os vetores têm magnitude e direção no espaço geométrico."}]


def test_public_api_unchanged_and_model_protocol():
    assert isinstance(StubModel(), BookModelPort)
    assert hasattr(OllamaBookModel, "generate")
    for name in ("migrate", "_chapter", "_batched", "_validate_items",
                 "_save_item", "study_chapter", "report", "build_learning_map",
                 "answer", "compare_books"):
        assert callable(getattr(BookReasoningEngine, name))
    assert _normal(" OLÁ  LIVROS ") == "olá livros"
    assert _tokens("Os vetores estão presentes")
    assert _quote_valid({"text":"Os vetores têm magnitude e direção no espaço geométrico."},
                        "Os vetores têm magnitude e direção no espaço geométrico.")
    assert _plausible("Vetores e direção geométrica",
                      "Os vetores têm magnitude e direção no espaço geométrico.")


def test_index_is_injectable_without_optional_ollama_or_pdf(tmp_path):
    StubIndex.calls = 0
    db = Database(tmp_path / "architecture_v74.sqlite3", require_encryption=False)
    engine = BookReasoningEngine(db, semantic_index_factory=StubIndex)
    assert engine._semantic_index_factory is StubIndex
    result = asyncio.run(engine.answer("Como se definem os vetores?", StubModel()))
    assert result["abstained"] is False
    assert result["citations"][0]["page"] == 4
    assert result["status"] == "source_anchored_unverified"
    assert StubIndex.calls == 1


def test_components_do_not_import_public_facade_or_each_other_backwards():
    root = Path(__file__).resolve().parents[1] / "aura" / "book_reasoning_components"
    expected = {"__init__.py", "evidence.py", "model.py",
                "storage.py", "study.py", "questions.py"}
    assert {p.name for p in root.glob("*.py")} == expected
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "book_reasoning"
                assert not (node.module or "").endswith(".book_reasoning")
    for name in ("evidence", "model"):
        source = (root / f"{name}.py").read_text(encoding="utf-8")
        assert "import httpx" not in source.split("class OllamaBookModel:")[0]
        assert "from ..database" not in source
