"""6.5: measurable model routing and single-flight embeddings (mocked Ollama)."""
import asyncio
import json

import httpx
from aura.config import Settings
from aura.database import Database
from aura.llm import Ollama
from aura.memory import MemoryEngine


def test_same_question_one_embedding_request_per_reply(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        embedding_model='embeddings-local')
    db = Database(tmp_path / 'semantic.sqlite3')
    memory = MemoryEngine(settings, db)
    requests = []

    def handler(request):
        requests.append(json.loads(request.content)['input'])
        return httpx.Response(200, json={'embeddings': [[0.2, 0.4, 0.6]]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            memory._transport = lambda: client
            # Legacy behavior: two separate embedding calls for the same query.
            assert await memory._embed('mesma pergunta') == [0.2, 0.4, 0.6]
            assert await memory._embed('mesma pergunta') == [0.2, 0.4, 0.6]
            assert len(requests) == 2
            requests.clear()

            # New behavior: parallel retrievals share a single in-flight request.
            async with memory.query_scope():
                left, right = await asyncio.gather(
                    memory._embed('mesma pergunta'), memory._embed('mesma pergunta'))
                assert left == right == [0.2, 0.4, 0.6]
                assert len(requests) == 1

            # Request-scoped, not stored across future conversations.
            await memory._embed('mesma pergunta')
            assert len(requests) == 2
    asyncio.run(run())


def test_adaptive_fast_model_and_404_fallback(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        performance_mode='balanced', ollama_model='main',
                        ollama_fast_model='tiny')
    db = Database(tmp_path / 'models.sqlite3')
    llm = Ollama(settings, db)
    selected = []

    def handler(request):
        data = json.loads(request.content)
        selected.append(data['model'])
        if data['model'] == 'tiny':
            return httpx.Response(404)
        return httpx.Response(200, json={'message': {'content': 'Resposta principal.'},
                                         'eval_count': 12, 'eval_duration': 1000000000})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            llm._transport = lambda: client
            assert await llm.reply('O que é Python?') == 'Resposta principal.'
            assert selected == ['tiny', 'main']
            selected.clear()
            assert await llm.reply('O que é Python?') == 'Resposta principal.'
            assert selected == ['main']  # No repeated 404 every turn.
            assert llm.metrics.summary()['model_counts'] == {'main': 2}
    asyncio.run(run())


def test_adaptive_deep_model_and_streaming_tokens(tmp_path):
    settings = Settings(data_dir=tmp_path, database_encryption_required=False,
                        performance_mode='balanced', ollama_model='main',
                        ollama_deep_model='reasoner')
    db = Database(tmp_path / 'deep.sqlite3')
    llm = Ollama(settings, db)
    called = []

    async def notes(*args):
        return []
    llm.memory.recall = notes
    llm.memory.recall_episodes = notes

    def handler(request):
        data = json.loads(request.content)
        called.append(data['model'])
        body = ('{"message":{"content":"Olá "},"done":false}\n'
                '{"message":{"content":"mundo"},"done":false}\n'
                '{"message":{"content":""},"done":true,'
                '"eval_count":20,"eval_duration":1000000000}\n')
        return httpx.Response(200, text=body)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            llm._transport = lambda: client
            pieces = []
            async def on_token(piece):
                pieces.append(piece)
            answer = await llm.reply('Demonstra passo a passo uma equação', on_token=on_token)
            assert answer == 'Olá mundo'
            assert pieces == ['Olá ', 'mundo']
            assert called == ['reasoner']
            assert llm.metrics.summary()['latency_ms']['tokens_per_second']['median'] == 20
    asyncio.run(run())
