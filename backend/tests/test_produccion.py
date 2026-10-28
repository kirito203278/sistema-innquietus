import base64
import secrets

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.config import Settings
from app.models import Bitacora, Usuario
from app.security.passwords import verify_password


def _ajustes(**cambios):
    base = dict(database_url="postgresql://u:p@host/db", jwt_secret=secrets.token_urlsafe(32), jobs_secret=secrets.token_urlsafe(16),
                aes_key_b64=base64.b64encode(secrets.token_bytes(32)).decode())
    return Settings(_env_file=None, **{**base, **cambios})


def test_url_de_neon_se_normaliza_al_driver_psycopg2():
    assert _ajustes(database_url="postgres://u:p@h/db?sslmode=require").database_url == "postgresql+psycopg2://u:p@h/db?sslmode=require"
    assert _ajustes(database_url="postgresql://u:p@h/db").database_url.startswith("postgresql+psycopg2://")
    assert _ajustes(database_url="postgresql+psycopg2://u:p@h/db").database_url == "postgresql+psycopg2://u:p@h/db"


@pytest.mark.parametrize("campo,valor", [("jwt_secret", "corto"), ("jwt_secret", "__GENERADA__" + "x" * 40),
                                          ("jobs_secret", "corto"), ("aes_key_b64", "no-es-base64!"),
                                          ("aes_key_b64", base64.b64encode(b"16 bytes solamente").decode())])
def test_la_app_no_arranca_con_secretos_debiles(campo, valor):
    with pytest.raises(ValidationError):
        _ajustes(**{campo: valor})


def test_cors_y_reglas_de_negocio_por_defecto():
    s = _ajustes(cors_origins="https://a.com, https://b.com")
    assert s.cors_origins_list == ["https://a.com", "https://b.com"]
    assert (s.ciclo_dias, s.prorroga_max_dias, s.dias_para_decidir, s.purga_meses, s.reingreso_meses, s.tz) == \
        (30, 5, 2, 12, 2, "America/Mexico_City")


def test_cabeceras_de_seguridad_y_sin_cache_en_api(api):
    r = api.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_cli_crear_admin_con_password_de_18_y_bitacora(db):
    from app.cli import crear_admin
    usuario, password = crear_admin(db, "Cristina Pérez")
    u = db.scalars(select(Usuario).where(Usuario.username == usuario)).one()
    assert usuario == "cristina.perez" and u.rol == "admin" and not u.solo_lectura and len(password) == 18
    assert verify_password(password, u.password_hash)
    assert db.scalars(select(Bitacora).where(Bitacora.accion == "alta_usuario")).one().detalle["via"] == "cli"


def test_cli_reset_password(db, crear_usuario):
    from app.cli import reset_password
    u = crear_usuario("unico.admin", rol="admin")
    nueva = reset_password(db, "Unico.Admin")
    assert verify_password(nueva, u.password_hash) and not verify_password(u._password, u.password_hash)
    assert reset_password(db, "nadie") is None
