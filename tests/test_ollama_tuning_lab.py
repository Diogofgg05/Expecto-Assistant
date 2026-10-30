"""Local CPU-only tests: transport and model are synthetic, not real Ollama."""
import asyncio
import json
import pytest
import httpx

from aura import ollama_tuning_lab as lab


def test_safety_bounds():
    with pytest.raises(ValueError):
        asyncio.run(lab.tune('qwen3', url='https://example.com:11434'))
    with pytest.raises(ValueError):
        asyncio.run(lab.tune('qwen3', baseline_ctx=4096, candidate_ctx=4096))
    with pytest.raises(ValueError):
        asyncio.run(lab.tune('qwen3', runs=1))


def test_decision_gates():
    base = dict(runs=20, correct=20, errors=0, p50_ms=120, p95_ms=160)
    cand = dict(runs=20, correct=20, errors=0, p50_ms=90, p95_ms=130)
    assert lab._decision(base, cand, 5)[0] == 'candidate_for_review'
    assert lab._decision(base, dict(cand, correct=19), 5)[0] == 'reject'
    assert lab._decision(dict(base, correct=19), cand, 5)[0] == 'inconclusive'
    assert lab._decision(base, dict(cand, p95_ms=165), 5)[0] == 'inconclusive'


def test_mock_transport_paired_trials(monkeypatch):
    calls=[]
    actual=httpx.AsyncClient
    def handler(request):
        data=json.loads(request.content)
        calls.append(data['options']['num_ctx'])
        question=data['messages'][0]['content']
        expected={'Calcula 7 + 5.': '12', 'Calcula 9 * 3.': '27', 'Calcula 100 - 42.':'58'}
        number=next(v for k,v in expected.items() if question.startswith(k))
        return httpx.Response(200, json={'message': {'content': json.dumps({'answer':number})},
                                         'eval_count':4, 'eval_duration':40000000})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs: actual(transport=httpx.MockTransport(handler), **kwargs))
    async def identity(url, model):
        return {'model_digest':'a'*64,'hardware':{'cpu_model':'mock'},'workload_sha256':'b'*64,'schema_version':2}
    monkeypatch.setattr(lab,'collect_identity',identity)
    output=asyncio.run(lab.tune('qwen3',runs=10,warmup=1))
    assert output['baseline']['correct']==10
    assert output['candidate']['correct']==10
    assert output['baseline']['tokens_per_second_p50']==100.0
    assert len(calls)==22
    assert set(calls)=={8192,4096}
    assert output['decision'] in ('candidate_for_review','inconclusive')
    assert 'samples' not in output


def test_bad_model_answers_rejected(monkeypatch):
    def handler(request):
        data=json.loads(request.content)
        wrong=(data['options']['num_ctx']==4096)
        return httpx.Response(200,json={'message':{'content': json.dumps({'answer':'0' if wrong else '12'})}})
    actual=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw: actual(transport=httpx.MockTransport(handler), **kw))
    async def identity(url,model): return {'model_digest':'a'*64}
    monkeypatch.setattr(lab,'collect_identity',identity)
    # Probe rotation makes some baseline tests intentionally fail; gate must be inconclusive.
    out=asyncio.run(lab.tune('qwen3',runs=10,warmup=0))
    assert out['decision'] == 'inconclusive'
    assert out['candidate']['correct'] == 0


def test_candidate_wrong_answers_are_rejected(monkeypatch):
    def handler(request):
        data = json.loads(request.content)
        question = data['messages'][0]['content']
        expected = {'Calcula 7 + 5.': '12', 'Calcula 9 * 3.': '27',
                    'Calcula 100 - 42.': '58'}
        number = next(v for k, v in expected.items() if question.startswith(k))
        if data['options']['num_ctx'] == 4096:
            number = '0'
        return httpx.Response(200, json={'message': {'content': json.dumps({'answer': number})}})
    actual = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient',
                        lambda **kw: actual(transport=httpx.MockTransport(handler), **kw))
    async def identity(url, model): return {'model_digest': 'a' * 64}
    monkeypatch.setattr(lab, 'collect_identity', identity)
    result = asyncio.run(lab.tune('qwen3', runs=10, warmup=0))
    assert result['baseline']['correct'] == 10
    assert result['candidate']['correct'] == 0
    assert result['decision'] == 'reject'
