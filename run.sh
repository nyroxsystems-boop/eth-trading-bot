#!/usr/bin/env bash
set -euo pipefail
cd /root/ethbot

# venv aktivieren
source /root/ethbot/.venv/bin/activate

# .env sauber laden (unterstützt Kommentare)
set -a
[ -f .env ] && . ./.env
set +a

PYTHONUNBUFFERED=1 python -u /root/ethbot/eth_master_bot.py "$@"
