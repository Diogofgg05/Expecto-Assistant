"""Performance 4.3: opt-in faster processing without bypassing arithmetic safety.

Simulated model calls only. No hardware speedup is implied by these tests.
"""
import asyncio
import json
import pytest
from aura.reasoning_runtime import ReasoningRuntime
from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine


def test_fast_mode_one_pass_for_complex_non_arithmetic():
    async def test():
        runtime = ReasoningRuntime(review_mode="fast")
        calls = []
        async def must_not_call(prompt):
            calls.append(prompt)
            raise AssertionError("Unnecessary model review")
        outcome = await runtime.refine(
            "Explica detalhadamente um algoritmo de pesquisa",
            "A pesquisa usa uma sequência de passos.",
            must_not_call,
        )
        assert outcome.status == "fast_single_pass"
        assert outcome.model_calls == 0
        assert calls == []
        assert runtime.status()["fast_skipped_reviews"] == 1
        assert outcome.limitations
    asyncio.run(test())


def test_fast_mode_still_repairs_wrong_arithmetic_without_critic_call():
    async def test():
        runtime = ReasoningRuntime(review_mode="fast")
        prompts = []
        async def model(prompt):
            data = json.loads(prompt)
            prompts.append(data)
            assert "verified_arithmetic_corrections" in data
            return "125 + 75 = 200"
        outcome = await runtime.refine(
            "Calcula detalhadamente 125 mais 75",
            "125 + 75 = 201",
            model,
        )
        assert outcome.status == "revised_model_only"
        assert outcome.answer == "125 + 75 = 200"
        assert outcome.model_calls == 1
        assert len(prompts) == 1
        assert runtime.status()["arithmetic_rejections"] == 1
    asyncio.run(test())


def test_fast_mode_does_not_release_wrong_math_when_repair_is_invalid():
    async def test():
        runtime = ReasoningRuntime(review_mode="fast")
        async def invalid(prompt):
            return "125 + 75 = 201"
        result = await runtime.refine("Calcula 125 + 75", "125 + 75 = 201", invalid)
        assert result.status == "abstained_wrong_arithmetic"
        assert "201" not in result.answer
    asyncio.run(test())


def test_fast_mode_refuses_unverifiable_arithmetic_without_proof():
    async def test():
        runtime = ReasoningRuntime(review_mode="fast")
        async def untrusted(prompt):
            return "A conta está certa."
        result = await runtime.refine("Calcula detalhadamente",
                                      "999999999999999999 + 2 = 3", untrusted)
        assert result.status != "fast_single_pass"
    asyncio.run(test())


def test_balanced_remains_unchanged_and_reviews_complex_prompts():
    async def test():
        runtime = ReasoningRuntime(review_mode="balanced")
        prompts = []
        async def critic(prompt):
            prompts.append(json.loads(prompt))
            return json.dumps({"needs_revision":False, "issues":[]})
        result = await runtime.refine(
            "Explica e demonstra a segurança do algoritmo",
            "A análise começa com uma hipótese.",
            critic,
        )
        assert result.status == "reviewed_model_only"
        assert result.model_calls == 1
        assert len(prompts) == 1
    asyncio.run(test())


def test_opt_in_only_configuration(tmp_path):
    settings = Settings(data_dir=tmp_path,database_encryption_required=False,
                        reasoning_review_mode="fast")
    engine = AuraEngine(settings, Database(tmp_path / "fast.sqlite3"))
    assert engine.reasoning_runtime.review_mode == "fast"
    assert Settings(data_dir=tmp_path).reasoning_review_mode == "balanced"


@pytest.mark.parametrize("mode", ["fast!", "", "quick", "turbo"])
def test_unknown_modes_rejected(mode):
    with pytest.raises(ValueError):
        ReasoningRuntime(review_mode=mode)
