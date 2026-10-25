"""3.2 evidence integrity, source duplication, revision and conservative gate."""
import asyncio
import pytest
from fastapi.testclient import TestClient

from aura.app import create_app
from aura.config import Settings
from aura.database import Database
from aura.epistemics import EpistemicEngine
from aura.engine import AuraEngine
from aura.learning import LearningEngine
from aura.quality import KnowledgeQuality


def setup(tmp_path):
    config = Settings(data_dir=tmp_path, database_encryption_required=False,
                      embedding_model='', auto_extract_memory=False)
    db = Database(tmp_path/'aura.sqlite3')
    return config, db, LearningEngine(config, db), KnowledgeQuality(db)


def claim(db, learning, expression, url='https://publisher.example.net/1', topic='Teste'):
    content = f'A fonte de teste apresenta o cálculo {expression} de forma explícita.'
    source = db.remember_document(topic,'Fonte de teste',content,url,
                                  'documentation','single_source')
    result=learning.record(topic,[source],[{'statement':expression,
            'exact_quote':content,'document_id':source['id']}])
    assert result.stored == 1
    cid=next(x['id'] for x in learning.claims(topic) if x['statement']==expression)
    return cid,source


def test_attestation_is_captured_as_evidence_is_ingested(tmp_path):
    _,db,learning,quality=setup(tmp_path)
    cid,source=claim(db,learning,'125 + 75 = 200')
    report=quality.inspect(cid)
    assert report['snapshot_status']=='intact_at_capture'
    assert report['attested_evidence']==1
    assert report['decision']=='use_only_as_qualified_hypothesis'
    with db.connect() as conn:
        record=conn.execute('SELECT document_sha256,quote_sha256,url_sha256 FROM evidence_snapshots').fetchone()
    assert all(len(record[key])==64 for key in record.keys())
    assert all(c in '0123456789abcdef' for val in record for c in val)
    assert report['independence_confirmed'] is False


def test_capture_detects_modified_document_even_if_original_quote_remains(tmp_path):
    _,db,learning,quality=setup(tmp_path)
    cid,source=claim(db,learning,'125 + 75 = 200')
    with db.connect() as conn:
        conn.execute('UPDATE knowledge SET content = content || ? WHERE id=?',
                     (' NOTA POSTERIOR QUE MODIFICOU O ARQUIVO',source['id']))
    assert EpistemicEngine(db).assess(cid)['evidence_status']=='intact'  # 3.1 limitation
    report=quality.inspect(cid)
    assert report['snapshot_status']=='changed'
    assert report['evidence'][0]['status']=='changed_since_capture'
    assert report['decision']=='withhold'


def test_detects_repeated_quote_across_host_without_claiming_independence(tmp_path):
    _,db,learning,quality=setup(tmp_path)
    expression='125 + 75 = 200'
    cid,a=claim(db,learning,expression,'https://writer.example.com/1')
    cid2,b=claim(db,learning,expression,'https://republisher.example.org/2')
    assert cid==cid2
    report=quality.inspect(cid)
    assert report['repeated_text_across_hosts'] is True
    assert report['independence_confirmed'] is False
    assert report['grade']=='reproduced_calculation'


def test_arithmetic_conflicts_and_false_results_are_withheld(tmp_path):
    _,db,learning,quality=setup(tmp_path)
    ok,_=claim(db,learning,'125 + 75 = 200','https://one.example.com/a')
    bad,_=claim(db,learning,'125 + 75 = 201','https://two.example.com/b')
    reliable=quality.inspect(ok)
    unreliable=quality.inspect(bad)
    assert bad in reliable['possible_math_conflicts']
    assert ok in unreliable['possible_math_conflicts']
    assert reliable['grade']=='reproduced_calculation'
    assert unreliable['grade']=='falsified_calculation'
    assert unreliable['decision']=='withhold'
    assert reliable['decision']=='use_only_as_qualified_hypothesis'


