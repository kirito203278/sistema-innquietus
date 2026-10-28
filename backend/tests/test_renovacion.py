import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import (ArchivoNoRenovado, Bitacora, Cliente, Notificacion, PaqueteCliente, Pago, RecordatorioCliente,
                        Renovacion)

H = dt.date(2026, 10, 1)
D = dt.timedelta


@pytest.fixture(autouse=True)
def _hoy(hoy_fijo):
    hoy_fijo(H)


@pytest.fixture
def ctx(db, crear_usuario, fabrica, auth):
    ana = crear_usuario("ana.ruiz")
    admin = crear_usuario("admin.jefe", rol="admin")
    c = fabrica.cliente(ana, "Cliente Ana")
    return dict(ana=ana, admin=admin, c=c, h=auth(admin), h_cm=auth(ana))


def _pagado(p, monto=None):
    return [(monto if monto is not None else p, H - D(1))]


def test_renovar_exige_pago_completo(api, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H + D(2), costo=1500, pagos=[(500, H)])
    r = api.post(f"/api/paquetes/{p.id}/renovar", headers=ctx["h"], json={})
    assert r.status_code == 422 and "pagado por completo" in r.json()["detail"]


def test_renovar_abre_ciclo_que_empieza_hoy_y_renueva_en_30_dias(api, db, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H + D(2), costo=1500, pagos=[(1500, H)])
    r = api.post(f"/api/paquetes/{p.id}/renovar", headers=ctx["h"], json={"fecha_renovacion": "2030-01-01"})
    assert r.status_code == 200
    nuevo, ant = r.json()["nuevo"], r.json()["anterior"]
    assert nuevo["fecha_inicio"] == str(H) and nuevo["fecha_renovacion"] == str(H + D(30))
    assert float(nuevo["pagado"]) == 0 and nuevo["ciclo_anterior_id"] == p.id and nuevo["estado"] == "activo"
    assert ant["estado"] == "renovado" and ant["renovacion_decision"] == "si" and float(ant["pagado"]) == 1500
    rn = db.scalars(select(Renovacion)).one()
    assert (rn.costo_anterior, rn.costo_nuevo) == (Decimal(1500), Decimal(1500))


def test_renovar_despues_de_vencido_tambien_empieza_el_dia_que_se_confirma(api, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1000, pagos=_pagado(1000))
    nuevo = api.post(f"/api/paquetes/{p.id}/renovar", headers=ctx["h"], json={}).json()["nuevo"]
    assert (nuevo["fecha_inicio"], nuevo["fecha_renovacion"]) == (str(H), str(H + D(30)))


def test_renovar_con_otro_paquete_cambia_nombre_tipo_y_costo(api, db, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H + D(2), costo=1500, paquete="Básico", pagos=_pagado(1500))
    r = api.post(f"/api/paquetes/{p.id}/renovar", headers=ctx["h"], json={"paquete_id": 3, "tipo_id": 2, "costo": 4500})
    n = r.json()["nuevo"]
    assert (n["paquete"], n["tipo"], float(n["costo"])) == ("Élite", "Dinamita", 4500)
    rn = db.scalars(select(Renovacion)).one()
    assert (rn.costo_anterior, rn.costo_nuevo, rn.paquete_nuevo_id) == (Decimal(1500), Decimal(4500), 3)


def test_cambiar_de_paquete_reinicia_el_contador_de_renovaciones(api, db, ctx, fabrica):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H + D(2), paquete="Básico", pagos=_pagado(1500))

    def renovar(pk, **cuerpo):
        n = api.post(f"/api/paquetes/{pk}/renovar", headers=h, json=cuerpo).json()["nuevo"]
        api.post(f"/api/paquetes/{n['id']}/pagos", headers=h, json={"monto": float(n["costo"])})
        return n
    n1 = renovar(p.id)
    n2 = renovar(n1["id"])
    assert (n1["veces_renovado"], n2["veces_renovado"]) == (1, 2)
    n3 = renovar(n2["id"], paquete_id=3, tipo_id=2, costo=4500)
    assert (n3["veces_renovado"], n3["paquete"], n3["tipo"], float(n3["costo"])) == (0, "Élite", "Dinamita", 4500)
    n4 = renovar(n3["id"])
    assert n4["veces_renovado"] == 1
    d = api.get(f"/api/paquetes/{n4['id']}", headers=h).json()
    assert d["veces_renovado"] == 1 and len(d["ciclos"]) == 5


def test_no_se_renueva_dos_veces_el_mismo_ciclo(api, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H + D(2), pagos=_pagado(1500))
    assert api.post(f"/api/paquetes/{p.id}/renovar", headers=ctx["h"], json={}).status_code == 200
    assert api.post(f"/api/paquetes/{p.id}/renovar", headers=ctx["h"], json={}).status_code == 409


def test_renovar_marca_leidos_los_avisos_del_paquete(api, db, ctx, fabrica):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H + D(3), pagos=_pagado(1500))
    tareas.avisos_renovacion(db, H)
    assert db.scalar(select(func.count()).select_from(Notificacion).where(Notificacion.leida.is_(False))) == 1
    api.post(f"/api/paquetes/{p.id}/renovar", headers=ctx["h"], json={})
    assert db.scalar(select(func.count()).select_from(Notificacion).where(Notificacion.leida.is_(False))) == 0


