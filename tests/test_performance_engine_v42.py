"""Performance Engine 4.2: deterministic, offline RAM pressure/admission tests."""
from __future__ import annotations

import asyncio
import io
import math
import sys
import httpx
import pytest

from aura.config import Settings
from aura.llm import Ollama
from aura.resource_budget import (
    HostMemory, AdaptiveMemoryBudget, pressure_bucket, read_host_memory,
)
from aura.app import create_app
from fastapi.testclient import TestClient


@pytest.mark.parametrize(("total", "available", "expected"), [
    (16384, 9000, "normal"),
    (8192, 900, "constrained"),
    (8192, 250, "critical"),
    (4096, 500, "critical"),
    (1024, 800, "constrained"),
    (1024, 950, "constrained"),
])
def test_pressure_thresholds(total, available, expected):
    assert pressure_bucket(HostMemory(total, available)) == expected


def test_unknown_and_invalid_readings_do_not_downscale():
    assert pressure_bucket(None) == "unknown"
    for total, available in ((0, 0), (128, -1), (128, 129)):
        with pytest.raises(ValueError):
            HostMemory(total, available)
    guard = AdaptiveMemoryBudget(sampler=lambda:None)
    options = {"num_ctx":3072, "num_batch":64, "num_predict":220}
    assert guard.tune_quick(options) == options
    assert guard.status()["last_pressure"] == "unknown"
    assert guard.status()["quick_requests_downscaled"] == 0


def test_critical_and_constrained_caps_keep_input_unchanged():
    options = {"num_ctx":3072, "num_batch":64, "num_predict":220, "temperature":0.2}
    for available, ctx, batch, predict in ((800,2048,32,160), (300,1536,16,112)):
        guard = AdaptiveMemoryBudget(sampler=lambda:HostMemory(8192, available))
        result = guard.tune_quick(options)
        assert result == {"num_ctx":ctx,"num_batch":batch,
                          "num_predict":predict,"temperature":0.2}
        assert options["num_ctx"]==3072
        assert guard.status()["quick_requests_downscaled"] == 1


def test_probes_are_ttl_bounded_and_status_never_probes():
    t = [0.0]
    count = [0]
    def sampler():
        count[0] += 1
        return HostMemory(8192, 250)
    guard = AdaptiveMemoryBudget(sampler=sampler, clock=lambda:t[0], ttl_seconds=10)
    assert guard.status()["probes"] == 0
    assert guard.bucket() == "critical"
    assert guard.bucket() == "critical"
    t[0] = 9.9
    assert guard.bucket() == "critical"
    assert count[0] == 1
    t[0] = 10.0
    assert guard.bucket() == "critical"
    assert count[0] == 2
    guard.status()
    assert count[0] == 2


def test_probe_exception_gracefully_keeps_original_options():
    def fail():
        raise OSError("no memory data")
    guard = AdaptiveMemoryBudget(sampler=fail)
    original = {"num_ctx":4096, "num_batch":128, "num_predict":450}
    assert guard.tune_quick(original) == original
    assert guard.status()["last_pressure"] == "unknown"


def test_disabled_guard_does_not_measure_host():
    def fail():
        raise AssertionError("Disabled guard must not sample")
    guard = AdaptiveMemoryBudget(enabled=False, sampler=fail)
    assert guard.tune_quick({"num_ctx":3072}) == {"num_ctx":3072}
    assert guard.bucket() == "disabled"
    assert guard.status()["probes"] == 0


def test_linux_host_probe(monkeypatch):
    import aura.resource_budget as resources
    monkeypatch.setattr(resources.sys, "platform", "linux")
    content = "MemTotal:        8388608 kB\nMemFree:           40 kB\nMemAvailable:    1048576 kB\n"
    def file_open(path, *args, **kwargs):
        assert path == "/proc/meminfo"
        return io.StringIO(content)
    monkeypatch.setattr("builtins.open",file_open)
    assert read_host_memory() == HostMemory(8192, 1024)


