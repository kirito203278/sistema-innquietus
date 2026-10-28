"""Módulo de campañas dentro de la plataforma unificada: reglas puras, API con aislamiento por rol,
jobs, mensuales inmutables y, sobre todo, las reglas que UNEN campañas con clientes y paquetes."""
import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.jobs import tareas_campanas
from app.models import (ArchivoNoRenovado, Bitacora, Campana, Cliente, Mensual, Notificacion, Observacion, Semana)
from app.services import renovacion, rendimiento
from app.services import semanas as cal

H = dt.date(2026, 10, 1)  # jueves; la semana en curso es sáb 26-sep -> vie 02-oct
D = dt.timedelta
SEMANA_ACTUAL = dt.date(2026, 9, 26)
SEMANA_PASADA = dt.date(2026, 9, 19)
CUERPO = {"nombre": "LOCAL ADV", "tipo": "local", "presupuesto": 3500}


@pytest.fixture(autouse=True)
def _hoy(hoy_fijo):
    hoy_fijo(H)


@pytest.fixture
def ctx(db, crear_usuario, fabrica, auth):
    ana, beto = crear_usuario("ana.ruiz"), crear_usuario("beto.luna")
    admin = crear_usuario("admin.jefe", rol="admin")
    ro = crear_usuario("admin.ro", rol="admin", solo_lectura=True)
    cliente = fabrica.cliente(ana, "Café Acento")
    paquete = fabrica.ciclo(cliente, H + D(20), costo=2500, pagos=[(2500, H)])
    return SimpleNamespace(ana=ana, beto=beto, admin=admin, ro=ro, c=cliente, p=paquete,
                           h_ana=auth(ana), h_beto=auth(beto), h_admin=auth(admin), h_ro=auth(ro))


def _campana(db, cliente, estado="activa", **kw):
    campos = dict(cliente_id=cliente.id, nombre="LOCAL ADV", tipo="local", presupuesto=Decimal(3500),
                  fecha_inicio=H - D(10), fecha_renovacion=H + D(20), estado=estado)
    campos.update(kw)
    c = Campana(**campos)
    db.add(c)
    db.flush()
    return c


def _semana(db, campana, inicio, mensajes=None, costo=None, importe=None, editable=True):
    s = Semana(campana_id=campana.id, inicio=inicio, fin=inicio + D(6), mensajes=mensajes,
               costo_por_resultado=costo, importe_gastado=importe, editable=editable)
    db.add(s)
    db.flush()
    return s


# ====================================================== reglas puras: semáforo
def _cfg(bueno=19, regular=29, caida=30):
    return SimpleNamespace(umbral_bueno=Decimal(bueno), umbral_regular=Decimal(regular), caida_mensajes_alerta_pct=Decimal(caida))


@pytest.mark.parametrize("costo,esperado", [(0, "bueno"), (19, "bueno"), (19.01, "regular"), (29, "regular"), (29.01, "bajo"), (80, "bajo")])
def test_umbrales_locales_definitivos(costo, esperado):
    assert rendimiento.nivel_por_costo(_cfg(), costo) == esperado


def test_nacional_es_mas_estricto_que_local():
    nacional = _cfg(14, 19)
    assert rendimiento.nivel_por_costo(nacional, 17) == "regular"
    assert rendimiento.nivel_por_costo(nacional, 20) == "bajo"
    assert rendimiento.nivel_por_costo(_cfg(), 17) == "bueno"


def test_caida_fuerte_de_mensajes_baja_un_nivel():
    previas = [SimpleNamespace(mensajes=100), SimpleNamespace(mensajes=100)]
    sem = SimpleNamespace(costo_por_resultado=Decimal(10), mensajes=50)
    assert rendimiento.nivel_semana(_cfg(), sem, previas) == "regular"  # 10 es 'bueno' pero cayó 50%
    assert rendimiento.nivel_semana(_cfg(), SimpleNamespace(costo_por_resultado=Decimal(10), mensajes=90), previas) == "bueno"


def test_tres_semanas_empeorando_bajan_un_nivel_y_el_tope_es_bajo():
    sem = [SimpleNamespace(costo_por_resultado=Decimal(c)) for c in (10, 12, 15)]
    assert rendimiento.nivel_ciclo(_cfg(), 10.0, sem) == "regular"
    assert rendimiento.nivel_ciclo(_cfg(), 40.0, sem) == "bajo"  # no baja más allá de 'bajo'
    assert rendimiento.nivel_ciclo(None, 10.0, sem) is None


