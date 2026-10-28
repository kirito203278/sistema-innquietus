import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Bitacora, Cliente, PaqueteCliente, Pago, RecordatorioCliente
from app.security.crypto import decrypt_value

H = dt.date(2026, 10, 1)
D = dt.timedelta


@pytest.fixture(autouse=True)
def _hoy(hoy_fijo):
    hoy_fijo(H)


@pytest.fixture
def escenario(db, crear_usuario, fabrica):
    ana, beto = crear_usuario("ana.ruiz"), crear_usuario("beto.luna")
    admin = crear_usuario("admin.jefe", rol="admin")
    ca = fabrica.cliente(ana, "Cliente de Ana")
    cb = fabrica.cliente(beto, "Cliente de Beto")
    pa = fabrica.ciclo(ca, H + D(10))
    pb = fabrica.ciclo(cb, H + D(10))
    return dict(ana=ana, beto=beto, admin=admin, ca=ca, cb=cb, pa=pa, pb=pb)


def test_cm_solo_ve_su_cartera_en_la_lista(api, auth, escenario):
    h = auth(escenario["ana"])
    nombres = [c["nombre"] for c in api.get("/api/clientes", headers=h).json()]
    assert nombres == ["Cliente de Ana"]
    r = api.get(f"/api/clientes?cm_id={escenario['beto'].id}", headers=h).json()
    assert [c["nombre"] for c in r] == ["Cliente de Ana"]


@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("get", "/api/clientes/{cb}", None),
    ("patch", "/api/clientes/{cb}", {"nombre": "Hackeado"}),
    ("post", "/api/clientes/{cb}/password-fb/ver", None),
    ("delete", "/api/clientes/{cb}?confirmar_nombre=Cliente de Beto", None),
    ("post", "/api/clientes/{cb}/paquetes", {"paquete_id": 1, "tipo_id": 1, "costo": 100, "fecha_inicio": "2026-10-01"}),
    ("get", "/api/paquetes/{pb}", None),
    ("patch", "/api/paquetes/{pb}", {"costo": 1}),
    ("post", "/api/paquetes/{pb}/pagos", {"monto": 10}),
    ("post", "/api/paquetes/{pb}/prorroga", None),
    ("post", "/api/paquetes/{pb}/recordatorio", None),
    ("post", "/api/clientes/{cb}/reasignar", {"cm_id": None}),
])
def test_cm_no_toca_datos_de_otro_cm(api, auth, escenario, metodo, ruta, cuerpo):
    h = auth(escenario["ana"])
    url = ruta.format(cb=escenario["cb"].id, pb=escenario["pb"].id)
    r = getattr(api, metodo)(url, headers=h, **({"json": cuerpo} if cuerpo is not None else {}))
    assert r.status_code in (403, 404), (url, r.status_code, r.text)


def test_cm_no_borra_pagos_el_admin_si(api, db, auth, escenario, fabrica):
    p = fabrica.ciclo(escenario["cb"], H + D(10), pagos=[(100, H)], por=escenario["admin"])
    pago = db.scalars(select(Pago).where(Pago.paquete_id == p.id)).one()
    assert api.delete(f"/api/pagos/{pago.id}", headers=auth(escenario["beto"])).status_code == 403
    assert api.delete(f"/api/pagos/{pago.id}", headers=auth(escenario["ana"])).status_code == 403
    assert db.get(Pago, pago.id) is not None
    assert api.delete(f"/api/pagos/{pago.id}", headers=auth(escenario["admin"])).status_code == 200


def test_admin_ve_todo_y_solo_lectura_no_escribe(api, auth, escenario, crear_usuario):
    adm = auth(crear_usuario("admin.demo", rol="admin"))
    assert len(api.get("/api/clientes", headers=adm).json()) == 2
    ro = auth(crear_usuario("lectura.demo", rol="admin", solo_lectura=True))
    assert len(api.get("/api/clientes", headers=ro).json()) == 2
    assert api.post(f"/api/paquetes/{escenario['pa'].id}/pagos", headers=ro, json={"monto": 10}).status_code == 403
    assert api.patch(f"/api/clientes/{escenario['ca'].id}", headers=ro, json={"nombre": "X"}).status_code == 403


def test_admin_con_escritura_opera_por_un_cm_y_queda_en_bitacora(api, db, auth, escenario, crear_usuario):
    adm = auth(crear_usuario("admin.demo", rol="admin"))
    r = api.post(f"/api/paquetes/{escenario['pa'].id}/pagos", headers=adm, json={"monto": 100})
    assert r.status_code == 201
    assert db.scalars(select(Bitacora).where(Bitacora.accion == "pago_por_admin")).one()


