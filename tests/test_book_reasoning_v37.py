import asyncio
import functools
"""Deterministic tests: actual PDF ingestion + mocked model JSON responses."""
import pytest
from aura.database import Database
from aura.books import BookLearningEngine
from aura.deep_books import DeepBookStudy
from aura.book_reasoning import BookReasoningEngine


class Model:
    model = 'controlled-test-model'
    def __init__(self, hallucinate=False, invalid_synthesis=False):
        self.hallucinate=hallucinate
        self.invalid_synthesis=invalid_synthesis
        self.calls=[]

    async def generate(self, task, payload):
        self.calls.append((task,payload))
        if task == 'extract':
            p=payload['passages'][0]
            data={'claims':[{'statement':'Os vetores têm magnitude e direção no espaço geométrico.',
                 'passage_id':p['passage_id'],'quote':'Os vetores têm magnitude e direção no espaço geométrico.'}],
                  'concepts':[{'name':'Vetor','definition':'Um vetor possui magnitude e direção no espaço geométrico.',
                  'passage_id':p['passage_id'],'quote':'Os vetores têm magnitude e direção no espaço geométrico.'}],
                  'questions':[{'question':'Quais são as características geométricas dos vetores?',
                  'expected_answer':'Os vetores têm magnitude e direção no espaço geométrico.',
                  'passage_id':p['passage_id'],'quote':'Os vetores têm magnitude e direção no espaço geométrico.'}]}
            if self.hallucinate:
                data['claims'].append({'statement':'Vetores produzem energia infinita.',
                        'passage_id':p['passage_id'],'quote':'Comprovação de energia infinita em 2040.'})
            return data
        if task == 'synthesize':
            return {'overview':'Estudo da representação geométrica dos vetores.',
                    'key_points':[{'text':'Os vetores têm magnitude e direção no espaço geométrico.',
                                   'evidence_ids':['inventado' if self.invalid_synthesis else payload['evidence'][0]['id']]}]}
        if task == 'answer':
            p=payload['passages'][0]
            return {'answer':'Os vetores têm magnitude e direção no espaço geométrico.',
                    'abstain':False,'citations':[{'passage_id':p['passage_id'],
                     'quote':'Os vetores têm magnitude e direção no espaço geométrico.'}]}
        if task == 'compare':
            return {'relation':'related','explanation':'Ambos descrevem vetores geométricos.',
                    'quote_a':'Os vetores têm magnitude e direção no espaço geométrico.',
                    'quote_b':'Os vetores têm magnitude e direção no espaço geométrico.'}
        assert False,task


@pytest.fixture
def library(tmp_path):
    fitz=pytest.importorskip('fitz')
    db=Database(tmp_path/'books.sqlite3',require_encryption=False)
    books=BookLearningEngine(db)
    deep=DeepBookStudy(db)
    imported=[]
    for i in range(2):
        name=tmp_path/f'livro{i}.pdf'
        with fitz.open() as pdf:
            for n in range(11):
                p=pdf.new_page()
                p.insert_text((55,65),'Os vetores têm magnitude e direção no espaço geométrico.');
                for k in range(7):
                    p.insert_text((55,90+k*22),f'Aplicações na área de matemática e física capítulo {n}. Vetores são representações geométricas relevantes para este estudo.')
            pdf.set_toc([[1,'Vetores e aplicações',1]])
            pdf.save(name)
        result=books.import_pdf(name,rights_confirmed=True,rights_note='PDF criado para teste')
        chapter=deep.chapterize(result['book_id'],name)[0]
        deep.study(chapter['id'])
        imported.append((result['book_id'],chapter['id']))
    return db,books,imported


async def run_full_chapter_coverage_and_sources(library):
    db,books,ids=library
    core=BookReasoningEngine(db);model=Model(hallucinate=True)
    result=await core.study_chapter(ids[0][1],model)
    assert result['status']=='completed'
    assert result['coverage_pages']==result['available_pages']==11
    assert result['rejected']>=1
    assert len([x for x in result['items'] if x['item_type']=='synthesis'])>0
    assert len([x for x in result['items'] if x['item_type']=='question'])>0
    assert all(x['label']!='verified_truth' for x in result['items'])
    assert len([x for x in model.calls if x[0]=='extract'])>1
    assert all(i['evidence'][0]['page']>0 for i in result['items'])
    assert core.report(result['id'])['status']=='completed'


