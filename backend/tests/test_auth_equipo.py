import datetime as dt

import jwt as pyjwt
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Bitacora, Cliente, Usuario
from app.security.passwords import verify_password


def test_login_correcto_y_me(api, crear_usuario):
    u = crear_usuario("ana.ruiz")
    r = api.post("/api/auth/login", json={"username": "Ana.Ruiz", "password": u._password})
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "cm"
    tok = r.json()["access_token"]
    assert api.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["username"] == "ana.ruiz"


def test_token_dura_12_horas(api, crear_usuario):
    u = crear_usuario("ana.ruiz")
    tok = api.post("/api/auth/login", json={"username": u.username, "password": u._password}).json()["access_token"]
    claims = pyjwt.decode(tok, get_settings().jwt_secret, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 12 * 3600


def test_login_incorrecto_y_mensaje_generico(api, crear_usuario):
    crear_usuario("ana.ruiz")
    a = api.post("/api/auth/login", json={"username": "ana.ruiz", "password": "mala"})
    b = api.post("/api/auth/login", json={"username": "nadie", "password": "mala"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_bloqueo_tras_5_intentos_fallidos(api, crear_usuario):
    u = crear_usuario("ana.ruiz")
    for _ in range(5):
        assert api.post("/api/auth/login", json={"username": u.username, "password": "mala"}).status_code == 401
    assert api.post("/api/auth/login", json={"username": u.username, "password": u._password}).status_code == 429


def test_ventana_de_bloqueo_expira(crear_usuario):
    from app.security import rate_limit
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    for i in range(5):
        rate_limit.registrar_intento_fallido("x", t0)
    assert rate_limit.bloqueado("x", t0 + dt.timedelta(minutes=14))
    assert not rate_limit.bloqueado("x", t0 + dt.timedelta(minutes=16))


def test_usuario_dado_de_baja_no_entra_ni_con_token_previo(api, db, crear_usuario, auth):
    u = crear_usuario("ana.ruiz")
    h = auth(u)
    u.activo = False
    db.flush()
    assert api.get("/api/auth/me", headers=h).status_code == 401
    assert api.post("/api/auth/login", json={"username": u.username, "password": u._password}).status_code == 401


def test_sin_token_o_token_falso(api):
    assert api.get("/api/usuarios").status_code == 401
    assert api.get("/api/usuarios", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_cm_no_accede_a_rutas_de_admin(api, crear_usuario, auth):
    h = auth(crear_usuario("ana.ruiz"))
    assert api.get("/api/usuarios", headers=h).status_code == 403
    assert api.post("/api/usuarios", headers=h, json={"nombre": "X Y", "rol": "cm", "password": "Clave-1234"}).status_code == 403
    assert api.get("/api/admin/bitacora", headers=h).status_code == 403


def test_admin_solo_lectura_ve_pero_no_escribe(api, crear_usuario, auth):
    h = auth(crear_usuario("lectura.demo", rol="admin", solo_lectura=True))
    assert api.get("/api/usuarios", headers=h).status_code == 200
    assert api.post("/api/usuarios", headers=h, json={"nombre": "Nuevo Cm", "rol": "cm", "password": "Clave-1234"}).status_code == 403
    assert api.post("/api/catalogos/paquetes", headers=h, json={"nombre": "Nuevo"}).status_code == 403


def test_alta_de_usuario_con_la_contrasena_que_elige_el_admin(api, db, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    r = api.post("/api/usuarios", headers=h, json={"nombre": "María López", "rol": "cm", "password": "Mi-clave-2026"})
    assert r.status_code == 201
    datos = r.json()
    assert datos["username"] == "maria.lopez" and "password" not in datos
    u = db.scalars(select(Usuario).where(Usuario.username == "maria.lopez")).one()
    assert verify_password("Mi-clave-2026", u.password_hash) and "Mi-clave-2026" not in u.password_hash
    listado = api.get("/api/usuarios", headers=h).text
    assert "Mi-clave-2026" not in listado and "password_hash" not in listado
    bit = db.scalars(select(Bitacora).where(Bitacora.accion == "alta_usuario")).one()
    assert bit.detalle["username"] == "maria.lopez" and "Mi-clave" not in str(bit.detalle)
    assert api.post("/api/auth/login", json={"username": "maria.lopez", "password": "Mi-clave-2026"}).status_code == 200


@pytest.mark.parametrize("password", ["corta", "1234567", " espacios al borde ", "x" * 73, "ñ" * 40])
def test_contrasenas_invalidas_se_rechazan(api, crear_usuario, auth, password):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    r = api.post("/api/usuarios", headers=h, json={"nombre": "Ana Nueva", "rol": "cm", "password": password})
    assert r.status_code == 422
    cm = crear_usuario("beto.luna")
    assert api.post(f"/api/usuarios/{cm.id}/reset-password", headers=h, json={"password": password}).status_code == 422


def test_la_contrasena_es_obligatoria_al_crear_y_al_resetear(api, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    assert api.post("/api/usuarios", headers=h, json={"nombre": "Ana Nueva", "rol": "cm"}).status_code == 422
    assert api.post(f"/api/usuarios/{crear_usuario('beto.luna').id}/reset-password", headers=h, json={}).status_code == 422


def test_username_repetido_recibe_sufijo(api, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    a = api.post("/api/usuarios", headers=h, json={"nombre": "Luis Pérez", "rol": "cm", "password": "Clave-1234"}).json()["username"]
    b = api.post("/api/usuarios", headers=h, json={"nombre": "Luis Pérez", "rol": "admin", "password": "Clave-1234"}).json()["username"]
    assert (a, b) == ("luis.perez", "luis.perez2")


def test_cm_no_puede_ser_solo_lectura(api, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    assert api.post("/api/usuarios", headers=h, json={"nombre": "Ana Ruiz", "rol": "cm", "solo_lectura": True, "password": "Clave-1234"}).status_code == 422


def test_reset_password_pone_la_que_escribe_el_admin_e_invalida_la_anterior(api, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    cm = crear_usuario("ana.ruiz")
    r = api.post(f"/api/usuarios/{cm.id}/reset-password", headers=h, json={"password": "Nueva-clave-77"})
    assert r.status_code == 200 and r.json() == {"username": "ana.ruiz"}
    assert api.post("/api/auth/login", json={"username": "ana.ruiz", "password": cm._password}).status_code == 401
    assert api.post("/api/auth/login", json={"username": "ana.ruiz", "password": "Nueva-clave-77"}).status_code == 200


def test_un_cm_no_puede_cambiar_contrasenas(api, crear_usuario, auth):
    h = auth(crear_usuario("ana.ruiz"))
    otro = crear_usuario("beto.luna")
    assert api.post(f"/api/usuarios/{otro.id}/reset-password", headers=h, json={"password": "Hackeada-123"}).status_code == 403


def _cliente(db, cm, nombre, estado="activo"):
    c = Cliente(cm_id=cm.id if cm else None, nombre=nombre, estado=estado)
    db.add(c)
    db.flush()
    return c


def test_baja_de_cm_migra_toda_la_cartera_incluidos_no_renovados(api, db, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    ana, beto = crear_usuario("ana.ruiz"), crear_usuario("beto.luna")
    c1, c2 = _cliente(db, ana, "A"), _cliente(db, ana, "B", estado="no_renovado")
    r = api.post(f"/api/usuarios/{ana.id}/baja", headers=h, json={"migrar_a_cm_id": beto.id})
    assert r.status_code == 200 and r.json()["clientes_migrados"] == 2
    db.refresh(c1), db.refresh(c2), db.refresh(ana)
    assert c1.cm_id == c2.cm_id == beto.id and not ana.activo
    assert db.scalars(select(Bitacora).where(Bitacora.accion == "baja_usuario")).one().detalle["clientes_migrados"] == 2


def test_baja_con_clientes_exige_otro_cm_no_se_pueden_dejar_sueltos(api, db, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    ana, beto = crear_usuario("ana.ruiz"), crear_usuario("beto.luna")
    c = _cliente(db, ana, "A")
    r = api.post(f"/api/usuarios/{ana.id}/baja", headers=h, json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "requiere_destino"
    assert api.post(f"/api/usuarios/{ana.id}/baja", headers=h, json={"migrar_a_cm_id": None}).status_code == 409
    assert api.post(f"/api/usuarios/{ana.id}/baja", headers=h, json={"migrar_a_cm_id": beto.id}).status_code == 200
    db.refresh(c)
    assert c.cm_id == beto.id


def test_baja_sin_clientes_no_pide_destino(api, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    assert api.post(f"/api/usuarios/{crear_usuario('ana.ruiz').id}/baja", headers=h, json={}).status_code == 200


def test_destino_de_migracion_debe_ser_cm_activo(api, db, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    ana, baja = crear_usuario("ana.ruiz"), crear_usuario("vieja.baja", activo=False)
    adm2 = crear_usuario("otro.admin", rol="admin")
    _cliente(db, ana, "A")
    for destino in (baja.id, adm2.id, ana.id, 99999):
        assert api.post(f"/api/usuarios/{ana.id}/baja", headers=h, json={"migrar_a_cm_id": destino}).status_code == 422


def test_no_puedes_darte_de_baja_ni_dejar_al_sistema_sin_admin(api, crear_usuario, auth):
    yo = crear_usuario("admin.demo", rol="admin")
    h = auth(yo)
    assert api.post(f"/api/usuarios/{yo.id}/baja", headers=h, json={}).status_code == 409
    otro = crear_usuario("otro.admin", rol="admin")
    assert api.post(f"/api/usuarios/{otro.id}/baja", headers=h, json={}).status_code == 200
    ro = crear_usuario("lectura.demo", rol="admin", solo_lectura=True)
    assert api.post(f"/api/usuarios/{ro.id}/baja", headers=h, json={}).status_code == 200


def test_catalogos_crud_y_duplicados(api, crear_usuario, auth):
    h = auth(crear_usuario("admin.demo", rol="admin"))
    cm = auth(crear_usuario("ana.ruiz"))
    assert api.post("/api/catalogos/paquetes", headers=h, json={"nombre": "Premium"}).status_code == 201
    assert api.post("/api/catalogos/paquetes", headers=h, json={"nombre": "Premium"}).status_code == 409
    assert api.post("/api/catalogos/paquetes", headers=cm, json={"nombre": "Pirata"}).status_code == 403
    items = api.get("/api/catalogos/paquetes", headers=cm).json()
    assert "Premium" in [i["nombre"] for i in items]
    pid = next(i["id"] for i in items if i["nombre"] == "Premium")
    api.patch(f"/api/catalogos/paquetes/{pid}", headers=h, json={"activo": False})
    assert "Premium" not in [i["nombre"] for i in api.get("/api/catalogos/paquetes", headers=cm).json()]
    assert "Premium" in [i["nombre"] for i in api.get("/api/catalogos/paquetes?todos=true", headers=h).json()]
    assert api.get("/api/catalogos/cosas", headers=h).status_code == 404
