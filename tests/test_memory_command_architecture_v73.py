"""Regression tests for the memory command domain split."""
import asyncio

from aura.command_memory import handle_memory_command as public_handler
from aura.memory_commands import HANDLERS, handle_memory_command
from aura.database import Database
from aura.config import Settings
from aura.engine import AuraEngine, normalized, reply


def invoke(engine, message):
    return asyncio.run(public_handler(engine, message, normalized(message).rstrip(".!?"), reply))


def test_public_memory_entry_point_and_handler_precedence():
    assert public_handler is handle_memory_command
    assert [handler.__module__.rsplit(".", 1)[-1] for handler in HANDLERS] == [
        "policy", "relations", "temporal", "episodes", "notes"
    ]


def test_domains_and_unrecognized_commands(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False)
    db = Database(tmp_path / "memory_v73.sqlite3")
    engine = AuraEngine(settings, db)

    assert invoke(engine, "comando completamente desconhecido xyz") is None
    status = invoke(engine, "Mostra as minhas memórias")
    assert status["action"]["panel"] == "memory"
    assert "meses" in status["text"]

    private_on = invoke(engine, "Ativa modo privado")
    assert "Modo privado ligado" in private_on["text"]
    assert db.get_option("private_mode", "false") == "true"
    invoke(engine, "Desativa modo privado")
    assert db.get_option("private_mode", "true") == "false"

    invoke(engine, "Ativa relações automáticas")
    assert db.get_option("auto_link_memory", "false") == "true"
    invoke(engine, "Desativa relações automáticas")
    assert db.get_option("auto_link_memory", "true") == "false"

    updated = invoke(engine, "Atualiza o meu browser para Firefox")
    assert "preservei a versão anterior" in updated["text"]
    assert db.temporal_current("browser")[0]["value"] == "Firefox"

    invoke(engine, "Desativa memória automática")
    assert db.get_option("episodic_capture", "true") == "false"
    invoke(engine, "Ativa memória automática")
    assert db.get_option("episodic_capture", "false") == "true"

    missing = invoke(engine, "Apaga a nota deadbeefdead")
    assert missing["action"]["panel"] == "memory"
    assert "Não encontrei essa nota" in missing["text"]

    missing_episode = invoke(engine, "Apaga conversa deadbeefdead")
    assert "Não encontrei essa mensagem" in missing_episode["text"]
