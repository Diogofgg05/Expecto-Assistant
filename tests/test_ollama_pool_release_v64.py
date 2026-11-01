"""Pooled transport and provider metrics regression without a live Ollama."""
import asyncio
import json
import httpx
from fastapi.testclient import TestClient
from aura.config import Settings
from aura.database import Database
from aura.llm import Ollama
from aura.app import create_app

def test_pooled_transport_reuse_and_close(tmp_path, monkeypatch):
    s=Settings(data_dir=tmp_path, database_encryption_required=False)
    db=Database(tmp_path/'pool.sqlite3')
    llm=Ollama(s,db)
    requests=[]
    real=httpx.AsyncClient
    def handler(request):
        requests.append(request.url.path)
        if request.url.path=='/api/tags':
            return httpx.Response(200,json={'models':[{'name':s.ollama_model}]})
        return httpx.Response(200,json={'message':{'content':'Um compilador converte código.'},
            'eval_count':20,'eval_duration':1000000000,'prompt_eval_count':30})
    clients=[]
    def factory(*a,**kw):
        client=real(*a,transport=httpx.MockTransport(handler),**{
            k:v for k,v in kw.items() if k!='transport'})
        clients.append(client)
        return client
    monkeypatch.setattr('aura.llm.httpx.AsyncClient',factory)
    async def run():
        await llm.health()
        a=await llm.reply('Define compilador')
        b=await llm.reply('Define compilador')
        assert a==b
        assert len(clients)==1
        stats=llm.metrics.summary()
        assert stats['latency_ms']['tokens_per_second']['median']==20
        await llm.aclose()
        assert clients[0].is_closed
    asyncio.run(run())
    assert requests==['/api/tags','/api/chat','/api/chat']

def test_api_version_and_lifecycle(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    with TestClient(app) as client:
        response=client.get('/api/health')
        assert response.status_code==200
        assert response.json()['version']=='6.5.0'


def test_embedding_http_client_closed_after_app_shutdown(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    class FakeAsyncClient:
        def __init__(self):
            self.is_closed=False
        async def aclose(self):
            self.is_closed=True
    client=FakeAsyncClient()
    app.state.engine.memory._client=client
    with TestClient(app):
        assert not client.is_closed
    assert client.is_closed
