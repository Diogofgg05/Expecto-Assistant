"""Ultra Performance Engine 6.0: profiles, context limits, privacy and Ollama behavior."""
from __future__ import annotations

import asyncio
import json

import httpx
from fastapi.testclient import TestClient

from aura.app import create_app
from aura.config import Settings
from aura.database import Database
from aura.llm import Ollama
from aura.performance import (
    FAST, STANDARD, DEEP, PerformanceMonitor, bound_context, choose_profile,
)


def test_conservative_routing():
    assert choose_profile('O que é Python?') == FAST
    assert choose_profile('Define compilador') == FAST
    assert choose_profile('O que é o meu projeto Expecto?') == STANDARD
    assert choose_profile('O que significa isso?') == STANDARD
    assert choose_profile('O que é o preço atual da eletricidade?') == STANDARD
    assert choose_profile('Explica passo a passo uma matriz 4x4') == DEEP
    assert choose_profile('Demonstra a equação de Maxwell') == DEEP
    assert choose_profile('O que é Python?', mode='conservative') == STANDARD
    assert choose_profile('O que é Python?', mode='off').name == 'off'
    assert choose_profile('O que é Python?', mode='off').context_limit == 0


def test_context_bounds_and_monitor_never_include_private_text():
    long_context = 'Texto pessoal reservado.\n' * 2000
    result = bound_context(long_context, 400)
    assert len(result) <= 400
    assert result.endswith('[Contexto secundário truncado por limite de processamento.]')
    monitor = PerformanceMonitor()
    for i in range(90):
        monitor.record(profile='fast', prep_ms=i, total_ms=i + 20,
                       ttft_ms=i + 4, context_chars=0, ok=(i % 10 != 0))
    summary = monitor.summary()
    assert summary['sample_count'] == 64
    assert summary['profile_counts'] == {'fast': 64}
    assert summary['latency_ms']['first_token']['median'] is not None
    assert 'Texto pessoal reservado' not in json.dumps(summary)


def test_fast_model_skips_personal_retrieval_and_reports_metrics(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        performance_mode='balanced')
    db = Database(tmp_path / 'unit.sqlite3')
    llm = Ollama(settings, db)

    async def forbidden(*args, **kwargs):
        raise AssertionError('Fast general definition must not inspect personal memory')
    llm.memory.recall = forbidden
    llm.memory.recall_episodes = forbidden

    requests = []
    original_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != '/api/chat':
            return httpx.Response(404)
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(200, json={'message': {'content': 'É uma linguagem.'}})

    monkeypatch.setattr('aura.llm.httpx.AsyncClient',
                        lambda *args, **kwargs: original_client(
                            *args, transport=httpx.MockTransport(handler), **{
                                key: val for key, val in kwargs.items() if key != 'transport'
                            }))

    answer = asyncio.run(llm.reply('O que é Python?'))
    assert answer == 'É uma linguagem.'
    assert len(requests) == 1
    assert requests[0]['options']['num_predict'] == FAST.max_predict
    assert 'ESTRUTURAS CONSOLIDADAS' not in requests[0]['messages'][0]['content']
    stats = llm.metrics.summary()
    assert stats['profile_counts'] == {'fast': 1}
    assert stats['failed_requests'] == 0
    assert stats['latency_ms']['preparation']['median'] is not None


def test_performance_endpoint_anonymous_only(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False,
                              performance_mode='balanced'))
    with TestClient(app) as client:
        status = client.get('/api/performance/status')
        assert status.status_code == 200
        assert status.json()['mode'] == 'balanced'
        assert status.json()['metrics']['sample_count'] == 0
        assert status.json()['metrics']['stores_user_content'] is False
        assert client.get('/api/config').json()['performance_mode'] == 'balanced'


def test_config_mode_from_environment(monkeypatch):
    monkeypatch.setenv('AURA_PERFORMANCE_MODE', 'off')
    assert Settings.from_env().performance_mode == 'off'
    monkeypatch.setenv('AURA_PERFORMANCE_MODE', 'balanced')
    assert Settings.from_env().performance_mode == 'balanced'
    monkeypatch.setenv('AURA_PERFORMANCE_MODE', 'bad')
    assert Settings.from_env().performance_mode == 'balanced'
