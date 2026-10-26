"""3.9 regression: human curated, held-out open-book eval and integrity checks."""
import asyncio
import json
from pathlib import Path

import pytest
from aura.database import Database
from aura.books import BookLearningEngine
from aura.deep_books import DeepBookStudy
from aura.book_mastery import BookMasteryLab, token_f1


@pytest.fixture
def example(tmp_path):
    fitz=pytest.importorskip('fitz')
    source=tmp_path/'science.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page()
        page.insert_text((50,65),'A fotossintese transforma energia luminosa em energia quimica nas plantas.')
        page.insert_text((50,90),'A clorofila participa na absorcao de luz durante a fotossintese.')
        page=pdf.new_page()
        page.insert_text((50,65),'Os vetores possuem magnitude e direcao, conforme o sistema geometrico.')
        pdf.set_toc([[1,'Capitulo Luz',1],[1,'Capitulo Vetores',2]])
        pdf.save(source)
    db=Database(tmp_path/'library.sqlite3',require_encryption=False)
    imported=BookLearningEngine(db).import_pdf(source,rights_confirmed=True,rights_note='Documento fictício criado para teste')
    chapters=DeepBookStudy(db).chapterize(imported['book_id'],source)
    with db.connect() as conn:
        pages={r['page']:r['id'] for r in conn.execute('SELECT id,page FROM book_passages ORDER BY page')}
    return db, imported['book_id'], chapters, pages


def _cases(book,chapters,pages):
    return [
      {'id':'light-001','curation':'human_reviewed','book_id':book,'chapter_id':chapters[0]['id'],
       'question':'Explica o papel da clorofila na fotossíntese das plantas.',
       'expected_answer':'A clorofila participa na absorcao de luz durante a fotossintese.',
       'gold_passage_ids':[pages[1]]},
      {'id':'vetor-001','curation':'human_reviewed','book_id':book,'chapter_id':chapters[1]['id'],
       'question':'Quais são as propriedades fundamentais de vetores geométricos?',
       'expected_answer':'Os vetores possuem magnitude e direcao, conforme o sistema geometrico.',
       'gold_passage_ids':[pages[2]]},
      {'id':'unknown-001','curation':'human_reviewed','book_id':book,'chapter_id':chapters[0]['id'],
       'question':'Qual a pressão atmosférica descrita no capítulo sobre luz?',
       'unanswerable':True,'expected_answer':'','gold_passage_ids':[]}
    ]


class ControlledModel:
    model='controlled-test-no-real-ollama'
    def __init__(self):self.inputs=[]
    async def generate(self,task,payload):
        assert task=='answer'
        self.inputs.append(json.dumps(payload))
        q=payload['question']
        if 'pressão' in q:
            return {'answer':'','abstain':True,'citations':[]}
        p=payload['passages'][0]
        if 'clorofila' in q.casefold():
            return {'answer':'A clorofila participa na absorcao de luz durante a fotossintese.',
                    'abstain':False,'citations':[{'passage_id':p['passage_id'],'quote':p['text']}]}
        return {'answer':'Os vetores possuem magnitude e direcao, conforme o sistema geometrico.',
                'abstain':False,'citations':[{'passage_id':p['passage_id'],'quote':p['text']}]}


def test_holdout_reference_never_sent_to_model_and_full_score(example):
    db,book,chapters,pages=example
    cases=_cases(book,chapters,pages)
    model=ControlledModel()
    result=asyncio.run(BookMasteryLab(db).assess(cases,model))
    assert result['total']==3 and result['passed']==3
    assert result['provisional_pass_rate']==1 and result['stale_sources'] is False
    assert result['evidence_recall']==1 and result['average_token_f1']>=0.66
    for payload in model.inputs:
        assert 'expected_answer' not in payload and 'gold_passage_ids' not in payload
        assert 'human_reviewed' not in payload
    assert len(model.inputs)==3  # benchmark sent questions only, never solutions
    saved=BookMasteryLab(Database(db.path,require_encryption=False)).report(result['id'])
    assert saved['dataset_hash']==result['dataset_hash'] and saved['cases'][0]['result']=='provisional_match'
    assert BookMasteryLab(db).history(result['dataset_hash'])[0]['id']==result['id']


def test_low_similarity_and_missing_citation_report_gap(example):
    db,book,chapters,pages=example
    class Wrong(ControlledModel):
        async def generate(self,task,payload):
            r=await super().generate(task,payload)
            if 'vetores' in payload['question']:
                r['answer']='Os vetores possuem apenas magnitude, sem direção.'
            return r
    result=asyncio.run(BookMasteryLab(db).assess(_cases(book,chapters,pages),Wrong(),min_f1=0.9))
    assert result['passed']<3 and result['gaps']
    assert result['gaps'][0]['pages_for_review']
    assert any(r['result']=='polarity_mismatch' for r in result['cases'])