# ======================================================== reglas puras: calendario
def test_semana_operativa_es_sabado_a_viernes():
    assert cal.rango_semana(H) == (SEMANA_ACTUAL, dt.date(2026, 10, 2))
    assert cal.sabado_mas_reciente(dt.date(2026, 10, 3)) == dt.date(2026, 10, 3)  # un sábado se devuelve a sí mismo
    assert cal.rango_semana(dt.date(2026, 10, 2))[0] == SEMANA_ACTUAL            # viernes: aún la misma semana


@pytest.mark.parametrize("momento,ok", [
    (dt.datetime(2026, 10, 7, 10, 0), True), (dt.datetime(2026, 10, 9, 14, 59), True),
    (dt.datetime(2026, 10, 9, 15, 0), False), (dt.datetime(2026, 10, 10, 7, 59), False), (dt.datetime(2026, 10, 10, 8, 0), True)])
def test_ventana_para_habilitar_edicion(momento, ok):
    assert cal.en_ventana_habilitacion(momento) is ok


def test_edicion_temporal_expira():
    s = SimpleNamespace(editable=False, fin=H - D(5), edicion_habilitada_hasta=dt.datetime(2026, 10, 1, 14, 0, tzinfo=dt.timezone.utc))
    assert cal.puede_editar(s, H, dt.datetime(2026, 10, 1, 13, 59, tzinfo=dt.timezone.utc)) is True
    assert cal.puede_editar(s, H, dt.datetime(2026, 10, 1, 14, 0, tzinfo=dt.timezone.utc)) is False


# ===================================================================== alta y alcance
def test_cm_crea_campana_y_se_liga_sola_al_paquete_vigente_del_cliente(api, db, ctx):
    r = api.post(f"/api/clientes/{ctx.c.id}/campanas", headers=ctx.h_ana, json=CUERPO)
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["estado"] == "activa" and c["paquete_cliente_id"] == ctx.p.id and c["paquete"] == "Básico"
    assert (c["fecha_inicio"], c["fecha_renovacion"]) == (str(H), str(H + D(30)))
    assert db.scalars(select(Semana).where(Semana.campana_id == c["id"])).one().inicio == SEMANA_ACTUAL
    assert db.scalars(select(Bitacora).where(Bitacora.accion == "alta_campana")).one().usuario_id == ctx.ana.id


def test_un_cm_no_puede_crear_ni_ver_campanas_de_clientes_ajenos(api, db, ctx):
    camp = _campana(db, ctx.c)
    assert api.post(f"/api/clientes/{ctx.c.id}/campanas", headers=ctx.h_beto, json=CUERPO).status_code == 404
    assert api.get(f"/api/campanas/{camp.id}", headers=ctx.h_beto).status_code == 404
    assert api.get(f"/api/campanas/{camp.id}/semanas", headers=ctx.h_beto).status_code == 404
    assert api.get("/api/campanas", headers=ctx.h_beto).json() == []
    assert [x["id"] for x in api.get("/api/campanas", headers=ctx.h_ana).json()] == [camp.id]
    assert [x["id"] for x in api.get("/api/campanas", headers=ctx.h_admin).json()] == [camp.id]


def test_admin_solo_lectura_ve_pero_no_escribe(api, db, ctx):
    camp = _campana(db, ctx.c)
    assert api.get(f"/api/campanas/{camp.id}", headers=ctx.h_ro).status_code == 200
    assert api.post(f"/api/clientes/{ctx.c.id}/campanas", headers=ctx.h_ro, json=CUERPO).status_code == 403
    s = _semana(db, camp, SEMANA_ACTUAL)
    assert api.put(f"/api/semanas/{s.id}", headers=ctx.h_ro, json={"mensajes": 1, "costo_por_resultado": 1, "importe_gastado": 1}).status_code == 403


@pytest.mark.parametrize("cambio", [{"presupuesto": 0}, {"tipo": "mundial"}, {"nombre": ""}, {"fecha_renovacion": str(H - D(1))}])
def test_alta_valida_los_datos(api, ctx, cambio):
    r = api.post(f"/api/clientes/{ctx.c.id}/campanas", headers=ctx.h_ana, json={**CUERPO, **cambio})
    assert r.status_code == 422


