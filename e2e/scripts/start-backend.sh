#!/usr/bin/env bash
# Brings the API up for a Playwright run: database, then schema, then server.
#
# Playwright invokes this with every key from .env.e2e already in the
# environment, which outranks backend/.env in pydantic-settings.
set -euo pipefail

e2e_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

node "$e2e_root/scripts/ensure-db.mjs"

cd "$e2e_root/../backend"
uv run alembic upgrade head
exec uv run uvicorn backend.main:app --host 127.0.0.1 --port "${E2E_BACKEND_PORT:-8000}"
