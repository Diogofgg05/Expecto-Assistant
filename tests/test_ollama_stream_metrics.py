"""Opt-in Ollama streamed JSON timing tests using an in-memory HTTP transport."""
import asyncio
import json
import httpx
import pytest
from aura.ollama_stream_metrics import collect_json_stream


def test_stream_collects_json_and_measures_first_content():
    def handler(request):
        events = [
            {"message": {"content": '{"answer":'},"done": False},
            {"message": {"content": '"ok"}'},"done": False},
            {"message": {"content": ""},"done": True},
        ]
        return httpx.Response(200, text="\n".join(json.dumps(e) for e in events)+"\n")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await collect_json_stream(client,"http://localhost:11434/api/chat",{"model":"test"})
    answer, metrics = asyncio.run(run())
    assert answer == {"answer":"ok"}
    assert metrics["ttft_ms"] is not None
    assert metrics["elapsed_ms"] >= metrics["ttft_ms"] >= 0


def test_stream_refuses_incomplete_json():
    def handler(request):
        return httpx.Response(200,text=json.dumps({"message":{"content":'{"x":'},"done":True})+"\n")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await collect_json_stream(client,"http://localhost:11434/api/chat",{"model":"test"})
    with pytest.raises(json.JSONDecodeError):
        asyncio.run(run())


def test_stream_requires_terminal_event():
    def handler(request):
        return httpx.Response(200,text=json.dumps({"message":{"content":'{}'},"done":False})+"\n")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await collect_json_stream(client,"http://localhost:11434/api/chat",{"model":"test"})
    with pytest.raises(ValueError,match="terminal"):
        asyncio.run(run())
