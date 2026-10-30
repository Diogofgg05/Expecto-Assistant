"""API regression: isolated, read-only code inspection, same-origin protection."""
from fastapi.testclient import TestClient
from aura.app import create_app
from aura.config import Settings


def test_code_inspection_returns_findings_and_syntax_error(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        response = client.post('/api/code/inspect', json={
            'code': "import subprocess\nsubprocess.run('echo hello', shell=True)\n"})
        assert response.status_code == 200
        body = response.json()
        assert body['valid_syntax'] is True
        assert [f['rule'] for f in body['findings']] == ['shell-subprocess']
        assert body['verification'] == 'static_heuristics_no_execution'

        bad = client.post('/api/code/inspect', json={'code': 'def oops(:\n'})
        assert bad.status_code == 200
        assert bad.json()['valid_syntax'] is False
        assert bad.json()['syntax_error']['line'] == 1


def test_code_inspection_enforces_limits_and_origin(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    with TestClient(app) as client:
        assert client.post('/api/code/inspect', json={'code': ''}).status_code == 422
        assert client.post('/api/code/inspect', json={'code': 'x' * 25001}).status_code == 422
        blocked = client.post('/api/code/inspect', json={'code': 'pass'},
                              headers={'origin': 'https://other.example'})
        assert blocked.status_code == 403
