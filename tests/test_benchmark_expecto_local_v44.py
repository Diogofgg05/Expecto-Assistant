"""Privacy, timing and comparison contracts for real local benchmark CLI."""
from __future__ import annotations

import json
import pytest

from scripts import benchmark_expecto_local_v44 as b


@pytest.mark.parametrize("host", [
    "http://192.168.1.1:8000", "https://127.0.0.1:8000",
    "http://localhost:8000/path", "http://localhost:8000?foo=bar",
    "http://someone:password@localhost:8000",
    "http://example.org:8000", "file:///tmp/data",
])
def test_benchmark_refuses_nonlocal_urls(host):
    with pytest.raises(ValueError):
        b.local_url(host)


def test_benchmark_accepts_explicit_loopback_port_only():
    assert b.local_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert b.local_url("http://localhost:8765/") == "http://localhost:8765"
    with pytest.raises(ValueError):
        b.local_url("http://127.0.0.1")


def test_sse_measures_from_request_start_and_never_returns_draft_text():
    lines = [
        "data: " + json.dumps({"type":"token","text":"Segredo fictício!"}),
        "data: " + json.dumps({"type":"final","payload":{
            "ok":True, "text":"Resposta fictícia"}}),
    ]
    clocks = iter((10.1, 10.3))
    result = b.parse_sse_lines(lines, started_at=10.0, now=lambda:next(clocks))
    assert result["first_token_ms"] == pytest.approx(100)
    assert result["final_ms"] == pytest.approx(300)
    assert result["draft_char_count"] == len("Segredo fictício!")
    assert "Segredo" not in str(result)
    assert "Resposta" not in str(result)


def test_sse_refuses_missing_final():
    with pytest.raises(RuntimeError, match="Missing verified final"):
        b.parse_sse_lines(['data: '+json.dumps({"type":"token","text":"texto"})],
                          started_at=0., now=lambda:1.)


def test_benchmark_refuses_recording_before_any_post(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return
        def json(self):
            return {"recording":True,"private_mode":False}
    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return
        def get(self, url):
            return FakeResponse()
        def stream(self, *args, **kwargs):
            raise AssertionError("Never send prompts while recording on")
    monkeypatch.setattr(b.httpx, "Client", FakeClient)
    with pytest.raises(RuntimeError, match="recording is enabled"):
        b.benchmark("http://127.0.0.1:8000","test",1,0)


def test_mocked_local_stream_records_only_timings_and_metadata(monkeypatch):
    class FakeResponse:
        headers={"content-type":"text/event-stream"}
        def __init__(self, kind):
            self.kind=kind
        def raise_for_status(self):
            return
        def json(self):
            if self.kind=="status":
                return {"recording":False,"private_mode":False}
            return {"policy":{"primary_model":"hermes3","profile":"balanced"},
                    "performance":{"profile":"balanced"}}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return
        def iter_lines(self):
            yield 'data: '+json.dumps({"type":"token","text":"Synthetic private text"})
            yield 'data: '+json.dumps({"type":"final","payload":{
                "ok":True,"text":"Do not save this answer"}})
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return
        def get(self, url):
            return FakeResponse("status" if url.endswith("/api/memory/status") else "compute")
        def stream(self, method, url, json):
            assert method=="POST" and url.endswith("/api/command/stream")
            assert json["history"] == []
            return FakeResponse("stream")
    monkeypatch.setattr(b.httpx,"Client",FakeClient)
    report=b.benchmark("http://127.0.0.1:8000","mock",2,0)
    assert report["model_draft_stream_confirmed"] is True
    assert report["cases"]["cpu"]["verified_final"]["samples"] == 2
    assert report["cases"]["matrices"]["first_token"]["samples"] == 2
    assert "Synthetic private text" not in str(report)
    assert "Do not save this answer" not in str(report)
    assert report["saved_private_text"] is False


def test_compare_checks_same_model_and_tasks(capsys):
    def report(model="model"):
        return {"schema":"expecto-real-local-v44", "model":model,
                "prompt_ids":["cpu"],
                "cases":{"cpu":{"verified_final":{"p50_ms":100.}}}}
    before=report()
    after=report()
    after["cases"]["cpu"]["verified_final"]["p50_ms"]=50.
    b.compare(before,after)
    assert "2.00x" in capsys.readouterr().out
    with pytest.raises(ValueError,match="model differs"):
        b.compare(before,report("different"))
