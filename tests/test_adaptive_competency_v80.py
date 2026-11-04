"""EXPECTO 8.0: offline adaptive practice, privacy and independent grading."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest

from aura.competency import (
    CompetencyEngine, DOMAINS, MAX_AGE, generate, normalized_answer, utcnow,
)
from aura.config import Settings
from aura.core.services import CoreServices
from aura.database import Database
from aura.engine import AuraEngine


def store(tmp_path):
    return Database(tmp_path / "practice.sqlite3", require_encryption=False)


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("level", (1, 2, 3))
def test_deterministic_oracles_and_bounded_inputs(domain, level):
    q, answer, explanation = generate(domain, level, seed=42)
    assert (q, answer, explanation) == generate(domain, level, seed=42)
    assert len(q) < 500
    assert len(explanation) < 500
    assert normalized_answer(answer) == answer
    assert "eval(" not in explanation and "exec(" not in explanation


@pytest.mark.parametrize("invalid", ("1+2", "print(2)", "__import__('os')",
                                        "1; rm -rf /", "", "99999999999999999"))
def test_user_answer_is_strictly_numeric(invalid):
    with pytest.raises(ValueError):
        normalized_answer(invalid)


def test_private_solution_stays_hidden_until_answer(tmp_path):
    engine = CompetencyEngine(store(tmp_path))
    first = engine.next("matematica", seed=12)
    assert first["status"] == "pending"
    assert "solution" not in first and "explanation" not in first
    assert engine.next("matematica", seed=99)["id"] == first["id"]
    db = engine.db
    with db.connect() as conn:
        expected = conn.execute("SELECT solution FROM expecto_practice WHERE id=?",
                                (first["id"],)).fetchone()["solution"]
    completed = engine.submit(first["id"], expected)
    assert completed["correct"]
    assert completed["solution"] == expected
    assert engine.report()["domains"][0]["answered"] == 1
    assert not engine.report()["automatic_model_training"]
    with pytest.raises(ValueError, match="encerrado"):
        engine.submit(first["id"], expected)


def test_skip_and_switch_domain_never_count_as_errors(tmp_path):
    engine = CompetencyEngine(store(tmp_path))
    a = engine.next("matematica", seed=21)
    b = engine.next("fisica", seed=21)
    assert a["id"] != b["id"]
    assert engine.report()["domains"][0]["answered"] == 0
    assert engine.skip() is True
    assert engine.skip() is False
    assert engine.report()["domains"][2]["answered"] == 0
    with pytest.raises(ValueError, match="encerrado"):
        engine.submit(a["id"], "0")


def test_expired_challenge_is_persisted_as_skipped(tmp_path):
    engine = CompetencyEngine(store(tmp_path))
    challenge = engine.next("programacao", seed=2)
    expired = (utcnow() - MAX_AGE - timedelta(seconds=5)).isoformat()
    with engine.db.connect() as conn:
        conn.execute("UPDATE expecto_practice SET created_at=? WHERE id=?",
                     (expired, challenge["id"]))
    with pytest.raises(ValueError, match="expirou"):
        engine.submit(challenge["id"], "0")
    with engine.db.connect() as conn:
        row = conn.execute("SELECT status FROM expecto_practice WHERE id=?",
                           (challenge["id"],)).fetchone()
    assert row["status"] == "skipped"
    assert engine.next("programacao", seed=4)["id"] != challenge["id"]


def test_adaptation_probes_all_domains_then_selects_weakest(tmp_path):
    engine = CompetencyEngine(store(tmp_path))
    # Three independent observations in every subject.
    for domain, correct_results in [
        ("matematica", [True, True, True]),
        ("programacao", [False, False, False]),
        ("fisica", [True, False, True]),
    ]:
        for i, should_pass in enumerate(correct_results):
            question = engine.next(domain, seed=i+11)
            with engine.db.connect() as conn:
                expected = conn.execute("SELECT solution FROM expecto_practice WHERE id=?",
                                        (question["id"],)).fetchone()["solution"]
            wrong = str(int(expected.split(",")[0]) + 900) if "," not in expected else "900,900"
            outcome = engine.submit(question["id"], expected if should_pass else wrong)
            assert outcome["correct"] is should_pass
    report = engine.report()
    assert report["suggested_domain"] == "programacao"
    assert [r["answered"] for r in report["domains"]] == [3, 3, 3]
    assert engine.next(seed=99)["domain"] == "programacao"


def test_commands_are_scoped_and_do_not_trigger_local_model(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    db = store(tmp_path)
    container = CoreServices(settings, db)
    engine = AuraEngine(settings, db, services=container)
    async def forbidden(*args, **kwargs):
        raise AssertionError("Do not infer practice solutions using Ollama")
    engine.llm.reply = forbidden
    assert "competency" not in container.initialized
    first = asyncio.run(engine.command("Treina matemática"))
    question = first["data"]
    assert question["domain"] == "matematica"
    assert question["status"] == "pending"
    assert "solution" not in json.dumps(first)
    assert "competency" in container.initialized
    with db.connect() as conn:
        answer = conn.execute("SELECT solution FROM expecto_practice WHERE id=?",
                              (question["id"],)).fetchone()["solution"]
    result = asyncio.run(engine.command(
        f"Responde treino {question['id']}: {answer}"))
    assert result["data"]["correct"]
    status = asyncio.run(engine.command("Estado das competências"))
    assert status["data"]["domains"][0]["answered"] == 1
    assert "automatic_model_training" in status["data"]
    assert "learning" not in container.initialized
    next_question = asyncio.run(engine.command("Pratica física"))
    assert next_question["data"]["domain"] == "fisica"
    assert "capture" not in next_question
    assert "solution" not in json.dumps(next_question)
    ignored = asyncio.run(engine.command("Salta exercício"))
    assert "ignorado" in ignored["text"]


def test_restart_retains_history_without_affecting_other_memory(tmp_path):
    db = store(tmp_path)
    db.add_memory("Informação local privada que permanece inalterada")
    engine = CompetencyEngine(db)
    challenge = engine.next("fisica", seed=9)
    engine.submit(challenge["id"], "0")
    reopened = CompetencyEngine(store(tmp_path))
    assert reopened.report()["domains"][2]["answered"] == 1
    assert reopened.db.memories()[0]["content"] == (
        "Informação local privada que permanece inalterada")


def test_legacy_core_and_adaptive_engine_remain_separate():
    # The core's architecture does not import concrete competency logic.
    core = Path(__file__).resolve().parents[1] / "aura" / "core" / "ports.py"
    assert "competency" not in core.read_text(encoding="utf-8")
