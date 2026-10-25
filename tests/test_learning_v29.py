"""Self-contained learning regression suite; no network or real LLM required."""
import asyncio

from fastapi.testclient import TestClient

from aura.app import create_app
from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine
from aura.learning import LearningEngine, host
from aura.research import ResearchOutcome


def setup(tmp_path):
    s=Settings(data_dir=tmp_path, database_encryption_required=False)
    db=Database(tmp_path/'aura.sqlite3')
    return db,LearningEngine(s,db)


def doc(db, url='https://docs.example.com/a', topic='Python'):
    return db.remember_document(topic,'Documentação de teste',
        'A linguagem Python disponibiliza bibliotecas para desenvolvimento de software.',
        url,'documentation','single_source')


def proposal(d,quote=None):
    return {'document_id':d['id'],
            'statement':'Python disponibiliza bibliotecas para desenvolvimento de software.',
            'exact_quote':quote or d['content']}


def test_single_and_multiple_sources_are_not_verified(tmp_path):
    db, learn=setup(tmp_path)
    a=doc(db,'https://docs.example.com/a')
    b=doc(db,'https://python.org/b')
    r=learn.record('Python',[a,b],[proposal(a),proposal(b)])
    assert r.stored==2
    claims=learn.claims('Python')
    assert len(claims)==1
    assert claims[0]['state']=='multiple_sources'
    assert claims[0]['source_count']==2
    assert all(s['exact_quote']==a['content'] for s in claims[0]['sources'])
    assert learn.stats()['runs']==1
    assert 'NÃO comprova' in learn.stats()['meaning']


def test_quote_must_be_literal_and_https_public(tmp_path):
    db,learn=setup(tmp_path)
    d=doc(db)
    wrong=proposal(d,'Um texto completamente inventado e muito longo.')
    assert learn.record('Python',[d],[wrong]).rejected==1
    assert learn.claims()==[]
    assert host('https://127.0.0.1/secret')==''
    assert host('http://docs.example.org/info')==''
    assert host('https://docs.example.org/info')=='docs.example.org'


def test_do_not_duplicate_evidence_or_regenerate_rejected(tmp_path):
    db,learn=setup(tmp_path)
    d=doc(db)
    learn.record('Python',[d],[proposal(d)])
    ident=learn.claims()[0]['id']
    assert learn.record('Python',[d],[proposal(d)]).stored==0
    assert learn.review(ident,'reject')
    assert learn.record('Python',[d],[proposal(d)]).rejected==1
    assert learn.claims()[0]['state']=='rejected'


def test_user_approval_is_not_fact_verification(tmp_path):
    db,learn=setup(tmp_path)
    d=doc(db)
    learn.record('Python',[d],[proposal(d)])
    ident=learn.claims()[0]['id']
    assert learn.review(ident,'approve')
    assert learn.claims()[0]['state']=='approved_by_user'
    assert learn.claims()[0]['reviewed_at']


def test_migration_preserves_earlier_memory_and_learning(tmp_path):
    db,learn=setup(tmp_path)
    db.add_memory('Prefiro uma interface sem botões.')
    d=doc(db)
    learn.record('Python',[d],[proposal(d)])
    after=Database(tmp_path/'aura.sqlite3')
    assert after.memories()[0]['content']=='Prefiro uma interface sem botões.'
    assert LearningEngine(Settings(data_dir=tmp_path),after).claims()[0]['source_count']==1


def test_advanced_command_and_enable_option(tmp_path):
    s=Settings(data_dir=tmp_path, database_encryption_required=False)
    db=Database(tmp_path/'aura.sqlite3')
    eng=AuraEngine(s,db)
    d=doc(db)
    async def search(topic):return ResearchOutcome(topic,[d])
    async def extract(documents):return [proposal(d)],''
    eng.research.learn=search
    eng.learning.propose=extract
    result=asyncio.run(eng.command('Aprende profundamente sobre Python'))
    assert result['action']=={'type':'open','panel':'research'}
    assert result['data']['claims'][0]['statement'].startswith('Python')
    asyncio.run(eng.command('Ativa aprendizagem avançada'))
    assert db.get_option('advanced_learning_enabled')=='true'
    assert asyncio.run(eng.command('Estado da aprendizagem'))['data']['learning']['runs']==1
    assert asyncio.run(eng.command('Desativa aprendizagem avançada'))['ok']
    assert db.get_option('advanced_learning_enabled')=='false'


def test_api_and_existing_interface_remain_compatible(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path,database_encryption_required=False))) as client:
        assert client.get('/api/learning/status').status_code==200
        assert client.get('/api/learning/claims').json()=={'items':[]}
        assert client.get('/api/health').json()['version'].startswith('3.3')
        assert client.post('/api/command',json={'message':'Abre a memória'}).json()['action']['panel']=='memory'
        assert b'sidebar' not in client.get('/').content.lower()


def test_faulty_model_keeps_sources_without_fabricating_knowledge(tmp_path):
    db,learn=setup(tmp_path)
    d=doc(db)
    async def unavailable(documents):return [],'Ollama não disponível.'
    learn.propose=unavailable
    res=asyncio.run(learn.learn_from('Python',[d]))
    assert res.documents==1 and res.stored==0
    assert res.warning
    assert learn.claims()==[]
    assert len(db.documents('Python'))==1


def test_unrelated_statement_cannot_use_real_quote_as_cover(tmp_path):
    db,learn=setup(tmp_path)
    d=doc(db)
    misleading={'document_id':d['id'],
                'statement':'As estrelas são feitas de pedaços de queijo verde.',
                'exact_quote':d['content']}
    res=learn.record('Python',[d],[misleading])
    assert res.rejected==1 and learn.claims()==[]