def test_no_se_crea_campana_a_un_cliente_en_no_renovados(api, db, ctx):
    ctx.c.estado = "no_renovado"
    db.flush()
    assert api.post(f"/api/clientes/{ctx.c.id}/campanas", headers=ctx.h_admin, json=CUERPO).status_code == 409


def test_el_paquete_indicado_debe_ser_vigente_y_del_mismo_cliente(api, db, ctx, fabrica):
    otro = fabrica.ciclo(fabrica.cliente(ctx.ana, "Otro"), H + D(20))
    r = api.post(f"/api/clientes/{ctx.c.id}/campanas", headers=ctx.h_ana, json={**CUERPO, "paquete_cliente_id": otro.id})
    assert r.status_code == 422


def test_la_ficha_unica_del_cliente_trae_sus_campanas_y_datos_de_pago(api, db, ctx):
    _campana(db, ctx.c)
    ctx.c.metodo_pago = "Tarjeta"
    db.flush()
    f = api.get(f"/api/clientes/{ctx.c.id}", headers=ctx.h_ana).json()
    assert [k["nombre"] for k in f["campanas"]] == ["LOCAL ADV"] and f["metodo_pago"] == "Tarjeta"
    resumen = next(x for x in api.get("/api/clientes", headers=ctx.h_ana).json() if x["id"] == ctx.c.id)
    assert resumen["campanas_abiertas"] == 1


# ===================================================== ventana de decisión (pausa del cliente)
def test_cliente_en_pausa_por_contrato_sin_decidir_no_admite_escrituras_de_campana(api, db, ctx, fabrica):
    ctx.p.fecha_renovacion = H - D(3)  # terminó y nadie decidió -> bloqueado
    db.flush()
    camp = _campana(db, ctx.c)
    s = _semana(db, camp, SEMANA_ACTUAL)
    cuerpos = [("post", f"/api/clientes/{ctx.c.id}/campanas", CUERPO),
               ("put", f"/api/semanas/{s.id}", {"mensajes": 5, "costo_por_resultado": 10, "importe_gastado": 50}),
               ("post", f"/api/campanas/{camp.id}/observaciones", {"texto": "nota"})]
    for metodo, url, cuerpo in cuerpos:
        r = getattr(api, metodo)(url, headers=ctx.h_ana, json=cuerpo)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "bloqueado", url
    assert api.get(f"/api/campanas/{camp.id}", headers=ctx.h_ana).json()["cliente_bloqueado"] is True  # leer sí se puede


# ===================================================================== captura semanal
def test_captura_semanal_y_semaforo(api, db, ctx):
    camp = _campana(db, ctx.c)
    s = _semana(db, camp, SEMANA_ACTUAL)
    r = api.put(f"/api/semanas/{s.id}", headers=ctx.h_ana, json={"mensajes": 80, "costo_por_resultado": 12.5, "importe_gastado": 1000})
    assert r.status_code == 200, r.text
    assert (r.json()["mensajes"], r.json()["rendimiento"], r.json()["editable"]) == (80, "bueno", True)
    assert api.get(f"/api/campanas/{camp.id}", headers=ctx.h_ana).json()["costo_actual"] == 12.5
    db.refresh(s)
    assert s.capturado_por == ctx.ana.id


@pytest.mark.parametrize("malo", [{"mensajes": -1}, {"costo_por_resultado": -1}, {"importe_gastado": -5}])
def test_la_captura_rechaza_negativos(api, db, ctx, malo):
    s = _semana(db, _campana(db, ctx.c), SEMANA_ACTUAL)
    r = api.put(f"/api/semanas/{s.id}", headers=ctx.h_ana, json={"mensajes": 1, "costo_por_resultado": 1, "importe_gastado": 1, **malo})
    assert r.status_code == 422


def test_semana_terminada_queda_bloqueada_aunque_el_job_no_haya_corrido(api, db, ctx):
    s = _semana(db, _campana(db, ctx.c), SEMANA_PASADA, editable=True)  # bandera vieja: el job del sábado no corrió
    r = api.put(f"/api/semanas/{s.id}", headers=ctx.h_ana, json={"mensajes": 1, "costo_por_resultado": 1, "importe_gastado": 1})
    assert r.status_code == 403
    assert api.get(f"/api/campanas/{s.campana_id}/semanas", headers=ctx.h_ana).json()[0]["editable"] is False