def test_no_change_to_balanced_or_personal_requests(tmp_path, monkeypatch):
    sent=[]
    async def fake_post(self,url,**kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(200,json={"message":{"content":"Resposta"}},
                              request=httpx.Request("POST",url))
    monkeypatch.setattr(httpx.AsyncClient,"post",fake_post)
    async def run():
        normal=Ollama(Settings(data_dir=tmp_path,database_encryption_required=False,
                        performance_profile="balanced",
                        performance_adaptive_memory=True),object(),object())
        async def context(question):
            return "conteúdo pessoal", "", ""
        normal._personal_context=context
        normal.resource_guard.sampler=lambda:HostMemory(8192,100)
        assert await normal.reply("O que é uma CPU?") == "Resposta"
        assert normal.resource_guard.status()["probes"] == 0
        assert "num_ctx" not in sent[-1]["options"]
        await normal.close()

        legacy=Ollama(Settings(data_dir=tmp_path,database_encryption_required=False,
                        performance_profile="legacy",
                        performance_adaptive_memory=True),object(),object())
        legacy._personal_context=context
        legacy.resource_guard.sampler=lambda:HostMemory(8192,100)
        assert await legacy.reply("O que é o meu projeto?") == "Resposta"
        assert legacy.resource_guard.status()["probes"] == 0
        # Even Legacy must preserve the primary model context limit when
        # the prompt requires personal memory or complex reasoning.
        assert "num_ctx" not in sent[-1]["options"]
        assert "num_batch" not in sent[-1]["options"]
        assert sent[-1]["options"]["num_predict"] == 450
        await legacy.close()
    asyncio.run(run())


def test_legacy_simple_question_adapts_without_collecting_private_text(tmp_path, monkeypatch):
    sent=[]
    async def fake_post(self,url,**kwargs):
        sent.append(kwargs["json"])
        return httpx.Response(200,json={"message":{"content":"Resposta"}},
                              request=httpx.Request("POST",url))
    monkeypatch.setattr(httpx.AsyncClient,"post",fake_post)
    llm=Ollama(Settings(data_dir=tmp_path,database_encryption_required=False,
                      performance_profile="legacy", performance_adaptive_memory=True),
               object(),object())
    llm.resource_guard.sampler=lambda:HostMemory(8192,300)
    async def run():
        assert await llm.reply("O que é uma CPU?") == "Resposta"
        assert sent[0]["options"]["num_ctx"] == 1536
        assert sent[0]["options"]["num_predict"] == 112
        assert llm.resource_guard.status()["probes"] == 1
        assert llm.resource_guard.status()["quick_requests_downscaled"] == 1
        assert "O que é uma CPU?" not in str(llm.resource_guard.status())
        await llm.close()
    asyncio.run(run())


def test_readonly_diagnostics_do_not_touch_memory_sampler(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False,
                            performance_profile="legacy",
                            performance_adaptive_memory=True))
    with TestClient(app) as client:
        obj=app.state.engine.llm.resource_guard
        obj.sampler=lambda: (_ for _ in ()).throw(AssertionError("No probe"))
        snap=client.get("/api/performance/status")
        assert snap.status_code == 200
        assert snap.json()["resource_guard"]["probes"] == 0
        assert snap.json()["resource_guard"]["enabled"] is True
        compute=client.get("/api/compute/status")
        assert compute.status_code == 200
        assert compute.json()["resource_guard"]["version"] == "4.2"


def test_profile_feature_flag_parsing(monkeypatch):
    monkeypatch.setenv("AURA_PERFORMANCE_PROFILE","legacy")
    monkeypatch.setenv("AURA_PERFORMANCE_ADAPTIVE_MEMORY","yes")
    assert Settings.from_env().performance_adaptive_memory is True
    monkeypatch.setenv("AURA_PERFORMANCE_ADAPTIVE_MEMORY","no")
    assert Settings.from_env().performance_adaptive_memory is False
