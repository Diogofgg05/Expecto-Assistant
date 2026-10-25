"""v2.6 regression: attributable consolidation, six-month window, no data loss."""
import asyncio
from datetime import datetime,timezone,timedelta
from fastapi.testclient import TestClient
from aura.app import create_app
from aura.consolidation import ConsolidationEngine, _same_meaning
from aura.config import Settings, ROOT
from aura.database import Database, months_before


def samples(db):
    e1=db.record_exchange('s', 'No projeto AURA uso SQLite', 'Percebi.')[0]
    e2=db.record_exchange('s', 'No projeto AURA tenho problema de lentidão', 'Entendido.')[0]
    db.add_memory('O projeto AURA usa memória SQLite',category='project',topic='AURA')
    return e1,e2


def test_consolidate_with_sources_persists_and_no_deletion(tmp_path):
    path=tmp_path/'a.sqlite3'; db=Database(path)
    e1,e2=samples(db)
    count_before=db.episode_count()
    notes_before=len(db.memories())
    eng=ConsolidationEngine(db)
    stats=eng.consolidate()
    assert stats['summaries']>=1
    assert stats['automatic_merges']==stats['automatic_deletions']==0
    item=eng.summaries('AURA')[0]
    assert 'SQLite' in item['content']
    assert any(s['id']==e1['id'] and s['type']=='episode' for s in item['sources'])
    assert len(item['sources'])>=2
    assert db.episode_count()==count_before
    assert len(db.memories())==notes_before
    assert ConsolidationEngine(Database(path)).summaries('AURA')[0]['id']==item['id']
    assert db.export_full_memory()['consolidation_summaries'][0]['sources']


def test_idempotent_rerun_and_backup_restore(tmp_path):
    db=Database(tmp_path/'original.sqlite3'); samples(db)
    e=ConsolidationEngine(db)
    e.consolidate(); before=e.summaries('AURA')
    e.consolidate(); after=e.summaries('AURA')
    assert len(before)==len(after) == 1
    assert before[0]['id']==after[0]['id']
    restored=Database(db.backup(tmp_path/'backup'))
    assert ConsolidationEngine(restored).summaries('AURA')[0]['content']==after[0]['content']


def test_erase_source_invalidates_summary_immediately(tmp_path):
    db=Database(tmp_path/'a.sqlite3'); e1,e2=samples(db)
    engine=ConsolidationEngine(db);engine.consolidate()
    assert engine.summaries('AURA')
    assert db.delete_episode(e1['id'])
    assert engine.summaries('AURA')==[]
    engine.consolidate()
    assert engine.summaries('AURA')  # reconstructs with remaining valid evidence
    note=db.memories()[0]
    assert db.delete_memory(note['id'])
    assert engine.summaries('AURA')==[]


def test_update_note_invalidates_summary_and_reconsolidates(tmp_path):
    db=Database(tmp_path/'a.sqlite3');samples(db);engine=ConsolidationEngine(db)
    engine.consolidate();before=engine.summaries('AURA')[0]
    id=db.memories()[0]['id']
    db.update_memory(id,'O projeto AURA prefere Python')
    assert not engine.summaries('AURA')
    engine.consolidate()
    assert any('Python' in v['content'] for v in engine.summaries('AURA'))


def test_old_episodes_outside_six_month_window_and_assistant_excluded(tmp_path):
    db=Database(tmp_path/'a.sqlite3');old=db.record_exchange('s','No projeto AURA uso discos magnéticos','IA inventou uma solução')[0]
    recent=db.record_exchange('s','No projeto AURA uso SQLite','Entendi')[0]
    last=db.record_exchange('s','No projeto AURA uso Python','Entendi')[0]
    stamp=(datetime.fromisoformat(months_before(6))-timedelta(days=1)).isoformat(timespec='seconds')
    with db.connect() as con:con.execute('UPDATE conversation_episodes SET created_at=? WHERE id=?',(stamp,old['id']))
    e=ConsolidationEngine(db);e.consolidate(months=6)
    d=e.summaries('AURA')[0]
    assert old['id'] not in {s['id'] for s in d['sources']}
    assert recent['id'] in {s['id'] for s in d['sources']}
    assert last['id'] in {s['id'] for s in d['sources']}
    assert 'IA inventou' not in d['content']
    assert len(db.recent_episodes(6))>=4


