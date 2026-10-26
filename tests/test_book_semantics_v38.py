"""3.8 regression: actual generated PDFs, persistent embeddings, scoped retrieval.

Synthetic vectors prove integration and safety gates, NOT Ollama reasoning accuracy.
"""
import asyncio
import json
import math
import hashlib
from pathlib import Path
import pytest
from aura.database import Database
from aura.books import BookLearningEngine
from aura.deep_books import DeepBookStudy
from aura.book_semantics import BookSemanticIndex, OllamaBookEncoder
from aura.book_reasoning import BookReasoningEngine


class ControlledEncoder:
    model='controlled-embedding-v1'
    def __init__(self): self.calls=[]
    async def embed(self, texts):
        self.calls.extend(texts)
        vectors=[]
        for txt in texts:
            low=txt.casefold()
            if ('magnitude' in low or 'orientacao' in low or 'orientação' in low or 'direcao' in low or 'direção' in low or 'deslocamento' in low):
                vectors.append([1.0,0,0])
            elif 'fotossintese' in low or 'fotossíntese' in low or 'clorofila' in low:
                vectors.append([0.0,1,0])
            else:
                vectors.append([0.0,0,1])
        return vectors


@pytest.fixture
def library(tmp_path):
    fitz=pytest.importorskip('fitz')
    db=Database(tmp_path/'library.sqlite3',require_encryption=False)
    books=BookLearningEngine(db)
    result=[]
    content=[
      ('física','A propriedade de magnitude e direção determina a representação do vetor geométrico.'),
      ('biologia','A clorofila absorve luz no processo de fotossíntese que ocorre nas plantas.')]
    for name,text in content:
        file=tmp_path/(name+'.pdf')
        with fitz.open() as document:
            page=document.new_page();page.insert_text((40,60),text)
            document.set_toc([[1,'Capítulo fundamental',1]])
            document.save(file)
        data=books.import_pdf(file,rights_confirmed=True,rights_note='PDF inventado para testes')
        chapter=DeepBookStudy(db).chapterize(data['book_id'],file)[0]
        result.append((data['book_id'],chapter['id']))
    return db,books,result


def test_semantic_paraphrase_survives_restart(library):
    db,books, ids=library
    async def run():
        index=BookSemanticIndex(db);encoder=ControlledEncoder()
        assert (await index.search('deslocamento vetorial',book_id=ids[0][0]))==[]
        info=await index.index_book(ids[0][0],encoder)
        assert info['indexed']==1 and info['reused']==0
        assert (await index.index_book(ids[0][0],encoder))['reused']==1
        index=BookSemanticIndex(Database(db.path,require_encryption=False))
        out=await index.search('deslocamento vetorial',encoder=encoder,book_id=ids[0][0])
        assert len(out)==1 and out[0]['page']==1
        assert out[0]['title']=='física'
        assert await index.search('deslocamento vetorial',book_id=ids[0][0])==[]
        assert await index.search('deslocamento vetorial',encoder=encoder,book_id=ids[1][0])==[]
        assert len(encoder.calls)==3
    asyncio.run(run())


def test_lexical_and_scope_and_deletion(library):
    db,books,ids=library
    async def run():
        ix=BookSemanticIndex(db)
        hits=await ix.search('fotossíntese clorofila')
        assert hits and hits[0]['book_id']==ids[1][0]
        with pytest.raises(ValueError):
            await ix.search('fotossíntese clorofila',book_id=ids[0][0],chapter_id=ids[1][1])
        encoder=ControlledEncoder()
        await ix.index_book(ids[1][0],encoder)
        with db.connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM book_embeddings').fetchone()[0]==1
        books.delete_book(ids[1][0])
        with db.connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM book_embeddings').fetchone()[0]==0
        assert not await ix.search('fotossintese')
    asyncio.run(run())


def test_stale_embedding_and_corruption_refused(library):
    db,books,ids=library
    async def run():
        ix=BookSemanticIndex(db);enc=ControlledEncoder()
        await ix.index_book(ids[0][0],enc)
        with db.connect() as conn:
            conn.execute('UPDATE book_passages SET text=?,text_hash=? WHERE book_id=?',
                         ('Texto completamente substituído',hashlib.sha256('Texto completamente substituído'.encode()).hexdigest(),ids[0][0]))
        assert not await ix.search('deslocamento vetorial',encoder=enc,book_id=ids[0][0])
        report=await ix.index_book(ids[0][0],enc)
        assert report['indexed']==1
        assert not await ix.search('deslocamento vetorial',encoder=enc,book_id=ids[0][0])
    asyncio.run(run())


