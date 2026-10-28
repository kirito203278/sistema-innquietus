"""Reglas de negocio del módulo de CAMPAÑAS, integradas con el cliente y su paquete.

Una campaña cuelga del cliente (la misma ficha única que usa Control de Clientes)
y, si existe, del ciclo/paquete que la respalda. Ciclo de vida de una campaña:

    activa --(llega fecha_renovacion, job diario 12:00)--> vencida   [se archiva el mensual]
    vencida/cerrada --(CM confirma renovación)--> activa
    activa/vencida --(CM la da por terminada)--> cerrada

El estado del CLIENTE (por vencer / bloqueado / No renovados) sigue siendo cosa de
sus paquetes; cuando el cliente pasa a No renovados, sus campañas se cierran solas.
"""
import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import bitacora
from app.config import get_settings
from app.dates import ahora, hoy as hoy_mx
from app.models import Campana, Cliente, Mensual, Observacion, PaqueteCliente, Semana, Usuario
from app.services import ciclos, notificar, rendimiento
from app.services import semanas as cal

ABIERTAS = ("activa", "vencida")


def nombre_paquete(c: Campana) -> str | None:
    return c.paquete_cliente.paquete.nombre if c.paquete_cliente else None


# --------------------------------------------------------------------------- alta
def crear_campana(db: Session, user: Usuario, cliente: Cliente, datos: dict) -> Campana:
    if cliente.estado != "activo":
        raise HTTPException(409, "El cliente está en No renovados: primero reingrésalo")
    hoy = hoy_mx()

    pq_id = datos.get("paquete_cliente_id")
    if pq_id is not None:
        pq = db.get(PaqueteCliente, pq_id)
        if pq is None or pq.cliente_id != cliente.id or pq.estado not in ciclos.VIGENTES:
            raise HTTPException(422, "El paquete indicado no es un paquete vigente de este cliente")
    else:  # un cliente tiene un solo paquete vigente: la campaña se liga a él automáticamente
        vigentes = [p for p in cliente.paquetes if p.estado in ciclos.VIGENTES]
        pq_id = vigentes[0].id if len(vigentes) == 1 else None

    inicio = datos.get("fecha_inicio") or hoy
    renovacion = datos.get("fecha_renovacion") or inicio + dt.timedelta(days=get_settings().ciclo_dias)
    if renovacion <= inicio:
        raise HTTPException(422, "La fecha de renovación debe ser posterior a la de inicio")

    c = Campana(cliente_id=cliente.id, paquete_cliente_id=pq_id, nombre=datos["nombre"].strip(), tipo=datos["tipo"],
                presupuesto=datos["presupuesto"], presupuesto_esquema=datos.get("presupuesto_esquema", "mensual"),
                formato_post=datos.get("formato_post", False), formato_3d=datos.get("formato_3d", False),
                formato_boton=datos.get("formato_boton", False), formato_otro=datos.get("formato_otro", False),
                lugar=datos.get("lugar") or None, fecha_inicio=inicio, fecha_renovacion=renovacion, estado="activa")
    db.add(c)
    db.flush()
    if inicio <= hoy:
        cal.asegurar_semana_actual(db, c, hoy)
    bitacora.registrar(db, user, "alta_campana", {"campana_id": c.id, "cliente_id": cliente.id, "nombre": c.nombre})
    return c


