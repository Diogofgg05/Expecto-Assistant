"""Expecto 6.6: adversarial checks for reasoning and local document retrieval."""
import asyncio
import hashlib
import json
import pytest

from aura.reasoning_runtime import ReasoningRuntime, arithmetic_audit
from aura.database import Database
from aura.book_semantics import BookSemanticIndex


def test_short_answer_arithmetic_is_checked_even_when_review_is_balanced():
    async def run():
        engine=ReasoningRuntime()
        calls=[]
        async def model(prompt):
            calls.append(json.loads(prompt))
            if len(calls)==1:
                return json.dumps({"needs_revision":False,"issues":[]})
            return "2 + 2 = 4"
        result=await engine.refine("Quanto é?", "2 + 2 = 5", model)
        assert result.status=="revised_model_only"
        assert result.answer=="2 + 2 = 4"
        assert len(calls)==2
    asyncio.run(run())


def test_revision_cannot_hide_wrong_equation():
    async def run():
        engine=ReasoningRuntime()
        calls=[]
        async def model(prompt):
            calls.append(prompt)
            if len(calls)==1:
                return json.dumps({"needs_revision":True,"issues":["corrigir conta"]})
            return "A soma está correta."  # model evades the arithmetic
        result=await engine.refine("Calcula a soma", "125 + 75 = 201", model)
        assert result.status=="abstained_wrong_arithmetic"
        assert "201" not in result.answer
    asyncio.run(run())


def test_unverifiable_expression_is_not_accepted_as_checked():
    report=arithmetic_audit("5 / 0 = 1")
    assert report["status"]=="unverifiable_arithmetic"
    assert report["unverifiable_count"]==1


def test_too_many_arithmetic_checks_fail_closed():
    async def run():
        engine=ReasoningRuntime()
        async def unexpected(prompt):
            raise AssertionError("model should not be called")
        draft="; ".join(f"{i} + 1 = {i+1}" for i in range(12))
        result=await engine.refine("Quanto é?",draft,unexpected)
        assert result.status=="abstained_unchecked_arithmetic"
    asyncio.run(run())


def _seed_passage(db, text):
    ident="passage-a"
    digest=hashlib.sha256(text.encode()).hexdigest()
    with db.connect() as conn:
        conn.execute("INSERT INTO book_documents(id,title,filename,sha256,pages,imported_at,rights_note) VALUES(?,?,?,?,?,?,?)",
                     ("book-a","Livro teste","local.pdf","filehash",1,"2026-10-28","Teste sintético"))
        conn.execute("INSERT INTO book_passages(id,book_id,page,ordinal,text,text_hash) VALUES(?,?,?,?,?,?)",
                     (ident,"book-a",1,1,text,digest))
    return ident


def test_changed_document_during_embedding_is_not_indexed(tmp_path):
    db=Database(tmp_path/"index.sqlite3",require_encryption=False)
    original="O algoritmo de Dijkstra encontra caminhos mínimos."
    _seed_passage(db,original)
    index=BookSemanticIndex(db)
    class MutatingEncoder:
        model="test-encoder"
        async def embed(self,texts):
            replacement="Texto completamente diferente."
            with db.connect() as conn:
                conn.execute("UPDATE book_passages SET text=?, text_hash=? WHERE id=?",
                             (replacement,hashlib.sha256(replacement.encode()).hexdigest(),"passage-a"))
            return [[1.0,0.0] for _ in texts]
    result=asyncio.run(index.index_book("book-a",MutatingEncoder()))
    assert result["indexed"]==0
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM book_embeddings").fetchone()[0]==0


def test_corrupt_stored_vector_is_skipped(tmp_path):
    db=Database(tmp_path/"index.sqlite3",require_encryption=False)
    text="A fotossíntese depende da luz e da clorofila."
    pid=_seed_passage(db,text)
    index=BookSemanticIndex(db)
    class Encoder:
        model="test-encoder"
        async def embed(self,texts):
            return [[0.0,1.0] for _ in texts]
    asyncio.run(index.index_book("book-a",Encoder()))
    with db.connect() as conn:
        conn.execute("UPDATE book_embeddings SET vector_json=? WHERE passage_id=?",
                     (json.dumps([float("nan"),1.0]),pid))
    hits=asyncio.run(index.search("fotossíntese luz",encoder=Encoder()))
    # Lexical FTS may still find it; the corrupt vector must not crash retrieval.
    assert isinstance(hits,list)
    assert all(item["passage_id"]==pid for item in hits)


def test_embedding_request_does_not_hold_db_connection(tmp_path):
    db=Database(tmp_path/"index.sqlite3",require_encryption=False)
    _seed_passage(db,"Estudo de geometria algébrica de vetores.")
    index=BookSemanticIndex(db)
    original_connect=db.connect
    import contextlib
    opened=[0]
    @contextlib.contextmanager
    def tracked():
        with original_connect() as conn:
            opened[0]+=1
            try:
                yield conn
            finally:
                opened[0]-=1
    db.connect=tracked
    class Encoder:
        model="test-encoder"
        async def embed(self,texts):
            assert opened[0]==0
            return [[1.0,0.0] for _ in texts]
    asyncio.run(index.index_book("book-a",Encoder()))
    hits=asyncio.run(index.search("geometria algébrica",encoder=Encoder()))
    assert len(hits)==1
