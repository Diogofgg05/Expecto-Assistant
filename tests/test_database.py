from aura.database import Database


def test_local_memory_roundtrip(tmp_path):
    d = Database(tmp_path / 'aura.sqlite3')
    note = d.add_memory('Gosto de interfaces sem botões')
    assert d.memories()[0]['content'] == note['content']
    assert d.delete_memory(note['id'])
    assert not d.delete_memory(note['id'])
    assert d.memories() == []


def test_knowledge_upsert_and_lookup(tmp_path):
    d = Database(tmp_path / 'aura.sqlite3')
    url = 'https://pt.wikipedia.org/wiki/Linux'
    d.remember_document('Linux', 'Linux', 'Texto da fonte', url, 'wikipedia', 'single_source')
    d.remember_document('Linux', 'Linux', 'Outro texto', url, 'wikipedia', 'single_source')
    result = d.documents('Linux')
    assert len(result) == 1
    assert result[0]['content'] == 'Outro texto'
    assert d.documents('Não-existe') == []


def test_scheduled_job_opt_in_and_disable(tmp_path):
    d = Database(tmp_path / 'aura.sqlite3')
    assert d.due_jobs() == []
    d.create_job('inteligência artificial', 24)
    assert len(d.due_jobs()) == 1
    d.job_result('inteligência artificial')
    assert d.due_jobs() == []
    assert d.disable_job('inteligência artificial')
    assert d.jobs(True) == []
