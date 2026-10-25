"""Encrypted SQLCipher storage and explicit no-overwrite 2.7 -> 2.8 migration.

No plaintext fallback for production. SQLCipher is a required dependency for
creating/opening encrypted databases; SQLite cannot read them.
"""
from __future__ import annotations
import argparse
import getpass
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

SQLITE_HEADER = b'SQLite format 3\x00'


class VaultLockedError(RuntimeError):
    """Database encryption dependency, passphrase or format problem."""


def sqlcipher_backend():
    try:
        import sqlcipher3
    except ImportError as exc:
        raise VaultLockedError(
            'SQLCipher não está instalado. Executa: python -m pip install sqlcipher3>=0.6.2'
        ) from exc
    return sqlcipher3


def cipher_operational_errors():
    try:
        backend = sqlcipher_backend()
        return (sqlite3.OperationalError, backend.OperationalError)
    except VaultLockedError:
        return (sqlite3.OperationalError,)


def _literal(value: str) -> str:
    """SQLCipher PRAGMA KEY cannot be bound with ?; quote apostrophes safely."""
    if not isinstance(value, str) or '\x00' in value:
        raise VaultLockedError('Chave ou caminho inválido.')
    return "'" + value.replace("'", "''") + "'"


def is_plaintext_sqlite(path: Path) -> bool:
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        return False
    with path.open('rb') as f:
        return f.read(16) == SQLITE_HEADER


def encrypted_connection(path: Path, passphrase: str, *, create: bool = True):
    """Fail closed for missing key, plaintext SQLite or missing SQLCipher."""
    path = Path(path)
    if not isinstance(passphrase, str) or len(passphrase) < 12:
        raise VaultLockedError('A base cifrada exige frase-passe de pelo menos 12 caracteres.')
    if path.is_file() and is_plaintext_sqlite(path):
        raise VaultLockedError('Base antiga sem cifragem detetada. Migra com: python -m aura.vault migrate')
    if not create and not path.is_file():
        raise VaultLockedError('Base cifrada não encontrada.')
    backend = sqlcipher_backend()
    db = backend.connect(str(path), timeout=10)
    try:
        db.execute('PRAGMA key = ' + _literal(passphrase))
        version = db.execute('PRAGMA cipher_version').fetchone()
        if not version or not version[0]:
            raise VaultLockedError('Este driver não suporta SQLCipher; acesso recusado.')
        # Trigger real file read and key verification before any schema write.
        db.execute('SELECT count(*) FROM sqlite_master').fetchone()
        db.execute('PRAGMA cipher_memory_security = ON')
        db.execute('PRAGMA temp_store = MEMORY')
        db.execute('PRAGMA secure_delete = ON')
        return db
    except Exception as exc:
        db.close()
        if isinstance(exc, VaultLockedError):
            raise
        raise VaultLockedError('Não foi possível abrir a memória cifrada: chave errada, versão incompatível ou dados danificados.') from exc


def verify_encrypted_database(path: Path, passphrase: str) -> bool:
    if is_plaintext_sqlite(path):
        raise VaultLockedError('Ficheiro não cifrado.')
    with closing(encrypted_connection(path, passphrase, create=False)) as db:
        check = db.execute('PRAGMA integrity_check').fetchone()
        if not check or check[0] != 'ok':
            raise VaultLockedError('Falha de integridade SQLite.')
        # SQLCipher cipher_integrity_check returns zero rows when healthy.
        problems = db.execute('PRAGMA cipher_integrity_check').fetchall()
        if problems:
            raise VaultLockedError('Falha de integridade criptográfica.')
    return True


