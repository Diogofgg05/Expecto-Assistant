"""Cross-book research is a retrieval aid, never autonomous truth verification."""
import asyncio
from pathlib import Path
import pytest
from aura.database import Database
from aura.book_research import BookResearchEngine


def test_validate_inputs(tmp_path):
    db=Database(tmp_path/'test.sqlite3',require_encryption=False)
    engine=BookResearchEngine(db)
    for questions in [[], ['ab'], ['query']*7]:
        with pytest.raises(ValueError):
            asyncio.run(engine.investigate(questions))


def test_cross_book_coverage_and_missing_queries(tmp_path):
    db=Database(tmp_path/'test.sqlite3',require_encryption=False)
    engine=BookResearchEngine(db)
    cases={
      'matrizes inversas':[{'passage_id':'p1','book_id':'b1','title':'Álgebra','page':12,'text':'Matrizes inversas exigem determinante não nulo.', 'text_hash':'h1','score':1}, {'passage_id':'p2','book_id':'b2','title':'Matemática','page':8,'text':'A matriz inversa existe quando a transformação é invertível.','text_hash':'h2','score':0.5}],
      'historia do computador':[],
    }
    async def fake_search(question,**kwargs):return cases.get(question,[])
    engine.index.search=fake_search
    class Conn:
        def execute(self,stmt,params):
            class Rows:
                def fetchone(self):
                    pid=params[0]
                    for arr in cases.values():
                        for p in arr:
                            if p['passage_id']==pid:return p
            return Rows()
    class Context:
        def __enter__(self):return Conn()
        def __exit__(self,*a):return False
    db.connect=lambda: Context()
    r=asyncio.run(engine.investigate(['matrizes inversas','historia do computador']))
    assert len(r['evidence'])==2
    assert set(r['coverage'])=={'b1','b2'}
    assert r['unanswered_query_numbers']==[2]
    assert all(p['verified_against_index'] for p in r['evidence'])


def test_tampered_retrieval_dropped(tmp_path):
    db=Database(tmp_path/'test.sqlite3',require_encryption=False)
    engine=BookResearchEngine(db)
    async def fake_search(*a,**kw):return [{'passage_id':'x','book_id':'b','title':'X','page':1,'text':'Texto adulterado','text_hash':'bad','score':1}]
    engine.index.search=fake_search
    class Conn:
        def execute(self,*a):
            class Rows:
                def fetchone(self):return {'book_id':'b','page':1,'text':'Texto verdadeiro','text_hash':'hash'}
            return Rows()
    class Context:
        def __enter__(self):return Conn()
        def __exit__(self,*a):pass
    db.connect=lambda:Context()
    r=asyncio.run(engine.investigate(['pergunta sobre livro']))
    assert r['evidence']==[]
