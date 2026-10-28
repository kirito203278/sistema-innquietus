#!/bin/sh
set -e

python -m app.migrations.run_migrations

if [ "$SEED_ON_START" = "true" ]; then
    python -m app.seed || echo "[seed] omitido (ya hay datos)"
fi

RELOAD_FLAG=""
[ "$RELOAD" = "true" ] && RELOAD_FLAG="--reload"

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*" $RELOAD_FLAG
