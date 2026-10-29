"""Performance Engine 4.1 regressions: shared embeddings and on-demand local pool."""
import asyncio
import httpx
import pytest

from aura.config import Settings
from aura.database import Database
from aura.http_pool import LocalInferencePool
from aura.llm import Ollama
from aura.memory import MemoryEngine


def test_shared_query_embedding_single_call_and_same_results(tmp_path):
    db = Database(tmp_path / "memory.sqlite3")
    note = db.add_memory("Prefiro uma interface holográfica", importance=5)
    msgs = db.record_exchange("a", "Quero melhorar o holograma do Expecto",
                              "Vamos melhorar o holograma")
    db.set_vector(note["id"], "emb-test", [1.0, 0.0])
    db.save_episode_vector(msgs[0]["id"], "emb-test", [1.0, 0.0])
    mem = MemoryEngine(Settings(data_dir=tmp_path,embedding_model="emb-test"), db)
    calls = []

    async def fake_embed(question):
        calls.append(question)
        return [1.0, 0.0]

    mem._embed = fake_embed
    async def run():
        notes, episodes = await mem.recall_pair("holograma", months=6)
        assert any(x["id"] == note["id"] for x in notes)
        assert any(x["id"] == msgs[0]["id"] for x in episodes)
        assert len(calls) == 1
        # Direct API methods remain backward compatible.
        await mem.recall("holograma")
        await mem.recall_episodes("holograma")
        assert len(calls) == 3
    asyncio.run(run())


def test_embedding_failure_falls_back_once_to_lexical(tmp_path):
    db = Database(tmp_path/"mem.sqlite3")
    note = db.add_memory("Processador antigo",importance=5)
    mem = MemoryEngine(Settings(data_dir=tmp_path,embedding_model="emb-test"), db)
    counter = [0]
    async def failed(text):
        counter[0] += 1
        return None
    mem._embed = failed
    async def run():
        notes, episodes = await mem.recall_pair("Processador antigo")
        assert note["id"] in [x["id"] for x in notes]
        assert episodes == []
        assert counter[0] == 1
    asyncio.run(run())


def test_pooled_client_created_once_and_closed(monkeypatch):
    made=[]
    class Fake:
        is_closed=False
        def __init__(self, **kwargs):
            self.kwargs=kwargs
            made.append(self)
        async def aclose(self):
            self.is_closed=True
    monkeypatch.setattr("aura.http_pool.httpx.AsyncClient",Fake)
    pool=LocalInferencePool(max_connections=2)
    async def run():
        one=await pool.client()
        two=await pool.client()
        assert one is two
        assert pool.status()["active"] is True
        assert one.kwargs["limits"].max_connections == 2
        assert one.kwargs["trust_env"] is False
        await pool.aclose()
        assert pool.status()["active"] is False
        assert one.is_closed
        three=await pool.client()
        assert three is not one
        await pool.aclose()
    asyncio.run(run())
    assert len(made)==2
    assert all(x.is_closed for x in made)


def test_invalid_pool_config_rejected():
    for val in (0, -1, 9):
        with pytest.raises(ValueError):
            LocalInferencePool(max_connections=val)


def test_two_legacy_replies_share_http_pool_and_shutdown(tmp_path,monkeypatch):
    calls=[]
    clients=[]
    class FakeClient:
        is_closed=False
        def __init__(self, **kwargs):
            clients.append(self)
        async def post(self,url,**kwargs):
            calls.append(kwargs["json"])
            return httpx.Response(200,json={"message":{"content":"Resposta"}},
                                  request=httpx.Request("POST",url))
        async def aclose(self):
            self.is_closed=True
    monkeypatch.setattr("aura.http_pool.httpx.AsyncClient",FakeClient)
    llm=Ollama(Settings(data_dir=tmp_path, database_encryption_required=False,
                        performance_profile="legacy"), object(), object())
    async def run():
        assert await llm.reply("O que é uma CPU?")=="Resposta"
        assert await llm.reply("Define transístor.")=="Resposta"
        assert len(clients)==1
        assert len(calls)==2
        assert llm.compute_status()["ollama_http_pool"]["active"] is True
        await llm.close()
        assert clients[0].is_closed
    asyncio.run(run())


def test_contextual_question_uses_combined_retrieval(tmp_path,monkeypatch):
    llm=Ollama(Settings(data_dir=tmp_path,database_encryption_required=False),
               object(), object())
    class Memory:
        model="emb-test"
        async def recall_pair(self, question, **kwargs):
            assert question == "O que é o meu projeto?"
            assert kwargs["notes_limit"]==8
            return [],[]
        async def recall(self,*args,**kwargs):
            raise AssertionError("Should use combined retrieval")
        async def recall_episodes(self,*args,**kwargs):
            raise AssertionError("Should use combined retrieval")
    llm.memory=Memory()
    class DB:
        def documents(self,**kwargs):return []
        def temporal_current(self,**kwargs):return []
    llm.db=DB()
    # The personal-context builder also reads local learning and relation DB
    # tables; exercise the pair selection with a minimal, functional DB.
    from aura.database import Database
    llm.db=Database(tmp_path/"context.sqlite3")
    class FakeVerifier:
        def __init__(self,*args):pass
    # Use empty DB and no external requests; existing modules read only.
    async def fake_reply(self,url,**kwargs):
        return httpx.Response(200,json={"message":{"content":"Sim"}},
                              request=httpx.Request("POST",url))
    monkeypatch.setattr(httpx.AsyncClient,"post",fake_reply)
    assert asyncio.run(llm.reply("O que é o meu projeto?"))=="Sim"