async def run_ungrounded_synthesis_rejected_and_no_items_committed(library):
    db,_,ids=library; core=BookReasoningEngine(db)
    with pytest.raises(ValueError,match='Síntese sem referências'):
        await core.study_chapter(ids[0][1],Model(invalid_synthesis=True))
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM book_reasoning_items').fetchone()[0]==0
        assert conn.execute("SELECT status FROM book_reasoning_runs").fetchone()[0]=='failed'


async def run_qa_source_scope_and_abstention(library):
    db,_,ids=library; core=BookReasoningEngine(db);model=Model()
    answer=await core.answer('Quais são as características dos vetores na geometria?',model,
                              chapter_id=ids[0][1])
    assert not answer['abstained'] and answer['citations'][0]['page']==1
    assert answer['citations'][0]['book_id']==ids[0][0]
    assert (await core.answer('Que espécies de tartaruga marinha existem?',model))['abstained']
    assert (await core.answer('vetores',model,book_id='livro-inexistente'))['abstained']
    assert len(model.calls)==1


async def run_book_concept_comparison_and_cascade_delete(library):
    db,books,ids=library;core=BookReasoningEngine(db)
    result=await core.compare_books(ids[0][0],ids[1][0],Model())
    assert result and result[0]['status']=='model_assessed_unverified'
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM book_concept_relations').fetchone()[0]>0
    await core.study_chapter(ids[0][1],Model())
    books.delete_book(ids[0][0])
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM book_reasoning_items').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM book_concept_relations').fetchone()[0]==0


async def run_citation_forgery_abstained(library):
    db,_,ids=library;core=BookReasoningEngine(db)
    class Faker(Model):
        async def generate(self,task,payload):
            if task=='answer':
                return {'answer':'Os vetores têm magnitude e direção no espaço geométrico.',
                        'abstain':False,'citations':[{'passage_id':'falso','quote':'invenção sobre vetores'}]}
            return await super().generate(task,payload)
    result=await core.answer('características vetores direção',Faker(),chapter_id=ids[0][1])
    assert result['abstained'] and not result['citations']

def test_full_chapter_coverage_and_sources(library):
    return asyncio.run(run_full_chapter_coverage_and_sources(library))

def test_ungrounded_synthesis_rejected_and_no_items_committed(library):
    return asyncio.run(run_ungrounded_synthesis_rejected_and_no_items_committed(library))

def test_qa_source_scope_and_abstention(library):
    return asyncio.run(run_qa_source_scope_and_abstention(library))

def test_book_concept_comparison_and_cascade_delete(library):
    return asyncio.run(run_book_concept_comparison_and_cascade_delete(library))

def test_citation_forgery_abstained(library):
    return asyncio.run(run_citation_forgery_abstained(library))

async def run_invalid_synthesis_text(library):
    db,_,ids=library; core=BookReasoningEngine(db)
    class Mismatch(Model):
        async def generate(self,task,payload):
            if task=='synthesize':
                return {'key_points':[{'text':'Os planetas de Júpiter são feitos de chocolate espacial.',
                                       'evidence_ids':[payload['evidence'][0]['id']]}]}
            return await super().generate(task,payload)
    with pytest.raises(ValueError,match='Síntese sem referências'):
        await core.study_chapter(ids[0][1],Mismatch())

def test_invalid_synthesis_text(library):
    asyncio.run(run_invalid_synthesis_text(library))


def test_voice_query_grounded_and_empty(tmp_path,library,monkeypatch):
    from aura.engine import AuraEngine
    from aura.config import Settings
    from aura.book_reasoning import OllamaBookModel
    db,_,ids=library
    fake=Model()
    async def simulate(self,task,payload):
        return await fake.generate(task,payload)
    monkeypatch.setattr(OllamaBookModel,'generate',simulate)
    engine=AuraEngine(Settings(data_dir=tmp_path,database_encryption_required=False),db)
    result=asyncio.run(engine.command('Expecto, segundo os livros, quais as características dos vetores?'))
    assert 'magnitude' in result['text']
    assert result['action']['panel']=='research'
    assert result['data'][0]['category']=='book'
    assert 'página' in result['data'][0]['content']
    blank=Database(tmp_path/'empty.sqlite3',require_encryption=False)
    empty_engine=AuraEngine(Settings(data_dir=tmp_path,database_encryption_required=False),blank)
    no_pdf=asyncio.run(empty_engine.command('Expecto, segundo os livros, o que são vetores?'))
    assert 'não tenho livros' in no_pdf['text']
