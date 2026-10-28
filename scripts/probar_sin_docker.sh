#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || python3 scripts/generar_env.py
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r backend/requirements.txt

mkdir -p .devpg && cd .devpg
[ -d node_modules/@embedded-postgres ] || { npm init -y >/dev/null; npm i embedded-postgres >/dev/null; \
  (cd node_modules/@embedded-postgres/linux-x64 && node scripts/hydrate-symlinks.js >/dev/null 2>&1 || true); }
BIN="$PWD/node_modules/@embedded-postgres/linux-x64/native/bin"
[ -d data ] || "$BIN/initdb" -D data -U postgres --auth=trust -E UTF8 >/dev/null
"$BIN/pg_ctl" -D data -o "-p 55432 -k ''" -l pg.log -w start >/dev/null
trap '"$BIN/pg_ctl" -D "$PWD/data" stop -m fast >/dev/null' EXIT
cd ..

python - <<'PY'
import psycopg2
c = psycopg2.connect("postgresql://postgres@127.0.0.1:55432/postgres"); c.autocommit = True
cur = c.cursor(); cur.execute("SELECT 1 FROM pg_database WHERE datname='control_clientes'")
if not cur.fetchone(): cur.execute("CREATE DATABASE control_clientes")
PY
export DATABASE_URL="postgresql+psycopg2://postgres@127.0.0.1:55432/control_clientes"
[ -f backend/app/static/index.html ] || (cd frontend && npm install >/dev/null && npm run build >/dev/null)
cd backend
python -m app.migrations.run_migrations
python -m app.seed 2>/dev/null || echo "[seed] ya había datos"
echo; echo "Usuarios y contraseñas de prueba: backend/seed_credentials.txt"; echo "Abre http://localhost:8000"
exec uvicorn app.main:app --port 8000
