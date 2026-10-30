"""RAG should not give a top-k slot to a passage with an invalid hash."""
import asyncio
import hashlib
import sqlite3
from aura.book_semantics import BookSemanticIndex


def test_tampered_lexical_result_cannot_occupy_top_k():
    bad = "python generators and iterator details"
    good = "python generators provide lazy values"
    def sha(s):
        return hashlib.sha256(s.encode()).hexdigest()

    class DB:
        def connect(self):
            return sqlite3.connect(":memory:")
    # Exercise the selection path with rows returned by SQLite, no model or PDF.
    # Both rows are lexically relevant, but the first has a false digest.
    class FakeConnection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, query, params=()):
            rows = [
                {"id": "bad", "book_id": "b", "page": 1, "ordinal": 0,
                 "text": bad, "text_hash": sha("different"), "title": "Book"},
                {"id": "good", "book_id": "b", "page": 2, "ordinal": 0,
                 "text": good, "text_hash": sha(good), "title": "Book"},
            ]
            class Cursor:
                def fetchall(self): return rows
            return Cursor()
    class FakeDb:
        def connect(self): return FakeConnection()
    index = BookSemanticIndex.__new__(BookSemanticIndex)
    index.db = FakeDb()
    matches = asyncio.run(index.search("python generators", limit=1))
    assert len(matches) == 1 and matches[0]["passage_id"] == "good"