# ----------------------------------------------------------------- cierre de ciclo
def cerrar_ciclo_campana(db: Session, c: Campana, hoy: dt.date, avisar: bool = True) -> Mensual:
    """Arma y archiva el mensual del ciclo, borra semanas y observaciones de ESTA campaña y la
    deja 'vencida'. No hace commit. Idempotente: si el mensual del periodo ya existe, lo reutiliza."""
    semanas = sorted(db.scalars(select(Semana).where(Semana.campana_id == c.id)), key=lambda s: s.inicio)
    mensajes = sum(s.mensajes or 0 for s in semanas)
    gasto = sum((s.importe_gastado or Decimal(0) for s in semanas), Decimal(0))
    costo_pm = (gasto / mensajes) if mensajes else Decimal(0)
    umbrales = rendimiento.cargar_umbrales(db)
    nivel = rendimiento.nivel_ciclo(rendimiento.buscar_umbral(umbrales, c.tipo, nombre_paquete(c)), float(costo_pm), semanas)

    mensual = db.scalars(select(Mensual).where(Mensual.campana_id == c.id, Mensual.periodo_inicio == c.fecha_inicio)).first()
    if mensual is None:
        mensual = Mensual(campana_id=c.id, periodo_inicio=c.fecha_inicio, periodo_fin=min(c.fecha_renovacion, hoy),
                          mensajes_total=mensajes, gasto_total=gasto.quantize(Decimal("0.01")),
                          costo_por_mensaje=costo_pm.quantize(Decimal("0.01")), presupuesto=c.presupuesto,
                          sobrante=(c.presupuesto - gasto).quantize(Decimal("0.01")), rendimiento=nivel,
                          origen="calculado")
        db.add(mensual)

    db.execute(delete(Observacion).where(Observacion.campana_id == c.id))
    db.execute(delete(Semana).where(Semana.campana_id == c.id))
    db.expire(c, ["semanas", "observaciones"])
    c.estado = "vencida"
    db.flush()
    if avisar:
        notificar.crear(
            db, c.cliente, "campana_vencida",
            f"La campaña «{c.nombre}» de {c.cliente.nombre} llegó a su fecha de renovación. "
            f"Confirma si el cliente renovó o la campaña termina para poder seguir capturando.",
            f"camp-venc:{c.id}:{c.fecha_renovacion}")
    return mensual


def renovar_campana(db: Session, user: Usuario, c: Campana, nueva_fecha: dt.date) -> Campana:
    if c.estado == "activa":
        raise HTTPException(409, "Esta campaña sigue activa; solo se renueva cuando está vencida o cerrada")
    if c.cliente.estado != "activo":
        raise HTTPException(409, "El cliente está en No renovados: primero reingrésalo")
    hoy = hoy_mx()
    if nueva_fecha <= hoy or nueva_fecha <= c.fecha_renovacion:
        raise HTTPException(422, "La nueva fecha de renovación debe ser futura y posterior a la anterior")
    c.fecha_inicio, c.fecha_renovacion, c.estado = hoy, nueva_fecha, "activa"
    db.flush()
    cal.asegurar_semana_actual(db, c, hoy)
    bitacora.registrar(db, user, "renovar_campana", {"campana_id": c.id, "nueva_fecha": str(nueva_fecha)})
    return c


def cerrar_campana(db: Session, user: Usuario | None, c: Campana, motivo: str | None = None,
                   avisar: bool = False) -> Campana:
    """La campaña termina (el cliente puede seguir con otras). Si estaba activa, primero se archiva su mensual."""
    if c.estado == "cerrada":
        raise HTTPException(409, "La campaña ya está cerrada")
    if c.estado == "activa":
        cerrar_ciclo_campana(db, c, hoy_mx(), avisar=avisar)
    c.estado = "cerrada"
    if user is not None:
        bitacora.registrar(db, user, "cerrar_campana", {"campana_id": c.id, "motivo": motivo})
    return c


def cerrar_abiertas_de_cliente(db: Session, cliente: Cliente) -> int:
    """Cuando el cliente pasa a No renovados, sus campañas abiertas se cierran (conservando el histórico)."""
    n = 0
    for c in cliente.campanas:
        if c.estado in ABIERTAS:
            cerrar_campana(db, None, c)
            n += 1
    return n


