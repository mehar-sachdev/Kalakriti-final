#!/usr/bin/env bash
# One-command setup: virtualenv + packages + .env.   Run from the project root (or via the VS Code task).
#   bash scripts/bootstrap.sh
# Env: PYTHON=python3.12 (choose interpreter)   SKIP_INSTALL=1 (only create .venv and .env)
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "ERROR: $PY not found. In WSL/Ubuntu:  sudo apt update && sudo apt install -y python3 python3-venv python3-pip" >&2
  exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "ERROR: Python 3.10 or newer is required (found $("$PY" --version 2>&1))." >&2
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo ">> Creating .venv"
  "$PY" -m venv .venv || { echo "ERROR: venv failed. In Ubuntu:  sudo apt install -y python3-venv" >&2; exit 1; }
fi

if [ -z "${SKIP_INSTALL:-}" ]; then
  echo ">> Installing packages (docling is large; the first run can take several minutes)"
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements-dev.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo ">> Created .env from .env.example - open it and fill in SUPABASE_DB_URL and OLLAMA_API_KEY."
else
  echo ">> .env already exists - left unchanged."
fi

cat <<'MSG'

Setup finished. Next in VS Code:
  1. Ctrl+Shift+P  ->  "Python: Select Interpreter"  ->  .venv/bin/python   (usually picked automatically)
  2. Edit .env  (Supabase URL + Ollama key), then run the task "Check configuration"
  3. Task "Database: apply schema", copy your documents into data/raw/, task "Ingest: parse + index (all)"
  4. Run and Debug (F5) -> "1. API server + open UI"
MSG