def test_no_renovar_antes_del_fin_del_contrato_queda_programado_y_se_archiva_solo(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    a = fabrica.ciclo(ctx["c"], H + D(2))
    r = api.post(f"/api/paquetes/{a.id}/no-renovar", headers=ctx["h"], json={"accion": "conservar"})
    assert r.json()["programado"] is True and r.json()["se_archiva_el"] == str(H + D(3))
    db.refresh(a), db.refresh(ctx["c"])
    assert a.estado == "activo" and a.renovacion_decision == "no" and ctx["c"].estado == "activo"
    d = api.get(f"/api/paquetes/{a.id}", headers=ctx["h"]).json()
    assert d["no_renovara"] is True and d["bloqueado"] is False
    hoy_fijo(H + D(2))
    tareas.avisos_renovacion(db, H + D(2))
    db.refresh(a)
    assert a.estado == "activo"
    hoy_fijo(H + D(3))
    tareas.avisos_renovacion(db, H + D(3))
    db.refresh(a), db.refresh(ctx["c"])
    assert a.estado == "archivado" and ctx["c"].estado == "no_renovado"
    assert db.scalars(select(ArchivoNoRenovado)).one().reingresado_en is None


def test_programado_con_otros_paquetes_el_cliente_sigue_activo(api, db, ctx, fabrica):
    from app.jobs import tareas
    a, _ = fabrica.ciclo(ctx["c"], H - D(1), decision="no"), fabrica.ciclo(ctx["c"], H + D(20), paquete="Élite")
    tareas.avisos_renovacion(db, H)
    db.refresh(a), db.refresh(ctx["c"])
    assert a.estado == "archivado" and ctx["c"].estado == "activo"
    assert db.scalar(select(func.count()).select_from(ArchivoNoRenovado)) == 0


def test_se_puede_deshacer_la_marca_no_renovara_antes_del_fin(api, db, ctx, fabrica):
    a = fabrica.ciclo(ctx["c"], H + D(2))
    api.post(f"/api/paquetes/{a.id}/no-renovar", headers=ctx["h"], json={"accion": "conservar"})
    r = api.post(f"/api/paquetes/{a.id}/revertir-decision", headers=ctx["h"])
    assert r.status_code == 200 and r.json()["renovacion_decision"] == "pendiente" and r.json()["no_renovara"] is False
    assert api.post(f"/api/paquetes/{a.id}/revertir-decision", headers=ctx["h"]).status_code == 409


def test_no_renovar_ya_vencido_es_inmediato_y_si_era_el_ultimo_el_cliente_pasa_a_no_renovados(api, db, ctx, fabrica):
    a = fabrica.ciclo(ctx["c"], H - D(1))
    r = api.post(f"/api/paquetes/{a.id}/no-renovar", headers=ctx["h"], json={"accion": "conservar"})
    assert r.json() == {"cliente_eliminado": False, "cliente_a_no_renovados": True, "programado": False}
    db.refresh(a), db.refresh(ctx["c"])
    assert a.estado == "archivado" and a.archivado_en and ctx["c"].estado == "no_renovado"
    assert [c["nombre"] for c in api.get("/api/clientes?estado=no_renovado", headers=ctx["h"]).json()] == ["Cliente Ana"]
    assert api.get("/api/clientes", headers=ctx["h"]).json() == []


def test_cliente_con_ciclo_renovado_pero_sin_vigentes_tambien_pasa_a_no_renovados(api, db, ctx, fabrica):
    viejo = fabrica.ciclo(ctx["c"], H - D(5), estado="renovado", decision="si")
    nuevo = fabrica.ciclo(ctx["c"], H - D(1), anterior=viejo)
    api.post(f"/api/paquetes/{nuevo.id}/no-renovar", headers=ctx["h"], json={"accion": "conservar"})
    db.refresh(ctx["c"])
    assert ctx["c"].estado == "no_renovado"


def test_borrar_paquete_exige_nombre_exacto(api, db, ctx, fabrica):
    a, _ = fabrica.ciclo(ctx["c"], H + D(2), paquete="Estándar"), fabrica.ciclo(ctx["c"], H + D(20))
    url = f"/api/paquetes/{a.id}/no-renovar"
    for mal in (None, "estándar", "Estandar", "Básico"):
        assert api.post(url, headers=ctx["h"], json={"accion": "borrar", "confirmar_nombre": mal}).status_code == 422
    assert api.post(url, headers=ctx["h"], json={"accion": "borrar", "confirmar_nombre": "Estándar"}).status_code == 200
    db.refresh(a)
    assert a.estado == "eliminado"
    assert all(p["id"] != a.id for p in api.get(f"/api/clientes/{ctx['c'].id}", headers=ctx["h"]).json()["historial"])


def test_borrar_ultimo_paquete_pregunta_si_se_elimina_el_cliente(api, db, ctx, fabrica):
    a = fabrica.ciclo(ctx["c"], H + D(2))
    cuerpo = {"accion": "borrar", "confirmar_nombre": "Básico"}
    r = api.post(f"/api/paquetes/{a.id}/no-renovar", headers=ctx["h"], json=cuerpo)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ultimo_paquete"
    db.refresh(a)
    assert a.estado == "activo"
    r = api.post(f"/api/paquetes/{a.id}/no-renovar", headers=ctx["h"], json={**cuerpo, "eliminar_cliente": False})
    assert r.json()["cliente_a_no_renovados"] is True and db.get(Cliente, ctx["c"].id).estado == "no_renovado"


def test_borrar_ultimo_paquete_y_cliente_con_historial_de_ciclos(api, db, ctx, fabrica):
    viejo = fabrica.ciclo(ctx["c"], H - D(5), estado="renovado", decision="si", pagos=[(100, H)])
    nuevo = fabrica.ciclo(ctx["c"], H + D(25), anterior=viejo)
    db.add(Renovacion(ciclo_anterior_id=viejo.id, ciclo_nuevo_id=nuevo.id, paquete_anterior_id=1, paquete_nuevo_id=1,
                      costo_anterior=1500, costo_nuevo=1500, fecha=H))
    db.flush()
    cid = ctx["c"].id
    r = api.post(f"/api/paquetes/{nuevo.id}/no-renovar", headers=ctx["h"],
                 json={"accion": "borrar", "confirmar_nombre": "Básico", "eliminar_cliente": True})
    assert r.json()["cliente_eliminado"] is True
    db.expire_all()
    assert db.get(Cliente, cid) is None
    assert db.scalar(select(func.count()).select_from(Pago)) == 0


def test_el_contrato_termina_a_las_2359_del_dia_R_el_bloqueo_empieza_al_dia_siguiente(api, ctx, fabrica, hoy_fijo):
    p = fabrica.ciclo(ctx["c"], H + D(2))
    hoy_fijo(H + D(2))
    assert api.get(f"/api/paquetes/{p.id}", headers=ctx["h"]).json()["bloqueado"] is False
    assert api.get("/api/bloqueos", headers=ctx["h"]).json() == []
    hoy_fijo(H + D(3))
    d = api.get(f"/api/paquetes/{p.id}", headers=ctx["h"]).json()
    assert d["bloqueado"] is True and d["estado_efectivo"] == "vencido" and d["semaforo"] == "rojo"
    b = api.get("/api/bloqueos", headers=ctx["h"]).json()
    assert [x["id"] for x in b] == [p.id] and b[0]["cliente_nombre"] == "Cliente Ana"


def test_opciones_de_la_ventana_segun_el_caso(api, ctx, fabrica):
    h = ctx["h"]
    sin_respuesta = fabrica.ciclo(ctx["c"], H - D(1), pagos=[(100, H)])
    pagado = fabrica.ciclo(ctx["c"], H - D(1), pagos=_pagado(1500))
    confirmo = fabrica.ciclo(ctx["c"], H - D(1), decision="si", pagos=[(100, H)])
    usada = fabrica.ciclo(ctx["c"], H - D(3), decision="si", prorroga=(H - D(2), H - D(1)))
    op = {p.id: api.get(f"/api/paquetes/{p.id}", headers=h).json()["opciones_bloqueo"]
          for p in (sin_respuesta, pagado, confirmo, usada)}
    assert op[sin_respuesta.id] == ["va_a_renovar", "no_renovo"]
    assert op[pagado.id] == ["renovo", "no_renovo"]
    assert op[confirmo.id] == ["prorroga", "no_renovo"]
    assert op[usada.id] == ["no_renovo"]


def test_mientras_hay_bloqueo_solo_se_traba_ESE_cliente_y_las_salidas_funcionan(api, db, ctx, fabrica):
    h = ctx["h"]
    bloqueado = fabrica.ciclo(ctx["c"], H - D(1), pagos=[(100, H)])
    aj = fabrica.cliente(ctx["ana"], "Cliente sin problema")
    libre = fabrica.ciclo(aj, H + D(20))
    intentos = [
        ("post", f"/api/paquetes/{bloqueado.id}/pagos", {"monto": 50}),
        ("patch", f"/api/clientes/{ctx['c'].id}", {"nombre": "X"}),
        ("patch", f"/api/paquetes/{bloqueado.id}", {"costo": 1}),
        ("post", f"/api/paquetes/{bloqueado.id}/recordatorio", None),
    ]
    for metodo, url, cuerpo in intentos:
        r = getattr(api, metodo)(url, headers=h, **({"json": cuerpo} if cuerpo is not None else {}))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "bloqueado", (url, r.status_code, r.text)
    assert api.delete(f"/api/clientes/{ctx['c'].id}?confirmar_nombre=Cliente Ana", headers=h).status_code == 409
    assert api.get(f"/api/clientes/{ctx['c'].id}", headers=h).status_code == 200
    assert api.post(f"/api/paquetes/{libre.id}/pagos", headers=h, json={"monto": 50}).status_code == 201
    assert api.patch(f"/api/clientes/{aj.id}", headers=h, json={"nombre": "Otro nombre"}).status_code == 200
    r = api.post(f"/api/paquetes/{bloqueado.id}/confirmar-renovacion", headers=h)
    assert r.status_code == 200 and r.json()["paquete"]["bloqueado"] is False
    assert api.post(f"/api/paquetes/{bloqueado.id}/pagos", headers=h, json={"monto": 50}).status_code == 201


def test_el_bloqueo_tambien_aplica_a_un_admin_que_opera_por_el_cm(api, ctx, fabrica, crear_usuario, auth):
    p = fabrica.ciclo(ctx["c"], H - D(1))
    adm = auth(crear_usuario("admin.demo", rol="admin"))
    assert api.post(f"/api/paquetes/{p.id}/pagos", headers=adm, json={"monto": 10}).status_code == 409
    assert api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=adm).status_code == 200


