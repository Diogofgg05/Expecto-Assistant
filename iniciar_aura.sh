#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then echo 'Executa ./install_linux.sh primeiro'; exit 1; fi
.venv/bin/python launch.py
