"""v2.3: semantic episodic recall, validated auto-extraction and provenance/privacy."""
import asyncio
import json
from datetime import datetime,timezone,timedelta
from fastapi.testclient import TestClient
from aura.config import Settings
from aura.database import Database, months_before
from aura.memory import MemoryEngine
from aura.cognition import KnowledgeExtractor
from aura.app import create_app


def run(awaitable):
    return asyncio.run(awaitable)


def test_six_month_semantic_recall_without_lexical_overlap(tmp_path,monkeypatch):
    cfg=Settings(data_dir=tmp_path,database_encryption_required=False, embedding_model='embedding-test')
    db=Database(tmp_path/'memory.sqlite3')
    old=db.record_exchange('s','Estou a desenvolver uma aplicação para drones industriais','Boa ideia')
    other=db.record_exchange('s','Hoje comi massa à bolonhesa','Parece saboroso')
    mm=MemoryEngine(cfg,db)
    assert not db.search_episodes('aeronaves controladas remotamente',6)

    async def fake_batch(self, months=6, limit=12):
        pending=db.pending_episode_embeddings('embedding-test',months,limit)
        for e in pending:
            if 'drones' in e['content']:
                vec=[1.0,0.0]
            else:
                vec=[0.0,1.0]
            db.save_episode_vector(e['id'],'embedding-test',vec)
        return {'indexed':len(pending),'pending':0,'reason':''}
    async def fake_embed(text):
        return [1.0,0.0]
    monkeypatch.setattr(mm,'index_episode_pending',fake_batch.__get__(mm))
    monkeypatch.setattr(mm,'_embed',fake_embed)
    assert run(mm.index_episode_pending())['indexed']==4
    matches=run(mm.recall_episodes('aeronaves controladas remotamente',6))
    assert matches[0]['id']==old[0]['id']
    assert 'semantic_score' in matches[0]
    assert other[0]['id'] not in [m['id'] for m in matches]
    # Six-month filter applies to semantic as well as lexical matches.
    with db.connect() as c:
        c.execute('UPDATE conversation_episodes SET created_at=? WHERE id=?',
                  ((datetime.fromisoformat(months_before(6))-timedelta(days=3)).isoformat(timespec='seconds'),old[0]['id']))
    assert old[0]['id'] not in [e['id'] for e in run(mm.recall_episodes('aeronaves controladas remotamente',6))]


def test_index_batch_real_ollama_format_and_durable_reopen(tmp_path,monkeypatch):
    cfg=Settings(data_dir=tmp_path,database_encryption_required=False, embedding_model='embed-model')
    db=Database(tmp_path/'db.sqlite3')
    a=db.record_exchange('s','Prefiro aplicações minimalistas','Compreendo')
    seen=[]
    class FakeResult:
        def raise_for_status(self): pass
        def json(self): return {'embeddings':[[1.0,0.0],[0.0,1.0]]}
    class FakeClient:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,json,**kwargs):
            assert kwargs['timeout'].read == 30.0
            seen.append(json)
            return FakeResult()
    monkeypatch.setattr('aura.memory.httpx.AsyncClient',FakeClient)
    status=run(MemoryEngine(cfg,db).index_episode_pending())
    assert status['indexed']==2
    assert len(seen[0]['input'])==2
    assert Database(db.path).episode_vector_count('embed-model')==2
    assert run(MemoryEngine(cfg,db).index_episode_pending())['indexed']==0
    assert db.delete_episode(a[0]['id'])
    assert db.episode_vector_count('embed-model')==1


