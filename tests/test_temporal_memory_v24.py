"""v2.4 temporal memory: historical revisions, migration, privacy, voice and API."""
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
import pytest
from aura.config import Settings
from aura.database import Database
from aura.temporal import extract_statement
from aura.app import create_app


def test_versioning_current_as_of_reopen_and_no_duplicate(tmp_path):
    path=tmp_path/'mem.sqlite3'
    db=Database(path)
    first=db.set_temporal_fact('browser','Chrome')
    assert db.set_temporal_fact('navegador','chrome')['id']==first['id']
    midway=datetime.now(timezone.utc).isoformat(timespec='microseconds')
    second=db.set_temporal_fact('navegador','Brave')
    assert second['id'] != first['id']
    assert db.temporal_as_of('browser',midway)['value']=='Chrome'
    assert db.temporal_current('browser')[0]['value']=='Brave'
    versions=Database(path).temporal_history('browser')
    assert [x['value'] for x in versions]==['Brave','Chrome']
    assert versions[1]['valid_to']==versions[0]['valid_from']
    assert db.temporal_as_of('browser',second['valid_from'])['value']=='Brave'
    assert db.export_full_memory()['temporal_history'][0]['value']=='Chrome'
    assert db.temporal_count()==2


def test_six_month_window_includes_preexisting_state(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    older=db.set_temporal_fact('editor','VS Code')
    recent=db.set_temporal_fact('editor','Zed')
    from aura.database import months_before
    past=datetime.fromisoformat(months_before(6))-timedelta(days=40)
    # Before the window but valid until replaced recently: important context.
    with db.connect() as conn:
        conn.execute('UPDATE temporal_facts SET valid_from=? WHERE id=?',
                     (past.isoformat(timespec='microseconds'),older['id']))
    assert [r['value'] for r in db.temporal_history('editor')]==['Zed','VS Code']


def test_conservative_patterns_and_sensitive_values():
    assert extract_statement('O meu browser é Chrome')==('browser','Chrome')
    assert extract_statement('O meu browser agora é Brave')==('browser','Brave')
    assert extract_statement('Agora uso Fedora como distribuição Linux')==('distribuicao_linux','Fedora')
    assert extract_statement('O meu browser era Chrome') is None
    assert extract_statement('O meu browser é Brave?') is None
    assert extract_statement('O meu editor é VS Code e gosto dele') is None
    assert extract_statement('O meu salário é 1200 euros') is None
    assert extract_statement('O meu browser é Brave; palavra-passe: segredo') is None
    assert extract_statement('O meu endereço é Rua da Paz') is None


def test_auto_source_and_erasure_of_conversation_and_explicit_preserved(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    ep=db.record_exchange('s','O meu browser é Chrome','Compreendo')[0]
    assert db.observe_temporal_episode(ep['id'])['value']=='Chrome'
    ep2=db.record_exchange('s','O meu browser agora é Brave','Compreendo')[0]
    assert db.observe_temporal_episode(ep2['id'])['value']=='Brave'
    assert db.temporal_count()==2
    assert db.delete_episode(ep2['id'])
    assert db.temporal_current('browser')==[]  # No silent resurrection of Chrome.
    assert db.temporal_count()==1
    db.set_temporal_fact('editor','Zed')
    assert db.erase_episodes()==3
    assert db.temporal_current('browser')==[]
    assert db.temporal_current('editor')[0]['value']=='Zed'


def test_migration_from_23_preserves_old_data(tmp_path):
    from sqlite3 import connect
    path=tmp_path/'old.sqlite3'
    with connect(path) as old:
        old.execute('CREATE TABLE memories(id TEXT PRIMARY KEY, content TEXT NOT NULL, created_at TEXT NOT NULL)')
        old.execute("INSERT INTO memories VALUES('old_note_123','Tenho um projeto em Python','2026-10-01')")
    db=Database(path)
    assert db.get_memory('old_note_123')['content']=='Tenho um projeto em Python'
    db.set_temporal_fact('browser','Brave')
    assert Database(path).temporal_current('browser')[0]['value']=='Brave'
    assert len(db.memories())==1


def test_endpoint_commands_auto_vs_optout_and_no_gui_navigation(tmp_path,monkeypatch):
    from aura.llm import Ollama
    async def local_response(self,question,history=None):
        return 'Recebido.'
    monkeypatch.setattr(Ollama,'reply',local_response)
    cfg=Settings(data_dir=tmp_path,database_encryption_required=False,embedding_model='')
    with TestClient(create_app(cfg)) as client:
        send=lambda msg:client.post('/api/command',json={'message':msg,'session_id':'session'}).json()
        status=client.get('/api/memory/status').json()
        assert status['temporal_facts']==0
        send('O meu browser é Chrome')
        send('O meu browser agora é Brave')
        data=client.get('/api/memory/temporal/current',params={'subject':'browser'}).json()['items']
        assert [x['value'] for x in data]==['Brave']
        history=client.get('/api/memory/temporal/history',params={'subject':'browser'}).json()['items']
        assert [x['value'] for x in history]==['Brave','Chrome']
        assert send('Qual é o meu browser')['text'].find('Brave')!=-1
        assert send('Histórico do meu browser')['action']=={'type':'open','panel':'memory'}
        send('Desativa aprendizagem da memória')
        send('O meu browser é Firefox')
        assert client.get('/api/memory/temporal/current',params={'subject':'browser'}).json()['items'][0]['value']=='Brave'
        send('Ativa aprendizagem da memória')
        send('Desativa memória automática')
        send('O meu browser é Opera')
        assert client.get('/api/memory/temporal/current',params={'subject':'browser'}).json()['items'][0]['value']=='Brave'
        send('Atualiza o meu browser para Firefox')
        assert client.get('/api/memory/temporal/current',params={'subject':'browser'}).json()['items'][0]['value']=='Firefox'
        assert client.get('/api/memory/temporal/as-of',params={'subject':'browser','date':'bad'}).status_code==400
        assert 'temporal_history' in client.app.state.db.export_full_memory()
        assert send('Esquece o meu browser')['text'].startswith('Eliminei')
        assert client.get('/api/memory/temporal/current').json()['items']==[]
    from aura.config import ROOT
    web=(ROOT/'web/app.js').read_text()
    assert 'openPanel' in web and 'closeAll' in web


def test_temporal_backup_restore(tmp_path):
    db=Database(tmp_path/'original.sqlite3')
    db.set_temporal_fact('editor','VS Code')
    db.set_temporal_fact('editor','Zed')
    backup=db.backup(tmp_path/'backups')
    cloned=Database(backup)
    assert len(cloned.temporal_history('editor'))==2
    assert cloned.temporal_current('editor')[0]['value']=='Zed'