def test_bloqueos_solo_muestra_la_cartera_del_cm(api, ctx, fabrica, crear_usuario, auth):
    fabrica.ciclo(ctx["c"], H - D(1))
    beto = crear_usuario("beto.luna")
    fabrica.ciclo(fabrica.cliente(beto, "Ajeno"), H - D(1))
    assert len(api.get("/api/bloqueos", headers=ctx["h_cm"]).json()) == 1
    assert len(api.get("/api/bloqueos", headers=auth(beto)).json()) == 1
    assert len(api.get("/api/bloqueos", headers=auth(crear_usuario("admin.demo", rol="admin"))).json()) == 2


def test_prorroga_dura_5_dias_naturales_y_la_fecha_es_automatica(api, db, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H - D(1), decision="si")
    r = api.post(f"/api/paquetes/{p.id}/prorroga", headers=ctx["h"], json={"hasta": "2030-01-01"})
    assert r.status_code == 200
    assert r.json()["prorroga_hasta"] == str(H + D(5)) and r.json()["prorroga_registrada_en"] == str(H)
    assert r.json()["prorroga_dias_restantes"] == 5 and r.json()["bloqueado"] is False and r.json()["prorroga_activa"] is True


def test_prorroga_solo_con_el_contrato_terminado_con_saldo_confirmado_y_una_vez(api, ctx, fabrica):
    h = ctx["h"]
    antes = fabrica.ciclo(ctx["c"], H + D(2), decision="si")
    pagado = fabrica.ciclo(ctx["c"], H - D(1), decision="si", pagos=_pagado(1500))
    sin_confirmar = fabrica.ciclo(ctx["c"], H - D(1))
    ok = fabrica.ciclo(ctx["c"], H - D(1), decision="si")
    assert api.post(f"/api/paquetes/{antes.id}/prorroga", headers=h).status_code == 422
    assert api.post(f"/api/paquetes/{pagado.id}/prorroga", headers=h).status_code == 422
    assert api.post(f"/api/paquetes/{sin_confirmar.id}/prorroga", headers=h).status_code == 422
    assert api.post(f"/api/paquetes/{ok.id}/prorroga", headers=h).status_code == 200
    assert api.post(f"/api/paquetes/{ok.id}/prorroga", headers=h).status_code == 409


def test_en_prorroga_admite_pagar_parcial_o_el_resto_y_al_completar_renueva_solo(api, db, ctx, fabrica):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1000, decision="si")
    api.post(f"/api/paquetes/{p.id}/prorroga", headers=h)
    r = api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 400})
    assert r.status_code == 201 and r.json()["renovado_automaticamente"] is None
    assert api.get("/api/bloqueos", headers=h).json() == []
    assert api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 700}).status_code == 422
    r = api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 600})
    assert r.status_code == 201 and r.json()["renovado_automaticamente"]
    assert r.json()["paquete"]["estado"] == "renovado" and r.json()["paquete"]["renovacion_decision"] == "si"
    n = api.get(f"/api/paquetes/{r.json()['renovado_automaticamente']}", headers=h).json()
    assert (n["fecha_inicio"], n["fecha_renovacion"], n["estado"]) == (str(H - D(1)), str(H + D(29)), "activo")
    assert (n["paquete"], float(n["costo"]), float(n["pagado"])) == ("Básico", 1000.0, 0.0)
    assert api.get("/api/bloqueos", headers=h).json() == []
    assert db.scalars(select(Renovacion)).one().ciclo_anterior_id == p.id


