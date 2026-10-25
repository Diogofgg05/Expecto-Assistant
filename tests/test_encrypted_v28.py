"""Safety tests; marked tests execute full SQLCipher only when installed."""
from pathlib import Path
import sqlite3
import pytest
from aura.config import Settings
from aura.database import Database
from aura.app import create_app
from aura.security import SecureBackupManager, decrypt_file
from aura import vault

KEY = "frase-passe-muito-segura-2026"
BACKUP_KEY = 'uma-outra-frase-passe-comprida'


def test_production_refuses_missing_secret_without_creating_db(tmp_path):
    with pytest.raises(vault.VaultLockedError, match='exige a chave'):
        create_app(Settings(data_dir=tmp_path))
    assert not (tmp_path/'aura.sqlite3').exists()


def test_plaintext_db_rejected_when_password_specified(tmp_path):
    path = tmp_path / 'aura.sqlite3'
    plain=Database(path)
    plain.add_memory('Não quero perder a memória anterior')
    before=path.read_bytes()
    with pytest.raises(vault.VaultLockedError, match='sem cifragem'):
        Database(path,KEY,True)
    assert path.read_bytes() == before


def test_no_plaintext_fallback_if_backend_is_missing(tmp_path,monkeypatch):
    def unavailable():
        raise vault.VaultLockedError('Driver indisponível')
    monkeypatch.setattr(vault,'sqlcipher_backend',unavailable)
    with pytest.raises(vault.VaultLockedError,match='Driver indisponível'):
        Database(tmp_path/'new.sqlite3',KEY,True)
    assert not (tmp_path/'new.sqlite3').exists()


def test_database_settings_dont_leak_secret(tmp_path):
    settings=Settings(data_dir=tmp_path,database_passphrase=KEY)
    assert KEY not in repr(settings)


def test_key_sql_quoting_and_invalid_bytes():
    assert vault._literal("sa'fe") == "'sa''fe'"
    with pytest.raises(vault.VaultLockedError):
        vault._literal('invalid\x00name')


def test_migration_never_overwrites_existing_db(tmp_path):
    source=tmp_path/'original.sqlite3'
    Database(source).add_memory('A memória deve sobreviver à atualização')
    dest=tmp_path/'destination.sqlite3'
    dest.write_bytes(b'keep untouched')
    original=source.read_bytes()
    with pytest.raises(vault.VaultLockedError,match='não pode existir'):
        vault.migrate_plaintext(source,dest,KEY)
    assert source.read_bytes()==original
    assert dest.read_bytes()==b'keep untouched'


def test_migration_refuses_short_password_or_wrong_source(tmp_path):
    db=tmp_path/'old.sqlite3'; Database(db)
    with pytest.raises(vault.VaultLockedError,match='curta'):
        vault.migrate_plaintext(db,tmp_path/'new.sqlite3','1234')
    with pytest.raises(vault.VaultLockedError,match='origem'):
        vault.migrate_plaintext(tmp_path/'missing.db',tmp_path/'new.sqlite3',KEY)
    assert not (tmp_path/'new.sqlite3').exists()


def test_plaintext_mode_must_be_explicit_in_api_tests(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, database_encryption_required=False))
    assert app.state.db.encrypted is False


@pytest.mark.skipif(pytest.importorskip('importlib').util.find_spec('sqlcipher3') is None,
                    reason='Requer wheel sqlcipher3 (a instalação de teste está offline)')
def test_real_sqlcipher_roundtrip_migrate_and_encrypted_backup(tmp_path):
    old=tmp_path/'old.sqlite3'
    db=Database(old)
    db.add_memory('Utilizo a memória de seis meses')
    db.record_exchange('sessao','Guardei uma conversa antiga','Vou recordar-me')
    converted=tmp_path/'new.sqlite3'
    vault.migrate_plaintext(old,converted,KEY)
    assert vault.verify_encrypted_database(converted,KEY)
    assert converted.read_bytes()[:16] != vault.SQLITE_HEADER
    encrypted=Database(converted,KEY,True)
    assert encrypted.episode_count()==2
    assert 'seis meses' in encrypted.memories()[0]['content']
    encrypted.add_memory('Nova nota cifrada')
    assert len(Database(converted,KEY,True).memories())==2
    with pytest.raises(vault.VaultLockedError):
        Database(converted,'senha-invalida-e-longa',True)
    manager=SecureBackupManager(encrypted,tmp_path/'backup',BACKUP_KEY)
    protected=manager.create_backup()
    assert protected.exists()
    decrypted=tmp_path/'from_backup.sqlite3'
    decrypt_file(protected,decrypted,BACKUP_KEY)
    assert decrypted.read_bytes()[:16] != vault.SQLITE_HEADER
    assert len(Database(decrypted,KEY,True).memories())==2
    # Existing plaintext version remains untouched for rollback.
    assert len(Database(old).memories())==1