def test_admin_habilita_edicion_2h_y_el_cm_puede_corregir(api, db, ctx):
    s = _semana(db, _campana(db, ctx.c), SEMANA_PASADA, mensajes=10, costo=10, importe=100, editable=False)
    cuerpo = {"mensajes": 99, "costo_por_resultado": 9, "importe_gastado": 900}
    assert api.put(f"/api/semanas/{s.id}", headers=ctx.h_ana, json=cuerpo).status_code == 403
    assert api.post(f"/api/semanas/{s.id}/habilitar-edicion", headers=ctx.h_ana).status_code == 403   # el CM no se lo da
    assert api.post(f"/api/semanas/{s.id}/habilitar-edicion", headers=ctx.h_ro).status_code == 403    # ni un admin de solo lectura
    assert api.post(f"/api/semanas/{s.id}/habilitar-edicion", headers=ctx.h_admin).status_code == 200
    assert api.put(f"/api/semanas/{s.id}", headers=ctx.h_ana, json=cuerpo).status_code == 200
    aviso = db.scalars(select(Notificacion).where(Notificacion.usuario_id == ctx.ana.id, Notificacion.tipo == "sistema")).one()
    assert "2 horas" in aviso.mensaje
    assert db.scalars(select(Bitacora).where(Bitacora.accion == "habilitar_edicion_semana")).one()


def test_no_se_habilita_una_semana_que_ya_esta_abierta(api, db, ctx):
    s = _semana(db, _campana(db, ctx.c), SEMANA_ACTUAL)
    assert api.post(f"/api/semanas/{s.id}/habilitar-edicion", headers=ctx.h_admin).status_code == 400


def test_observaciones(api, db, ctx):
    camp = _campana(db, ctx.c)
    r = api.post(f"/api/campanas/{camp.id}/observaciones", headers=ctx.h_ana, json={"texto": "  Subir presupuesto  "})
    assert r.status_code == 201 and r.json()["texto"] == "Subir presupuesto"
    assert [o["autor"] for o in api.get(f"/api/campanas/{camp.id}/observaciones", headers=ctx.h_admin).json()] == ["Ana"]
    vencida = _campana(db, ctx.c, estado="vencida", nombre="Vieja")
    assert api.post(f"/api/campanas/{vencida.id}/observaciones", headers=ctx.h_ana, json={"texto": "x"}).status_code == 403


# ================================================================== cierre de ciclo (job)
def test_cierre_de_ciclo_archiva_el_mensual_y_deja_la_campana_vencida(db, ctx):
    camp = _campana(db, ctx.c, fecha_renovacion=H)
    _semana(db, camp, SEMANA_PASADA, 100, Decimal(10), Decimal(1000), editable=False)
    _semana(db, camp, SEMANA_ACTUAL, 200, Decimal(10), Decimal(2000))
    db.add(Observacion(campana_id=camp.id, texto="nota", autor_id=ctx.ana.id))
    db.flush()

    assert tareas_campanas.cierre_ciclo_campanas(db, H) == {"campanas_cerradas": 1}

    m = db.scalars(select(Mensual).where(Mensual.campana_id == camp.id)).one()
    assert (m.mensajes_total, float(m.gasto_total), float(m.costo_por_mensaje), float(m.sobrante)) == (300, 3000.0, 10.0, 500.0)
    assert (m.rendimiento, m.origen, m.periodo_inicio, m.periodo_fin) == ("bueno", "calculado", camp.fecha_inicio, H)
    db.refresh(camp)
    assert camp.estado == "vencida" and camp.semanas == [] and camp.observaciones == []
    assert db.scalars(select(Notificacion).where(Notificacion.tipo == "campana_vencida")).one().usuario_id == ctx.ana.id


def test_el_cierre_es_idempotente_y_alcanza_a_las_campanas_atrasadas(db, ctx):
    atrasada = _campana(db, ctx.c, fecha_renovacion=H - D(3))  # el servidor estuvo caído: antes nunca vencía
    futura = _campana(db, ctx.c, nombre="Otra", fecha_renovacion=H + D(5))
    assert tareas_campanas.cierre_ciclo_campanas(db, H)["campanas_cerradas"] == 1
    assert tareas_campanas.cierre_ciclo_campanas(db, H)["campanas_cerradas"] == 0
    db.refresh(atrasada), db.refresh(futura)
    assert (atrasada.estado, futura.estado) == ("vencida", "activa")
    assert len(db.scalars(select(Mensual)).all()) == 1 and len(db.scalars(select(Notificacion)).all()) == 1


