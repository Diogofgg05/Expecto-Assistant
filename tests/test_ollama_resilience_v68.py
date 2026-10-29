"""Failure containment for local Ollama, with no real network access."""
import asyncio
import pytest
import httpx
from aura.ollama_resilience import OllamaCircuitBreaker
from aura.config import Settings
from aura.database import Database
from aura.llm import Ollama

def test_breaker_opens_and_recovers():
    t=[1.]
    c=OllamaCircuitBreaker(threshold=2,cooldown_s=2,clock=lambda:t[0])
    assert c.allow()
    c.failure()
    assert c.allow()
    c.failure()
    assert not c.allow()
    assert c.status().status=="open"
    t[0]+=2.1
    assert c.allow()
    assert not c.allow()
    c.success()
    assert c.allow() and c.status().status=="closed"

def test_no_race_of_half_open_probes():
    t=[0.]
    c=OllamaCircuitBreaker(threshold=1,cooldown_s=1,clock=lambda:t[0])
    c.failure(); t[0]=2.
    assert c.allow()
    assert not c.allow()
    c.release_probe()
    assert c.allow()

def test_invalid_configuration():
    with pytest.raises(ValueError):
        OllamaCircuitBreaker(threshold=0)
    with pytest.raises(ValueError):
        OllamaCircuitBreaker(cooldown_s=0)

def test_error_does_not_hammer_backend(tmp_path,monkeypatch):
    llm=Ollama(Settings(data_dir=tmp_path,database_encryption_required=False),Database(tmp_path/"test.db"))
    llm._circuit=OllamaCircuitBreaker(threshold=1,cooldown_s=30.)
    calls=[0]
    async def failed(*args,**kwargs):
        calls[0]+=1
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(llm.memory,"recall",lambda *args,**kw: asyncio.sleep(0,result=[]))
    monkeypatch.setattr(llm.memory,"recall_episodes",lambda *args,**kw: asyncio.sleep(0,result=[]))
    # Stub only transport; all pre-inference lookups preserve their real behavior.
    monkeypatch.setattr(httpx.AsyncClient,"post",failed)
    async def run():
        first=await llm.reply("Qual é a velocidade da CPU?")
        second=await llm.reply("O que é uma GPU?")
        assert "Não consigo contactar" in first
        assert "temporariamente indisponível" in second
        assert calls[0]==1
        assert llm.compute_status()["ollama_resilience"]["status"]=="open"
    asyncio.run(run())