def test_alta_cliente_cifra_credenciales_y_ficha_no_expone_password(api, db, auth, crear_usuario):
    ana = crear_usuario("ana.ruiz")
    h = auth(ana)
    r = api.post("/api/clientes", headers=h, json={
        "nombre": "Nuevo", "correo_fb": "nuevo@fb.test", "password_fb": "SuperSecreta1", "telefono": "5511112222",
        "cm_id": 999,
        "paquetes": [{"paquete_id": 1, "tipo_id": 1, "costo": 1500, "fecha_inicio": "2026-10-01"}]})
    assert r.status_code == 201
    c = db.get(Cliente, r.json()["id"])
    assert c.cm_id == ana.id and "SuperSecreta1" not in c.cuenta.password_enc and "nuevo@fb.test" not in c.cuenta.correo_enc
    ficha = api.get(f"/api/clientes/{c.id}", headers=h)
    assert "SuperSecreta1" not in ficha.text and ficha.json()["correo_fb"] == "nuevo@fb.test"
    assert ficha.json()["tiene_password_fb"] is True
    ver = api.post(f"/api/clientes/{c.id}/password-fb/ver", headers=h)
    assert ver.json() == {"password": "SuperSecreta1"}
    assert db.scalars(select(Bitacora).where(Bitacora.accion == "ver_password_fb")).one().detalle == {"cliente_id": c.id}


def test_editar_ficha_y_password_vacio_no_lo_cambia(api, db, auth, escenario):
    h = auth(escenario["ana"])
    cid = escenario["ca"].id
    api.patch(f"/api/clientes/{cid}", headers=h, json={"correo_fb": "ana@fb.test", "password_fb": "Primera1", "observaciones": "nota"})
    api.patch(f"/api/clientes/{cid}", headers=h, json={"password_fb": "", "telefono": "5599998888"})
    c = db.get(Cliente, cid)
    assert api.patch(f"/api/clientes/{cid}", headers=h, json={"correo_fb": "", "password_fb": "x"}).status_code == 422
    assert decrypt_value(c.cuenta.password_enc) == "Primera1" and c.telefono == "5599998888" and c.observaciones == "nota"


def test_solo_el_admin_elimina_y_solo_a_los_que_estan_en_no_renovados(api, db, auth, escenario):
    cm, adm = auth(escenario["ana"]), auth(escenario["admin"])
    c = escenario["ca"]
    assert api.delete(f"/api/clientes/{c.id}?confirmar_nombre=Cliente de Ana", headers=cm).status_code == 403
    assert api.delete(f"/api/clientes/{c.id}?confirmar_nombre=Cliente de Ana", headers=adm).status_code == 409
    c.estado = "no_renovado"
    db.flush()
    assert api.delete(f"/api/clientes/{c.id}?confirmar_nombre=cliente de ana", headers=adm).status_code == 422
    assert api.delete(f"/api/clientes/{c.id}?confirmar_nombre=Cliente de Ana", headers=adm).status_code == 200
    assert db.get(Cliente, c.id) is None


def test_el_cm_no_borra_el_paquete_ni_al_cliente_al_marcar_que_no_renovo(api, auth, escenario):
    cm = auth(escenario["ana"])
    pid = escenario["pa"].id
    r = api.post(f"/api/paquetes/{pid}/no-renovar", headers=cm,
                 json={"accion": "borrar", "confirmar_nombre": "Básico"})
    assert r.status_code == 403
    assert api.post(f"/api/paquetes/{pid}/no-renovar", headers=cm, json={"accion": "conservar"}).status_code == 200


def test_reasignar_cliente_solo_admin_a_cm_activo(api, db, auth, escenario, crear_usuario):
    adm = auth(crear_usuario("admin.demo", rol="admin"))
    cid = escenario["ca"].id
    assert api.post(f"/api/clientes/{cid}/reasignar", headers=adm, json={"cm_id": escenario["beto"].id}).status_code == 200
    assert db.get(Cliente, cid).cm_id == escenario["beto"].id
    assert api.post(f"/api/clientes/{cid}/reasignar", headers=adm, json={"cm_id": None}).status_code == 200
    por = api.get("/api/clientes?por_reasignar=true", headers=adm).json()
    assert [c["id"] for c in por] == [cid]
    assert api.post(f"/api/clientes/{cid}/reasignar", headers=adm, json={"cm_id": adm and 99999}).status_code == 422


