"""Un CM maneja varios clientes con la misma cuenta de Facebook: se captura una vez y se comparte."""
from sqlalchemy import select

from app.models import Cliente, CuentaFb
from app.security.crypto import decrypt_value


def _alta(api, h, nombre, correo, pwd=None):
    r = api.post("/api/clientes", headers=h, json={"nombre": nombre, "correo_fb": correo, "password_fb": pwd})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_mismo_correo_del_mismo_cm_comparte_una_sola_cuenta(api, db, auth, crear_usuario):
    ana = crear_usuario("ana.ruiz"); h = auth(ana)
    a = _alta(api, h, "Cliente A", "Agencia@FB.test", "Secreta-1")
    b = _alta(api, h, "Cliente B", "agencia@fb.test")           # sin contraseña: usa la guardada
    assert db.scalar(select(CuentaFb.id).where(CuentaFb.cm_id == ana.id)) is not None
    assert len(db.scalars(select(CuentaFb)).all()) == 1
    fb = api.get(f"/api/clientes/{b}", headers=h).json()
    assert fb["tiene_password_fb"] and [x["nombre"] for x in fb["cuenta_compartida_con"]] == ["Cliente A"]
    assert api.post(f"/api/clientes/{b}/password-fb/ver", headers=h).json() == {"password": "Secreta-1"}
    # cambiar la contraseña desde un cliente la cambia para todos
    assert api.patch(f"/api/clientes/{a}", headers=h, json={"password_fb": "Nueva-2"}).status_code == 200
    assert api.post(f"/api/clientes/{b}/password-fb/ver", headers=h).json() == {"password": "Nueva-2"}


def test_otro_cm_con_el_mismo_correo_tiene_su_propia_cuenta(api, db, auth, crear_usuario):
    h_ana, h_beto = auth(crear_usuario("ana.ruiz")), auth(crear_usuario("beto.luna"))
    _alta(api, h_ana, "De Ana", "comun@fb.test", "Clave-Ana")
    b = _alta(api, h_beto, "De Beto", "comun@fb.test", "Clave-Beto")
    assert len(db.scalars(select(CuentaFb)).all()) == 2
    assert api.post(f"/api/clientes/{b}/password-fb/ver", headers=h_beto).json() == {"password": "Clave-Beto"}
    assert api.get(f"/api/clientes/{b}", headers=h_beto).json()["cuenta_compartida_con"] == []


def test_cambiar_el_correo_mueve_solo_a_ese_cliente_y_limpia_cuentas_huerfanas(api, db, auth, crear_usuario):
    h = auth(crear_usuario("ana.ruiz"))
    a, b = _alta(api, h, "A", "uno@fb.test", "Clave-Uno"), _alta(api, h, "B", "uno@fb.test")
    api.patch(f"/api/clientes/{b}", headers=h, json={"correo_fb": "dos@fb.test", "password_fb": "Clave-Dos"})
    assert api.get(f"/api/clientes/{a}", headers=h).json()["correo_fb"] == "uno@fb.test"
    assert api.get(f"/api/clientes/{b}", headers=h).json()["correo_fb"] == "dos@fb.test"
    assert api.post(f"/api/clientes/{a}/password-fb/ver", headers=h).json() == {"password": "Clave-Uno"}
    # quitar el correo deja al cliente sin cuenta y borra la cuenta que nadie usa
    api.patch(f"/api/clientes/{b}", headers=h, json={"correo_fb": ""})
    assert len(db.scalars(select(CuentaFb)).all()) == 1


def test_endpoint_de_cuentas_lista_las_del_cm_con_su_numero_de_clientes(api, db, auth, crear_usuario):
    h_ana, h_beto = auth(crear_usuario("ana.ruiz")), auth(crear_usuario("beto.luna"))
    _alta(api, h_ana, "A", "x@fb.test", "p1"); _alta(api, h_ana, "B", "x@fb.test"); _alta(api, h_beto, "C", "z@fb.test", "p2")
    r = api.get("/api/clientes/cuentas-fb", headers=h_ana).json()
    assert [(c["correo"], c["clientes"]) for c in r] == [("x@fb.test", 2)]
    assert "password" not in r[0]


def test_reasignar_lleva_la_cuenta_al_cm_nuevo_sin_tocar_a_los_demas(api, db, auth, crear_usuario):
    ana, beto = crear_usuario("ana.ruiz"), crear_usuario("beto.luna")
    admin = crear_usuario("admin.jefe", rol="admin")
    h, ha = auth(ana), auth(admin)
    a, b = _alta(api, h, "A", "x@fb.test", "Clave-X"), _alta(api, h, "B", "x@fb.test")
    assert api.post(f"/api/clientes/{b}/reasignar", headers=ha, json={"cm_id": beto.id}).status_code == 200
    cb = db.get(Cliente, b); db.refresh(cb)
    assert cb.cuenta.cm_id == beto.id and decrypt_value(cb.cuenta.password_enc) == "Clave-X"
    assert api.get(f"/api/clientes/{a}", headers=h).json()["cuenta_compartida_con"] == []