def test_el_mensual_es_inmutable_en_la_base(db, ctx):
    camp = _campana(db, ctx.c, fecha_renovacion=H)
    tareas_campanas.cierre_ciclo_campanas(db, H)
    m = db.scalars(select(Mensual).where(Mensual.campana_id == camp.id)).one()
    m.gasto_total = Decimal(1)
    with pytest.raises(DBAPIError, match="inmutable"):
        db.flush()
    db.rollback()


def test_mensual_manual_solo_una_vez(api, db, ctx):
    camp = _campana(db, ctx.c)
    cuerpo = {"periodo_inicio": "2026-08-01", "periodo_fin": "2026-08-30", "mensajes_total": 200, "gasto_total": 3000}
    r = api.post(f"/api/campanas/{camp.id}/mensuales/manual", headers=ctx.h_ana, json=cuerpo)
    assert r.status_code == 201 and r.json()["origen"] == "manual" and r.json()["costo_por_mensaje"] == 15.0
    assert r.json()["rendimiento"] == "bueno"
    assert api.post(f"/api/campanas/{camp.id}/mensuales/manual", headers=ctx.h_ana, json=cuerpo).status_code == 409


def test_el_comparativo_es_de_2_meses_para_el_cm_y_3_para_el_admin(api, db, ctx):
    camp = _campana(db, ctx.c)
    for i in range(4):
        db.add(Mensual(campana_id=camp.id, periodo_inicio=dt.date(2026, 1 + i, 1), periodo_fin=dt.date(2026, 1 + i, 28),
                       mensajes_total=10, gasto_total=100, costo_por_mensaje=10, presupuesto=3500, sobrante=3400))
    db.flush()
    assert len(api.get(f"/api/campanas/{camp.id}/mensuales", headers=ctx.h_ana).json()) == 2
    assert len(api.get(f"/api/campanas/{camp.id}/mensuales", headers=ctx.h_admin).json()) == 3


# ================================================================ renovar / cerrar
def test_renovar_campana_vencida(api, db, ctx):
    camp = _campana(db, ctx.c, estado="vencida", fecha_renovacion=H - D(1))
    assert api.post(f"/api/campanas/{camp.id}/renovar", headers=ctx.h_ana, json={"fecha_renovacion": str(H)}).status_code == 422
    r = api.post(f"/api/campanas/{camp.id}/renovar", headers=ctx.h_ana, json={"fecha_renovacion": str(H + D(30))})
    assert r.status_code == 200 and r.json()["estado"] == "activa"
    assert (r.json()["fecha_inicio"], r.json()["fecha_renovacion"]) == (str(H), str(H + D(30)))
    assert db.scalars(select(Semana).where(Semana.campana_id == camp.id)).one().inicio == SEMANA_ACTUAL
    assert api.post(f"/api/campanas/{camp.id}/renovar", headers=ctx.h_ana, json={"fecha_renovacion": str(H + D(60))}).status_code == 409


def test_cerrar_una_campana_activa_archiva_su_mensual_primero(api, db, ctx):
    camp = _campana(db, ctx.c)
    _semana(db, camp, SEMANA_ACTUAL, 50, Decimal(8), Decimal(400))
    r = api.post(f"/api/campanas/{camp.id}/cerrar", headers=ctx.h_ana, json={"motivo": "El cliente cambió de agencia"})
    assert r.status_code == 200 and r.json()["estado"] == "cerrada"
    m = db.scalars(select(Mensual).where(Mensual.campana_id == camp.id)).one()
    assert (m.mensajes_total, m.periodo_fin) == (50, H)  # cierre anticipado: el periodo termina hoy
    assert api.post(f"/api/campanas/{camp.id}/cerrar", headers=ctx.h_ana, json={}).status_code == 409
    # una campaña cerrada se puede reabrir renovándola
    assert api.post(f"/api/campanas/{camp.id}/renovar", headers=ctx.h_ana, json={"fecha_renovacion": str(H + D(30))}).json()["estado"] == "activa"