def test_filtro_por_quincena_usa_fecha_de_renovacion_de_algun_paquete_vigente(api, db, auth, crear_usuario, fabrica):
    ana = crear_usuario("ana.ruiz")
    h = auth(ana)
    uno = fabrica.cliente(ana, "Solo 1ra")
    fabrica.ciclo(uno, dt.date(2026, 10, 15))
    dos = fabrica.cliente(ana, "Solo 2da")
    fabrica.ciclo(dos, dt.date(2026, 10, 16))
    ambos = fabrica.cliente(ana, "En ambas")
    fabrica.ciclo(ambos, dt.date(2026, 10, 5))
    fabrica.ciclo(ambos, dt.date(2026, 10, 31))
    arch = fabrica.cliente(ana, "Archivado")
    fabrica.ciclo(arch, dt.date(2026, 10, 3), estado="archivado")
    q1 = {c["nombre"] for c in api.get("/api/clientes?quincena=1", headers=h).json()}
    q2 = {c["nombre"] for c in api.get("/api/clientes?quincena=2", headers=h).json()}
    assert q1 == {"Solo 1ra", "En ambas"} and q2 == {"Solo 2da", "En ambas"}


def test_pagado_se_suma_de_pagos_y_restante_con_avance(api, auth, escenario):
    h = auth(escenario["admin"])
    pid = escenario["pa"].id
    api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": 500})
    r = api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": "250.50", "nota": "efectivo"}).json()["paquete"]
    assert Decimal(str(r["pagado"])) == Decimal("750.50") and Decimal(str(r["restante"])) == Decimal("749.50")
    assert r["avance_pct"] == 50.0 and r["renovacion_pagada"] is False
    r = api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": "749.50"}).json()["paquete"]
    assert r["renovacion_pagada"] is True and r["semaforo"] == "verde"


def test_pago_invalido(api, auth, escenario):
    h = auth(escenario["admin"])
    pid = escenario["pa"].id
    assert api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": 0}).status_code == 422
    assert api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": -5}).status_code == 422
    assert api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": 1500.01}).status_code == 422
    assert api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": 10, "fecha": "2026-10-02"}).status_code == 422


def test_el_admin_borra_pagos_de_cualquier_fecha(api, db, auth, escenario):
    h = auth(escenario["admin"])
    pid = escenario["pa"].id
    pago_id = api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": 100}).json()["pago_id"]
    assert api.delete(f"/api/pagos/{pago_id}", headers=h).status_code == 200
    antiguo = Pago(paquete_id=pid, monto=Decimal(50), fecha=H, registrado_por=escenario["admin"].id,
                   creado_en=dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc))
    db.add(antiguo)
    db.flush()
    assert api.delete(f"/api/pagos/{antiguo.id}", headers=h).status_code == 200


def test_semaforo_y_estado_efectivo(api, auth, fabrica, escenario):
    h, c = auth(escenario["ana"]), escenario["ca"]
    casos = {
        "gris": fabrica.ciclo(c, H + D(20)),
        "rojo": fabrica.ciclo(c, H - D(1)),
        "amarillo": fabrica.ciclo(c, H + D(20), estado="renovado", decision="si", pagos=[(100, H)]),
        "verde": fabrica.ciclo(c, H + D(20), estado="renovado", decision="si", pagos=[(1500, H)]),
    }
    for esperado, p in casos.items():
        assert api.get(f"/api/paquetes/{p.id}", headers=h).json()["semaforo"] == esperado
    assert api.get(f"/api/paquetes/{fabrica.ciclo(c, H + D(4)).id}", headers=h).json()["estado_efectivo"] == "por_vencer"
    assert api.get(f"/api/paquetes/{fabrica.ciclo(c, H + D(5)).id}", headers=h).json()["estado_efectivo"] == "activo"


def test_recordatorio_con_wa_me_y_marcado_de_envio(api, db, auth, escenario):
    h = auth(escenario["admin"])
    pid = escenario["pa"].id
    r = api.post(f"/api/paquetes/{pid}/recordatorio", headers=h)
    assert r.status_code == 201
    d = r.json()
    assert d["wa_url"].startswith("https://wa.me/525512345678?text=") and "1%2C500.00" in d["wa_url"]
    assert "Cliente de Ana" in d["texto"] and d["enviado_en"] is None
    assert api.post(f"/api/recordatorios/{d['id']}/marcar-enviado", headers=h).json()["enviado_en"]
    assert db.scalars(select(RecordatorioCliente)).one().enviado_en is not None