def test_no_summary_from_sensitive_messages(tmp_path):
    db=Database(tmp_path/'a.sqlite3')
    db.record_exchange('s','O meu salário é 1200 euros e falo sobre AURA','Ok')
    db.record_exchange('s','O meu NIF está num contrato sobre AURA','Ok')
    db.record_exchange('s','A minha password: segredo e estou na AURA','Ok')
    assert ConsolidationEngine(db).consolidate()['summaries']==0


def test_duplicate_and_conflict_review_no_delete(tmp_path):
    db=Database(tmp_path/'a.sqlite3')
    a=db.add_memory('Prefiro programar com Python e Linux')
    b=db.add_memory('Prefiro programar com Python, e Linux!')
    c=db.add_memory('Quero notificações automáticas')
    d=db.add_memory('Não quero notificações automáticas')
    reviews=ConsolidationEngine(db)
    duplicates=reviews.duplicate_candidates()
    assert any({a['id'],b['id']} <= set(g['memory_ids']) for g in duplicates)
    conflicts=reviews.review_candidates()
    assert any({c['id'],d['id']} <= set(g.get('memory_ids',[])) for g in conflicts)
    assert len(db.memories())==4


def test_historical_updates_not_labeled_as_conflicts(tmp_path):
    db=Database(tmp_path/'a.sqlite3')
    db.set_temporal_fact('browser','Chrome')
    db.set_temporal_fact('browser','Brave')
    reports=ConsolidationEngine(db).review_candidates()
    assert len(reports)==1
    assert reports[0]['kind']=='historical_change'
    assert [v['value'] for v in reports[0]['values']]==['Brave','Chrome']


def test_api_voice_settings_and_no_new_navigation(tmp_path,monkeypatch):
    from aura.llm import Ollama
    async def fake_reply(self,question,history=None):return 'Percebi.'
    monkeypatch.setattr(Ollama,'reply',fake_reply)
    with TestClient(create_app(Settings(data_dir=tmp_path,database_encryption_required=False,embedding_model=''))) as client:
        send=lambda msg:client.post('/api/command',json={'message':msg,'session_id':'s'}).json()
        assert client.get('/api/memory/status').json()['auto_consolidate_memory'] is False
        assert send('Ativa consolidação automática')['ok']
        assert client.get('/api/config').json()['auto_consolidate'] is True
        send('No projeto AURA uso SQLite');send('No projeto AURA uso Python')
        result=send('Consolida a memória')
        assert result['action']=={'type':'open','panel':'memory'}
        assert client.get('/api/memory/consolidation/summaries',params={'topic':'AURA'}).json()['items']
        assert client.get('/api/memory/consolidation/status').json()['linked_sources']>=2
        assert client.get('/api/memory/consolidation/review').status_code==200
        assert send('Resume a memória sobre AURA')['data'][0]['category']=='summary'
        assert send('Mostra memórias repetidas')['action']=={'type':'open','panel':'memory'}
        assert send('Mostra contradições')['ok']
        assert send('Desativa consolidação automática')['ok']
        assert not client.get('/api/config').json()['auto_consolidate']
        assert client.get('/api/health').json()['version'].startswith('3.3')
    web=(ROOT/'web/app.js').read_text()
    assert 'openPanel' in web and 'closeAll' in web


def test_migration_from_25_existing_db_survives(tmp_path):
    # Simulate pre-v2.6 database by removing new schema after existing migration.
    path=tmp_path/'old.sqlite3';db=Database(path)
    db.add_memory('No meu projeto AURA uso Python',topic='AURA',category='project')
    db.set_temporal_fact('editor','VS Code')
    from aura.relations import RelationMemory
    RelationMemory(db).add_link('project','AURA','uses_technology','technology','Python')
    db.record_exchange('session','No projeto AURA uso Python','Ok')
    reopened=Database(path)
    assert reopened.get_memory(db.memories()[0]['id'])
    assert reopened.temporal_current('editor')[0]['value']=='VS Code'
    assert RelationMemory(reopened).list_links(name='AURA')
    assert reopened.episode_count()==2
    assert ConsolidationEngine(reopened).consolidate()['summaries']>=1


def test_repeated_conversation_marked_without_merging(tmp_path):
    db=Database(tmp_path/'db.sqlite3')
    e1=db.record_exchange('s','No projeto AURA uso SQLite','Ok')[0]
    e2=db.record_exchange('s','No projeto AURA uso SQLite','Ok')[0]
    items=ConsolidationEngine(db).duplicate_candidates()
    assert any({e1['id'],e2['id']}<=set(g.get('episode_ids',[])) for g in items)
    assert db.episode_count()==4
    assert db.get_memory(e1['id']) is None  # Episodic sources are distinct from notes.
