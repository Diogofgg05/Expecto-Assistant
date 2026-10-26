"""Expecto 4.0: true isolation between learning/validation/holdout questions."""
import asyncio
import json

import pytest
from aura.book_iteration import BookIterationLab
from aura.database import Database
from aura.books import BookLearningEngine
from aura.book_semantics import BookSemanticIndex


@pytest.fixture
def library(tmp_path, monkeypatch):
    fitz=pytest.importorskip('fitz')
    path=tmp_path/'physics.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page()
        page.insert_text((40,50),'Um vetor tem modulo direcao e sentido no espaco geometrico.')
        page=pdf.new_page()
        page.insert_text((40,50),'A aceleracao representa a mudanca de velocidade ao longo do tempo.')
        pdf.save(path)
    db=Database(tmp_path/'memory.sqlite3',require_encryption=False)
    book=BookLearningEngine(db).import_pdf(path,rights_confirmed=True,rights_note='PDF criado exclusivamente no teste')
    with db.connect() as conn:
        rows=[dict(x) for x in conn.execute('''SELECT p.id,p.page,p.text,p.book_id,b.title
                    FROM book_passages p JOIN book_documents b ON b.id=p.book_id ORDER BY p.page''')]
    mode={'holdout_regression':False,'calls':[]}
    async def fake_search(self,question,*,book_id=None,chapter_id=None,limit=7,encoder=None):
        mode['calls'].append({'question':question,'limit':limit})
        if 'isola' in question and mode['holdout_regression']:
            row=rows[0] if limit<8 else rows[1]
        else:
            row=rows[1] if limit<8 else rows[0]
        return [{'passage_id':row['id'],'book_id':row['book_id'],'title':row['title'],
                 'page':row['page'],'text':row['text']}]
    monkeypatch.setattr(BookSemanticIndex,'search',fake_search)
    questions={
      'train':['Explica como se caracteriza geometricamente um vetor ao longo de uma reta.',
               'Que componentes descrevem a grandeza vectorial no plano cartesiano?'],
      'validation':['Qual a constituicao conceptual de um deslocamento vetorial em geometria?',
                    'Descreve os atributos fundamentais da representacao de vetores.'],
      'holdout':['Como isola a definicao vetorial as propriedades de orientacao geometrica?',
                 'No exemplo isola, apresenta os atributos de um vetor num espaco.'],
    }
    dataset={}
    for split,qs in questions.items():
        dataset[split]=[{'id':f'{split}_{i}', 'curation':'human_reviewed',
            'book_id':book['book_id'], 'chapter_id':None,'question':q,
            'expected_answer':rows[0]['text'], 'gold_passage_ids':[rows[0]['id']]}
            for i,q in enumerate(qs)]
    return db,dataset,mode,rows


class QuoteModel:
    model='mock-local-book-engine'
    def __init__(self):self.prompts=[]
    async def generate(self,task,payload):
        assert task=='answer'
        self.prompts.append(json.dumps(payload,ensure_ascii=False))
        p=payload['passages'][0]
        return {'abstain':False,'answer':p['text'],
                'citations':[{'passage_id':p['passage_id'],'quote':p['text']}]}


def test_actual_isolated_cycle_and_recovery(library):
    db,bundle,mode,rows=library
    model=QuoteModel()
    lab=BookIterationLab(db)
    report=asyncio.run(lab.run(bundle,model,limits=(4,8)))
    assert report['status']=='completed'
    assert report['chosen_limit']==8
    assert report['recommendation']=='candidate_requires_human_approval'
    assert report['changed_production'] is False
    assert report['weights_updated'] is False
    assert report['trace']['validation']['candidate_score'] > report['trace']['validation']['baseline_score']
    assert report['trace']['holdout']['candidate_score'] > report['trace']['holdout']['baseline_score']
    assert len(mode['calls'])==12  # 2 train limits *2, validation *2, holdout *2
    assert all('expected_answer' not in p and 'gold_passage_ids' not in p for p in model.prompts)
    reopened=BookIterationLab(Database(db.path,require_encryption=False)).report(report['id'])
    assert reopened['chosen_limit']==8
    reviews=lab.review(report['id'])
    assert reviews['review_chapters'] and reviews['review_chapters'][0]['pages']==[1]
    assert 'holdout' not in json.dumps(reviews)


