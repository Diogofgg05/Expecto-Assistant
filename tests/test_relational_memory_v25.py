"""Relational graph regression checks: privacy, consent, provenance, migration."""
from datetime import datetime,timezone,timedelta
from fastapi.testclient import TestClient
import pytest
from aura.database import Database,months_before
from aura.config import Settings
from aura.app import create_app
from aura.relations import RelationMemory,parse_user_relationship


def test_graph_links_idempotent_persistent_export_backup(tmp_path):
    path=tmp_path/'memory.sqlite3'
    db=Database(path)
    graph=RelationMemory(db)
    a=graph.add_link('project','AURA','uses_technology','technology','SQLite')
    assert a['created']
    b=graph.add_link('project','aura','uses_technology','technology','sqlite')
    assert not b['created'] and a['id']==b['id']
    assert graph.stats()=={'entities':2,'links':1,'automatic_links':0}
    assert len(RelationMemory(Database(path)).list_links(name='AURA'))==1
    assert db.export_full_memory()['relational_graph']['links'][0]['id']==a['id']
    restored=Database(db.backup(tmp_path/'backup'))
    assert RelationMemory(restored).stats()['links']==1
    assert graph.remove_link(a['id'])
    assert graph.stats()['entities']==0


def test_automatic_links_have_real_user_episode_and_correct_deletion(tmp_path):
    db=Database(tmp_path/'x.sqlite3'); graph=RelationMemory(db)
    e=db.record_exchange('s','No projeto AURA uso SQLite','OK')[0]
    assert graph.observe_episode(e['id'])==1
    assert graph.observe_episode(e['id'])==0
    x=graph.list_links(name='AURA')[0]
    assert x['episode_id']==e['id'] and x['source_quote']=='No projeto AURA uso SQLite'
    with pytest.raises(ValueError):
        graph.add_link('project','AURA','uses_technology','technology','PostgreSQL',
                       origin='auto_episode',episode_id=e['id'],quote='No projeto AURA uso SQLite')
    assert db.delete_episode(e['id'])
    assert graph.list_links(name='AURA')==[]
    assert graph.stats()['entities']==0


def test_erasing_episodes_preserves_explicit_links(tmp_path):
    db=Database(tmp_path/'d.sqlite3'); graph=RelationMemory(db)
    explicit=graph.add_link('project','NovaEX','has_problem','problem','Erro de arranque')
    e=db.record_exchange('s','No projeto NovaEX uso Wine','OK')[0]
    assert graph.observe_episode(e['id'])==1
    assert db.erase_episodes()==2
    assert graph.stats()['links']==1
    assert graph.list_links(name='NovaEX')[0]['id']==explicit['id']


def test_patterns_are_literal_conservative_and_sensitive_rejected(tmp_path):
    assert parse_user_relationship('O projeto NovaEX usa Wine')==[
        ('project','NovaEX','uses_technology','technology','Wine')]
    assert parse_user_relationship('No projeto AURA decidi usar SQLite')==[
        ('project','AURA','has_decision','decision','SQLite')]
    assert len(parse_user_relationship('Resolvi o problema de lentidão com um modelo pequeno no projeto AURA'))==2
    for line in [
        'Se no projeto AURA uso SQLite', 'No projeto AURA talvez uso SQLite',
        'No projeto AURA uso SQLite?', 'No projeto AURA uso palavra-passe: secret',
        'No projeto AURA uso SQLite e se funcionar será bom',
        'No projeto AURA uso SQLite\nNo projeto NovaEX uso Wine',
        'O meu salário é 1500 euros',
    ]:
        assert parse_user_relationship(line)==[], line
    db=Database(tmp_path/'d.sqlite3')
    with pytest.raises(ValueError):
        RelationMemory(db).add_link('project','AURA','has_problem','solution','bug')


def test_batch_backfill_only_window_and_user_turns(tmp_path):
    db=Database(tmp_path/'d.sqlite3'); graph=RelationMemory(db)
    e1=db.record_exchange('s','O projeto AURA usa Python','OK')[0]
    e2=db.record_exchange('s','O projeto NovaEX usa Wine','OK')[0]
    old=(datetime.fromisoformat(months_before(6))-timedelta(days=2)).isoformat(timespec='seconds')
    with db.connect() as conn:
        conn.execute('UPDATE conversation_episodes SET created_at=? WHERE id=?',(old,e2['id']))
    result=graph.backfill(months=6)
    assert result['linked']==1
    assert result['examined']==1
    assert graph.backfill(months=6)=={'linked':0,'examined':0}
    assert graph.search_related('Que tecnologias usa a AURA?')[0]['target_name']=='Python'
    assert graph.list_links(name='NovaEX')==[]


def test_api_commands_and_auto_optout(tmp_path,monkeypatch):
    from aura.llm import Ollama
    async def fake(self,question,history=None):
        return 'Entendido.'
    monkeypatch.setattr(Ollama,'reply',fake)
    with TestClient(create_app(Settings(data_dir=tmp_path,database_encryption_required=False,embedding_model=''))) as client:
        send=lambda m:client.post('/api/command',json={'message':m,'session_id':'s'}).json()
        assert send('Associa a tecnologia SQLite ao projeto AURA')['action']=={'type':'open','panel':'memory'}
        assert send('Associa o problema lentidão ao projeto AURA')['text'].startswith('Relação guardada')
        assert send('Associa a solução modelo leve ao problema lentidão')['ok']
        links=client.get('/api/memory/relations',params={'name':'AURA'}).json()['items']
        assert len(links)==2
        assert send('Mostra relações do projeto AURA')['data'][0]['category']=='relation'
        send('Desativa relações automáticas')
        send('No projeto NovaEX uso Wine')
        assert client.get('/api/memory/relations',params={'name':'NovaEX'}).json()['items']==[]
        send('Ativa relações automáticas')
        send('No projeto NovaEX uso Wine')
        assert len(client.get('/api/memory/relations',params={'name':'NovaEX'}).json()['items'])==1
        assert client.get('/api/memory/status').json()['relational_graph']['links']==4
        assert send('Organiza relações das conversas')['ok']
        found=client.get('/api/memory/relations/search',params={'q':'O que usa NovaEX?'}).json()['items']
        assert any(x['target_name']=='Wine' for x in found)
        assert client.get('/api/config').json()['auto_link']
        oldlink=client.get('/api/memory/relations',params={'name':'AURA'}).json()['items'][0]
        assert send('Esquece a relação '+oldlink['id'])['ok']
        assert len(client.get('/api/memory/relations',params={'name':'AURA'}).json()['items'])==1


def test_migration_from_24_retains_notes_temporal(tmp_path):
    import sqlite3
    dbpath=tmp_path/'old.sqlite3'
    with sqlite3.connect(dbpath) as db:
        db.execute('CREATE TABLE memories(id TEXT PRIMARY KEY, content TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute("INSERT INTO memories VALUES('note_1234567','Gosto de programar','2026-09-01')")
    db=Database(dbpath)
    db.set_temporal_fact('browser','Brave')
    assert db.get_memory('note_1234567')['content']=='Gosto de programar'
    assert db.temporal_current('browser')[0]['value']=='Brave'
    assert RelationMemory(db).stats()['entities']==0
