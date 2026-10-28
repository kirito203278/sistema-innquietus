"""Calendario de la semana operativa (sábado -> viernes) y reglas de edición.

Todo se calcula con el reloj del negocio (app.dates), nunca con date.today():
así las pruebas pueden congelar el día.
"""
import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campana, Semana

SABADO = 5  # date.weekday(): lunes=0 ... sábado=5


def sabado_mas_reciente(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=(d.weekday() - SABADO) % 7)


def rango_semana(d: dt.date) -> tuple[dt.date, dt.date]:
    inicio = sabado_mas_reciente(d)
    return inicio, inicio + dt.timedelta(days=6)


def en_ventana_habilitacion(momento_local: dt.datetime) -> bool:
    """El admin solo puede habilitar la edición de una semana cerrada entre el sábado
    8:00 y el viernes 15:00 siguiente (hora local). De viernes 15:00 a sábado 8:00 no."""
    dia, hora = momento_local.weekday(), momento_local.time()
    if dia == 4 and hora >= dt.time(15, 0):
        return False
    if dia == 5 and hora < dt.time(8, 0):
        return False
    return True


def semana_editable(s: Semana, hoy: dt.date) -> bool:
    """Editable mientras no termine su viernes. Derivado de la fecha: no depende de que
    el job del sábado haya corrido (si el servidor estuvo apagado, igual se bloquea)."""
    return bool(s.editable) and hoy <= s.fin


def puede_editar(s: Semana, hoy: dt.date, ahora: dt.datetime) -> bool:
    permiso = s.edicion_habilitada_hasta is not None and ahora < s.edicion_habilitada_hasta
    return semana_editable(s, hoy) or permiso


def asegurar_semana_actual(db: Session, campana: Campana, hoy: dt.date) -> Semana:
    """Crea la fila de la semana en curso si todavía no existe (idempotente)."""
    inicio, fin = rango_semana(hoy)
    s = db.scalars(select(Semana).where(Semana.campana_id == campana.id, Semana.inicio == inicio)).first()
    if s is None:
        s = Semana(campana_id=campana.id, inicio=inicio, fin=fin, editable=True)
        db.add(s)
        db.flush()
    return s
