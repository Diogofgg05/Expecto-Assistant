import asyncio
from pathlib import Path
from aura.config import Settings
from aura.database import Database
from aura.engine import AuraEngine, normalized
from aura.research import ResearchOutcome


def make_engine(tmp_path):
    s = Settings(data_dir=tmp_path)
    return AuraEngine(s, Database(tmp_path / 'test.sqlite3'))


def ask(engine, text):
    return asyncio.run(engine.command(text))


def test_accents_and_layout(tmp_path):
    e = make_engine(tmp_path)
    assert normalized('  MEMÓRIA  ') == 'memoria'
    assert ask(e, 'Abre a memória')['action'] == {'type': 'open', 'panel': 'memory'}
    assert ask(e, 'Abre os diagnósticos')['action']['panel'] == 'diagnostics'
    assert ask(e, 'Aumenta a memória')['action']['size'] == 'large'
    assert ask(e, 'Coloca a memória à direita')['action']['type'] == 'move'
    assert ask(e, 'Fecha tudo')['action']['type'] == 'close_all'


def test_memory_write_and_read(tmp_path):
    e = make_engine(tmp_path)
    result = ask(e, 'Lembra-te de que gosto de computadores')
    assert result['action']['panel'] == 'memory'
    note = e.db.memories()[0]
    assert note['content'] == 'que gosto de computadores'
    assert ask(e, 'O que te lembras?')['data'][0]['id'] == note['id']
    assert 'eliminada' in ask(e, 'Esquece a nota ' + note['id'])['text'].lower()
    assert e.db.memories() == []


def test_manual_research_and_job(mock_research, tmp_path):
    e = make_engine(tmp_path)
    e.research.learn = mock_research
    result = ask(e, 'Investiga sobre Python')
    assert result['action']['panel'] == 'research'
    assert result['data']['topic'] == 'Python'
    assert len(result['data']['documents']) == 1
    recurring = ask(e, 'Investiga autonomamente sobre Python')
    assert 'pesquisa periódica' in recurring['text']
    assert e.db.jobs(True)[0]['topic'] == 'Python'
    assert len(e.db.due_jobs()) == 0
    assert 'desativada' in ask(e, 'Desativa investigação sobre Python')['text']

import pytest
@pytest.fixture
def mock_research():
    async def execute(topic):
        return ResearchOutcome(topic, [{
            'topic': topic, 'title':'Fonte', 'content':'Conteúdo de teste',
            'url':'https://example.org', 'evidence_level':'single_source',
            'source_type':'wikipedia', 'learned_at':'2026-01-01'
        }])
    return execute