def test_pagar_completo_sin_prorroga_no_renueva_solo(api, db, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H + D(2), costo=1000)
    r = api.post(f"/api/paquetes/{p.id}/pagos", headers=ctx["h"], json={"monto": 1000})
    assert r.json()["renovado_automaticamente"] is None
    db.refresh(p)
    assert p.estado == "activo"


def test_prorroga_vencida_sin_pago_el_cliente_pasa_solo_a_no_renovados_y_queda_el_mensaje(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1000, decision="si", pagos=[(300, H)])
    api.post(f"/api/paquetes/{p.id}/prorroga", headers=ctx["h"])
    hoy_fijo(H + D(5))
    assert tareas.avisos_prorroga(db, H + D(5))["prorrogas_vencidas"] == 0
    hoy_fijo(H + D(6))
    res = tareas.avisos_prorroga(db, H + D(6))
    assert res["prorrogas_vencidas"] == 1
    db.refresh(p), db.refresh(ctx["c"])
    assert p.estado == "archivado" and ctx["c"].estado == "no_renovado"
    n = db.scalars(select(Notificacion).where(Notificacion.tipo == "prorroga_vencida")).one()
    assert not n.requiere_respuesta and "No renovados" in n.mensaje and "$700.00" in n.mensaje
    r = db.scalars(select(RecordatorioCliente)).one()
    assert r.enviado_en is None and "$700.00" in r.texto
    assert tareas.avisos_prorroga(db, H + D(6))["prorrogas_vencidas"] == 0
    assert db.scalar(select(func.count()).select_from(RecordatorioCliente)) == 1


def test_prorroga_pagada_a_tiempo_se_renueva_y_no_se_archiva(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1000, decision="si")
    api.post(f"/api/paquetes/{p.id}/prorroga", headers=ctx["h"])
    api.post(f"/api/paquetes/{p.id}/pagos", headers=ctx["h"], json={"monto": 1000})
    hoy_fijo(H + D(6))
    assert tareas.avisos_prorroga(db, H + D(6))["prorrogas_vencidas"] == 0
    db.refresh(p), db.refresh(ctx["c"])
    assert p.estado == "renovado" and ctx["c"].estado == "activo"


def test_aviso_de_prorroga_3_dias_antes_de_vencer(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1000, decision="si")
    api.post(f"/api/paquetes/{p.id}/prorroga", headers=ctx["h"])
    assert tareas.avisos_prorroga(db, H + D(1))["avisos_prorroga"] == 0
    assert tareas.avisos_prorroga(db, H + D(2))["avisos_prorroga"] == 1
    assert tareas.avisos_prorroga(db, H + D(2))["avisos_prorroga"] == 0


def test_el_mensaje_se_puede_enviar_una_sola_vez(api, db, ctx, fabrica):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H + D(2), costo=1000, pagos=[(100, H)])
    a = api.post(f"/api/paquetes/{p.id}/recordatorio", headers=h)
    assert a.status_code == 201 and a.json()["wa_url"].startswith("https://wa.me/525512345678?text=")
    b = api.post(f"/api/paquetes/{p.id}/recordatorio", headers=h)
    assert b.json()["id"] == a.json()["id"] and db.scalar(select(func.count()).select_from(RecordatorioCliente)) == 1
    assert api.post(f"/api/recordatorios/{a.json()['id']}/marcar-enviado", headers=h).json()["enviado_en"]
    assert api.post(f"/api/paquetes/{p.id}/recordatorio", headers=h).status_code == 409
    assert api.post(f"/api/recordatorios/{a.json()['id']}/marcar-enviado", headers=h).status_code == 409


def test_sin_decision_tras_2_dias_de_bloqueo_pasa_solo_a_no_renovados(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H)
    hoy_fijo(H + D(1))
    r = tareas.avisos_renovacion(db, H + D(1))
    assert r["marcados_vencidos"] == 1 and r["pasaron_a_no_renovados"] == 0
    assert db.scalars(select(Notificacion).where(Notificacion.tipo == "paquete_vencido")).one()
    db.refresh(p)
    assert p.estado == "vencido"
    tareas.avisos_renovacion(db, H + D(2))
    db.refresh(p)
    assert p.estado == "vencido"
    r = tareas.avisos_renovacion(db, H + D(3))
    assert r["pasaron_a_no_renovados"] == 1
    db.refresh(p), db.refresh(ctx["c"])
    assert p.estado == "archivado" and ctx["c"].estado == "no_renovado"


def test_con_prorroga_corriendo_no_se_archiva_por_falta_de_decision(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1000, decision="si")
    hoy_fijo(H)
    api.post(f"/api/paquetes/{p.id}/prorroga", headers=ctx["h"])
    hoy_fijo(H + D(4))
    assert tareas.avisos_renovacion(db, H + D(4))["pasaron_a_no_renovados"] == 0
    db.refresh(p)
    assert p.estado != "archivado"


def test_avisos_de_renovacion_en_R_menos_4(db, ctx, fabrica):
    from app.jobs import tareas
    fabrica.ciclo(ctx["c"], H + D(5))
    fabrica.ciclo(ctx["c"], H + D(4))
    assert tareas.avisos_renovacion(db, H)["avisos"] == 1


def test_ejemplo_renueva_10_nov_aviso_6_nov_y_bloqueo_desde_el_11(db, ctx, fabrica):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], dt.date(2026, 11, 10))
    assert tareas.avisos_renovacion(db, dt.date(2026, 11, 5))["avisos"] == 0
    assert tareas.avisos_renovacion(db, dt.date(2026, 11, 6))["avisos"] == 1
    assert tareas.avisos_renovacion(db, dt.date(2026, 11, 10))["marcados_vencidos"] == 0
    assert tareas.avisos_renovacion(db, dt.date(2026, 11, 11))["marcados_vencidos"] == 1
    db.refresh(p)
    assert p.estado == "vencido"


def test_jobs_son_idempotentes_no_duplican_notificaciones(db, ctx, fabrica):
    from app.jobs import tareas
    fabrica.ciclo(ctx["c"], H + D(2))
    fabrica.ciclo(ctx["c"], H - D(1))
    fabrica.ciclo(ctx["c"], H - D(30), costo=1000, decision="si", prorroga=(H - D(3), H + D(2)))
    for _ in range(3):
        tareas.avisos_renovacion(db, H)
        tareas.avisos_prorroga(db, H)
    assert db.scalar(select(func.count()).select_from(Notificacion)) == 3