def test_normalizar_telefono():
    from app.services.recordatorios import normalizar_telefono as n
    assert n("55 1234-5678") == "525512345678" and n("+52 1 55 1234 5678") == "525512345678"
    assert n("525512345678") == "525512345678" and n("123") is None and n(None) is None


def test_alta_de_paquete_captura_inicio_y_renovacion_es_inicio_mas_30(api, db, auth, crear_usuario):
    ana = crear_usuario("ana.ruiz")
    h = auth(ana)
    cid = api.post("/api/clientes", headers=h, json={"nombre": "Sin paquete"}).json()["id"]
    r = api.post(f"/api/clientes/{cid}/paquetes", headers=h, json={"paquete_id": 3, "tipo_id": 1, "costo": 4500, "fecha_inicio": "2026-10-10"})
    d = api.get(f"/api/paquetes/{r.json()['id']}", headers=h).json()
    assert (d["fecha_inicio"], d["fecha_renovacion"]) == ("2026-10-10", "2026-11-09")
    cid2 = api.post("/api/clientes", headers=h, json={"nombre": "Otro"}).json()["id"]
    r = api.post(f"/api/clientes/{cid2}/paquetes", headers=h, json={"paquete_id": 1, "tipo_id": 1, "costo": 1})
    assert api.get(f"/api/paquetes/{r.json()['id']}", headers=h).json()["fecha_renovacion"] == str(H + D(30))


def test_un_cliente_tiene_un_solo_paquete(api, auth, escenario):
    h = auth(escenario["ana"])
    r = api.post(f"/api/clientes/{escenario['ca'].id}/paquetes", headers=h, json={"paquete_id": 3, "tipo_id": 1, "costo": 100})
    assert r.status_code == 409 and "un solo paquete" in r.json()["detail"].lower()
    dos = [{"paquete_id": 1, "tipo_id": 1, "costo": 1}, {"paquete_id": 2, "tipo_id": 1, "costo": 1}]
    assert api.post("/api/clientes", headers=h, json={"nombre": "Con dos", "paquetes": dos}).status_code == 422
    assert api.post("/api/clientes", headers=h, json={"nombre": "Con uno", "paquetes": dos[:1]}).status_code == 201


def test_paquete_tipo_y_costo_solo_cambian_al_renovar_no_editando(api, auth, escenario, crear_usuario):
    h, pid = auth(escenario["ana"]), escenario["pa"].id
    for cuerpo in ({"paquete_id": 3}, {"tipo_id": 2}, {"costo": 1}):
        assert api.patch(f"/api/paquetes/{pid}", headers=h, json=cuerpo).status_code == 403
    assert api.patch(f"/api/paquetes/{pid}", headers=h, json={"fecha_inicio": "2026-10-02"}).status_code == 200
    adm = auth(crear_usuario("admin.demo", rol="admin"))
    assert api.patch(f"/api/paquetes/{pid}", headers=adm, json={"costo": 1600}).status_code == 200


def test_cambiar_el_inicio_recalcula_renovacion_y_mueve_al_cliente_de_quincena(api, auth, crear_usuario, fabrica):
    ana = crear_usuario("ana.ruiz")
    h = auth(ana)
    c = fabrica.cliente(ana, "Se mueve")
    p = fabrica.ciclo(c, dt.date(2026, 10, 14))
    nombres = lambda q: [x["nombre"] for x in api.get(f"/api/clientes?quincena={q}", headers=h).json()]
    assert nombres(1) == ["Se mueve"] and nombres(2) == []
    r = api.patch(f"/api/paquetes/{p.id}", headers=h, json={"fecha_inicio": "2026-10-02"})
    assert r.json()["fecha_renovacion"] == "2026-11-01" and nombres(1) == ["Se mueve"]
    r = api.patch(f"/api/paquetes/{p.id}", headers=h, json={"fecha_inicio": "2026-10-10"})
    r = api.patch(f"/api/paquetes/{p.id}", headers=h, json={"fecha_inicio": "2026-10-20"})
    assert r.json()["fecha_renovacion"] == "2026-11-19" and nombres(1) == [] and nombres(2) == ["Se mueve"]
    assert r.json()["quincena"] == 2


def test_la_fecha_de_renovacion_ya_no_se_puede_editar_a_mano(api, auth, escenario):
    r = api.patch(f"/api/paquetes/{escenario['pa'].id}", headers=auth(escenario["ana"]), json={"fecha_renovacion": "2027-01-01"})
    assert r.status_code == 200 and r.json()["fecha_renovacion"] == str(H + D(10))


