#!/usr/bin/env bash
# Start the conference app locally, preserving explicit shell overrides.
set -euo pipefail
cd "$(dirname "$0")"
export DEMO_MODE="${DEMO_MODE:-local}"
export DATABASE_URL="${DATABASE_URL:-postgresql://coffee:coffee@127.0.0.1:5432/coffee}"
export APP_HOST="${APP_HOST:-127.0.0.1}"
export APP_PORT="${APP_PORT:-8017}"
export ENABLE_STAGE_CONTROLS="${ENABLE_STAGE_CONTROLS:-0}"
DEMO_PYTHON="${DEMO_PYTHON:-.venv/bin/python}"
if [ ! -x "$DEMO_PYTHON" ]; then
  echo "Create .venv and install requirements.txt first. See README.md." >&2
  exit 1
fi
exec "$DEMO_PYTHON" app.py