def test_holdout_regression_vetoes_recommendation(library):
    db,bundle,mode,rows=library
    mode['holdout_regression']=True
    result=asyncio.run(BookIterationLab(db).run(bundle,QuoteModel(),limits=[4,8]))
    assert result['recommendation']=='holdout_regression'
    assert result['trace']['validation']['candidate_score'] > result['trace']['validation']['baseline_score']
    assert result['trace']['holdout']['candidate_score'] < result['trace']['holdout']['baseline_score']


def test_duplicate_questions_rejected_before_model_calls(library):
    db,ds,mode,rows=library
    ds['holdout'][0]['question']=ds['train'][0]['question']
    with pytest.raises(ValueError,match='iguais'):
        asyncio.run(BookIterationLab(db).run(ds,QuoteModel(),limits=[4,8]))
    assert not mode['calls']


def test_near_duplicate_between_splits_rejected(library):
    db,ds,mode,rows=library
    ds['validation'][0]['question']=ds['train'][0]['question']+' por favor.'
    with pytest.raises(ValueError,match='semelhantes'):
        asyncio.run(BookIterationLab(db).run(ds,QuoteModel(),limits=[4,8]))


def test_bad_limits_and_unreviewed_sources_rejected(library):
    db,ds,mode,rows=library
    lab=BookIterationLab(db)
    with pytest.raises(ValueError,match='Limites duplicados'):
        asyncio.run(lab.run(ds,QuoteModel(),limits=(8,8)))
    ds['holdout'][0]['curation']='model_generated'
    with pytest.raises(ValueError,match='human_reviewed'):
        asyncio.run(lab.run(ds,QuoteModel(),limits=(4,8)))


def test_mutation_invalidates_prior_learning_recommendation(library):
    db,ds,mode,rows=library
    lab=BookIterationLab(db)
    result=asyncio.run(lab.run(ds,QuoteModel(),limits=(4,8)))
    with db.connect() as conn:
        conn.execute('UPDATE book_passages SET text=? WHERE id=?',('conteudo adulterado',rows[0]['id']))
    assert lab.report(result['id'])['recommendation']=='stale_sources_do_not_apply'
    with pytest.raises(ValueError,match='Fontes alteradas'):
        lab.review(result['id'])


def test_explicit_restudy_only_missed_train_chapter(library, tmp_path):
    db,bundle,mode,rows=library
    from aura.deep_books import DeepBookStudy
    # The learning review must be an actual chapter (rather than a whole-book ID).
    with db.connect() as conn:
        conn.execute('INSERT INTO book_chapters VALUES(?,?,?,?,?,?,?)',
                     ('chapter_a',rows[0]['book_id'],1,'Vetores',1,1,'manual_test'))
    for split in bundle:
        for case in bundle[split]:
            case['chapter_id']='chapter_a'
    cycle=BookIterationLab(db)
    result=asyncio.run(cycle.run(bundle,QuoteModel(),limits=[4,8]))

    class RestudyModel(QuoteModel):
        async def generate(self,task,payload):
            if task=='extract':
                p=payload['passages'][0]
                return {'claims':[{'statement':p['text'], 'passage_id':p['passage_id'],
                                    'quote':p['text']}], 'concepts':[], 'questions':[]}
            if task=='synthesize':
                e=payload['evidence'][0]
                return {'overview':'Releitura de conceitos',
                       'key_points':[{'text':e['body'],'evidence_ids':[e['id']]}]}
            return await super().generate(task,payload)

    studied=asyncio.run(cycle.restudy(result['id'],RestudyModel(),max_chapters=1))
    assert len(studied['study_runs'])==1
    assert studied['study_runs'][0]['status']=='completed'
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM book_reasoning_items').fetchone()[0]>=1
    assert cycle.report(result['id'])['changed_production'] is False


def test_history_and_revisit_invalid_limit(library):
    db,ds,mode,rows=library
    lab=BookIterationLab(db)
    result=asyncio.run(lab.run(ds,QuoteModel(),limits=[4,8]))
    assert lab.history(1)[0]['id']==result['id']
    with pytest.raises(ValueError,match='inválido'):
        lab.history(0)
    with pytest.raises(ValueError,match='inválido'):
        asyncio.run(lab.restudy(result['id'],QuoteModel(),max_chapters=0))
