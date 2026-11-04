"""EXPECTO 7.9: offline regression of lab, DI and modular inference safeguards."""
import asyncio
import json

import httpx
import pytest

from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine
from aura.core.services import CoreServices
from aura.llm import Ollama
from aura.laboratory_cases import generate_cases


def test_exact_calculation_uses_no_model_and_keeps_scoped_services(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    db = Database(tmp_path / "combined.sqlite3", require_encryption=False)
    container = CoreServices(settings, db)
    engine = AuraEngine(settings, db, services=container)

    async def forbidden(*args, **kwargs):
        raise AssertionError("No model call for exact arithmetic")

    engine.llm.reply = forbidden
    result = asyncio.run(engine.command("calcula: 12 * (7 + 3)"))
    assert result["text"] == "120"
    assert result["data"]["verification"] == "exact_arithmetic"
    assert engine.memory is container.get("memory")


def test_structured_input_does_not_truncate_system_instructions(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    llm = Ollama(settings, Database(tmp_path / "bounded.sqlite3", require_encryption=False))
    original = httpx.AsyncClient
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload["messages"])
        return httpx.Response(200, json={"message": {"content": "ok"}, "done": True})

    monkeypatch.setattr("aura.llm.httpx.AsyncClient",
        lambda *a, **kw: original(
            *a, transport=httpx.MockTransport(handler),
            **{k: v for k, v in kw.items() if k != "transport"}))

    long_question = "x" * 2300
    assert asyncio.run(llm.reply(long_question, input_limit=2400)) == "ok"
    assert seen[0][-1]["content"] == long_question
    assert "Nunca afirmes" in seen[0][0]["content"]
    with pytest.raises(ValueError):
        asyncio.run(llm.reply(long_question, input_limit=2200))


def test_truncated_stream_is_not_a_completed_exchange(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    llm = Ollama(settings, Database(tmp_path / "stream.sqlite3", require_encryption=False))

    async def run():
        text = (
            '{"message":{"content":"draft"},"done":false}\n'
            '{"done":true,"done_reason":"length"}\n'
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda req: httpx.Response(200, text=text))) as client:
            llm._transport = lambda: client

            async def on_token(piece):
                assert piece == "draft"

            with pytest.raises(ValueError):
                await llm.reply("Define compilador", on_token=on_token)

    asyncio.run(run())
    assert llm.metrics.recent()[-1]["ok"] is False


def test_lab_holdouts_do_not_imply_live_model_success():
    cases = generate_cases(42, 4)
    assert len(cases) == 28
    assert {c.domain for c in cases} == {"math", "programming", "research"}
    assert all(c.grade(c.expected) for c in cases)