def test_notificaciones_van_al_cm_y_si_esta_por_reasignar_a_los_admin(db, ctx, fabrica, crear_usuario):
    from app.jobs import tareas
    adm1, adm2 = crear_usuario("admin.uno", rol="admin"), crear_usuario("admin.dos", rol="admin", solo_lectura=True)
    crear_usuario("admin.baja", rol="admin", activo=False)
    huerfano = fabrica.cliente(None, "Sin CM")
    fabrica.ciclo(huerfano, H + D(1), por=adm1)
    fabrica.ciclo(ctx["c"], H + D(1))
    tareas.avisos_renovacion(db, H)
    assert sorted(n.usuario_id for n in db.scalars(select(Notificacion))) == sorted([ctx["ana"].id, adm1.id, adm2.id, ctx["admin"].id])


def test_cm_solo_ve_y_lee_sus_notificaciones(api, db, ctx, fabrica, crear_usuario, auth):
    from app.jobs import tareas
    fabrica.ciclo(ctx["c"], H + D(1))
    tareas.avisos_renovacion(db, H)
    beto = auth(crear_usuario("beto.luna"))
    assert api.get("/api/notificaciones", headers=beto).json()["items"] == []
    nid = api.get("/api/notificaciones", headers=ctx["h_cm"]).json()["items"][0]["id"]
    assert api.post(f"/api/notificaciones/{nid}/leer", headers=beto).status_code == 404
    assert api.post(f"/api/notificaciones/{nid}/leer", headers=ctx["h_cm"]).json()["leida"] is True
    assert api.get("/api/notificaciones?solo_no_leidas=true", headers=ctx["h_cm"]).json()["no_leidas"] == 0


def test_endpoint_de_jobs_exige_secreto(api, db, monkeypatch):
    from app.config import get_settings
    from app.jobs import tareas

    class _S:
        def __enter__(self): return db
        def __exit__(self, *a): return False
    monkeypatch.setattr(tareas, "get_sessionmaker", lambda: (lambda: _S()))
    assert api.post("/api/jobs/run/renovaciones").status_code == 401
    assert api.post("/api/jobs/run/renovaciones", headers={"X-Jobs-Secret": "mal"}).status_code == 401
    ok = api.post("/api/jobs/run/renovaciones", headers={"X-Jobs-Secret": get_settings().jobs_secret})
    assert ok.status_code == 200 and ok.json()["resultado"] == {"avisos": 0, "marcados_vencidos": 0, "pasaron_a_no_renovados": 0}
    assert api.post("/api/jobs/run/inexistente", headers={"X-Jobs-Secret": get_settings().jobs_secret}).status_code == 404


def _no_renovado(db, fabrica, ctx, dias):
    c = ctx["c"]
    c.estado = "no_renovado"
    p = fabrica.ciclo(c, H - D(dias + 1), estado="archivado", decision="no", costo=2500, paquete="Estándar",
                      pagos=[(2500, H - D(dias + 5))])
    p.archivado_en = dt.datetime.combine(H, dt.time(12), tzinfo=dt.timezone.utc) - D(dias)
    db.add(ArchivoNoRenovado(cliente_id=c.id, cm_id=c.cm_id, archivado_en=p.archivado_en))
    db.flush()
    return p


def test_reingreso_menos_de_2_meses_continuar_empieza_hoy_y_conserva_historial(api, db, ctx, fabrica):
    anterior = _no_renovado(db, fabrica, ctx, 20)
    assert api.get(f"/api/clientes/{ctx['c'].id}/reingreso-info", headers=ctx["h"]).json()["forzar_nuevo"] is False
    r = api.post(f"/api/clientes/{ctx['c'].id}/reingreso", headers=ctx["h"], json={"modo": "continuar"})
    assert r.status_code == 200 and r.json()["estado"] == "activo"
    nuevo = r.json()["paquetes"][0]
    assert nuevo["paquete"] == "Estándar" and float(nuevo["costo"]) == 2500 and nuevo["ciclo_anterior_id"] == anterior.id
    assert (nuevo["fecha_inicio"], nuevo["fecha_renovacion"]) == (str(H), str(H + D(30)))
    assert [h["id"] for h in r.json()["historial"]] == [anterior.id]
    assert db.scalars(select(ArchivoNoRenovado)).one().reingresado_en is not None


def test_reingreso_menos_de_2_meses_paquete_nuevo_conserva_historial(api, db, ctx, fabrica):
    anterior = _no_renovado(db, fabrica, ctx, 59)
    r = api.post(f"/api/clientes/{ctx['c'].id}/reingreso", headers=ctx["h"],
                 json={"modo": "nuevo", "paquete_id": 3, "tipo_id": 2, "costo": 4500})
    assert r.status_code == 200 and r.json()["paquetes"][0]["paquete"] == "Élite" and len(r.json()["historial"]) == 1
    assert r.json()["paquetes"][0]["fecha_renovacion"] == str(H + D(30))
    assert db.get(PaqueteCliente, anterior.id) is not None


def test_reingreso_2_meses_o_mas_fuerza_nuevo_y_borra_el_historial(api, db, ctx, fabrica):
    anterior = _no_renovado(db, fabrica, ctx, 62)
    assert api.get(f"/api/clientes/{ctx['c'].id}/reingreso-info", headers=ctx["h"]).json()["forzar_nuevo"] is True
    cid = ctx["c"].id
    assert api.post(f"/api/clientes/{cid}/reingreso", headers=ctx["h"], json={"modo": "continuar"}).status_code == 422
    r = api.post(f"/api/clientes/{cid}/reingreso", headers=ctx["h"], json={"modo": "nuevo", "paquete_id": 1, "tipo_id": 1, "costo": 1500})
    assert r.status_code == 200 and r.json()["historial"] == []
    db.expire_all()
    assert db.get(PaqueteCliente, anterior.id) is None and db.scalar(select(func.count()).select_from(Pago)) == 0
    assert db.scalars(select(Bitacora).where(Bitacora.accion == "reingreso")).one().detalle["historial_borrado"] is True


def test_reingreso_frontera_exacta_de_2_meses(api, db, ctx, fabrica, hoy_fijo):
    hoy_fijo(dt.date(2026, 10, 31))
    _no_renovado(db, fabrica, ctx, 0)
    a = db.scalars(select(ArchivoNoRenovado)).one()
    tz = dt.timezone(dt.timedelta(hours=-6))
    for archivado, forzar in ((dt.datetime(2026, 8, 31, 11, 0, tzinfo=tz), True), (dt.datetime(2026, 9, 1, 11, 0, tzinfo=tz), False)):
        a.archivado_en = archivado
        db.flush()
        assert api.get(f"/api/clientes/{ctx['c'].id}/reingreso-info", headers=ctx["h"]).json()["forzar_nuevo"] is forzar


