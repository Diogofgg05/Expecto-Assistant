"""API v7.0.6: same method/path set and mounted static web UI after route split."""
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from aura.app import create_app, Message, VoiceText
from aura.config import Settings
from aura.api_contracts import validate_api_routes


EXPECTED = {
    "GET /api/health", "POST /api/command", "POST /api/command/stream",
    "GET /api/voice/capabilities", "POST /api/voice/transcribe",
    "POST /api/voice/synthesize", "GET /api/panel/{name}",
    "GET /api/memory/search", "GET /api/memory/conversations/search",
    "POST /api/memory/index-conversations", "POST /api/memory/extract-knowledge",
    "GET /api/memory/status", "GET /api/memory/temporal/current",
    "GET /api/memory/temporal/history", "GET /api/memory/temporal/as-of",
    "GET /api/memory/relations", "GET /api/memory/relations/search",
    "GET /api/memory/consolidation/status",
    "GET /api/memory/consolidation/summaries",
    "GET /api/memory/consolidation/review",
    "POST /api/memory/consolidation/run", "GET /api/optimizer/status",
    "GET /api/learning/status", "GET /api/learning/claims",
    "GET /api/epistemics/claims/{claim_id}", "GET /api/epistemics/audits",
    "GET /api/quality/claims/{claim_id}", "GET /api/factcheck/history",
    "GET /api/factcheck/claims/{claim_id}", "GET /api/quality/summary",
    "GET /api/resources/status", "GET /api/performance/status",
    "GET /api/config", "GET /",
}


def test_routes_keep_paths_and_models(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    seen = {f"{method} {route.path}" for route in app.routes if isinstance(route, APIRoute)
            for method in (route.methods or [])}
    assert seen == EXPECTED
    assert validate_api_routes(app)["duplicates"] == 0
    assert any(route.path == "/api/voice/continuous" for route in app.routes)
    assert Message(message="Olá").message == "Olá"
    assert VoiceText(text="Olá").text == "Olá"


def test_split_handlers_keep_output_and_security(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/api/health").json()["version"] == "7.0.6"
        assert client.get("/api/resources/status").status_code == 200
        assert client.get("/api/memory/status").status_code == 200
        assert client.get("/api/config").status_code == 200
        assert client.post("/api/command", json={"message":""}).status_code == 422
        assert client.post("/api/command", json={"message":"Abre a memória"}).json()["action"]["panel"] == "memory"
        assert client.post("/api/command", json={"message":"Abre a memória"},
                           headers={"Origin":"https://evil.example"}).status_code == 403
        assert client.get("/api/panel/other").status_code == 404
