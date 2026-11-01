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