# ============================================== REGLAS QUE UNEN CAMPAÑAS CON EL CLIENTE
def test_cuando_el_cliente_pasa_a_no_renovados_sus_campanas_se_cierran_conservando_el_historico(db, ctx):
    abierta = _campana(db, ctx.c)
    _semana(db, abierta, SEMANA_ACTUAL, 30, Decimal(10), Decimal(300))
    vencida = _campana(db, ctx.c, estado="vencida", nombre="Vencida")
    renovacion.enviar_a_no_renovados(db, ctx.c, "No renovó")
    db.flush()
    db.refresh(abierta), db.refresh(vencida)
    assert (abierta.estado, vencida.estado) == ("cerrada", "cerrada")
    assert db.scalars(select(Mensual).where(Mensual.campana_id == abierta.id)).one().mensajes_total == 30
    assert not db.scalars(select(Notificacion).where(Notificacion.tipo == "campana_vencida")).all()  # no avisa de más


def test_reingreso_con_cuenta_nueva_borra_tambien_las_campanas_viejas(db, ctx):
    ctx.c.estado = "no_renovado"
    vieja = _campana(db, ctx.c, estado="cerrada")
    db.add(ArchivoNoRenovado(cliente_id=ctx.c.id, cm_id=ctx.ana.id, archivado_en=dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)))
    db.flush()
    renovacion.reingresar(db, ctx.admin, ctx.c, modo="nuevo", paquete_id=1, tipo_id=1, costo=Decimal(1500))
    db.flush()
    assert db.get(Campana, vieja.id) is None


def test_reingreso_reciente_conserva_las_campanas(db, ctx):
    ctx.c.estado = "no_renovado"
    vieja = _campana(db, ctx.c, estado="cerrada")
    db.add(ArchivoNoRenovado(cliente_id=ctx.c.id, cm_id=ctx.ana.id, archivado_en=dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc)))
    db.flush()
    renovacion.reingresar(db, ctx.admin, ctx.c, modo="nuevo", paquete_id=1, tipo_id=1, costo=Decimal(1500))
    db.flush()
    assert db.get(Campana, vieja.id) is not None


def test_borrar_al_cliente_borra_en_cascada_campanas_semanas_y_mensuales(db, ctx):
    camp = _campana(db, ctx.c)
    _semana(db, camp, SEMANA_ACTUAL, 1, Decimal(1), Decimal(1))
    db.add(Mensual(campana_id=camp.id, periodo_inicio=H - D(40), periodo_fin=H - D(10), mensajes_total=1, gasto_total=1,
                   costo_por_mensaje=1, presupuesto=1, sobrante=0))
    db.flush()
    db.execute(Cliente.__table__.delete().where(Cliente.id == ctx.c.id))
    for tabla in (Campana, Semana, Mensual):
        assert db.scalars(select(tabla)).all() == []


# ============================================================================= jobs
def test_cierre_de_semana_bloquea_rellena_y_abre_la_nueva(db, ctx):
    camp = _campana(db, ctx.c)
    vieja = _semana(db, camp, SEMANA_PASADA, editable=True)             # nunca se capturó
    capturada = _semana(db, camp, dt.date(2026, 9, 12), 40, Decimal(10), Decimal(400), editable=True)
    r = tareas_campanas.cierre_semana(db, H)
    assert r == {"rellenadas_en_0": 1, "bloqueadas": 2, "semanas_nuevas": 1}
    db.refresh(vieja), db.refresh(capturada)
    assert (vieja.mensajes, vieja.editable, capturada.mensajes, capturada.editable) == (0, False, 40, False)
    assert db.scalars(select(Semana).where(Semana.campana_id == camp.id, Semana.inicio == SEMANA_ACTUAL)).one().editable is True
    assert tareas_campanas.cierre_semana(db, H)["semanas_nuevas"] == 0   # idempotente


def test_recordatorio_de_captura_agrupa_por_cm_y_no_se_duplica(db, ctx):
    _semana(db, _campana(db, ctx.c), SEMANA_ACTUAL)
    _semana(db, _campana(db, ctx.c, nombre="Segunda"), SEMANA_ACTUAL)
    _semana(db, _campana(db, ctx.c, nombre="Capturada"), SEMANA_ACTUAL, 5, Decimal(1), Decimal(5))
    assert tareas_campanas.recordatorio_captura(db, H) == {"avisos": 1, "campanas_pendientes": 2}
    assert tareas_campanas.recordatorio_captura(db, H)["avisos"] == 0
    aviso = db.scalars(select(Notificacion).where(Notificacion.tipo == "recordatorio_captura")).one()
    assert aviso.usuario_id == ctx.ana.id and "Te faltan 2 campañas" in aviso.mensaje


