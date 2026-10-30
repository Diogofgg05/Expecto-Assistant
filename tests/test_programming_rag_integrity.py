"""Regression tests for static code review and source-integrity-aware retrieval."""
import asyncio
import hashlib
from aura.code_inspection import inspect_python
from aura.book_research import BookResearchEngine


def test_inspection_safe_and_suspicious():
    safe = inspect_python("def add(a,b):\n    return a+b\n")
    assert safe["valid_syntax"] and safe["findings"] == []
    risky = inspect_python("import subprocess\neval('2+2')\nsubprocess.run('ls',shell=True)\n")
    assert {f["rule"] for f in risky["findings"]} == {"dynamic-execution", "shell-subprocess"}


def test_inspection_does_not_run_source(tmp_path):
    path = tmp_path / "danger.txt"
    result = inspect_python(f"open({str(path)!r},'w').write('x')\n")
    assert result["valid_syntax"]
    assert not path.exists()


def test_invalid_syntax_and_bounds():
    assert not inspect_python("def f(:")["valid_syntax"]
    try:
        inspect_python("x" * 150001)
        assert False
    except ValueError:
        pass


def test_rag_invalid_top_hit_cannot_block_valid_hit():
    def digest(text):
        return hashlib.sha256(text.encode()).hexdigest()
    stale = {"passage_id":"bad","book_id":"book","title":"Book","page":1,
             "text":"Stale fabricated information","text_hash":digest("different")}
    valid = {"passage_id":"good","book_id":"book","title":"Book","page":2,
             "text":"Reliable unique explanation of a vector","text_hash":digest("Reliable unique explanation of a vector")}
    class Conn:
        def execute(self, sql, args):
            passage = {"bad":stale,"good":valid}[args[0]]
            class Cursor:
                def fetchone(self):
                    return passage
            return Cursor()
    class CM:
        def __enter__(self): return Conn()
        def __exit__(self,*args): return False
    class DB:
        def connect(self): return CM()
    engine = BookResearchEngine.__new__(BookResearchEngine)
    engine.db = DB()
    class Index:
        async def search(self, *args, **kwargs): return [stale, valid]
    engine.index = Index()
    answer = asyncio.run(engine.investigate(["Explain vectors"], limit=1))
    assert [p["passage_id"] for p in answer["evidence"]] == ["good"]
    assert answer["evidence"][0]["verified_against_index"]
