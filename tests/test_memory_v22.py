"""Six-calendar-month episodic memory / privacy / durability regression suite."""
from datetime import datetime, timedelta, timezone
import asyncio
import json
import sqlite3
from fastapi.testclient import TestClient
from aura.database import Database, months_before
from aura.app import create_app
from aura.config import Settings
from aura.engine import AuraEngine
from aura.privacy import safe_to_capture


def test_calendar_month_math_and_last_six_months_without_deletion(tmp_path):
    assert months_before(6, datetime(2026, 8, 31, 15, tzinfo=timezone.utc)).startswith('2026-02-28T15:')
    db = Database(tmp_path / 'aura.sqlite3')
    a = db.record_exchange('session_a', 'O projeto AURA foi criado com memória persistente',
                           'Vamos melhorar o armazenamento')
    b = db.record_exchange('session_a', 'O projeto AURA terá testes de regressão', 'Combinado')
    cutoff = datetime.fromisoformat(months_before(6))
    older = cutoff - timedelta(days=2)
    with db.connect() as raw:
        raw.execute('UPDATE conversation_episodes SET created_at=? WHERE id=?',
                    (older.isoformat(timespec='seconds'), a[0]['id']))
        raw.execute('UPDATE conversation_episodes SET created_at=? WHERE id=?',
                    ((cutoff + timedelta(days=1)).isoformat(timespec='seconds'), a[1]['id']))
    hits = db.search_episodes('memória projeto AURA', months=6)
    assert a[0]['id'] not in [x['id'] for x in hits]
    assert db.episode_count(months=6) == 3
    assert Database(db.path).episode_count(months=6) == 3
    with db.connect() as raw:
        assert raw.execute('SELECT count(*) FROM conversation_episodes').fetchone()[0] == 4
    assert db.export_full_memory(6)['conversations'][0]['id'] != a[0]['id']
    assert b[0]['id'] in [x['id'] for x in db.recent_episodes(6)]


def test_migration_of_v21_preserves_notes_and_restarts(tmp_path):
    path = tmp_path / 'v21.sqlite3'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE memories(id TEXT PRIMARY KEY,content TEXT NOT NULL,created_at TEXT NOT NULL)')
        conn.execute("INSERT INTO memories VALUES('012345abcdef','Prefiro voz e holograma','2026-10-01')")
    db = Database(path)
    assert db.get_memory('012345abcdef')['content'] == 'Prefiro voz e holograma'
    db.record_exchange('browser_tab','Conversa antiga guardada', 'Ficará na base local')
    assert len(Database(path).search_episodes('Conversa antiga',6)) == 1
    assert Database(path).get_memory('012345abcdef')


def test_api_records_only_conversations_and_can_pause_resume(tmp_path):
    cfg = Settings(data_dir=tmp_path,database_encryption_required=False)
    with TestClient(create_app(cfg)) as client:
        status = client.get('/api/memory/status').json()
        assert status['lookback_months'] == 6
        assert status['recording'] is True
        cmd = lambda message: client.post('/api/command', json={'message':message,'session_id':'teste'}).json()
        cmd('Olá')
        assert client.get('/api/memory/status').json()['episodes_in_window'] == 2
        cmd('Abre a memória')
        cmd('Lembra-te de que prefiro uma interface holográfica')
        assert client.get('/api/memory/status').json()['episodes_in_window'] == 2
        cmd('Desativa memória automática')
        cmd('Olá')
        assert client.get('/api/memory/status').json()['episodes_in_window'] == 2
        cmd('Ativa memória automática')
        cmd('Olá')
        assert client.get('/api/memory/status').json()['episodes_in_window'] == 4
        result = cmd('Procura conversa sobre Olá')
        assert result['action']['panel'] == 'memory'
        cmd('Apaga histórico de conversas')
        assert client.get('/api/memory/status').json()['episodes_in_window'] == 0
        assert len(client.get('/api/panel/memory').json()['data']) == 1
    # State persists across independent FastAPI instances.
    with TestClient(create_app(cfg)) as client:
        assert client.get('/api/memory/status').json()['recording'] is True
        assert client.get('/api/memory/status').json()['episodes_in_window'] == 0


def test_export_backup_and_single_erase(tmp_path):
    db = Database(tmp_path / 'aura.sqlite3')
    db.add_memory('Guardar 6 meses', importance=4)
    msgs = db.record_exchange('session', 'Falar sobre SQL', 'Base de dados funciona')
    assert len(db.export_full_memory(6)['conversations']) == 2
    assert db.delete_episode(msgs[0]['id'])
    assert len(db.search_episodes('SQL',6)) == 0
    saved = db.backup_if_due(tmp_path / 'backups', days=7)
    assert saved and saved.exists()
    assert db.backup_if_due(tmp_path / 'backups',days=7) is None
    clone = Database(saved)
    assert clone.episode_count() == 1
    assert clone.memories()[0]['content'] == 'Guardar 6 meses'
    assert db.erase_episodes() == 1
    assert db.memories()[0]['content'] == 'Guardar 6 meses'
    assert clone.episode_count() == 1  # Backup isn't retroactively rewritten.


def test_secret_filter_and_invalid_session_id(tmp_path):
    assert safe_to_capture('Vamos fazer um projeto em Python')
    assert not safe_to_capture('password: teste_super_secreto')
    assert not safe_to_capture('A minha palavra-passe é segredo')
    assert not safe_to_capture('Visa 4111 1111 1111 1111')
    db = Database(tmp_path / 'test.sqlite3')
    items = db.record_exchange('../../bad/id','Mensagem normal','Resposta')
    assert items[0]['session_id'] != '../../bad/id'


def test_consistent_date_and_recall_in_llm_context(tmp_path, monkeypatch):
    from aura.llm import Ollama
    db = Database(tmp_path / 'db.sqlite3')
    db.record_exchange('old_session','Desenvolvo um programa com sensores agrícolas',
                       'A aplicação processa dados de sensores')
    calls=[]
    class FakeResponse:
        status_code=200
        def raise_for_status(self): pass
        def json(self): return {'message':{'content':'Resposta de teste'}}
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): pass
        async def post(self, url, json):
            calls.append(json)
            return FakeResponse()
    monkeypatch.setattr('aura.llm.httpx.AsyncClient',FakeClient)
    llm=Ollama(Settings(data_dir=tmp_path,database_encryption_required=False),db)
    assert asyncio.run(llm.reply('O que falámos sobre sensores agrícolas?')) == 'Resposta de teste'
    context=calls[0]['messages'][0]['content']
    assert 'sensores agrícolas' in context
    assert 'Excertos de conversas anteriores' in context