def test_reingreso_solo_aplica_a_clientes_en_no_renovados(api, ctx):
    assert api.post(f"/api/clientes/{ctx['c'].id}/reingreso", headers=ctx["h"],
                    json={"modo": "nuevo", "paquete_id": 1, "tipo_id": 1, "costo": 1}).status_code == 409


def test_cliente_en_no_renovados_no_admite_paquetes_ni_renovar(api, db, ctx, fabrica):
    _no_renovado(db, fabrica, ctx, 10)
    r = api.post(f"/api/clientes/{ctx['c'].id}/paquetes", headers=ctx["h"], json={"paquete_id": 1, "tipo_id": 1, "costo": 100})
    assert r.status_code == 409


def test_purga_elimina_solo_a_los_de_1_año_o_mas(api, db, ctx, fabrica):
    from app.services.renovacion import purgar_no_renovados
    ahora = dt.datetime(2026, 10, 1, 12, tzinfo=dt.timezone(dt.timedelta(hours=-6)))
    ana, nombres = ctx["ana"], {}
    for dias, nombre in ((89, "Reciente"), (200, "Medio año"), (364, "Casi un año"), (366, "Antiguo"), (500, "Muy antiguo")):
        c = fabrica.cliente(ana, nombre, estado="no_renovado")
        fabrica.ciclo(c, H - D(dias), estado="archivado", decision="no", pagos=[(100, H - D(dias))])
        db.add(ArchivoNoRenovado(cliente_id=c.id, cm_id=ana.id, archivado_en=ahora - D(dias)))
        nombres[nombre] = c.id
    activo = fabrica.cliente(ana, "Activo viejo")
    fabrica.ciclo(activo, H + D(5))
    db.flush()
    assert sorted(purgar_no_renovados(db, ahora)) == ["Antiguo", "Muy antiguo"]
    db.expire_all()
    for n in ("Reciente", "Medio año", "Casi un año"):
        assert db.get(Cliente, nombres[n]) is not None
    assert db.get(Cliente, activo.id) is not None and db.get(Cliente, nombres["Antiguo"]) is None
    assert db.scalar(select(func.count()).select_from(ArchivoNoRenovado)) == 3


def test_purga_frontera_de_12_meses_calendario(db, ctx, fabrica):
    from app.services.renovacion import purgar_no_renovados
    tz = dt.timezone(dt.timedelta(hours=-6))
    c = fabrica.cliente(ctx["ana"], "Frontera", estado="no_renovado")
    fabrica.ciclo(c, H, estado="archivado", decision="no")
    db.add(ArchivoNoRenovado(cliente_id=c.id, archivado_en=dt.datetime(2025, 10, 1, 12, tzinfo=tz)))
    db.flush()
    assert purgar_no_renovados(db, dt.datetime(2026, 9, 30, 23, tzinfo=tz)) == []
    assert purgar_no_renovados(db, dt.datetime(2026, 10, 1, 12, tzinfo=tz)) == ["Frontera"]


def test_tablero_cinco_columnas(api, db, ctx, fabrica, crear_usuario, auth):
    c = ctx["c"]
    por_vencer = fabrica.ciclo(c, H + D(3))
    vencido = fabrica.ciclo(c, H - D(1))
    sin_pago = fabrica.ciclo(c, H + D(1), estado="renovado", decision="si", pagos=[(100, H)])
    completo = fabrica.ciclo(c, H + D(2), estado="renovado", decision="si", pagos=[(1500, H)])
    fabrica.ciclo(c, H + D(10))
    fabrica.ciclo(c, H + D(20))
    fabrica.ciclo(c, H + D(2), estado="archivado", decision="no")
    otro = fabrica.cliente(crear_usuario("beto.luna"), "Ajeno")
    fabrica.ciclo(otro, H + D(2))
    r = api.get("/api/renovaciones/tablero?anio=2026&mes=10&quincena=1", headers=ctx["h_cm"]).json()
    ids = {k: [t["id"] for t in v] for k, v in r["columnas"].items()}
    assert ids == {"por_vencer": [por_vencer.id], "en_prorroga": [], "vencidos": [vencido.id],
                   "renovados_sin_pago": [sin_pago.id], "completos": [completo.id]}
    assert r["en_plazo"] == 1
    assert r["columnas"]["vencidos"][0]["arrastrado"] is True
    assert r["columnas"]["por_vencer"][0]["cliente_nombre"] == "Cliente Ana"
    r2 = api.get("/api/renovaciones/tablero?anio=2026&mes=10&quincena=2", headers=ctx["h_cm"]).json()
    ids2 = {k: [t["id"] for t in v] for k, v in r2["columnas"].items()}
    assert vencido.id in ids2["vencidos"] and sin_pago.id in ids2["renovados_sin_pago"] and r2["en_plazo"] == 1
    adm = auth(crear_usuario("admin.demo", rol="admin"))
    todos = api.get("/api/renovaciones/tablero?anio=2026&mes=10&quincena=1", headers=adm).json()
    assert sum(len(v) for v in todos["columnas"].values()) == 5 and todos["en_plazo"] == 1
    solo = api.get(f"/api/renovaciones/tablero?anio=2026&mes=10&quincena=1&cm_id={ctx['ana'].id}", headers=adm).json()
    assert sum(len(v) for v in solo["columnas"].values()) == 4
    assert "Ajeno" not in api.get(f"/api/renovaciones/tablero?anio=2026&mes=10&quincena=1&cm_id={otro.cm_id}", headers=ctx["h_cm"]).text


def test_caso1_no_contesta_pregunta_si_va_a_renovar_y_tiene_2_dias_o_pasa_a_no_renovados(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H, pagos=[(100, H)])
    hoy_fijo(H + D(1))
    tareas.avisos_renovacion(db, H + D(1))
    assert "va a renovar o no" in db.scalars(select(Notificacion).where(Notificacion.tipo == "paquete_vencido")).one().mensaje
    tareas.avisos_renovacion(db, H + D(2))
    db.refresh(p)
    assert p.estado == "vencido"
    tareas.avisos_renovacion(db, H + D(3))
    db.refresh(p), db.refresh(ctx["c"])
    assert p.estado == "archivado" and ctx["c"].estado == "no_renovado"


