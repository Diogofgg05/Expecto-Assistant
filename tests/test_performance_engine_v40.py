"""Performance Engine 4.0 -- offline, deterministic and privacy-preserving."""
import asyncio
import httpx
from fastapi.testclient import TestClient
from aura.config import Settings
from aura.performance_engine import PerformanceEngine, Route
from aura.llm import Ollama
from aura.app import create_app


def test_balanced_always_uses_full_context():
    p = PerformanceEngine()
    assert p.route("O que é uma CPU?").use_context
    assert p.route("O que é uma CPU?", []).use_context


def test_legacy_only_skips_obvious_context_free_definitions():
    p = PerformanceEngine("legacy")
    for prompt in (
        "O que é uma CPU?", "Define computação quântica.",
        "Explica o conceito de algoritmo",
        "Qual é a definição de sistema operativo?",
    ):
        result = p.route(prompt)
        assert result.use_context is False, prompt
    for prompt in (
        "O que é o meu projeto?", "O que é a última versão?",
        "O que é uma GPU hoje?", "O que é a Expecto?",
        "O que é a minha memória?", "Explica o que falámos ontem",
        "O que é uma CPU e como escolher para mim?",
        "Apaga a minha memória", "O que é Python? E o meu projeto?",
        "Como estás?", "O que disseste anteriormente?",
    ):
        assert p.route(prompt).use_context is True, prompt
    assert p.route("O que é uma CPU?", [{"role":"user","content":"contexto"}]).use_context


def test_bounded_private_metrics():
    p = PerformanceEngine("legacy", samples=16)
    for i in range(50):
        p.record(route=Route(False, "general_definition"), prepare_ms=i,
                 total_ms=i + 10, first_token_ms=i+2, error=(i == 2))
    s = p.status()
    assert s["requests"] == 50
    assert s["errors"] == 1
    assert s["context_skips"] == 50
    assert s["sample_count"] == 16
    assert s["first_visible_token"]["p50_ms"] is not None
    assert s["request_total"]["p95_ms"] >= s["request_total"]["p50_ms"]
    assert not any(x in s for x in ("prompts", "messages", "history", "questions", "tokens"))
    assert s["private_text_stored"] is False


def test_bad_metrics_ignored():
    p = PerformanceEngine("legacy")
    p.record(route=Route(True, "full_context"), prepare_ms=float("nan"),
             total_ms=100, first_token_ms=None)
    assert p.status()["requests"] == 0


def test_legacy_skips_private_db_calls_for_generic_question(tmp_path, monkeypatch):
    class DenyMemory:
        async def recall(self, *args, **kwargs):
            raise AssertionError("private recall called for generic definition")
        async def recall_episodes(self, *args, **kwargs):
            raise AssertionError("episode recall called for generic definition")

    llm = Ollama(Settings(data_dir=tmp_path, database_encryption_required=False,
                          performance_profile="legacy"), object(), DenyMemory())
    observed = []

    async def post(self, url, **kwargs):
        observed.append(kwargs["json"])
        return httpx.Response(200, json={"message":{"content":"Definição local."}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    result = asyncio.run(llm.reply("O que é uma CPU?"))
    assert result == "Definição local."
    assert "Memórias do utilizador" not in observed[0]["messages"][0]["content"]
    assert observed[0]["options"]["num_ctx"] == 3072
    assert observed[0]["options"]["num_batch"] == 64
    assert observed[0]["options"]["num_predict"] == 220
    assert llm.compute_status()["performance"]["context_skips"] == 1


def test_contextual_question_preserves_context(tmp_path, monkeypatch):
    llm = Ollama(Settings(data_dir=tmp_path, database_encryption_required=False,
                          performance_profile="legacy"), object(), object())
    checked = []
    async def context(question):
        checked.append(question)
        return "MEMÓRIA RELEVANTE", "CONTINUIDADE", "REFLEXÃO"
    llm._personal_context = context

    async def post(self, url, **kwargs):
        assert "MEMÓRIA RELEVANTE" in kwargs["json"]["messages"][0]["content"]
        return httpx.Response(200, json={"message":{"content":"Resposta."}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    assert asyncio.run(llm.reply("O que é o meu projeto?")) == "Resposta."
    assert checked == ["O que é o meu projeto?"]
    assert llm.performance.status()["context_skips"] == 0


def test_model_listing_cached_only_after_success(tmp_path, monkeypatch):
    llm = Ollama(Settings(data_dir=tmp_path, database_encryption_required=False,
                          compute_fast_model="modelo:small"), object(), object())
    count = [0]

    async def get(self, url):
        count[0] += 1
        return httpx.Response(200, json={"models":[{"name":"modelo:small","size":12345}]},
                              request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", get)

    async def run():
        a = await llm._installed_models()
        a["modelo:small"] = 999
        b = await llm._installed_models()
        assert b["modelo:small"] == 12345
        assert count[0] == 1
    asyncio.run(run())


def test_first_token_metric_streaming_without_persisting_text(tmp_path):
    llm = Ollama(Settings(data_dir=tmp_path,database_encryption_required=False,
                          performance_profile="legacy"), object(), object())
    delivered = []
    async def fake_impl(question, history, *, route, mark_prepared, on_token):
        mark_prepared()
        await on_token("Segredo privado que não deve aparecer nas métricas")
        return "Resposta"
    llm._reply_impl = fake_impl
    async def run():
        result = await llm.reply("O que é uma CPU?", on_token=lambda token: on_token(token))
        return result
    async def on_token(token):
        delivered.append(token)
    assert asyncio.run(run()) == "Resposta"
    assert len(delivered) == 1
    status = llm.performance.status()
    assert status["first_visible_token"]["p50_ms"] is not None
    assert "Segredo privado" not in str(status)


def test_read_only_performance_endpoint(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False,
                              performance_profile="legacy"))
    with TestClient(app) as client:
        response=client.get("/api/performance/status")
        assert response.status_code==200
        body=response.json()
        assert body["version"]=="4.0"
        assert body["requests"]==0
        assert body["profile"]=="legacy"
        assert client.get("/api/compute/status").json()["performance"]["version"]=="4.0"
