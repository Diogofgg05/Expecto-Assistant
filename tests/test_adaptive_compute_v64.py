"""Expecto 6.4 deterministic tests: no accelerator, real model or internet required."""
import asyncio
import pytest
from fastapi.testclient import TestClient
from aura.adaptive_compute import (
    AdaptiveCompute, ComputePolicy, ComputeBusyError, InferenceLimiter, classify_task,
)
from aura.app import create_app
from aura.config import Settings


def test_classification_preserves_quality_for_real_tasks():
    assert classify_task("Olá!") == "quick"
    assert classify_task("Bom dia") == "quick"
    assert classify_task("Explica a matriz inversa") == "complex"
    assert classify_task("Olá", history_len=3) == "complex"
    assert classify_task("O que devo fazer amanhã?") == "standard"


def test_fast_model_only_when_explicitly_installed():
    scheduler = AdaptiveCompute(ComputePolicy("hermes3", fast_model="qwen2.5:1.5b"))
    assert scheduler.plan("Olá").model == "hermes3"
    assert scheduler.plan("Olá", installed={}).model == "hermes3"
    quick = scheduler.plan("Olá", installed={"qwen2.5:1.5b": 400_000_000})
    assert quick.model == "qwen2.5:1.5b" and quick.options["num_predict"] == 160
    hard = scheduler.plan("Explica álgebra linear", installed={"qwen2.5:1.5b": 400_000_000})
    assert hard.model == "hermes3"
    assert hard.options["num_predict"] == 450


def test_budget_is_conservative_when_model_size_unknown():
    scheduler = AdaptiveCompute(ComputePolicy("hermes3", fast_model="small", memory_budget_mb=200))
    assert scheduler.plan("Olá", installed={"small": None}).model == "hermes3"
    assert scheduler.plan("Olá", installed={"small": 400_000_000}).model == "hermes3"
    assert scheduler.plan("Olá", installed={"small": 60_000_000}).model == "small"


def test_eco_cpu_offloads_by_policy_not_fake_hardware_detection():
    scheduler = AdaptiveCompute(ComputePolicy("hermes3", fast_model="small",
                                              profile="eco", gpu_mode="cpu"))
    plan = scheduler.plan("Olá", installed={"small": 40_000_000})
    assert plan.options["num_gpu"] == 0
    assert plan.keep_alive == "0s"
    status = scheduler.status()
    assert status["policy"]["actual_gpu_residency"] == "managed_by_ollama_not_measured"


def test_performance_profile_uses_primary():
    policy = ComputePolicy("hermes3", fast_model="small", profile="performance")
    assert AdaptiveCompute(policy).plan("Olá", installed={"small": 30_000_000}).model == "hermes3"


@pytest.mark.parametrize("kwargs", [
    {"primary_model": ""}, {"primary_model": "invalid model"},
    {"primary_model": "ok", "fast_model": "../ bad"},
    {"primary_model": "ok", "max_active": 0},
    {"primary_model": "ok", "max_waiting": -1},
    {"primary_model": "ok", "memory_budget_mb": -1},
    {"primary_model": "ok", "gpu_mode": "gpu-magic"},
    {"primary_model": "ok", "profile": "turbo"},
])
def test_invalid_policy_fail_closed(kwargs):
    with pytest.raises(ValueError):
        ComputePolicy(**kwargs)


def test_admission_control_blocks_overload():
    async def exercise():
        limiter = InferenceLimiter(1, 0, 1.0)
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow():
            entered.set()
            await release.wait()
            return "ok"
        task = asyncio.create_task(limiter.run(slow))
        await entered.wait()
        assert limiter.snapshot()["active"] == 1
        with pytest.raises(ComputeBusyError):
            await limiter.run(slow)
        assert limiter.snapshot()["rejected"] == 1
        release.set()
        assert await task == "ok"
        assert limiter.snapshot()["active"] == 0
    asyncio.run(exercise())


def test_timeout_cancels_waiter_and_releases_capacity():
    async def exercise():
        limiter = InferenceLimiter(1, 1, 0.05)
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow():
            entered.set()
            await release.wait()
        first = asyncio.create_task(limiter.run(slow))
        await entered.wait()
        with pytest.raises(ComputeBusyError):
            await limiter.run(slow)
        assert limiter.snapshot()["waiting"] == 0
        assert limiter.snapshot()["rejected"] == 1
        release.set()
        await first
        assert limiter.snapshot()["active"] == 0
    asyncio.run(exercise())


def test_cancelled_inference_releases_slot():
    async def exercise():
        limiter = InferenceLimiter(1, 1, 1)
        entered = asyncio.Event()
        async def block():
            entered.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(limiter.run(block))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert limiter.snapshot()["active"] == 0
        assert limiter.snapshot()["waiting"] == 0
        assert await limiter.run(lambda: asyncio.sleep(0, result=42)) == 42
    asyncio.run(exercise())


def test_compute_status_endpoint_no_network_or_private_messages(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False,
                              compute_fast_model="qwen2.5:1.5b"))
    with TestClient(app) as client:
        response = client.get("/api/compute/status")
        assert response.status_code == 200
        body = response.json()
        assert body["version"] == "6.4"
        assert body["queue"] == {"active":0,"waiting":0,"completed":0,"rejected":0,"failed":0}
        assert body["policy"]["primary_model"] == "hermes3"
        assert body["policy"]["fast_model_configured"] is True
        assert "prompts" not in response.text.lower()
        assert client.get("/api/chiplets").status_code == 200
