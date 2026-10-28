"""Deterministic offline checks for Expecto 6.5 reasoning in normal chat."""
import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from aura.reasoning_runtime import (
    ReasoningRuntime, arithmetic_audit, exact_math_reply,
)
from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine
from aura.app import create_app


def test_exact_determinant_no_llm():
    r = exact_math_reply("Calcula o determinante de [[2,1],[3,4]]")
    assert r is not None
    assert r.calculation["result"]["actual"] == "5"
    assert "det(A) = 5" in r.text


def test_exact_inverse_and_singular_matrix():
    r = exact_math_reply("Calcula a inversa de [[1,2],[3,4]]")
    assert r is not None and "-2" in r.text
    singular = exact_math_reply("Calcula a inversa de [[1,2],[2,4]]")
    assert singular is not None and "não tem inversa" in singular.text


def test_exact_linear_system_and_inconsistent():
    r = exact_math_reply("Resolve 2x+y=5; x-y=1")
    assert r is not None and "x = 2" in r.text and "y = 1" in r.text
    bad = exact_math_reply("Resolve x+y=2; x+y=3")
    assert bad is not None and "não tem soluções" in bad.text


def test_unsupported_question_does_not_guess():
    assert exact_math_reply("Como resolver sistemas de equações?") is None
    assert exact_math_reply("Calcula o determinante de uma matriz arbitrária") is None
    assert exact_math_reply("Resolve x*y=2; y=3") is None


def test_arithmetic_audit_detects_error_and_correct_value():
    wrong = arithmetic_audit("Na conta, 125 + 75 = 201.")
    assert wrong["status"] == "incorrect_arithmetic"
    assert wrong["checks"][0]["computed_result"] == "200"
    right = arithmetic_audit("125 + 75 = 200")
    assert right["status"] == "arithmetic_checked"
    assert arithmetic_audit("Não há valores.")["status"] == "no_explicit_arithmetic"


def test_bad_calculation_not_released_without_correct_revision():
    async def test():
        runtime = ReasoningRuntime()
        calls = []
        async def model(prompt):
            calls.append(json.loads(prompt))
            if len(calls) == 1:
                return json.dumps({"needs_revision": False, "issues": []})
            return "125 + 75 = 201"
        outcome = await runtime.refine(
            "Calcula detalhadamente os valores", "125 + 75 = 201", model)
        assert outcome.status == "abstained_wrong_arithmetic"
        assert "201" not in outcome.answer
        assert len(calls) == 2
        assert runtime.status()["arithmetic_rejections"] == 1
    asyncio.run(test())


def test_good_revision_fixes_arithmetic():
    async def test():
        runtime = ReasoningRuntime()
        calls = []
        async def model(prompt):
            calls.append(json.loads(prompt))
            if len(calls) == 1:
                return json.dumps({"needs_revision": True, "issues": ["soma errada"]})
            assert "125 + 75 = 200" in calls[-1]["verified_arithmetic_corrections"]
            return "125 + 75 = 200"
        result = await runtime.refine("Calcula e explica", "125 + 75 = 201", model)
        assert result.status == "revised_model_only"
        assert result.answer == "125 + 75 = 200"
        assert result.model_calls == 2
    asyncio.run(test())


def test_review_failure_keeps_non_arithmetic_draft():
    async def test():
        runtime = ReasoningRuntime()
        async def broken(prompt):
            raise ValueError("model offline")
        result = await runtime.refine(
            "Explica o algoritmo de pesquisa", "Um algoritmo tem etapas.", broken)
        assert result.status == "reviewed_model_only"
        assert result.answer == "Um algoritmo tem etapas."
        assert "Crítica estruturada indisponível." in result.limitations
    asyncio.run(test())


def test_simple_question_skips_extra_model_call():
    async def test():
        runtime = ReasoningRuntime()
        async def broken(prompt):
            raise AssertionError("should not be called")
        result = await runtime.refine("Olá!", "Olá, tudo bem?", broken)
        assert result.status == "single_pass"
        assert result.model_calls == 0
    asyncio.run(test())


def test_engine_exact_algebra_is_in_chat_and_no_ollama(tmp_path):
    e = AuraEngine(Settings(data_dir=tmp_path, database_encryption_required=False),
                   Database(tmp_path / "v65.sqlite3"))
    assert e.chiplet_status()["active_count"] == 0
    response = asyncio.run(e.command("Calcula o determinante de [[2,1],[3,4]]"))
    assert response["data"]["reasoning"]["status"] == "exact_algebra"
    assert "det(A) = 5" in response["text"]
    assert "llm" not in e.chiplet_status()["active"]


def test_engine_complex_chat_calls_critic(tmp_path, monkeypatch):
    e = AuraEngine(Settings(data_dir=tmp_path, database_encryption_required=False),
                   Database(tmp_path / "v65.sqlite3"))
    counter = {"review": 0}
    async def draft(question, history=None):
        return "125 + 75 = 201"
    async def review(prompt):
        counter["review"] += 1
        if counter["review"] == 1:
            return json.dumps({"needs_revision": True, "issues": ["erro aritmético"]})
        return "125 + 75 = 200"
    monkeypatch.setattr(e.llm, "reply", draft)
    monkeypatch.setattr(e.llm, "review_text", review)
    response = asyncio.run(e.command("Calcula e demonstra a soma"))
    assert response["text"] == "125 + 75 = 200"
    assert counter["review"] == 2
    assert e.reasoning_runtime.status()["revisions"] == 1


def test_http_existing_chat_and_diagnostic_regression(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        result = client.post("/api/command",
                             json={"message":"Calcula o determinante de [[2,1],[3,4]]"})
        assert result.status_code == 200
        assert result.json()["data"]["reasoning"]["status"] == "exact_algebra"
        assert client.get("/api/chiplets").status_code == 200


@pytest.mark.parametrize("mode", ["unknown", "", "turbo"])
def test_invalid_review_mode_rejected(mode):
    with pytest.raises(ValueError):
        ReasoningRuntime(review_mode=mode)
