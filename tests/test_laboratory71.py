import asyncio
import json
from dataclasses import replace
import httpx
import pytest
from aura.config import Settings
from aura.database import Database
from aura.llm import Ollama
from aura.laboratory_cases import generate_cases, corpus_digest
from aura.performance_laboratory import recommend, run_laboratory
from aura.response_resources import ResponseResources


def sample_rows():
    rows = []
    for mode, latency in [('eco', 100), ('balanced', 200), ('max', 300)]:
        for repeat in range(2):
            for case in generate_cases(123, 4):
                rows.append({'profile': mode, 'effective_profile': mode, 'pipeline': 'raw',
                    'case_id': case.id, 'domain': case.domain, 'repeat': repeat,
                    'correct': True, 'ok': True, 'total_ms': latency})
    return rows


def test_fresh_cases_reproducible_and_oracles_not_in_prompt():
    first = generate_cases(12)
    assert first == generate_cases(12)
    assert corpus_digest(first) != corpus_digest(generate_cases(13))
    assert len(first) == 15
    assert all(c.grade(c.expected) for c in first)
    assert all(not c.grade('a plausible but wrong answer') for c in first)
    assert {c.domain for c in first} == {'math', 'programming', 'research'}


def test_recommendation_never_trades_correctness_for_speed():
    rows = sample_rows()
    assert recommend(rows)['recommended']['profile'] == 'eco'
    rows[0]['correct'] = False
    report = recommend(rows)
    assert report['recommended']['profile'] == 'balanced'
    assert next(s for s in report['scores'] if s['profile'] == 'eco')['paired_regressions'] == 1


@pytest.mark.parametrize('mutation', ['missing', 'failed', 'pressure', 'duplicate'])
def test_invalid_candidate_never_wins(mutation):
    rows = sample_rows()
    if mutation == 'missing': rows.pop(0)
    if mutation == 'failed': rows[0]['ok'] = False
    if mutation == 'pressure': rows[0]['effective_profile'] = 'pressure_override'
    if mutation == 'duplicate': rows.append(dict(rows[0]))
    assert recommend(rows)['recommended']['profile'] == 'balanced'


def test_no_recommendation_with_small_or_inaccurate_samples():
    assert recommend(sample_rows()[:4])['recommended'] is None
    rows = sample_rows()
    for r in rows: r['correct'] = False
    assert recommend(rows)['recommended'] is None


def test_resource_samples_missing_not_zero_and_cleanup(monkeypatch):
    monkeypatch.setattr('aura.response_resources.ram_sample', lambda: {'app_rss_bytes': 123, 'ollama_rss_bytes': None})
    async def probe(): return {'available': False}
    async def run():
        sampler = ResponseResources(probe)
        await sampler.sample()
        assert sampler.public()['sampled_peak_bytes'] == {'app_rss_bytes': 123, 'ollama_rss_bytes': None, 'loaded_vram_bytes': None}
        async with sampler:
            await asyncio.sleep(0)
        assert sampler.task.done()
    asyncio.run(run())


def test_incomplete_stream_is_not_success(tmp_path):
    config = Settings(data_dir=tmp_path, database_encryption_required=False)
    llm = Ollama(config, Database(tmp_path / 'db'))
    async def handler(req):
        return httpx.Response(200, text='{"message":{"content":"partial"},"done":false}\n')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            llm._transport = lambda: client
            async def token(piece): pass
            with pytest.raises(ValueError):
                await llm.reply('O que é Python?', on_token=token)
            assert llm.metrics.recent()[-1]['ok'] is False
    asyncio.run(run())


def test_lab_end_to_end_with_fake_ollama_is_not_quality_evidence(tmp_path, monkeypatch):
    import aura.performance_laboratory as laboratory
    calls = []
    original = httpx.AsyncClient
    async def handler(req):
        if req.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': 'test:1', 'digest': 'test-digest'}]})
        if req.url.path == '/api/ps':
            return httpx.Response(200, json={'models': []})
        body = json.loads(req.content)
        calls.append(body)
        # Deliberately wrong answers must block every recommendation.
        return httpx.Response(200, text='{"message":{"content":"wrong"},"done":false}\n{"done":true,"eval_count":2,"eval_duration":1000000000}\n')
    monkeypatch.setattr(laboratory.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    config = Settings(data_dir=tmp_path / 'private-do-not-touch')
    async def run():
        return await run_laboratory(config, seed=222, per_domain=4, repeats=2, warmup=0,
            models=dict.fromkeys(('eco', 'balanced', 'max'), 'test:1'), output=tmp_path / 'report.json')
    report = asyncio.run(run())
    assert report['complete'] and len(report['rows']) == 72
    assert report['recommendation']['recommended'] is None
    assert not config.data_dir.exists()
    assert all(row['calls'][0]['tokens_per_second'] == 2 for row in report['rows'])
    assert all('answer' not in row for row in report['rows'])
    assert json.loads((tmp_path / 'report.json').read_text())['complete']
    assert all(c['model'] == 'test:1' for c in calls)
