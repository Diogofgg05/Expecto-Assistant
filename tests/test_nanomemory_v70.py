"""NanoMemory 7.0: deterministic resource profiles and Ollama integration."""
import asyncio
import json
import httpx
from fastapi.testclient import TestClient

from aura.nanomemory import MemorySnapshot, plan, NanoMemoryEngine, GIB
from aura.config import Settings
from aura.database import Database
from aura.llm import Ollama
from aura.app import create_app


def test_auto_low_memory_eco_and_stable_profiles():
    low = MemorySnapshot(8*GIB, 950_000_000, "test")
    p = plan("auto", "deep", low, "10m", 700)
    assert p.effective == "eco"
    assert p.keep_alive == "0m"
    assert p.num_ctx == 4096
    assert p.visual_fps == 12
    assert p.max_predict <= 700


def test_auto_max_and_user_override():
    plenty = MemorySnapshot(32*GIB, 15*GIB, "test")
    p = plan("auto", "deep", plenty, "10m", 700)
    assert p.effective == "max"
    assert p.num_ctx >= 16000
    assert p.visual_particles == 145
    manual = plan("balanced", "standard", plenty, "10m", 450)
    assert manual.effective == "balanced"
    assert manual.keep_alive == "2m"


def test_emergency_pressure_overrides_manual_max():
    snap = MemorySnapshot(32*GIB, 400_000_000, "test")
    result = plan("max", "standard", snap)
    assert result.effective == "eco"
    assert result.low_memory


def test_unknown_os_memory_safe_default():
    snap = MemorySnapshot(None, None, "unavailable")
    assert plan("auto", "standard", snap).effective == "balanced"
    assert plan("unsupported", "standard", snap).effective == "balanced"
    assert snap.public()["available_mib"] is None


def test_env_configuration(monkeypatch):
    monkeypatch.setenv("AURA_NANOMEMORY_MODE", "eco")
    assert Settings.from_env().nanomemory_mode == "eco"
    monkeypatch.setenv("AURA_NANOMEMORY_MODE", "bad")
    assert Settings.from_env().nanomemory_mode == "auto"


def test_ollama_chat_receives_memory_budgets(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        nanomemory_mode="eco", performance_mode="balanced")
    db = Database(tmp_path / "nanomemory.sqlite3")
    llm = Ollama(settings, db)
    requests = []
    client_class = httpx.AsyncClient

    def handler(request):
        if request.url.path != "/api/chat":
            return httpx.Response(404)
        data = json.loads(request.content)
        requests.append(data)
        return httpx.Response(200, json={"message":{"content":"É um programa local."}})
    monkeypatch.setattr("aura.llm.httpx.AsyncClient",
                        lambda *a, **k: client_class(*a, transport=httpx.MockTransport(handler),
                           **{name: value for name, value in k.items() if name != "transport"}))

    async def runner():
        output = await llm.reply("Define o que é um compilador.")
        await llm.aclose()
        return output
    assert asyncio.run(runner()) == "É um programa local."
    assert len(requests) == 1
    assert requests[0]["keep_alive"] == "0m"
    assert requests[0]["options"]["num_ctx"] == 2048  # FAST definition profile
    assert requests[0]["options"]["num_predict"] <= 450


def test_health_and_public_status(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        nanomemory_mode="balanced")
    app = create_app(settings)
    with TestClient(app) as client:
        data = client.get("/api/performance/status")
        assert data.status_code == 200
        policy = data.json()["nanomemory"]["policy"]
        assert policy["effective"] in ("eco", "balanced", "max")
        assert policy["visual_particles"] <= 145
        assert data.json()["nanomemory"]["vram"] == "not_measured"
        config = client.get("/api/config").json()
        assert config["nanomemory"]["policy"]["requested"] == "balanced"
        health = client.get("/api/health").json()
        assert health["version"] == "7.0.2"


def test_loaded_models_vram_from_ollama(tmp_path):
    settings=Settings(data_dir=tmp_path,database_encryption_required=False)
    db=Database(tmp_path/"vram.sqlite3")
    llm=Ollama(settings,db)
    def handler(request):
        if request.url.path=="/api/ps":
            return httpx.Response(200,json={"models":[
                {"name":"model-a","size_vram":268435456},
                {"name":"model-b","size_vram":134217728}
            ]})
        return httpx.Response(404)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            llm._transport=lambda:client
            return await llm.loaded_models()
    result=asyncio.run(run())
    assert result["available"] is True
    assert result["loaded_models"]==2
    assert result["loaded_vram_mib"]==384
