"""Consolidación de campañas por CLIENTE.

El reporte formal consolida todas las campañas del cliente, que es como el
cliente final lo entiende (una campaña puede cerrarse y abrirse otra dentro del
mismo ciclo y para él fue una sola).
"""
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cliente, Mensual, Semana
from app.services import rendimiento


@dataclass
class MesConsolidado:
    periodo_inicio: dt.date
    periodo_fin: dt.date
    mensajes_total: int
    gasto_total: float
    costo_por_mensaje: float
    presupuesto: float
    sobrante: float
    rendimiento: str | None


@dataclass
class SemanaConsolidada:
    inicio: dt.date
    fin: dt.date
    mensajes: int
    costo_por_resultado: float | None
    importe_gastado: float


def mensuales_consolidados(db: Session, cliente: Cliente, limite: int = 3) -> list[MesConsolidado]:
    ids = [c.id for c in cliente.campanas]
    if not ids:
        return []
    campana = {c.id: c for c in cliente.campanas}
    umbrales = rendimiento.cargar_umbrales(db)
    por_periodo: dict[dt.date, dict] = defaultdict(
        lambda: {"fin": None, "mensajes": 0, "gasto": 0.0, "presupuesto": 0.0, "ref": None})
    for m in db.scalars(select(Mensual).where(Mensual.campana_id.in_(ids)).order_by(Mensual.periodo_inicio.desc())):
        acc = por_periodo[m.periodo_inicio]
        acc["fin"] = m.periodo_fin
        acc["mensajes"] += m.mensajes_total
        acc["gasto"] += float(m.gasto_total)
        acc["presupuesto"] += float(m.presupuesto)
        acc["ref"] = acc["ref"] or campana.get(m.campana_id)

    salida = []
    for periodo in sorted(por_periodo, reverse=True)[:limite]:
        a = por_periodo[periodo]
        costo = a["gasto"] / a["mensajes"] if a["mensajes"] else 0.0
        nivel = None
        if a["ref"] is not None:
            nombre_pq = a["ref"].paquete_cliente.paquete.nombre if a["ref"].paquete_cliente else None
            nivel = rendimiento.nivel_ciclo(rendimiento.buscar_umbral(umbrales, a["ref"].tipo, nombre_pq), costo, [])
        salida.append(MesConsolidado(
            periodo_inicio=periodo, periodo_fin=a["fin"], mensajes_total=a["mensajes"],
            gasto_total=round(a["gasto"], 2), costo_por_mensaje=round(costo, 2),
            presupuesto=round(a["presupuesto"], 2), sobrante=round(a["presupuesto"] - a["gasto"], 2),
            rendimiento=nivel))
    return salida


def semanas_consolidadas(db: Session, cliente: Cliente) -> list[SemanaConsolidada]:
    """Suma, por fecha de inicio, las semanas del ciclo en curso de todas las campañas ACTIVAS."""
    ids = [c.id for c in cliente.campanas if c.estado == "activa"]
    if not ids:
        return []
    por_semana: dict[dt.date, dict] = defaultdict(lambda: {"fin": None, "mensajes": 0, "importe": 0.0})
    for s in db.scalars(select(Semana).where(Semana.campana_id.in_(ids)).order_by(Semana.inicio)):
        a = por_semana[s.inicio]
        a["fin"] = s.fin
        a["mensajes"] += s.mensajes or 0
        a["importe"] += float(s.importe_gastado or 0)
    salida = []
    for inicio in sorted(por_semana):
        a = por_semana[inicio]
        costo = a["importe"] / a["mensajes"] if a["mensajes"] else None
        salida.append(SemanaConsolidada(
            inicio=inicio, fin=a["fin"], mensajes=a["mensajes"],
            costo_por_resultado=round(costo, 2) if costo is not None else None,
            importe_gastado=round(a["importe"], 2)))
    return salida
