"""Public compatibility facade for evidence-grounded book reasoning.

Interfaces and storage schema remain unchanged. Internal responsibilities are
split into evidence, model, study, question and persistence components.
"""
from __future__ import annotations

from .book_semantics import BookSemanticIndex
from .book_reasoning_components.evidence import _normal, _tokens, _quote_valid, _plausible
from .book_reasoning_components.model import OllamaBookModel, BookModelPort
from .book_reasoning_components.storage import BookReasoningStorageMixin
from .book_reasoning_components.study import BookReasoningStudyMixin
from .book_reasoning_components.questions import BookReasoningQuestionMixin


class BookReasoningEngine(
    BookReasoningStudyMixin, BookReasoningQuestionMixin, BookReasoningStorageMixin
):
    """Incremental persisted study pipeline; no automatic knowledge promotion.

    `semantic_index_factory` is optional and only replaces the retrieval
    dependency for testing or controlled alternative backends. By default,
    it instantiates the same BookSemanticIndex as before this refactor.
    """
    def __init__(self, db, *, semantic_index_factory=None):
        self.db = db
        self._semantic_index_factory = semantic_index_factory or BookSemanticIndex
        with db.connect() as conn:
            self.migrate(conn)
