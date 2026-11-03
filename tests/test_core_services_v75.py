"""EXPECTO 7.5 - dependency isolation, laziness and public engine compatibility."""
import ast
import asyncio
from pathlib import Path

import pytest

from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine
from aura.core.ports import ChatPort, MemoryPort, ResearchPort
from aura.core.services import CoreServices, DEFAULT_FACTORIES


class StubMemory:
    def __init__(self):
        self.closed = False

    async def recall(self, query, limit=8):
        return []

    async def recall_episodes(self, query, months, limit=5):
        return []

    def query_scope(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def scope():
            yield

        return scope()

    async def aclose(self):
        self.closed = True


class StubChat:
    def __init__(self, memory):
        self.memory = memory
        self.calls = 0
        self.closed = False

    async def reply(self, question, history=None, *, on_token=None):
        self.calls += 1
        if on_token is not None:
            await on_token("Resposta local de teste")
        return "Resposta local de teste"

    async def health(self):
        return {"available": True}

    async def aclose(self):
        self.closed = True


class StubResearch:
    def __init__(self):
        self.calls = 0

    async def learn(self, topic):
        from aura.research import ResearchOutcome
        self.calls += 1
        return ResearchOutcome(topic, [], "Sem fontes no teste")


def make_storage(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    db = Database(tmp_path / "services_v75.sqlite3", require_encryption=False)
    return settings, db


def test_default_service_graph_is_scoped_and_lazy(tmp_path):
    settings, db = make_storage(tmp_path)
    provider = CoreServices(settings, db)
    assert provider.initialized == frozenset()
    engine = AuraEngine(settings, db, services=provider)
    assert provider.initialized == frozenset({"memory", "llm"})
    assert engine.memory is provider.get("memory")
    assert engine.llm is provider.get("llm")
    assert engine.llm.memory is engine.memory
    assert engine.research is provider.get("research")
    assert engine.research is engine.research
    assert "extractor" not in provider.initialized
    assert "optimizer" not in provider.initialized


def test_injected_ports_run_without_ollama_or_network(tmp_path):
    settings, db = make_storage(tmp_path)
    created = []

    def build_memory(c):
        created.append("memory")
        return StubMemory()

    def build_chat(c):
        created.append("llm")
        return StubChat(c.get("memory"))

    def build_research(c):
        created.append("research")
        return StubResearch()

    provider = CoreServices(settings, db, factories={
        "memory": build_memory,
        "llm": build_chat,
        "research": build_research,
    })
    engine = AuraEngine(settings, db, services=provider)
    assert created == ["memory", "llm"]
    assert isinstance(engine.llm, ChatPort)
    assert isinstance(engine.memory, MemoryPort)
    assert engine.llm.memory is engine.memory

    greeting = asyncio.run(engine.command("Olá"))
    assert greeting["capture"] is True
    assert engine.llm.calls == 0
    answer = asyncio.run(engine.command("Explica os vetores"))
    assert answer["text"] == "Resposta local de teste"
    assert engine.llm.calls == 1
    assert "research" not in created
    research = asyncio.run(engine.command("Investiga sobre Python"))
    assert research["action"]["panel"] == "research"
    assert engine.research.calls == 1
    assert isinstance(engine.research, ResearchPort)
    assert created == ["memory", "llm", "research"]
    asyncio.run(engine.llm.aclose())
    asyncio.run(engine.memory.aclose())
    assert engine.llm.closed and engine.memory.closed


def test_unknown_or_circular_services_rejected(tmp_path):
    settings, db = make_storage(tmp_path)
    with pytest.raises(ValueError, match="desconhecidas"):
        CoreServices(settings, db, factories={"unsafe_model_tool": lambda c: object()})
    with pytest.raises(TypeError, match="chamável"):
        CoreServices(settings, db, factories={"research": None})

    circular = CoreServices(settings, db, factories={
        "research": lambda c: c.get("research")
    })
    with pytest.raises(RuntimeError, match="circular"):
        circular.get("research")
    assert circular.initialized == frozenset()


def test_engine_rejects_mixed_storage_dependencies(tmp_path):
    settings, db = make_storage(tmp_path)
    mismatched = CoreServices(Settings(data_dir=tmp_path, database_encryption_required=False), db)
    with pytest.raises(ValueError, match="mesmas definições"):
        AuraEngine(settings, db, services=mismatched)


def test_core_ports_have_no_framework_or_database_imports():
    folder = Path(__file__).resolve().parents[1] / "aura" / "core"
    ports = ast.parse((folder / "ports.py").read_text(encoding="utf-8"))
    assert all(not isinstance(n, (ast.Import, ast.ImportFrom)) or
               not any(s in ast.unparse(n) for s in (
                   "httpx", "fastapi", "sqlite3", "ollama", "research", "database"))
               for n in ast.walk(ports))
    services = ast.parse((folder / "services.py").read_text(encoding="utf-8"))
    # Provider adapters may import implementations only inside their builders.
    assert all(not isinstance(n, (ast.Import, ast.ImportFrom)) or
               not any(s in ast.unparse(n) for s in ("httpx", "fastapi"))
               for n in services.body)
    assert {"memory", "llm", "research", "secure_backups"} <= DEFAULT_FACTORIES.keys()