def migrate_plaintext(source: Path, destination: Path, passphrase: str) -> Path:
    """Create a separate encrypted DB from a coherent snapshot; retain original.

    IMPORTANT: the temporary plaintext snapshot is written in a private directory,
    and securely erasing it cannot be guaranteed on SSDs/modern filesystems.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.exists():
        raise VaultLockedError('O destino tem de ser diferente e não pode existir.')
    if not is_plaintext_sqlite(source):
        raise VaultLockedError('A origem deve ser uma base SQLite antiga, sem cifragem.')
    if len(passphrase) < 12:
        raise VaultLockedError('Frase-passe demasiado curta (mínimo 12 caracteres).')
    backend = sqlcipher_backend()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Restrict access while conversion takes place, for snapshot and new vault.
    with tempfile.TemporaryDirectory(prefix='.aura-migration-', dir=destination.parent) as folder:
        private_dir = Path(folder)
        if os.name == 'posix':
            private_dir.chmod(0o700)
        snapshot = private_dir / 'snapshot.sqlite3'
        staged = private_dir / 'encrypted.sqlite3'
        with sqlite3.connect(str(source), timeout=15) as plain:
            with sqlite3.connect(str(snapshot)) as consistent:
                plain.backup(consistent)
        if os.name == 'posix':
            snapshot.chmod(0o600)
        # SQLCipher must be in plaintext mode for the source, encrypted for ATTACH.
        with closing(backend.connect(str(snapshot), timeout=15)) as db:
            version = db.execute('PRAGMA cipher_version').fetchone()
            if not version or not version[0]:
                raise VaultLockedError('Driver SQLCipher inválido.')
            db.execute('ATTACH DATABASE ' + _literal(str(staged)) + ' AS encrypted KEY ' + _literal(passphrase))
            try:
                db.execute("SELECT sqlcipher_export('encrypted')").fetchone()
                db.commit()
            finally:
                db.execute('DETACH DATABASE encrypted')
        if not staged.exists() or is_plaintext_sqlite(staged):
            raise VaultLockedError('A migração não produziu uma base cifrada.')
        verify_encrypted_database(staged, passphrase)
        # Check critical data copied, never silently drop six-month history.
        with sqlite3.connect(str(snapshot)) as original, closing(encrypted_connection(staged, passphrase, create=False)) as cipher:
            for table in ('memories', 'conversation_episodes', 'knowledge', 'temporal_facts', 'memory_relations'):
                present = original.execute('SELECT count(*) FROM sqlite_master WHERE type=\'table\' AND name=?',(table,)).fetchone()[0]
                if present:
                    left = original.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]
                    right = cipher.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]
                    if left != right:
                        raise VaultLockedError(f'Contagem divergente na tabela: {table}.')
        # Hardlink is atomic, never replaces a concurrent newly-created file.
        try:
            os.link(staged, destination)
        except FileExistsError as exc:
            raise VaultLockedError('Destino já existe; não foi substituído.') from exc
        if os.name == 'posix':
            destination.chmod(0o600)
    return destination


def cli() -> None:
    parser = argparse.ArgumentParser(description='AURA 2.8: migrar e verificar memória SQLCipher.')
    commands = parser.add_subparsers(dest='command', required=True)
    m = commands.add_parser('migrate', help='Migrar ficheiro SQLite 2.7 sem sobrescrever a origem.')
    m.add_argument('--source', default='data/aura.sqlite3')
    m.add_argument('--out', default='data/aura.encrypted.sqlite3')
    v = commands.add_parser('verify', help='Verificar um ficheiro SQLCipher sem o alterar.')
    v.add_argument('--db', default='data/aura.sqlite3')
    args = parser.parse_args()
    phrase = getpass.getpass('Frase-passe da base de dados (não é mostrada): ')
    try:
        if args.command == 'migrate':
            repeat = getpass.getpass('Repete a frase-passe: ')
            if repeat != phrase:
                raise VaultLockedError('As frases-passe são diferentes.')
            print('Migração concluída:', migrate_plaintext(Path(args.source), Path(args.out), phrase))
            print('Base antiga preservada. Lê o README antes de substituir a instalação ativa.')
        else:
            verify_encrypted_database(Path(args.db), phrase)
            print('Integridade e chave verificadas.')
    except (VaultLockedError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f'Erro: {exc}\n')


if __name__ == '__main__':
    cli()
