#!/bin/bash
# Run the Dating Coach AI backend.
# Usage: ./run.sh            (serves API + frontend on http://localhost:8000)
# Env:   SECRET_KEY (required), ANTHROPIC_API_KEY (unless MOCK_AI=true),
#        ANTHROPIC_MODEL (default claude-sonnet-4-5), DATABASE_URL (default sqlite),
#        MOCK_AI=true (canned AI responses, no API spend), PORT (default 8000)
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

if [ -z "$SECRET_KEY" ]; then
  echo "ERROR: SECRET_KEY env var is required." >&2
  exit 1
fi

PORT="${PORT:-8000}"
exec .venv/bin/uvicorn main:app --host 0.0.0.0 --port "$PORT"
