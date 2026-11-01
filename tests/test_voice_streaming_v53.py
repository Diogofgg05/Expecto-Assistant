"""Regression tests for streaming responses and the unchanged intent router."""
import json

from fastapi.testclient import TestClient

from aura.app import create_app
from aura.config import Settings


def test_streaming_preserves_intents(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        response = client.post('/api/command/stream', json={'message': 'Abre a memória'})
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert [e['type'] for e in events] == ['final']
        assert events[-1]['payload']['action']['panel'] == 'memory'
        assert events[-1]['metrics']['total_ms'] >= 0
        assert events[-1]['metrics']['ttft_ms'] is None


def test_streaming_chat_sends_tokens_and_final_reply(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    async def fake_reply(question, history, *, on_token=None):
        assert question == 'Explica Python em duas frases.'
        if on_token:
            await on_token('Olá. ')
            await on_token('Python é uma linguagem.')
        return 'Olá. Python é uma linguagem.'
    app.state.engine.llm.reply = fake_reply

    with TestClient(app) as client:
        response = client.post('/api/command/stream', json={
            'message': 'Explica Python em duas frases.', 'session_id': 'stream-test'
        })
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert [item['type'] for item in events] == ['token', 'token', 'final']
        assert ''.join(item['text'] for item in events[:-1]) == events[-1]['payload']['text']
        assert events[-1]['payload']['spoken'] == events[-1]['payload']['text']
        assert events[-1]['metrics']['ttft_ms'] >= 0
        assert events[-1]['metrics']['total_ms'] >= events[-1]['metrics']['ttft_ms']


def test_existing_nonstream_endpoint_still_works(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        response = client.post('/api/command', json={'message': 'Abre a memória'})
        assert response.status_code == 200
        assert response.json()['action']['panel'] == 'memory'


def test_full_stream_survives_bounded_queue_pressure(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    async def many_tokens(question, history, *, on_token=None):
        for _ in range(220):
            await on_token('A')
        return 'A' * 220
    app.state.engine.llm.reply = many_tokens
    with TestClient(app) as client:
        response = client.post('/api/command/stream', json={'message': 'Uma pergunta nova sobre IA.'})
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert [event['type'] for event in events].count('token') == 220
        assert events[-1]['type'] == 'final'
        assert events[-1]['payload']['text'] == 'A' * 220


def test_failed_stream_does_not_save_partial_response(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    async def failed_reply(question, history, *, on_token=None):
        await on_token('Resposta incompleta...')
        raise RuntimeError('stream disconnected mid-response')
    app.state.engine.llm.reply = failed_reply
    with TestClient(app) as client:
        response = client.post('/api/command/stream', json={
            'message': 'Explica uma nova linguagem de programação.', 'session_id': 'failed-test'
        })
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert [event['type'] for event in events] == ['token', 'error']
        assert app.state.db.episode_count(6) == 0


def test_model_residency_setting_is_validated(monkeypatch):
    monkeypatch.setenv('AURA_OLLAMA_KEEP_ALIVE', '0m')
    assert Settings.from_env().ollama_keep_alive == '0m'
    monkeypatch.setenv('AURA_OLLAMA_KEEP_ALIVE', '20m')
    assert Settings.from_env().ollama_keep_alive == '20m'
    monkeypatch.setenv('AURA_OLLAMA_KEEP_ALIVE', 'bad value')
    assert Settings.from_env().ollama_keep_alive == '10m'
