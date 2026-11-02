"""Regression: lightweight core and explicit command handlers preserve behavior."""
import asyncio
from fastapi.testclient import TestClient
from aura.app import create_app
from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine


def make_engine(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    db = Database(tmp_path / "core.sqlite3")
    return AuraEngine(settings, db)


def run(engine, command):
    return asyncio.run(engine.command(command))


def test_heavy_services_load_only_when_used(tmp_path):
    engine = make_engine(tmp_path)
    assert set(engine.__dict__).issuperset({"settings", "db", "memory", "llm"})
    optional = {"optimizer", "epistemics", "factcheck", "quality", "research",
                "reflection", "continuity", "relations", "consolidation",
                "secure_backups", "extractor", "learning"}
    assert not optional.intersection(engine.__dict__)
    assert engine.optimizer is engine.optimizer
    assert "optimizer" in engine.__dict__
    assert optional.difference({"optimizer"}).isdisjoint(engine.__dict__)


def test_note_count_does_not_materialize_all_records(tmp_path, monkeypatch):
    engine = make_engine(tmp_path)
    ids = [engine.db.add_memory("nota " + str(i))["id"] for i in range(5)]
    assert engine.db.memory_count() == 5
    engine.db.delete_memory(ids[0])
    assert engine.db.memory_count() == 4
    def forbidden(*args, **kwargs):
        raise AssertionError("Não carregar todas as memórias para contar")
    monkeypatch.setattr(engine.db, "memories", forbidden)
    assert engine.db.memory_count() == 4
    monkeypatch.undo()
    result = run(engine, "O que te lembras?")
    assert result["ok"]
    assert "4 notas" in result["text"]


def test_interface_commands_have_same_structured_actions(tmp_path):
    e=make_engine(tmp_path)
    cases = [
      ("Abre a memória", {"type":"open","panel":"memory"}),
      ("Mostra os diagnósticos", {"type":"open","panel":"diagnostics"}),
      ("Fecha a memória", {"type":"close","panel":"memory"}),
      ("Aumenta a memória", {"type":"resize","panel":"memory","size":"large"}),
      ("Coloca a memória à direita", {"type":"move","panel":"memory"}),
      ("Fecha tudo", {"type":"close_all"}),
    ]
    for command, expected in cases:
        assert run(e, command)["action"] == expected


def test_commands_remain_explicit_and_private(tmp_path):
    e=make_engine(tmp_path)
    assert run(e,"Ativa modo privado")["ok"]
    assert e.db.get_option("private_mode") == "true"
    assert run(e,"Desativa modo privado")["ok"]
    assert e.db.get_option("private_mode") == "false"
    note = run(e,"Lembra-te de que a arquitetura está leve")
    assert note["action"]["panel"] == "memory"
    assert run(e,"Mostra o feedback")["ok"]


def test_loopback_host_matches_default(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    with TestClient(app,base_url="http://127.0.0.1") as client:
        assert client.get("/api/health").status_code == 200