def test_los_jobs_nuevos_se_disparan_por_endpoint_y_quedan_registrados(api, db, ctx, monkeypatch):
    from app.config import get_settings
    from app.jobs import tareas
    from app.models import JobEjecucion

    class _S:  # misma técnica que la suite original: el job usa la sesión de prueba, sin cerrarla
        def __enter__(self): return db
        def __exit__(self, *a): return False
    monkeypatch.setattr(tareas, "get_sessionmaker", lambda: (lambda: _S()))
    h = {"X-Jobs-Secret": get_settings().jobs_secret}
    for nombre in ("cierre_semana", "recordatorio_captura", "cierre_ciclo_campanas"):
        r = api.post(f"/api/jobs/run/{nombre}", headers=h)
        assert r.status_code == 200 and r.json()["ok"], nombre
    assert api.post("/api/jobs/run/cierre_semana").status_code == 401
    assert {j.nombre for j in db.scalars(select(JobEjecucion))} >= {"cierre_semana", "recordatorio_captura", "cierre_ciclo_campanas"}


# =============================================================== consolidado y reportes
def test_reportes_pdf_por_cliente_consolidan_sus_campanas(api, db, ctx):
    a = _campana(db, ctx.c, fecha_renovacion=H)
    _semana(db, a, SEMANA_ACTUAL, 100, Decimal(10), Decimal(1000))
    b = _campana(db, ctx.c, nombre="Nacional", tipo="nacional", presupuesto=Decimal(2000), fecha_renovacion=H)
    _semana(db, b, SEMANA_ACTUAL, 50, Decimal(10), Decimal(500))
    url = f"/api/clientes/{ctx.c.id}/campanas"
    assert api.get(f"{url}/reporte-mensual", headers=ctx.h_ana).status_code == 404          # aún sin mes cerrado
    sem = api.get(f"{url}/reporte-semanal", headers=ctx.h_ana)
    assert sem.status_code == 200 and sem.headers["content-type"] == "application/pdf" and sem.content.startswith(b"%PDF")

    tareas_campanas.cierre_ciclo_campanas(db, H)
    mens = api.get(f"{url}/reporte-mensual", headers=ctx.h_admin)
    assert mens.status_code == 200 and mens.content.startswith(b"%PDF")
    assert "attachment" in mens.headers["content-disposition"]
    cons = api.get(f"{url}/consolidado", headers=ctx.h_admin).json()
    assert (cons["mensuales"][0]["mensajes_total"], cons["mensuales"][0]["gasto_total"], cons["mensuales"][0]["presupuesto"]) == (150, 1500.0, 5500.0)
    assert api.get(f"{url}/reporte-mensual", headers=ctx.h_beto).status_code == 404         # otro CM no puede ni descargarlo


# ================================================================== umbrales editables
def test_el_admin_edita_los_umbrales_y_el_semaforo_cambia_sin_tocar_codigo(api, db, ctx):
    camp = _campana(db, ctx.c)
    s = _semana(db, camp, SEMANA_ACTUAL, 80, Decimal(25), Decimal(2000))
    assert api.get(f"/api/campanas/{camp.id}", headers=ctx.h_ana).json()["rendimiento"] == "regular"
    local = next(m for m in api.get("/api/metricas", headers=ctx.h_ana).json() if m["tipo"] == "local")
    assert (local["umbral_bueno"], local["umbral_regular"]) == (19.0, 29.0)
    assert api.patch(f"/api/metricas/{local['id']}", headers=ctx.h_ana, json={"umbral_bueno": 30}).status_code == 403
    assert api.patch(f"/api/metricas/{local['id']}", headers=ctx.h_admin, json={"umbral_bueno": 40, "umbral_regular": 10}).status_code == 422
    assert api.patch(f"/api/metricas/{local['id']}", headers=ctx.h_admin, json={"umbral_bueno": 30, "umbral_regular": 45}).status_code == 200
    assert api.get(f"/api/campanas/{camp.id}", headers=ctx.h_ana).json()["rendimiento"] == "bueno"