def test_caso1_si_contesta_que_renovara_ese_dia_es_el_inicio_y_a_las_2359_vuelve_la_ventana_sin_tolerancia(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H, costo=1000)
    hoy_fijo(H + D(1))
    assert api.get(f"/api/paquetes/{p.id}", headers=h).json()["opciones_bloqueo"] == ["va_a_renovar", "no_renovo"]
    r = api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h).json()
    assert r["renovado_automaticamente"] is None and r["paquete"]["bloqueado"] is False and r["paquete"]["confirmo_renovacion"]
    assert r["paquete"]["gracia_hasta"] == str(H + D(1)) and r["paquete"]["confirmado_en"] == str(H + D(1))
    assert r["paquete"]["limite_decision"] is None
    assert api.get("/api/bloqueos", headers=h).json() == []
    assert api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 300}).status_code == 201
    hoy_fijo(H + D(2))
    d = api.get(f"/api/paquetes/{p.id}", headers=h).json()
    assert d["bloqueado"] is True and d["opciones_bloqueo"] == ["prorroga", "no_renovo"]
    tareas.avisos_renovacion(db, H + D(2))
    assert "solicita prórroga o si no renovó" in db.scalars(select(Notificacion).where(Notificacion.tipo == "paquete_vencido")).one().mensaje
    assert api.post(f"/api/paquetes/{p.id}/prorroga", headers=h).status_code == 200
    r = api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 700}).json()
    n = api.get(f"/api/paquetes/{r['renovado_automaticamente']}", headers=h).json()
    assert (n["fecha_inicio"], n["fecha_renovacion"]) == (str(H), str(H + D(30)))


def test_quien_confirmo_que_renueva_no_tiene_plazo_de_2_dias_no_se_archiva_por_inactividad(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H, costo=1000)
    hoy_fijo(H + D(1))
    api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=ctx["h"])
    for dia in (2, 4, 10, 30):
        assert tareas.avisos_renovacion(db, H + D(dia))["pasaron_a_no_renovados"] == 0
    db.refresh(p)
    assert p.estado == "vencido"


def test_caso1_si_ya_pago_y_contesta_que_renovo_se_renueva_en_el_momento(api, db, ctx, fabrica, hoy_fijo):
    p = fabrica.ciclo(ctx["c"], H, costo=1000, pagos=[(1000, H)])
    hoy_fijo(H + D(1))
    r = api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=ctx["h"]).json()
    assert r["renovado_automaticamente"]
    n = api.get(f"/api/paquetes/{r['renovado_automaticamente']}", headers=ctx["h"]).json()
    assert (n["fecha_inicio"], n["fecha_renovacion"]) == (str(H + D(1)), str(H + D(31)))


def test_caso2_dijo_que_no_renovara_se_archiva_al_terminar_el_contrato_sin_ventana(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    p = fabrica.ciclo(ctx["c"], H + D(2))
    api.post(f"/api/paquetes/{p.id}/no-renovar", headers=ctx["h"], json={"accion": "conservar"})
    hoy_fijo(H + D(3))
    assert api.get("/api/bloqueos", headers=ctx["h"]).json() == []
    tareas.avisos_renovacion(db, H + D(3))
    db.refresh(p), db.refresh(ctx["c"])
    assert p.estado == "archivado" and ctx["c"].estado == "no_renovado"


def test_caso3_confirmo_que_renovara_sin_pagar_se_bloquea_al_terminar_y_pregunta_por_la_prorroga(api, db, ctx, fabrica, hoy_fijo):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H + D(2), costo=1000)
    r = api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h).json()
    assert r["renovado_automaticamente"] is None
    assert r["paquete"]["confirmo_renovacion"] is True and r["paquete"]["semaforo"] == "amarillo"
    assert r["paquete"]["gracia_hasta"] is None and r["paquete"]["bloqueado"] is False
    hoy_fijo(H + D(2))
    assert api.get(f"/api/paquetes/{p.id}", headers=h).json()["bloqueado"] is False
    hoy_fijo(H + D(3))
    d = api.get(f"/api/paquetes/{p.id}", headers=h).json()
    assert d["bloqueado"] is True and d["opciones_bloqueo"] == ["prorroga", "no_renovo"]
    assert api.post(f"/api/paquetes/{p.id}/prorroga", headers=h).status_code == 200


def test_caso3_si_paga_completo_despues_de_confirmar_se_renueva_solo(api, ctx, fabrica):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H + D(5), costo=1000)
    api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h)
    assert api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 400}).json()["renovado_automaticamente"] is None
    r = api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 600}).json()
    assert r["renovado_automaticamente"] and r["paquete"]["estado"] == "renovado"


def test_se_puede_deshacer_la_confirmacion_antes_del_fin_y_no_con_no_renovara_pendiente(api, ctx, fabrica):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H + D(5), costo=1000)
    api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h)
    r = api.post(f"/api/paquetes/{p.id}/revertir-decision", headers=h)
    assert r.status_code == 200 and r.json()["renovacion_decision"] == "pendiente" and r.json()["confirmo_renovacion"] is False
    api.post(f"/api/paquetes/{p.id}/no-renovar", headers=h, json={"accion": "conservar"})
    assert api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h).status_code == 409


def test_la_lista_de_clientes_marca_cuales_tienen_decision_pendiente(api, ctx, fabrica):
    fabrica.ciclo(ctx["c"], H - D(1))
    otro = fabrica.cliente(ctx["ana"], "Sin pendientes")
    fabrica.ciclo(otro, H + D(20))
    filas = {c["nombre"]: c["pendiente_decision"] for c in api.get("/api/clientes", headers=ctx["h"]).json()}
    assert filas == {"Cliente Ana": True, "Sin pendientes": False}


def test_caso3_el_dia_de_la_confirmacion_es_el_inicio_del_nuevo_contrato_aunque_pague_despues(api, ctx, fabrica, hoy_fijo):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H + D(10), costo=1000)
    api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h)
    hoy_fijo(H + D(4))
    r = api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 1000}).json()
    n = api.get(f"/api/paquetes/{r['renovado_automaticamente']}", headers=h).json()
    assert (n["fecha_inicio"], n["fecha_renovacion"]) == (str(H), str(H + D(30)))


def test_con_prorroga_el_nuevo_contrato_conserva_la_fecha_de_renovacion_original(api, ctx, fabrica, hoy_fijo):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H, costo=1000, decision="si")
    hoy_fijo(H + D(1))
    api.post(f"/api/paquetes/{p.id}/prorroga", headers=h)
    hoy_fijo(H + D(4))
    r = api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 1000}).json()
    n = api.get(f"/api/paquetes/{r['renovado_automaticamente']}", headers=h).json()
    assert (n["fecha_inicio"], n["fecha_renovacion"]) == (str(H), str(H + D(30)))