def test_embedding_validation():
    from aura.book_semantics import _unit
    for invalid in ([0,0],[1,math.inf],[math.nan,1],[1,'x'],[1],[],[True,1]):
        with pytest.raises(ValueError):_unit(invalid)
    with pytest.raises(ValueError):OllamaBookEncoder('model','https://example.com')


def test_manual_gold_benchmark(library):
    db,books,ids=library
    async def run():
        ix=BookSemanticIndex(db)
        with db.connect() as conn:
            gold=conn.execute('SELECT id FROM book_passages WHERE book_id=?',(ids[0][0],)).fetchone()[0]
        cases=[{'question':'deslocamento vetorial','book_id':ids[0][0],
                'gold_passage_ids':[gold]}]
        score=await ix.evaluate_retrieval(cases)
        assert score['hit_at_k']==0
        encoder=ControlledEncoder();await ix.index_book(ids[0][0],encoder)
        score=await ix.evaluate_retrieval(cases,encoder=encoder)
        assert score['hit_at_k']==1 and score['mrr']==1 and score['cases']==1
        with pytest.raises(ValueError): await ix.evaluate_retrieval([{'question':'x','gold_passage_ids':[]}])
    asyncio.run(run())


def test_grounded_book_answer_semantic_and_numeric_guard(library):
    db,books,ids=library
    async def run():
        encoder=ControlledEncoder();ix=BookSemanticIndex(db)
        await ix.index_book(ids[0][0],encoder)
        engine=BookReasoningEngine(db)
        class Controlled:
            async def generate(self, task, payload):
                assert task=='answer'
                p=payload['passages'][0]
                assert p['page']==1
                return {'answer':'A representação do vetor combina magnitude e direção.',
                        'citations':[{'passage_id':p['passage_id'],'quote':p['text']}],
                        'abstain':False}
        answer=await engine.answer('deslocamento vetorial',Controlled(),encoder=encoder,chapter_id=ids[0][1])
        assert not answer['abstained'] and answer['citations'][0]['page']==1
        class Fabricator(Controlled):
            async def generate(self,task,payload):
                data=await super().generate(task,payload)
                data['answer']='A magnitude do vetor aumenta 9000 unidades de direção.'
                return data
        failure=await engine.answer('deslocamento vetorial',Fabricator(),encoder=encoder)
        assert failure['abstained'] and 'números' in failure['reason']
    asyncio.run(run())


def test_map_requires_multiple_sources_and_retain_review_labels(library):
    db, books, ids = library
    from aura.book_reasoning import BookReasoningEngine
    class StudyModel:
        model='test-only'
        async def generate(self,task,payload):
            if task=='extract':
                p=payload['passages'][0]
                return {'claims':[{'statement':'A magnitude e direção são propriedades do vetor geométrico.',
                    'passage_id':p['passage_id'],'quote':p['text']}], 'concepts':[], 'questions':[]}
            if task=='synthesize':
                return {'key_points':[{'text':'A magnitude e direção são propriedades do vetor geométrico.',
                    'evidence_ids':[payload['evidence'][0]['id']]}]}
            if task=='map':
                entries=payload['evidence'];ref=entries[0]['id']
                return {'relations':[{'statement':'Magnitude e direção formam o vetor geométrico.',
                         'evidence_ids':[ref]}],
                        'misconceptions':[{'mistake':'O vetor geométrico não tem magnitude.',
                         'correction':'O vetor geométrico tem magnitude e direção.',
                         'evidence_ids':[ref]}],
                        'transfer_questions':[{'question':'Como distinguir direção e magnitude num vetor?',
                         'rubric':'Indicar magnitude e direção do vetor geométrico.',
                         'evidence_ids':[ref]}]}
    async def run():
        core=BookReasoningEngine(db);model=StudyModel()
        study=await core.study_chapter(ids[0][1],model)
        output=await core.build_learning_map(study['id'],model)
        assert output['items']==2 and output['rejected']==1
        assert all(x['label']=='model_generated_requires_review' for x in output['learning_map']['items']
                   if x['item_type'] in ('transfer_question','misconception'))
        rerun=await core.build_learning_map(study['id'],model)
        assert rerun['items']==2
        assert len([x for x in rerun['learning_map']['items'] if x['item_type']=='transfer_question'])==1
        assert rerun['learning_map']['citation_coverage_ratio']==1
    asyncio.run(run())
