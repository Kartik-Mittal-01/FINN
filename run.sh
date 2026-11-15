#!/usr/bin/env bash
# One-command local run: installs deps, builds the UI, starts FINN on http://localhost:8000
# (the FastAPI server also serves the built React app). First start seeds the labelled demo dataset.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then python3 -m venv backend/.venv; fi
# shellcheck disable=SC1091
source backend/.venv/bin/activate
pip install -q -r backend/requirements.txt

if [ ! -d frontend/node_modules ]; then (cd frontend && npm install --no-audit --no-fund); fi
(cd frontend && npm run build)

cd backend
[ -f .env ] || cp .env.example .env
echo "FINN running on http://localhost:8000  (Ctrl+C to stop)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