def test_el_cm_no_registra_pagos_ni_prorroga_ni_mensaje_de_cobro(api, auth, escenario, fabrica):
    h = auth(escenario["ana"])
    pid = escenario["pa"].id
    assert api.post(f"/api/paquetes/{pid}/pagos", headers=h, json={"monto": 100}).status_code == 403
    assert api.post(f"/api/paquetes/{pid}/prorroga", headers=h).status_code == 403
    assert api.post(f"/api/paquetes/{pid}/recordatorio", headers=h).status_code == 403
    assert api.get(f"/api/paquetes/{pid}/recordatorios", headers=h).status_code == 403


def test_la_ficha_del_cm_no_trae_montos_ni_pagos(api, auth, escenario, fabrica):
    p = fabrica.ciclo(escenario["ca"], H + D(10), costo=1500, pagos=[(500, H)], por=escenario["admin"])
    cm, adm = auth(escenario["ana"]), auth(escenario["admin"])
    d = api.get(f"/api/paquetes/{p.id}", headers=cm).json()
    assert not {"costo", "pagado", "restante", "avance_pct"} & set(d)
    assert d["pagos"] == [] and d["paquete"] == "Básico" and d["fecha_renovacion"] == str(H + D(10))
    assert d["semaforo"] and "estado_efectivo" in d and "prorroga_hasta" in d
    ficha = api.get(f"/api/clientes/{escenario['ca'].id}", headers=cm).json()
    assert all("costo" not in q for q in ficha["paquetes"] + ficha["historial"])
    dadm = api.get(f"/api/paquetes/{p.id}", headers=adm).json()
    assert Decimal(str(dadm["costo"])) == Decimal(1500) and len(dadm["pagos"]) == 1


def test_el_tablero_y_los_bloqueos_del_cm_tampoco_traen_montos(api, auth, escenario, fabrica):
    fabrica.ciclo(escenario["ca"], H - D(1), costo=900)
    h = auth(escenario["ana"])
    for b in api.get("/api/bloqueos", headers=h).json():
        assert "costo" not in b and "restante" not in b
    tablero = api.get("/api/renovaciones/tablero?anio=2026&mes=10&quincena=ambas", headers=h).json()
    for col in tablero["columnas"].values():
        for t in col:
            assert "costo" not in t and "pagado" not in t


def test_el_cm_da_de_alta_con_el_costo_del_catalogo_y_sin_pagos(api, db, auth, escenario):
    from app.models import CatalogoPaquete
    basico = db.scalars(select(CatalogoPaquete).where(CatalogoPaquete.nombre == "Básico")).one()
    basico.costo = Decimal(1234)
    db.flush()
    h = auth(escenario["ana"])
    r = api.post("/api/clientes", headers=h, json={"nombre": "Nuevo del CM",
                 "paquetes": [{"paquete_id": basico.id, "tipo_id": 1, "costo": 1, "fecha_inicio": str(H)}]})
    assert r.status_code == 201
    nuevo = db.scalars(select(PaqueteCliente).join(Cliente).where(Cliente.nombre == "Nuevo del CM")).one()
    assert nuevo.costo == Decimal(1234)
    assert db.scalars(select(Pago).where(Pago.paquete_id == nuevo.id)).all() == []


def test_el_admin_si_fija_el_costo_al_dar_de_alta(api, db, auth, escenario):
    h = auth(escenario["admin"])
    r = api.post("/api/clientes", headers=h, json={"nombre": "Nuevo del admin", "cm_id": escenario["ana"].id,
                 "paquetes": [{"paquete_id": 1, "tipo_id": 1, "costo": 777, "fecha_inicio": str(H)}]})
    assert r.status_code == 201
    nuevo = db.scalars(select(PaqueteCliente).join(Cliente).where(Cliente.nombre == "Nuevo del admin")).one()
    assert nuevo.costo == Decimal(777)


def test_el_costo_del_catalogo_lo_cambia_el_admin(api, auth, escenario):
    cm, adm = auth(escenario["ana"]), auth(escenario["admin"])
    assert api.patch("/api/catalogos/paquetes/1", headers=cm, json={"costo": 50}).status_code == 403
    r = api.patch("/api/catalogos/paquetes/1", headers=adm, json={"costo": 2100})
    assert r.status_code == 200 and Decimal(str(r.json()["costo"])) == Decimal(2100)
    assert Decimal(str(api.get("/api/catalogos/paquetes", headers=cm).json()[0]["costo"])) == Decimal(2100)
