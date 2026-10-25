"""Memory v2.1 migration, recall and safety regression tests."""
import asyncio
import json
import sqlite3
from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine
from aura.memory import cosine


def cmd(e, text):
    return asyncio.run(e.command(text))


def test_migration_legacy_preserves_old_notes_and_rebuilds_index(tmp_path):
    path = tmp_path / 'old.sqlite3'
    with sqlite3.connect(path) as raw:
        raw.execute('CREATE TABLE memories(id TEXT PRIMARY KEY,content TEXT NOT NULL,created_at TEXT NOT NULL)')
        raw.execute('INSERT INTO memories VALUES(?,?,?)', ('0123456789ab','Gosto de trabalhar com Figma','2026-10-01'))
    db = Database(path)
    assert len(db.memories()) == 1
    assert db.search_memories('Figma')[0]['id'] == '0123456789ab'
    again = Database(path)
    assert len(again.memories()) == 1
    assert again.search_memories('Figma')[0]['id'] == '0123456789ab'


def test_relevance_and_update_and_forget(tmp_path):
    db = Database(tmp_path / 'notes.sqlite3')
    db.add_memory('Vou cozinhar uma sopa de legumes')
    right = db.add_memory('AURA deve ter interface sem barras laterais')
    assert db.search_memories('interface AURA')[0]['id'] == right['id']
    assert db.add_memory(right['content'])['id'] == right['id']
    db.set_vector(right['id'], 'test', [0.1,0.2])
    corrected = db.update_memory(right['id'], 'AURA usa holograma central e comandos de voz')
    assert 'holograma' in corrected['content']
    assert db.search_memories('holograma')[0]['id'] == right['id']
    assert db.search_memories('barras') == []
    assert db.vectors('test') == []  # Never serve stale embedding after correction.
    assert db.delete_memory(right['id'])
    assert db.search_memories('holograma') == []
    with db.connect() as con:
        assert con.execute('SELECT count(*) FROM memory_revisions').fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM memory_vectors').fetchone()[0] == 0


def test_backup_export_and_restart(tmp_path):
    db = Database(tmp_path / 'memory.sqlite3')
    entry = db.add_memory('AURA e um projeto local', category='project', importance=5)
    backup = db.backup(tmp_path / 'backups')
    assert backup.is_file()
    assert Database(backup).get_memory(entry['id'])['category'] == 'project'
    assert len(json.dumps(db.export_memories())) > 40


def test_semantic_recall_mocked_embeddings(tmp_path):
    settings = Settings(data_dir=tmp_path, embedding_model='test-model')
    e = AuraEngine(settings, Database(tmp_path / 'db.sqlite3'))
    async def embed(text):
        return [1.0,0.0] if any(x in text.casefold() for x in ['interface','barras','ecrã']) else [0.0,1.0]
    e.memory._embed = embed
    async def full():
        await e.memory.remember('Não quero barras laterais na interface')
        await e.memory.remember('Gosto de massas com queijo')
        return await e.memory.recall('Como devo organizar o ecrã?', 2)
    items = asyncio.run(full())
    assert items[0]['content'] == 'Não quero barras laterais na interface'


def test_memory_voice_commands(tmp_path):
    e = AuraEngine(Settings(data_dir=tmp_path), Database(tmp_path / 'db.sqlite3'))
    cmd(e, 'Lembra-te de que a AURA tem voz')
    note = e.db.memories()[0]
    assert cmd(e,'Procura memória sobre voz')['data'][0]['id'] == note['id']
    assert 'atualizei' in cmd(e,f'Corrige a memória {note["id"]} para O projeto AURA precisa de memória') ['text'].casefold()
    assert 'projeto' in e.db.get_memory(note['id'])['content'].casefold()
    assert 'backup' in cmd(e,'Faz backup da memória')['text'].casefold() or 'cópia' in cmd(e,'Faz backup da memória')['text'].casefold()
    # v2.7: refuse plaintext backups when no encryption passphrase is configured.
    assert not (tmp_path / 'backups').exists()
    cmd(e,'Exporta a memória')
    assert not (tmp_path / 'memoria_exportada.json').exists()  # 2.7: no plaintext export without key
    assert cosine([1,0],[0,1]) == 0