# ---------------------------------------------------------------- captura semanal
def capturar_semana(db: Session, user: Usuario, s: Semana, mensajes: int, costo: Decimal, importe: Decimal) -> Semana:
    hoy, ahora_ = hoy_mx(), ahora()
    if not cal.puede_editar(s, hoy, ahora_):
        raise HTTPException(403, "Esta semana ya cerró y quedó bloqueada")
    s.mensajes, s.costo_por_resultado, s.importe_gastado = mensajes, costo, importe
    s.capturado_por, s.actualizado_en = user.id, ahora_
    bitacora.registrar_si_admin(db, user, "captura_semana_admin", {"semana_id": s.id, "campana_id": s.campana_id})
    return s


# --------------------------------------------------------------------- salidas
def costo_actual_y_nivel(umbrales: rendimiento.Umbrales, c: Campana) -> tuple[float | None, str | None]:
    semanas = sorted(c.semanas, key=lambda s: s.inicio)
    con_costo = [s for s in semanas if s.costo_por_resultado is not None]
    if not con_costo:
        return None, None
    ultima = con_costo[-1]
    previas = [s for s in semanas if s.inicio < ultima.inicio]
    cfg = rendimiento.buscar_umbral(umbrales, c.tipo, nombre_paquete(c))
    return float(ultima.costo_por_resultado), rendimiento.nivel_semana(cfg, ultima, previas)


def campana_out(c: Campana, umbrales: rendimiento.Umbrales, hoy: dt.date, cms: dict[int, str] | None = None) -> dict:
    costo, nivel = costo_actual_y_nivel(umbrales, c)
    cm_id = c.cliente.cm_id
    return {
        "id": c.id, "cliente_id": c.cliente_id, "cliente_nombre": c.cliente.nombre, "cliente_estado": c.cliente.estado,
        "cm_id": cm_id, "cm_nombre": (cms or {}).get(cm_id) if cm_id else None,
        "paquete_cliente_id": c.paquete_cliente_id, "paquete": nombre_paquete(c),
        "nombre": c.nombre, "tipo": c.tipo, "presupuesto": float(c.presupuesto), "presupuesto_esquema": c.presupuesto_esquema,
        "formato_post": c.formato_post, "formato_3d": c.formato_3d, "formato_boton": c.formato_boton,
        "formato_otro": c.formato_otro, "lugar": c.lugar, "fecha_inicio": c.fecha_inicio,
        "fecha_renovacion": c.fecha_renovacion, "dias_para_renovar": (c.fecha_renovacion - hoy).days,
        "estado": c.estado, "costo_actual": costo, "rendimiento": nivel,
    }


def semanas_out(c: Campana, umbrales: rendimiento.Umbrales, hoy: dt.date, ahora_: dt.datetime) -> list[dict]:
    cfg = rendimiento.buscar_umbral(umbrales, c.tipo, nombre_paquete(c))
    salida, previas = [], []
    for s in sorted(c.semanas, key=lambda s: s.inicio):
        permiso = s.edicion_habilitada_hasta if (s.edicion_habilitada_hasta and ahora_ < s.edicion_habilitada_hasta) else None
        salida.append({
            "id": s.id, "campana_id": s.campana_id, "inicio": s.inicio, "fin": s.fin, "mensajes": s.mensajes,
            "costo_por_resultado": float(s.costo_por_resultado) if s.costo_por_resultado is not None else None,
            "importe_gastado": float(s.importe_gastado) if s.importe_gastado is not None else None,
            "editable": cal.semana_editable(s, hoy), "permiso_hasta": permiso,
            "en_curso": s.inicio <= hoy <= s.fin, "rendimiento": rendimiento.nivel_semana(cfg, s, previas),
        })
        previas.append(s)
    return salida


def mensual_out(m: Mensual) -> dict:
    return {"id": m.id, "campana_id": m.campana_id, "periodo_inicio": m.periodo_inicio, "periodo_fin": m.periodo_fin,
            "mensajes_total": m.mensajes_total, "gasto_total": float(m.gasto_total),
            "costo_por_mensaje": float(m.costo_por_mensaje), "presupuesto": float(m.presupuesto),
            "sobrante": float(m.sobrante) if m.sobrante is not None else None, "rendimiento": m.rendimiento,
            "origen": m.origen}
