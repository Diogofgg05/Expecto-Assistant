"""AURA 2.7: authenticated encrypted backups and exports.

Format (v1): 8-byte magic + 16-byte salt + 12-byte nonce + AES-GCM
ciphertext + 16-byte authentication tag. Scrypt derives a per-file AES-256 key.
The active SQLCipher database is encrypted separately by aura.vault.
"""
from __future__ import annotations
import argparse
import getpass
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b'AURASEC1'
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
HEADER_SIZE = len(MAGIC) + SALT_BYTES + NONCE_BYTES
CHUNK_SIZE = 1024 * 1024


class VaultError(Exception):
    """Invalid password, damaged encrypted file, or unsupported format."""


def _key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or len(passphrase) < 12:
        raise VaultError('A frase-passe deve ter pelo menos 12 caracteres.')
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode('utf-8'))


def _private_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'posix':
        path.chmod(0o700)


def _exclusive_file(path: Path):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    return os.fdopen(fd, 'wb')


def encrypt_file(source: Path, destination: Path, passphrase: str) -> Path:
    """Encrypt a file using streaming AES-256-GCM; refuses overwrites."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise VaultError('A entrada e a saída têm de ser ficheiros diferentes.')
    salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
    key = _key(passphrase, salt)
    header = MAGIC + salt + nonce
    _private_folder(destination.parent)
    created = False
    try:
        if destination.exists():
            raise VaultError('O ficheiro de destino já existe.')
        with source.open('rb') as raw, _exclusive_file(destination) as out:
            created = True
            out.write(header)
            cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            cipher.authenticate_additional_data(header)
            while block := raw.read(CHUNK_SIZE):
                out.write(cipher.update(block))
            out.write(cipher.finalize())
            out.write(cipher.tag)
        return destination
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def encrypt_bytes(data: bytes, destination: Path, passphrase: str) -> Path:
    """Encrypted export without an intermediate plaintext JSON file."""
    salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
    key = _key(passphrase, salt)
    header = MAGIC + salt + nonce
    destination = Path(destination)
    _private_folder(destination.parent)
    created = False
    try:
        if destination.exists():
            raise VaultError('O ficheiro de destino já existe.')
        with _exclusive_file(destination) as out:
            created = True
            out.write(header)
            cipher = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
            cipher.authenticate_additional_data(header)
            for start in range(0, len(data), CHUNK_SIZE):
                out.write(cipher.update(data[start:start + CHUNK_SIZE]))
            out.write(cipher.finalize())
            out.write(cipher.tag)
        return destination
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def decrypt_file(source: Path, destination: Path, passphrase: str) -> Path:
    """Verify authentication before publishing decrypted data.

    Temporary plaintext may exist briefly during restoration. Restore to a new
    pathname with AURA shut down, not directly over a live database.
    """
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise VaultError('O destino já existe. A restauração nunca sobrescreve ficheiros.')
    if source.stat().st_size < HEADER_SIZE + TAG_BYTES:
        raise VaultError('Ficheiro cifrado incompleto.')
    _private_folder(destination.parent)
    temporary = None
    try:
        with source.open('rb') as raw:
            header = raw.read(HEADER_SIZE)
            if not header.startswith(MAGIC):
                raise VaultError('Formato de backup desconhecido.')
            salt = header[len(MAGIC):len(MAGIC) + SALT_BYTES]
            nonce = header[len(MAGIC) + SALT_BYTES:]
            key = _key(passphrase, salt)
            length = source.stat().st_size - HEADER_SIZE - TAG_BYTES
            raw.seek(-TAG_BYTES, os.SEEK_END)
            tag = raw.read(TAG_BYTES)
            raw.seek(HEADER_SIZE)
            decipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decipher.authenticate_additional_data(header)
            fd, filename = tempfile.mkstemp(prefix='.aura-restore-', dir=destination.parent)
            temporary = Path(filename)
            if os.name == 'posix':
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as out:
                while length:
                    piece = raw.read(min(CHUNK_SIZE, length))
                    if not piece:
                        raise VaultError('Ficheiro cifrado truncado.')
                    out.write(decipher.update(piece))
                    length -= len(piece)
                out.write(decipher.finalize())  # raises InvalidTag if passphrase/tampering wrong
        if destination.exists():
            raise VaultError('O destino já existe.')
        os.link(temporary, destination)  # fail rather than overwrite if destination appeared
        return destination
    except InvalidTag as exc:
        raise VaultError('Palavra-passe errada ou dados corrompidos.') from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class SecureBackupManager:
    def __init__(self, database, folder: Path, passphrase: str = ''):
        self.database = database
        self.folder = Path(folder)
        self.passphrase = passphrase

    @property
    def enabled(self) -> bool:
        return len(self.passphrase) >= 12

    def _check(self):
        if not self.enabled:
            raise VaultError('Backup protegido indisponível: configura uma frase-passe de 12+ caracteres no arranque.')

    def create_backup(self) -> Path:
        """Consistent snapshot -> encrypted file -> remove temporary plaintext snapshot."""
        self._check()
        _private_folder(self.folder)
        with tempfile.TemporaryDirectory(prefix='.aura-snapshot-', dir=self.folder) as tempdir:
            # Avoid copying live WAL files. sqlite3 backup creates a consistent image.
            source = self.database.backup(Path(tempdir))
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
            target = self.folder / f'aura_backup_{timestamp}.auraenc'
            return encrypt_file(source, target, self.passphrase)

    def backup_if_due(self, days: int = 7) -> Path | None:
        """No unencrypted fallback; absence of password never writes backups."""
        self._check()
        from datetime import timedelta
        from .database import now
        last = self.database.get_option('last_protected_backup_at', '')
        try:
            prior = datetime.fromisoformat(last)
            if datetime.now(timezone.utc) - prior < timedelta(days=days):
                return None
        except (ValueError, TypeError):
            pass
        target = self.create_backup()
        self.database.set_option('last_protected_backup_at', now())
        return target

    def export_memory(self, months: int = 6) -> Path:
        self._check()
        data = self.database.export_full_memory(months)
        data['version'] = '2.8'
        target = self.folder / ('aura_export_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f') + '.auraenc')
        return encrypt_bytes(json.dumps(data, ensure_ascii=False).encode('utf-8'), target, self.passphrase)


def cli() -> None:
    parser = argparse.ArgumentParser(description='AURA: backups cifrados AES-256-GCM de base SQLCipher')
    sub = parser.add_subparsers(dest='mode', required=True)
    b = sub.add_parser('backup', help='Criar backup cifrado da base SQLite')
    b.add_argument('--db', default='data/aura.sqlite3')
    b.add_argument('--out', default='data/secure_backups')
    r = sub.add_parser('restore', help='Restaurar um backup para um ficheiro novo, com AURA fechada')
    r.add_argument('--input', required=True)
    r.add_argument('--out', required=True)
    v = sub.add_parser('verify', help='Verificar integridade e frase-passe sem tocar na base ativa')
    v.add_argument('--input', required=True)
    args = parser.parse_args()
    phrase = getpass.getpass('Frase-passe do backup (não é mostrada): ')
    try:
        if args.mode == 'backup':
            from .database import Database
            if not Path(args.db).is_file():
                parser.error('A base de dados não existe.')
            db_phrase = getpass.getpass('Frase-passe SQLCipher da base ativa: ')
            manager = SecureBackupManager(Database(Path(args.db), passphrase=db_phrase, require_encryption=True), Path(args.out), phrase)
            print('Backup criado:', manager.create_backup())
        elif args.mode == 'restore':
            path = decrypt_file(Path(args.input), Path(args.out), phrase)
            print('Restaurado para ficheiro NOVO:', path)
        else:
            with tempfile.TemporaryDirectory(prefix='aura-verify-') as dirname:
                decrypt_file(Path(args.input), Path(dirname) / 'verified', phrase)
            print('Integridade e frase-passe verificadas.')
    except (VaultError, OSError, ValueError) as exc:
        parser.exit(2, f'Erro: {exc}\n')


if __name__ == '__main__':
    cli()
