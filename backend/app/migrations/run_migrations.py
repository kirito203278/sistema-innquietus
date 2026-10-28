import time
from pathlib import Path

import psycopg2

from app.config import get_settings

SQL_DIR = Path(__file__).parent / "sql"


def _dsn(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg2://", "postgresql://")


def _wait_for_db(dsn: str, attempts: int = 30, delay: float = 1.0) -> None:
    last = None
    for _ in range(attempts):
        try:
            psycopg2.connect(dsn).close()
            return
        except psycopg2.OperationalError as exc:
            last = exc
            time.sleep(delay)
    raise RuntimeError(f"No se pudo conectar a la base de datos tras {attempts} intentos: {last}")


def run_migrations(database_url: str | None = None) -> list[str]:
    dsn = _dsn(database_url or get_settings().database_url)
    _wait_for_db(dsn)
    conn = psycopg2.connect(dsn)
    aplicadas: list[str] = []
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "filename TEXT PRIMARY KEY, aplicada_en TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            cur.execute("SELECT filename FROM schema_migrations")
            hechas = {r[0] for r in cur.fetchall()}
        for archivo in sorted(SQL_DIR.glob("*.sql")):
            if archivo.name in hechas:
                continue
            with conn, conn.cursor() as cur:
                cur.execute(archivo.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (archivo.name,))
            aplicadas.append(archivo.name)
            print(f"[migraciones] aplicada {archivo.name}")
    finally:
        conn.close()
    if not aplicadas:
        print("[migraciones] nada que aplicar")
    return aplicadas


if __name__ == "__main__":
    run_migrations()
