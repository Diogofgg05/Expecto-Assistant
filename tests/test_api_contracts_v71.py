"""API contracts: detect route collisions before runtime and guard compatibility."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura.api_contracts import validate_api_routes
from aura.app import create_app
from aura.config import Settings


def test_routes_are_unique_and_openapi_describes_resources(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    report=validate_api_routes(app)
    assert report["duplicates"]==0
    assert report["routes_checked"]>=25
    schema=app.openapi()
    assert "/api/memory/status" in schema["paths"]
    assert "/api/resources/status" in schema["paths"]
    assert "/api/performance/status" in schema["paths"]
    assert schema["paths"]["/api/memory/status"]["get"]["operationId"] != (
        schema["paths"]["/api/resources/status"]["get"]["operationId"]
    )


def test_http_duplicate_rejected_before_service_begins():
    app=FastAPI()
    @app.get("/dup")
    async def first():
        return {"handler":1}
    @app.get("/dup")
    async def second():
        return {"handler":2}
    with pytest.raises(RuntimeError,match="GET /dup"):
        validate_api_routes(app)


def test_websocket_duplicate_rejected():
    app=FastAPI()
    @app.websocket("/ws")
    async def first(socket):
        pass
    @app.websocket("/ws")
    async def second(socket):
        pass
    with pytest.raises(RuntimeError,match="WEBSOCKET /ws"):
        validate_api_routes(app)


def test_memory_status_preserved_and_resources_separate(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    with TestClient(app) as client:
        memory=client.get("/api/memory/status")
        hardware=client.get("/api/resources/status")
        perf=client.get("/api/performance/status")
        assert memory.status_code==200
        assert memory.json()["no_automatic_deletion"] is True
        assert "lookback_months" in memory.json()
        assert "memory" not in memory.json()
        assert hardware.status_code==200
        assert "memory" in hardware.json()
        assert "policy" in hardware.json()
        assert "ollama" in hardware.json()
        assert "lookback_months" not in hardware.json()
        assert perf.status_code==200
        assert "metrics" in perf.json()


def test_api_rejects_invalid_request_and_cross_origin(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    with TestClient(app) as client:
        assert client.post("/api/command",json={"message":""}).status_code==422
        assert client.post("/api/command",json={"message":"x"*2001}).status_code==422
        assert client.post("/api/command",json={"message":"olá","history":[{}]*9}).status_code==422
        result=client.post("/api/command",json={"message":"olá"},
                           headers={"Origin":"https://attacker.example"})
        assert result.status_code==403
        assert client.get("/api/command").status_code==405
        assert client.get("/api/panel/invalid").status_code==404
        assert client.get("/api/health").status_code==200


def test_existing_reflection_and_research_handlers_still_route(tmp_path):
    import asyncio
    from aura.engine import AuraEngine
    from aura.database import Database
    from aura.research import ResearchOutcome
    engine=AuraEngine(
        Settings(data_dir=tmp_path,database_encryption_required=False),
        Database(tmp_path/"router.sqlite3")
    )
    async def fake_research(topic):
        return ResearchOutcome(topic,[{"title":"Fonte","content":"Conteúdo de teste",
                                      "url":"https://example.org","topic":topic,
                                      "source_type":"wikipedia","evidence_level":"single_source",
                                      "learned_at":"2026-01-01"}])
    engine.research.learn=fake_research
    async def run():
        reflection=await engine.command("Mostra o feedback")
        goals=await engine.command("Meus objetivos")
        research=await engine.command("Investiga sobre Python")
        return reflection,goals,research
    reflection,goals,research=asyncio.run(run())
    assert "feedback" in reflection["data"]
    assert "goals" in goals["data"]
    assert research["action"]["panel"]=="research"
    assert research["data"]["topic"]=="Python"
