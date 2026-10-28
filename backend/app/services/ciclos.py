import datetime as dt
from decimal import Decimal

from app.config import get_settings
from app.models import PaqueteCliente
from app.services.periodos import quincena_de

VIGENTES = ("activo", "vencido")
COBRABLES = ("activo", "vencido", "renovado")
ORDEN_SEMAFORO = {"rojo": 0, "amarillo": 1, "gris": 2, "verde": 3}


def dias_para_renovar(p: PaqueteCliente, hoy: dt.date) -> int:
    return (p.fecha_renovacion - hoy).days


def pagado_hasta(p: PaqueteCliente, corte: dt.date | None = None) -> Decimal:
    return sum((g.monto for g in p.pagos if corte is None or g.fecha <= corte), Decimal("0"))


def pagado_completo(p: PaqueteCliente) -> bool:
    return pagado_hasta(p) >= p.costo


def es_vencido(p: PaqueteCliente, hoy: dt.date) -> bool:
    return p.estado in VIGENTES and p.renovacion_decision in ("pendiente", "si") and hoy > p.fecha_renovacion


def prorroga_activa(p: PaqueteCliente, hoy: dt.date) -> bool:
    return p.prorroga_hasta is not None and hoy <= p.prorroga_hasta and not pagado_completo(p)


def prorroga_vencida(p: PaqueteCliente, hoy: dt.date) -> bool:
    return p.prorroga_hasta is not None and hoy > p.prorroga_hasta and not pagado_completo(p)


def gracia_activa(p: PaqueteCliente, hoy: dt.date) -> bool:
    return p.gracia_hasta is not None and hoy <= p.gracia_hasta and not pagado_completo(p)


def confirmo_renovacion(p: PaqueteCliente) -> bool:
    return p.estado in VIGENTES and p.renovacion_decision == "si"


def bloqueado(p: PaqueteCliente, hoy: dt.date) -> bool:
    return es_vencido(p, hoy) and not prorroga_activa(p, hoy) and not gracia_activa(p, hoy)


def limite_decision(p: PaqueteCliente) -> dt.date | None:
    if p.renovacion_decision != "pendiente":
        return None
    return p.fecha_renovacion + dt.timedelta(days=get_settings().dias_para_decidir)


def opciones_bloqueo(p: PaqueteCliente, hoy: dt.date) -> list[str]:
    if not bloqueado(p, hoy):
        return []
    if pagado_completo(p):
        return ["renovo", "no_renovo"]
    if p.renovacion_decision == "pendiente":
        return ["va_a_renovar", "no_renovo"]
    return ["no_renovo"] if p.prorroga_hasta is not None else ["prorroga", "no_renovo"]


def estado_efectivo(p: PaqueteCliente, hoy: dt.date) -> str:
    if es_vencido(p, hoy):
        return "vencido"
    if p.estado == "activo" and p.renovacion_decision == "pendiente":
        if 0 <= dias_para_renovar(p, hoy) <= get_settings().aviso_dias_antes_renovacion:
            return "por_vencer"
    return p.estado


def semaforo(p: PaqueteCliente, hoy: dt.date) -> str:
    if prorroga_activa(p, hoy):
        return "amarillo"
    if es_vencido(p, hoy):
        return "rojo"
    if p.estado in ("archivado", "eliminado"):
        return "gris"
    if pagado_completo(p):
        return "verde"
    if p.renovacion_decision == "si":
        return "amarillo"
    return "gris"


def recalcular_pagada(p: PaqueteCliente) -> None:
    p.renovacion_pagada = pagado_completo(p)


def paquete_out(p: PaqueteCliente, hoy: dt.date) -> dict:
    pagado = pagado_hasta(p)
    avance = float(min(Decimal(1), pagado / p.costo)) * 100 if p.costo > 0 else 100.0
    return {
        "id": p.id, "cliente_id": p.cliente_id,
        "paquete_id": p.paquete_id, "paquete": p.paquete.nombre,
        "tipo_id": p.tipo_id, "tipo": p.tipo.nombre,
        "costo": p.costo, "pagado": pagado, "restante": max(p.costo - pagado, Decimal(0)),
        "avance_pct": round(avance, 1),
        "fecha_inicio": p.fecha_inicio, "fecha_renovacion": p.fecha_renovacion,
        "quincena": quincena_de(p.fecha_renovacion),
        "dias_para_renovar": dias_para_renovar(p, hoy),
        "estado": p.estado, "estado_efectivo": estado_efectivo(p, hoy),
        "renovacion_decision": p.renovacion_decision, "renovacion_pagada": p.renovacion_pagada,
        "no_renovara": p.estado in VIGENTES and p.renovacion_decision == "no",
        "confirmo_renovacion": confirmo_renovacion(p),
        "gracia_hasta": p.gracia_hasta, "gracia_activa": gracia_activa(p, hoy),
        "semaforo": semaforo(p, hoy),
        "bloqueado": bloqueado(p, hoy), "opciones_bloqueo": opciones_bloqueo(p, hoy),
        "limite_decision": limite_decision(p) if es_vencido(p, hoy) else None,
        "confirmado_en": p.confirmado_en,
        "renovara_con": ({"paquete_id": p.renovara_paquete_id or p.paquete_id, "tipo_id": p.renovara_tipo_id or p.tipo_id,
                          "costo": p.renovara_costo if p.renovara_costo is not None else p.costo}
                         if p.estado in VIGENTES and p.renovacion_decision == "si" else None),
        "prorroga_hasta": p.prorroga_hasta, "prorroga_registrada_en": p.prorroga_registrada_en,
        "prorroga_dias_restantes": (p.prorroga_hasta - hoy).days if p.prorroga_hasta else None,
        "prorroga_activa": prorroga_activa(p, hoy), "prorroga_vencida": prorroga_vencida(p, hoy),
        "ciclo_anterior_id": p.ciclo_anterior_id, "archivado_en": p.archivado_en,
    }


def veces_renovado(db, p: PaqueteCliente) -> int:
    n, actual = 0, p
    while actual.ciclo_anterior_id is not None:
        anterior = db.get(PaqueteCliente, actual.ciclo_anterior_id)
        if anterior is None or anterior.paquete_id != p.paquete_id:
            break
        n, actual = n + 1, anterior
    return n
