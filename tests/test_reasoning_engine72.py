import asyncio
import json
import pytest
from aura.reasoning_engine72 import ReasoningEngine72, exact_request, inspect_answer


def test_exact_math_strict_grammar():
    assert exact_request('calcula: (15 + 3) / 4') == '9/2'
    assert exact_request('calcula: 1/0') is None
    assert exact_request('calcula: __import__("os")') is None
    assert exact_request('Lembra-te de calcula 2+2') is None


def test_code_never_executed_and_syntax_is_not_correctness(tmp_path):
    victim = tmp_path / 'must-not-exist'
    result = inspect_answer(f'```python\nopen({str(victim)!r}, "w").write("unsafe")\n```')
    assert result['checks'] == ['python_syntax_only']
    assert not victim.exists()
    assert inspect_answer('```python\ndef wrong(:\n```')['issues']
    assert inspect_answer('2+2 = 5')['issues']


def test_exact_answer_does_not_call_model():
    async def forbidden(prompt): raise AssertionError('must not call')
    result = asyncio.run(ReasoningEngine72(forbidden, model='test').run('calcula 12*13'))
    assert result['answer'] == '156' and result['model_calls'] == 0


def test_same_model_never_claims_independence():
    async def generate(prompt): return 'An unverified answer'
    async def forbidden(prompt): raise AssertionError('same model is not independent')
    result = asyncio.run(ReasoningEngine72(generate, model='x', review=forbidden, review_model='x').run('Question?'))
    assert result['status'] == 'unverified_proposal'


def test_refutation_corrected_once_and_rechecked():
    calls = []
    async def generate(prompt):
        calls.append('generate')
        return '2+2 = 5' if len(calls) == 1 else '2+2 = 4'
    async def review(prompt):
        calls.append('review')
        verdict = 'refuted' if len(calls) == 2 else 'supported'
        return json.dumps({'verdict': verdict, 'issues': ['arithmetic error'] if verdict == 'refuted' else [], 'evidence_ids': []})
    result = asyncio.run(ReasoningEngine72(generate, model='a', review=review, review_model='b').run('Explain 2+2'))
    assert result['status'] == 'reviewed_proposal'
    assert result['answer'] == '2+2 = 4' and calls == ['generate', 'review', 'generate', 'review']


@pytest.mark.parametrize('raw', ['not json', '[]', '{"verdict":"supported","issues":[],"evidence_ids":["invented"]}'])
def test_invalid_review_abstains(raw):
    async def generate(prompt): return 'Proposal'
    async def review(prompt): return raw
    result = asyncio.run(ReasoningEngine72(generate, model='a', review=review, review_model='b').run('Question?'))
    assert result['status'] == 'abstained' and not result['answer']


def test_research_needs_sources_and_review():
    async def forbidden(prompt): raise AssertionError('no source no inference')
    result = asyncio.run(ReasoningEngine72(forbidden, model='a').run('Question?', domain='research'))
    assert result['status'] == 'abstained'
    async def generate(prompt): return 'Unsupported claim'
    result = asyncio.run(ReasoningEngine72(generate, model='a').run('Question?', domain='research', evidence=[{'id': 's', 'text': 'source'}]))
    assert result['status'] == 'abstained'


def test_timeout_and_cancellation_do_not_publish_drafts():
    async def slow(prompt): await asyncio.sleep(1)
    result = asyncio.run(ReasoningEngine72(slow, model='a', timeout=.001).run('Question?'))
    assert result['status'] == 'abstained'
    async def cancel(prompt): raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ReasoningEngine72(cancel, model='a').run('Question?'))


def test_normal_command_uses_exact_solver(tmp_path):
    from aura.config import Settings
    from aura.database import Database
    from aura.engine import AuraEngine
    engine = AuraEngine(Settings(data_dir=tmp_path, database_encryption_required=False), Database(tmp_path / 'db'))
    async def forbidden(*args, **kwargs): raise AssertionError('No LLM for exact math')
    engine.llm.reply = forbidden
    result = asyncio.run(engine.command('calcula: (123 + 7) * 3'))
    assert result['text'] == '390'
    assert result['data']['verification'] == 'exact_arithmetic'


def test_latest_alias_is_not_a_second_model():
    async def generate(prompt): return 'proposal'
    async def forbidden(prompt): raise AssertionError('same weights alias')
    result = asyncio.run(ReasoningEngine72(generate, model='x', review=forbidden, review_model='x:latest').run('Question?'))
    assert result['status'] == 'unverified_proposal'


def test_repeated_bad_revision_is_withheld():
    async def generate(prompt): return '2+2 = 9'
    async def review(prompt): return '{"verdict":"supported","issues":[],"evidence_ids":[]}'
    result = asyncio.run(ReasoningEngine72(generate, model='x', review=review, review_model='y').run('Explain addition'))
    assert result['status'] == 'abstained' and result['answer'] == ''
    assert result['model_calls'] == 4


def test_measured_adapter_streams_internally_without_publishing_draft():
    import httpx
    from aura.reasoning_engine72 import LocalReasoningModel
    from aura.performance import PerformanceMonitor
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(.01)
            yield b'{"message":{"content":"checked"},"done":false}\n'
            await asyncio.sleep(.02)
            yield b'{"done":true,"eval_count":20,"eval_duration":2000000000}\n'
    async def run():
        monitor = PerformanceMonitor()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=Stream()))) as client:
            adapter = LocalReasoningModel(client, 'http://127.0.0.1:11434', 'reviewer:1', metrics=monitor)
            assert await adapter('Check this problem') == 'checked'
            row = monitor.recent()[0]
            assert row['ok'] and 0 < row['ttft_ms'] < row['total_ms']
            assert row['tokens_per_second'] == 10
            assert 'checked' not in json.dumps(row)
    asyncio.run(run())


def test_specialist_command_with_distinct_reviewer(tmp_path, monkeypatch):
    import httpx
    from aura.config import Settings
    from aura.database import Database
    from aura.engine import AuraEngine
    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
        reasoning_code_model='coder:1', reasoning_review_model='critic:1')
    engine = AuraEngine(settings, Database(tmp_path / 'db'))
    models = []
    original = httpx.AsyncClient
    def handler(req):
        if req.url.path == '/api/tags':
            return httpx.Response(200, json={'models':[{'name':'coder:1','digest':'c'},{'name':'critic:1','digest':'r'}]})
        data = json.loads(req.content)
        models.append(data['model'])
        content = '```python\nprint(4)\n```' if data['model'] == 'coder:1' else '{"verdict":"supported","issues":[],"evidence_ids":[]}'
        return httpx.Response(200, text=json.dumps({'message':{'content':content},'done':False})+'\n'+json.dumps({'done':True})+'\n')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    result = asyncio.run(engine.command('resolve com verificação: escreve Python para imprimir quatro'))
    assert models == ['coder:1','critic:1']
    assert result['data']['status'] == 'reviewed_proposal'
    assert 'não constitui prova' in result['text']
    assert len(engine.llm.metrics.recent()) == 2
