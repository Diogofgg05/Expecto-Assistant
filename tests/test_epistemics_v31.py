"""Offline verification tests: quote integrity != truth; only arithmetic reproducible."""
import asyncio
import pytest
from fastapi.testclient import TestClient

from aura.app import create_app
from aura.config import Settings
from aura.database import Database
from aura.epistemics import EpistemicEngine, exact_calculation, verify_identity
from aura.engine import AuraEngine
from aura.learning import LearningEngine


def setup(tmp_path):
    settings = Settings(data_dir=tmp_path,database_encryption_required=False)
    db = Database(tmp_path/'aura.sqlite3')
    return db, LearningEngine(settings,db), EpistemicEngine(db)


def add_claim(db, learning, statement, url='https://example.org/docs'):
    quote = f'No exemplo consta a seguinte afirmação: {statement}. Informação para testes.'
    d = db.remember_document('Matemática','Texto teste', quote, url,
                             'documentation','single_source')
    result=learning.record('Matemática',[d],[{
        'document_id':d['id'],'statement':statement,'exact_quote':quote
    }])
    assert result.stored==1
    return next(c['id'] for c in learning.claims('Matemática') if c['statement']==statement),d


def test_exact_arithmetic_and_false_claim(tmp_path):
    db,learn,e=setup(tmp_path)
    correct,_=add_claim(db,learn,'125 + 75 = 200')
    output=e.audit(correct)
    assert output['grade']=='reproduced_calculation'
    assert output['arithmetic']['computed']=='200'
    wrong,_=add_claim(db,learn,'125 + 75 = 201', 'https://elsewhere.net/article')
    assert e.audit(wrong)['grade']=='falsified_calculation'
    assert len(e.latest())==2


def test_quoted_content_is_not_automatically_a_fact(tmp_path):
    db,learn,e=setup(tmp_path)
    text='Python disponibiliza bibliotecas para desenvolvimento de software.'
    d1=db.remember_document('Python','A',text,'https://origin.example.com/a','documentation','single_source')
    d2=db.remember_document('Python','B',text,'https://mirror.example.net/a','documentation','single_source')
    claim={'statement':text,'exact_quote':text}
    learn.record('Python',[d1,d2],[{**claim,'document_id':d1['id']},{**claim,'document_id':d2['id']}])
    output=e.assess(learn.claims()[0]['id'])
    assert output['grade']=='multiple_reports_unverified'
    assert output['intact_evidence_count']==2
    assert 'não garantem independência' in output['meaning']


def test_quote_or_origin_missing_fails_closed(tmp_path):
    db,learn,e=setup(tmp_path)
    id,doc=add_claim(db,learn,'125 + 75 = 200')
    with db.connect() as conn:
        conn.execute('UPDATE knowledge SET content=? WHERE id=?',('O texto foi alterado.',doc['id']))
    result=e.audit(id)
    assert result['grade']=='unsubstantiated'
    assert result['evidence_status']=='broken'
    assert result['arithmetic']['passed'] # math is true, but original evidence vanished
    with db.connect() as conn:
        conn.execute('DELETE FROM knowledge WHERE id=?',(doc['id'],))
    assert e.assess(id)['grade']=='unsubstantiated'


def test_user_approval_never_becomes_verification(tmp_path):
    db,learn,e=setup(tmp_path)
    text='Python disponibiliza bibliotecas para desenvolvimento de software.'
    d=db.remember_document('Python','A',text,'https://sample.org/a','documentation','single_source')
    learn.record('Python',[d],[{'statement':text,'document_id':d['id'],'exact_quote':text}])
    id=learn.claims()[0]['id']
    assert learn.review(id,'approve')
    assessment=e.assess(id)
    assert assessment['grade']=='quoted_unverified'
    assert assessment['review_state']=='approved_by_user'
    assert learn.review(id,'reject')
    assert e.assess(id)['grade']=='rejected'


def test_math_parser_resists_code_execution_and_precision_traps():
    assert verify_identity('1/3 = 0.333333')['passed'] is False
    assert verify_identity('0.1 + 0.2 = 0.3')['passed'] is True
    assert verify_identity('1.0000000000000001 - 1 = 0')['passed'] is False
    assert verify_identity('(-2 + 5) * 4 = 12')['passed'] is True
    for payload in ['__import__("os").system("whoami") = 0', '2**10000000 = 0',
                    '1/0 = 1', 'len(2) = 2','1e500 = 1']:
        assert verify_identity(payload)['passed'] is False
    with pytest.raises(ValueError):
        exact_calculation('1/0')


def test_migration_and_http_are_read_only(tmp_path):
    db,learn,e=setup(tmp_path)
    claim,_=add_claim(db,learn,'125 + 75 = 200')
    reopened=Database(tmp_path/'aura.sqlite3')
    assert EpistemicEngine(reopened).assess(claim)['grade']=='reproduced_calculation'
    with TestClient(create_app(Settings(data_dir=tmp_path,database_encryption_required=False))) as client:
        url='/api/epistemics/claims/'+claim
        assert client.get(url).json()['grade']=='reproduced_calculation'
        assert client.get('/api/epistemics/audits').json()['items']==[]
        assert client.get('/api/epistemics/claims/'+'bad-id').status_code==422
        assert client.get('/api/epistemics/claims/'+'a'*12).status_code==404
        assert client.get('/api/health').json()['version'].startswith('3.3')
        assert b'sidebar' not in client.get('/').content.lower()


def test_explicit_natural_commands_and_no_lm_actions(tmp_path):
    db,learn,e=setup(tmp_path)
    claim,_=add_claim(db,learn,'125 + 75 = 200')
    eng=AuraEngine(Settings(data_dir=tmp_path,database_encryption_required=False),db)
    res=asyncio.run(eng.command('AURA, audita descoberta '+claim))
    assert res['action']=={'type':'open','panel':'research'}
    assert 'reproduzido' in res['text']
    res=asyncio.run(eng.command('Audita conhecimentos'))
    assert res['data']['epistemic_audit']['audited']==1
    assert e.latest()
