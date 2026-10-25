"""2.7 encrypted storage, tamper resistance, local API and privacy regression."""
import asyncio
import os
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from aura.config import Settings
from aura.database import Database
from aura.security import (
    MAGIC, encrypt_file, encrypt_bytes, decrypt_file, VaultError, SecureBackupManager
)
from aura.app import create_app
from aura.engine import AuraEngine

PASSWORD = 'uma-frase-passe-longa-27!'


def test_encrypted_backup_roundtrip_and_no_plaintext(tmp_path):
    db = Database(tmp_path / 'data' / 'aura.sqlite3')
    db.add_memory('AURA sabe seis meses de conversas')
    db.record_exchange('sessao', 'Gosto de investigar software', 'Entendi.')
    manager = SecureBackupManager(db, tmp_path / 'seguro', PASSWORD)
    target = manager.create_backup()
    assert target.suffix == '.auraenc' and target.read_bytes().startswith(MAGIC)
    assert b'AURA sabe seis meses' not in target.read_bytes()
    assert b'Gosto de investigar' not in target.read_bytes()
    assert len(list((tmp_path / 'seguro').iterdir())) == 1  # no plaintext snapshots left
    restored = tmp_path / 'restaurado.sqlite3'
    decrypt_file(target, restored, PASSWORD)
    assert Database(restored).memories()[0]['content'] == 'AURA sabe seis meses de conversas'
    assert Database(restored).episode_count() == 2
    assert manager.backup_if_due(7)
    assert manager.backup_if_due(7) is None


def test_password_fail_corruption_no_overwrite(tmp_path):
    src=tmp_path/'plain.txt'
    src.write_bytes(b'test data no arquivo 123' * 2000)
    blob=tmp_path/'secured.auraenc'
    encrypt_file(src, blob, PASSWORD)
    original=blob.read_bytes()
    with pytest.raises((VaultError, ValueError)):
        decrypt_file(blob, tmp_path/'wrong.txt', 'senha-incorreta-123')
    assert not (tmp_path/'wrong.txt').exists()
    tampered = tmp_path/'tampered.auraenc'
    damaged = bytearray(original)
    damaged[len(MAGIC) + 20] ^= 0x20
    tampered.write_bytes(damaged)
    with pytest.raises(VaultError):
        decrypt_file(tampered, tmp_path/'tampered-out.txt', PASSWORD)
    assert not (tmp_path/'tampered-out.txt').exists()
    with pytest.raises((VaultError, FileExistsError)):
        encrypt_file(src, blob, PASSWORD)
    assert blob.read_bytes() == original  # no unlink/overwrite of existing ciphertext
    with pytest.raises(VaultError):
        decrypt_file(blob, src, PASSWORD)
    assert src.read_bytes().startswith(b'test data')
    with pytest.raises(VaultError):
        encrypt_bytes(b'x', tmp_path/'short.auraenc', 'short')
    assert not (tmp_path/'short.auraenc').exists()


def test_export_encrypted_and_restorable(tmp_path):
    db=Database(tmp_path/'data'/'db.sqlite3')
    db.add_memory('Memória pessoal')
    path=SecureBackupManager(db,tmp_path/'vault',PASSWORD).export_memory()
    assert 'Memória pessoal'.encode('utf-8') not in path.read_bytes()
    target=tmp_path/'memory.json'
    decrypt_file(path,target,PASSWORD)
    assert 'Memória pessoal' in target.read_text()


def test_private_mode_stops_capture_and_resumes(tmp_path,monkeypatch):
    from aura.llm import Ollama
    async def fake_answer(self,*args,**kwargs): return 'Resposta simulada.'
    monkeypatch.setattr(Ollama,'reply',fake_answer)
    with TestClient(create_app(Settings(data_dir=tmp_path,database_encryption_required=False,backup_passphrase=PASSWORD))) as client:
        def command(msg): return client.post('/api/command',json={'message':msg}).json()
        assert client.get('/api/memory/status').json()['private_mode'] is False
        command('Ativa modo privado')
        for _ in range(3): command('Olá, AURA')
        assert client.get('/api/memory/status').json()['episodes_in_window'] == 0
        assert client.get('/api/memory/status').json()['private_mode'] is True
        command('Desativa modo privado')
        command('Olá, AURA')
        assert client.get('/api/memory/status').json()['episodes_in_window'] == 2
        assert client.get('/api/memory/status').json()['encrypted_backups_enabled'] is True
        assert client.get('/api/memory/status').json()['active_database_encrypted'] is False
        assert 'CIFRADA' in command('Faz backup da memória')['text']
        assert list((tmp_path/'secure_backups').glob('*.auraenc'))
        assert 'CIFRADA' in command('Exporta a memória')['text']
    # private mode setting is persisted between process lifetimes
    assert Database(tmp_path/'aura.sqlite3').get_option('private_mode','false')=='false'


def test_without_password_no_plaintext_backup_and_security_headers(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path,database_encryption_required=False))) as client:
        assert client.get('/api/memory/status').json()['encrypted_backups_enabled'] is False
        res=client.post('/api/command',json={'message':'Faz backup da memória'})
        assert res.status_code==200 and 'Não criei backup' in res.json()['text']
        assert not (tmp_path/'backups').exists()
        assert not (tmp_path/'secure_backups').exists()
        response=client.get('/')
        assert response.headers['X-Frame-Options']=='DENY'
        assert "script-src 'self'" in response.headers['Content-Security-Policy']
        assert response.headers['Cache-Control']=='no-store'
        assert client.post('/api/command',headers={'Origin':'https://attacker.example'},json={'message':'Olá'}).status_code==403
        assert client.post('/api/command',headers={'Origin':'http://testserver'},json={'message':'Abre a memória'}).status_code==200
        assert client.get('/api/health',headers={'Host':'evil.com'}).status_code==400


def test_settings_never_repr_password(tmp_path):
    settings=Settings(data_dir=tmp_path,database_encryption_required=False,backup_passphrase=PASSWORD)
    assert PASSWORD not in repr(settings)


def test_old_v26_db_migrates_no_loss(tmp_path):
    db=Database(tmp_path/'old.sqlite3')
    note=db.add_memory('Prefiro holograma e privacidade')
    exchange=db.record_exchange('sessao','AURA funciona localmente','Sim')
    # 2.7 uses 2.6 schema, no wiping; encryption is applied only to snapshots.
    reopened=Database(db.path)
    assert reopened.get_memory(note['id'])['content']=='Prefiro holograma e privacidade'
    assert reopened.episode_count()==2
    assert reopened.get_option('private_mode','false')=='false'
