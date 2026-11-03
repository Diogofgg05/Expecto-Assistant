import asyncio
import pytest
from aura.response_resources import ResponseResources


def test_probe_failure_keeps_answer_available(monkeypatch):
    def inaccessible(): raise PermissionError('private diagnostic detail')
    monkeypatch.setattr('aura.response_resources.ram_sample', inaccessible)
    async def probe(): raise RuntimeError('private diagnostic detail')
    async def run():
        resources=ResponseResources(probe)
        await resources.sample()
        assert resources.public()['probe_errors']==2
        assert all(v is None for v in resources.public()['sampled_peak_bytes'].values())
        assert 'private' not in str(resources.public())
        async with resources:
            await asyncio.sleep(.01)
        assert resources.task.done()
    asyncio.run(run())


def test_bad_values_do_not_become_measurements(monkeypatch):
    monkeypatch.setattr('aura.response_resources.ram_sample', lambda: {'app_rss_bytes':float('nan'),'ollama_rss_bytes':-1})
    async def probe(): return {'available':True,'loaded_vram_mib':float('inf')}
    async def run():
        r=ResponseResources(probe)
        await r.sample()
        assert all(v is None for v in r.public()['sampled_peak_bytes'].values())
    asyncio.run(run())


def test_cancellation_is_not_swallowed(monkeypatch):
    monkeypatch.setattr('aura.response_resources.ram_sample', lambda: {})
    async def cancelled(): raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError): asyncio.run(ResponseResources(cancelled).sample())


def test_verified_commands_share_inference_limit(tmp_path, monkeypatch):
    import httpx
    import json
    from aura.config import Settings
    from aura.database import Database
    from aura.engine import AuraEngine
    engine=AuraEngine(Settings(data_dir=tmp_path,database_encryption_required=False,ollama_model='local:1'),Database(tmp_path/'db'))
    active=0
    maximum=0
    async def handler(request):
        nonlocal active, maximum
        if request.url.path=='/api/tags':
            return httpx.Response(200,json={'models':[{'name':'local:1'}]})
        active+=1
        maximum=max(maximum,active)
        try:
            await asyncio.sleep(.02)
            return httpx.Response(200,text=json.dumps({'message':{'content':'Proposta'},'done':True})+'\n')
        finally:
            active-=1
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    async def run():
        results=await asyncio.gather(*(engine.command('resolve com verificação: explica Python') for _ in range(3)))
        assert all(r['data']['status']=='unverified_proposal' for r in results)
        assert maximum==1
    asyncio.run(run())