def test_se_elige_el_cambio_de_paquete_al_confirmar_que_va_a_renovar_y_se_aplica_al_renovar(api, db, ctx, fabrica, hoy_fijo):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H + D(5), costo=1000, paquete="Básico")
    r = api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h, json={"paquete_id": 3, "tipo_id": 2, "costo": 4500}).json()
    assert r["paquete"]["renovara_con"] == {"paquete_id": 3, "tipo_id": 2, "costo": 4500.0} or \
        (r["paquete"]["renovara_con"]["paquete_id"], float(r["paquete"]["renovara_con"]["costo"])) == (3, 4500.0)
    d = api.get(f"/api/paquetes/{p.id}", headers=h).json()
    assert (d["paquete"], float(d["costo"])) == ("Básico", 1000.0)
    hoy_fijo(H + D(2))
    nuevo_id = api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 1000}).json()["renovado_automaticamente"]
    n = api.get(f"/api/paquetes/{nuevo_id}", headers=h).json()
    assert (n["paquete"], n["tipo"], float(n["costo"]), n["veces_renovado"]) == ("Élite", "Dinamita", 4500.0, 0)
    assert db.scalars(select(Renovacion)).one().paquete_nuevo_id == 3


def test_confirmar_sin_cambios_renueva_con_el_mismo_paquete_y_deshacer_borra_el_plan(api, ctx, fabrica):
    h = ctx["h"]
    p = fabrica.ciclo(ctx["c"], H + D(5), costo=1000, paquete="Estándar")
    api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h, json={"paquete_id": 3})
    assert api.post(f"/api/paquetes/{p.id}/revertir-decision", headers=h).json()["renovara_con"] is None
    api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=h)
    n = api.post(f"/api/paquetes/{p.id}/pagos", headers=h, json={"monto": 1000}).json()["renovado_automaticamente"]
    d = api.get(f"/api/paquetes/{n}", headers=h).json()
    assert (d["paquete"], float(d["costo"]), d["veces_renovado"]) == ("Estándar", 1000.0, 1)


def test_el_plan_de_renovacion_valida_el_catalogo(api, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H + D(5), costo=1000)
    assert api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=ctx["h"], json={"paquete_id": 999}).status_code == 422


def test_el_cm_decide_si_renovo_o_no_pero_la_prorroga_la_activa_el_admin(api, db, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1500, decision="si", pagos=[(500, H - D(2))], por=ctx["admin"])
    assert api.get(f"/api/paquetes/{p.id}", headers=ctx["h"]).json()["opciones_bloqueo"] == ["prorroga", "no_renovo"]
    assert api.post(f"/api/paquetes/{p.id}/prorroga", headers=ctx["h_cm"]).status_code == 403
    db.refresh(p)
    assert p.prorroga_hasta is None
    assert api.post(f"/api/paquetes/{p.id}/prorroga", headers=ctx["h"]).status_code == 200
    db.refresh(p)
    assert p.prorroga_hasta == H + D(5)


def test_el_cm_si_confirma_que_va_a_renovar_y_si_marca_que_no_renovo(api, db, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1500)
    r = api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=ctx["h_cm"])
    assert r.status_code == 200 and r.json()["renovado_automaticamente"] is None
    db.refresh(p)
    assert p.renovacion_decision == "si" and p.confirmado_en == H

    otro = fabrica.ciclo(fabrica.cliente(ctx["ana"], "Otro"), H - D(1), costo=1500)
    r = api.post(f"/api/paquetes/{otro.id}/no-renovar", headers=ctx["h_cm"], json={"accion": "conservar"})
    assert r.status_code == 200 and r.json()["cliente_a_no_renovados"] is True


def test_el_cm_renueva_cuando_ya_esta_pagado_pero_no_elige_otro_paquete(api, db, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H - D(1), costo=1500, pagos=[(1500, H - D(2))], por=ctx["admin"])
    r = api.post(f"/api/paquetes/{p.id}/confirmar-renovacion", headers=ctx["h_cm"],
                 json={"paquete_id": 3, "tipo_id": 2, "costo": 4500})
    assert r.status_code == 200 and r.json()["renovado_automaticamente"]
    nuevo = db.get(PaqueteCliente, r.json()["renovado_automaticamente"])
    assert nuevo.paquete_id == p.paquete_id and nuevo.costo == Decimal(1500)


def test_con_la_prorroga_corriendo_se_trabaja_normal_no_sale_como_pendiente(api, db, ctx, fabrica):
    p = fabrica.ciclo(ctx["c"], H - D(2), costo=1500, estado="vencido", decision="si",
                      pagos=[(500, H - D(3))], por=ctx["admin"], prorroga=(H - D(1), H + D(4)))
    p.confirmado_en = H - D(3)
    db.flush()
    d = api.get(f"/api/paquetes/{p.id}", headers=ctx["h"]).json()
    assert d["prorroga_activa"] is True and d["bloqueado"] is False
    assert d["semaforo"] == "amarillo" and d["opciones_bloqueo"] == []

    assert api.get("/api/bloqueos", headers=ctx["h"]).json() == []
    assert api.post(f"/api/paquetes/{p.id}/pagos", headers=ctx["h"], json={"monto": 100}).status_code == 201
    assert api.patch(f"/api/clientes/{ctx['c'].id}", headers=ctx["h"], json={"telefono": "5500000000"}).status_code == 200

    cols = api.get("/api/renovaciones/tablero?anio=2026&mes=10&quincena=ambas", headers=ctx["h"]).json()["columnas"]
    assert p.id in [t["id"] for t in cols["en_prorroga"]]
    assert p.id not in [t["id"] for t in cols["vencidos"]]


def test_la_prorroga_no_mueve_la_fecha_de_renovacion_y_vence_al_terminar_su_ultimo_dia(api, db, ctx, fabrica, hoy_fijo):
    from app.jobs import tareas
    from app.models import Cliente
    r_original = H - D(2)
    p = fabrica.ciclo(ctx["c"], r_original, costo=1500, estado="vencido", decision="si",
                      pagos=[(500, H - D(3))], por=ctx["admin"], prorroga=(H - D(1), H + D(4)))
    p.confirmado_en = H - D(3)
    db.flush()
    assert p.fecha_renovacion == r_original

    hoy_fijo(H + D(4))
    tareas.avisos_prorroga(db, H + D(4))
    db.refresh(p)
    assert p.estado == "vencido" and db.get(Cliente, ctx["c"].id).estado == "activo"

    hoy_fijo(H + D(5))
    tareas.avisos_prorroga(db, H + D(5))
    db.refresh(p)
    assert p.estado == "archivado"
    assert db.get(Cliente, ctx["c"].id).estado == "no_renovado"
