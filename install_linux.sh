#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -c "from aura.vault import sqlcipher_backend; c=sqlcipher_backend().connect(':memory:'); v=c.execute('PRAGMA cipher_version').fetchone(); assert v and v[0], 'SQLCipher indisponível'; print('SQLCipher operacional:', v[0]); c.close()"
if [ ! -e .env ]; then cp .env.example .env; fi
echo 'Instalado. Executa ./iniciar_aura.sh'
