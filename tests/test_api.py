from fastapi.testclient import TestClient
from aura.app import create_app
from aura.config import Settings


def test_same_origin_and_command_api(tmp_path):
    app = create_app(Settings(data_dir=tmp_path,database_encryption_required=False))
    with TestClient(app) as client:
        index = client.get('/')
        assert index.status_code == 200
        assert 'EXPECTO' in index.text
        assert client.get('/static/app.js').status_code == 200
        memory = client.post('/api/command', json={'message':'Abre a memória'})
        assert memory.status_code == 200
        assert memory.json()['action']['panel'] == 'memory'
        assert client.post('/api/command', json={'message':''}).status_code == 422
        assert client.get('/api/panel/invalid').status_code == 404