def test_migration_does_not_forge_historical_snapshots(tmp_path):
    _,db,learning,quality=setup(tmp_path)
    cid,_=claim(db,learning,'125 + 75 = 200')
    with db.connect() as conn:
        conn.execute('DELETE FROM evidence_snapshots')  # simulate pre-3.2 evidence
    reopened=Database(tmp_path/'aura.sqlite3')
    report=KnowledgeQuality(reopened).inspect(cid)
    assert report['snapshot_status']=='legacy_or_partial'
    assert report['evidence'][0]['status']=='legacy_unattested'
    with reopened.connect() as conn:
        assert conn.execute('SELECT COUNT(*) AS n FROM evidence_snapshots').fetchone()['n']==0


def test_missing_document_rejected_and_cascade(tmp_path):
    _,db,learning,quality=setup(tmp_path)
    cid,src=claim(db,learning,'125 + 75 = 200')
    with db.connect() as conn:
        conn.execute('DELETE FROM knowledge WHERE id=?', (src['id'],))
    report=quality.inspect(cid)
    assert report['evidence'][0]['status']=='missing_document'
    assert report['decision']=='withhold'
    with db.connect() as conn:
        conn.execute('DELETE FROM learning_claims WHERE id=?',(cid,))
        assert conn.execute('SELECT COUNT(*) AS n FROM evidence_snapshots').fetchone()['n']==0


def test_get_api_and_natural_voice_commands(tmp_path):
    settings,db,learning,quality=setup(tmp_path)
    cid,_=claim(db,learning,'125 + 75 = 200')
    eng=AuraEngine(settings,db)
    answer=asyncio.run(eng.command('AURA, mostra qualidade da aprendizagem'))
    assert answer['action']=={'type':'open','panel':'research'}
    assert answer['data']['quality_report']['checked']==1
    answer=asyncio.run(eng.command('AURA, analisa qualidade '+cid))
    assert answer['data']['quality_report']['claim_id']==cid
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/quality/claims/'+cid).json()['snapshot_status']=='intact_at_capture'
        assert client.get('/api/quality/summary').json()['checked']==1
        assert client.get('/api/quality/claims/short').status_code==422
        assert client.get('/api/quality/claims/'+'f'*12).status_code==404
        assert client.get('/api/health').json()['version'].startswith('3.3')
        assert b'sidebar' not in client.get('/').content.lower()


def test_no_untrusted_claims_in_learned_context(tmp_path,monkeypatch):
    settings,db,learning,quality=setup(tmp_path)
    cid,_=claim(db,learning,'125 + 75 = 201')
    class FakeResponse:
        status_code=200
        def raise_for_status(self):pass
        def json(self):return {'message':{'content':'Uma resposta cautelosa.'}}
    calls=[]
    class FakeClient:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,json):
            calls.append(json)
            return FakeResponse()
    import aura.llm as llm_module
    monkeypatch.setattr(llm_module.httpx,'AsyncClient',FakeClient)
    answer=asyncio.run(llm_module.Ollama(settings,db).reply('125 + 75'))
    assert answer=='Uma resposta cautelosa.'
    assert calls
    system=calls[0]['messages'][0]['content']
    learning_chunk=system.split('HIPÓTESES DE APRENDIZAGEM (NÃO COMPROVADAS; manter a qualificação):\n',1)[1].split('Fontes recolhidas',1)[0]
    assert '125 + 75 = 201' not in learning_chunk


def test_quality_summary_has_read_only_semantics_and_bounded_limits(tmp_path):
    _,db,learning,quality=setup(tmp_path)
    cid,_=claim(db,learning,'125 + 75 = 200')
    with db.connect() as conn:
        before=conn.total_changes
    quality.overview(10**8)
    quality.inspect(cid,max_age_days=-500)
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) AS n FROM epistemic_audits').fetchone()['n']==0
    for value in ('x','a'*500,'abc;DROP TABLE learning_claims',''):
        with pytest.raises(ValueError):
            quality.inspect(value)
