import asyncio
import json
import httpx
import pytest
from aura.ollama_protocol import installed_models
from aura.config import Settings
from aura.database import Database
from aura.llm import Ollama


@pytest.mark.parametrize('payload',[None,[],{}, {'models':None},{'models':[None]},
    {'models':[{'name':[]} ]},{'models':[{'name':'x','digest':{}}]},
    {'models':[{'name':'x','digest':'a'},{'name':'x','digest':'b'}]}])
def test_malformed_discovery_is_rejected(payload):
    with pytest.raises(ValueError): installed_models(payload)


def test_empty_model_list_is_valid_but_missing_list_is_not():
    assert installed_models({'models':[]})=={}
    assert installed_models({'models':[{'name':'x:1','digest':'abc'}]})=={'x:1':'abc'}


@pytest.mark.parametrize('final',[{'done':True,'done_reason':'length'},{'done':'true'},{'done':1}])
def test_partial_stream_cannot_be_a_completed_answer(tmp_path,final):
    llm=Ollama(Settings(data_dir=tmp_path,database_encryption_required=False),Database(tmp_path/'db'))
    async def run():
        text=json.dumps({'message':{'content':'unfinished draft'}})+'\n'+json.dumps(final)+'\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,text=text))) as client:
            llm._transport=lambda:client
            async def token(piece): pass
            with pytest.raises(ValueError): await llm.reply('O que é Python?',on_token=token)
            assert not llm.metrics.recent()[-1]['ok']
    asyncio.run(run())


def test_bad_model_discovery_returns_controlled_command_result(tmp_path,monkeypatch):
    from aura.engine import AuraEngine
    engine=AuraEngine(Settings(data_dir=tmp_path,database_encryption_required=False),Database(tmp_path/'db'))
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'models':[None]})),**kw))
    result=asyncio.run(engine.command('resolve com verificação: explica Python'))
    assert 'indisponível' in result['text']