def test_validation_before_model_and_forged_gold_rejected(example):
    db,book,chapters,pages=example
    lab=BookMasteryLab(db);cases=_cases(book,chapters,pages)
    bad=json.loads(json.dumps(cases));bad[0]['gold_passage_ids']=['fake-id']
    model=ControlledModel()
    with pytest.raises(ValueError,match='gold'):
        asyncio.run(lab.assess(bad,model))
    assert model.inputs==[]
    bad=json.loads(json.dumps(cases));bad[0]['curation']='model_generated'
    with pytest.raises(ValueError,match='human_reviewed'):
        asyncio.run(lab.assess(bad,model))
    bad=json.loads(json.dumps(cases));bad[0]['chapter_id']=chapters[1]['id']
    with pytest.raises(ValueError,match='fora do capítulo'):
        asyncio.run(lab.assess(bad,model))
    assert lab.history()==[]


def test_manually_curated_unanswerable_false_positive(example):
    db,book,chapters,pages=example
    class Hallucinates(ControlledModel):
        async def generate(self,task,payload):
            return {'answer':'A clorofila participa na absorcao de luz durante a fotossintese.',
                   'abstain':False,'citations':[{'passage_id':payload['passages'][0]['passage_id'],
                                               'quote':payload['passages'][0]['text']}]}
    cases=_cases(book,chapters,pages)
    cases[0]['question']='Qual é a cor associada à absorcao de luz durante a fotossintese?'
    cases[0]['unanswerable']=True;cases[0]['expected_answer']='';cases[0]['gold_passage_ids']=[]
    case=cases[:1]
    result=asyncio.run(BookMasteryLab(db).assess(case,Hallucinates()))
    assert result['passed']==0 and result['cases'][0]['result']=='answered_without_reference'


def test_stale_source_after_modify_and_cascade_deletion(example):
    db,book,chapters,pages=example
    result=asyncio.run(BookMasteryLab(db).assess(_cases(book,chapters,pages),ControlledModel()))
    lab=BookMasteryLab(db)
    with db.connect() as conn:
        conn.execute('UPDATE book_passages SET text_hash=? WHERE id=?',('tampered',pages[1]))
    assert lab.report(result['id'])['stale_sources'] is True
    assert lab.report(result['id'])['provisional_pass_rate'] is None
    BookLearningEngine(db).delete_book(book)
    after=lab.report(result['id'])
    assert after['stale_sources'] and len(after['cases'])==0


def test_scoring_explicit_and_not_semantic_truth():
    assert token_f1('vetor magnitude direção','Direção, magnitude de um vetor')==1.0
    assert token_f1('um vetor NÃO tem direção','um vetor tem direção') > 0.5  # lexical metric cannot detect negation
    assert token_f1('unrelated astronomy','physics kinematics')==0


def test_failed_questions_become_actionable_reading_plan(example):
    db,book,chapters,pages=example
    class Abstainer(ControlledModel):
        async def generate(self,task,payload):
            if 'vetores' in payload['question']:
                return {'abstain':True,'answer':'','citations':[]}
            return await super().generate(task,payload)
    lab=BookMasteryLab(db)
    result=asyncio.run(lab.assess(_cases(book,chapters,pages),Abstainer()))
    plan=lab.remediation(result['id'])
    assert len(plan['chapters_to_review'])==1
    assert plan['chapters_to_review'][0]['review_pages']==[2]
    assert plan['chapters_to_review'][0]['chapter_title']=='Capitulo Vetores'
    assert 'novas perguntas' in plan['chapters_to_review'][0]['next_step']


def test_compare_requires_exact_same_heldout_dataset(example):
    db,book,chapters,pages=example
    lab=BookMasteryLab(db)
    cases=_cases(book,chapters,pages)
    first=asyncio.run(lab.assess(cases,ControlledModel()))
    second=asyncio.run(lab.assess(cases,ControlledModel()))
    assert lab.compare(first['id'],second['id'])['delta_provisional_pass_rate']==0
    changed=json.loads(json.dumps(cases));changed[0]['question']+=' Explica com cuidado.'
    third=asyncio.run(lab.assess(changed,ControlledModel()))
    with pytest.raises(ValueError,match='diferentes'):
        lab.compare(first['id'],third['id'])
    with pytest.raises(ValueError,match='diferentes'):
        lab.compare(first['id'],first['id'])


def test_tamper_without_updating_hash_detected(example):
    db,book,chapters,pages=example
    lab=BookMasteryLab(db)
    result=asyncio.run(lab.assess(_cases(book,chapters,pages),ControlledModel()))
    with db.connect() as conn:
        conn.execute('UPDATE book_passages SET text=? WHERE id=?',('adulterado',pages[1]))
    assert lab.report(result['id'])['stale_sources'] is True
    with pytest.raises(ValueError,match='hash'):
        asyncio.run(lab.assess(_cases(book,chapters,pages),ControlledModel()))