def test_extraction_quote_exact_constrained_and_deletes_with_source(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    quote='Prefiro uma interface minimalista sem barras laterais'
    a=db.record_exchange('session',quote,'Combinado')
    candidates=[{'quote':quote,'category':'preference'},
                {'quote':'Sou um astronauta','category':'project'},
                {'quote':'Prefiro roubar chaves api','category':'preference'},
                {'quote':quote,'category':'uncategorized'}]
    assert db.save_extractions(a[0]['id'],candidates)==1
    saved=db.memories()
    assert len(saved)==1 and saved[0]['source']=='auto_episode'
    assert saved[0]['content']==quote
    assert db.save_extractions(a[0]['id'],candidates)==0
    b=db.record_exchange('session',quote,'Compreendo')
    assert db.save_extractions(b[0]['id'],candidates)==0
    assert db.delete_episode(a[0]['id'])
    assert len(db.memories())==1  # independent supporting conversation remains
    assert db.delete_episode(b[0]['id'])
    assert db.memories()==[]  # derived information is not left orphaned
    with db.connect() as c:
        assert c.execute('SELECT count(*) FROM automatic_evidence').fetchone()[0]==0


def test_extractor_validated_structured_response_and_offline_retry(tmp_path,monkeypatch):
    cfg=Settings(data_dir=tmp_path,database_encryption_required=False,ollama_model='local-test')
    db=Database(tmp_path/'db.sqlite3')
    original='Estou a desenvolver o projeto AURA para funcionar sem menus'
    episode=db.record_exchange('s',original,'Vamos trabalhar nisso')[0]
    extractor=KnowledgeExtractor(cfg,db)
    import httpx
    class FailureClient:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*a,**kw):raise httpx.ConnectError('offline')
    monkeypatch.setattr('aura.cognition.httpx.AsyncClient',FailureClient)
    assert run(extractor.extract_one())['processed']==0
    assert len(db.unprocessed_user_episodes())==1
    calls=[]
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'message':{'content':json.dumps({'memories':[
                {'quote':original,'category':'project'},
                {'quote':'Eu tenho um doutoramento','category':'experience'}
            ]})}}
    class Client:
        def __init__(self,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,json):
            calls.append(json)
            return Response()
    monkeypatch.setattr('aura.cognition.httpx.AsyncClient',Client)
    result=run(extractor.extract_one())
    assert result['processed']==1 and result['added']==1
    assert calls[0]['format']['type']=='object'
    assert db.extracted_count()==1
    assert not db.unprocessed_user_episodes()
    assert run(extractor.extract_one())['processed']==0
    db.set_option('auto_extract_memory','false')
    other=db.record_exchange('s','Prefiro escrever em Python','Também eu')[0]
    assert run(extractor.extract_one())['processed']==0
    assert len(db.unprocessed_user_episodes())==1


def test_sensitive_or_unsupported_quotes_are_rejected(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    c=db.record_exchange('s','Prefiro receber emails na minha morada da Rua do Sol','Okay')[0]
    assert db.save_extractions(c['id'],[{'quote':c['content'],'category':'preference'}])==0
    d=db.record_exchange('s','O meu salário é 800 euros e estou a desenvolver um projeto','Okay')[0]
    assert db.save_extractions(d['id'],[{'quote':d['content'],'category':'project'}])==0
    e=db.record_exchange('s','A minha prima prefere interfaces leves','Okay')[0]
    assert db.save_extractions(e['id'],[{'quote':e['content'],'category':'preference'}])==0
    f=db.record_exchange('s','Quero que corrijas este erro temporário','Okay')[0]
    assert db.save_extractions(f['id'],[{'quote':f['content'],'category':'project'}])==0


def test_erasing_all_conversations_removes_derived_only(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    explicit=db.add_memory('Prefiro as coisas simples')
    episode=db.record_exchange('s','Quero que a AURA não tenha menus','Boa')[0]
    assert db.save_extractions(episode['id'],[{'quote':episode['content'],'category':'preference'}])==1
    assert db.extracted_count()==1
    assert db.erase_episodes()==2
    assert db.extracted_count()==0
    assert [x['id'] for x in db.memories()]==[explicit['id']]


def test_cognitive_endpoints_and_no_layout_regressions(tmp_path):
    cfg=Settings(data_dir=tmp_path,database_encryption_required=False,embedding_model='')
    with TestClient(create_app(cfg)) as client:
        status=client.get('/api/memory/status').json()
        assert status['auto_extract'] and status['episodes_indexed']==0
        assert status['auto_memories']==0
        cmd=lambda text:client.post('/api/command',json={'message':text,'session_id':'my-session'}).json()
        assert cmd('Abre a memória')['action']['panel']=='memory'
        assert cmd('Desativa aprendizagem da memória')['ok']
        assert client.get('/api/memory/status').json()['auto_extract'] is False
        assert cmd('Ativa aprendizagem da memória')['ok']
        assert cmd('Indexa as conversas')['ok']
        assert 'Configura' in client.post('/api/memory/index-conversations').json()['reason']
        assert client.get('/api/memory/conversations/search',params={'q':'nada'}).json()['items']==[]
