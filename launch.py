"""Run 'python launch.py'; also opens default browser, no build tools needed."""
from __future__ import annotations
from threading import Timer
import os
import sys
import getpass
from ipaddress import ip_address
import webbrowser
import uvicorn
from aura.config import Settings

if __name__ == '__main__':
    settings = Settings.from_env()
    try:
        if not ip_address(settings.host).is_loopback:
            raise SystemExit('Segurança: AURA_HOST deve ser um endereço loopback (127.0.0.1 ou ::1).')
    except ValueError:
        if settings.host != 'localhost':
            raise SystemExit('Segurança: AURA_HOST só pode ser localhost ou loopback.')
    if not settings.database_passphrase and sys.stdin.isatty():
        print('AURA 2.8: a memória ativa é cifrada com SQLCipher.')
        print('NÃO percas a frase-passe. Sem ela não podes abrir a tua memória.')
        phrase = getpass.getpass('Frase-passe da base de dados (mín. 12 caracteres): ')
        if len(phrase) < 12:
            raise SystemExit('Memória bloqueada: frase-passe insuficiente. Nada foi alterado.')
        os.environ['AURA_DATABASE_PASSPHRASE'] = phrase
    elif not settings.database_passphrase:
        raise SystemExit('Memória bloqueada: define AURA_DATABASE_PASSPHRASE no ambiente.')
    if not settings.backup_passphrase and sys.stdin.isatty():
        print('AURA 2.8: backups adicionalmente protegidos com AES-256-GCM.')
        print('A base ativa SQLCipher ESTÁ cifrada; esta segunda frase-passe protege os backups/exportações.')
        print('Se perderes a frase-passe, os backups deixam de poder ser recuperados.')
        phrase = getpass.getpass('Frase-passe (mín. 12 caracteres, Enter desativa backups): ')
        if len(phrase) >= 12:
            os.environ['AURA_BACKUP_PASSPHRASE'] = phrase
        elif phrase:
            print('Frase-passe curta: backups automáticos desativados.')
    # Fail before opening a browser when database is plaintext, locked or corrupted.
    from aura.database import Database
    Database(settings.data_dir / 'aura.sqlite3', os.environ.get('AURA_DATABASE_PASSPHRASE',''), True)
    Timer(1.4, lambda: webbrowser.open(f'http://{settings.host}:{settings.port}')).start()
    uvicorn.run('aura.app:app', host=settings.host, port=settings.port,
                reload=False, workers=1)
