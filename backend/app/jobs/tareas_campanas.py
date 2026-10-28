"""Trabajos programados del módulo de campañas. Misma convención que jobs/tareas.py:
reciben la sesión, usan el reloj del negocio (dates.hoy), son idempotentes y devuelven un
resumen que queda registrado en jobs_ejecuciones."""
import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.dates import hoy as hoy_mx
from app.models import Campana, Cliente, Semana
from app.services import campanas as svc
from app.services import notificar
from app.services import semanas as cal


def cierre_semana(db: Session, hoy: dt.date | None = None) -> dict:
    """Sábado 00:00: bloquea las semanas que terminaron (las no capturadas quedan en 0) y crea la semana
    nueva de cada campaña activa."""
    hoy = hoy or hoy_mx()
    inicio_actual, _ = cal.rango_semana(hoy)
    vencidas = (Semana.editable.is_(True), Semana.fin < inicio_actual)
    rellenadas = db.execute(update(Semana).where(*vencidas, Semana.mensajes.is_(None))
                            .values(mensajes=0, costo_por_resultado=0, importe_gastado=0)).rowcount
    bloqueadas = db.execute(update(Semana).where(*vencidas).values(editable=False)).rowcount
    creadas = 0
    for c in db.scalars(select(Campana).where(Campana.estado == "activa", Campana.fecha_inicio <= hoy)):
        existia = db.scalars(select(Semana.id).where(Semana.campana_id == c.id, Semana.inicio == inicio_actual)).first()
        if existia is None:
            cal.asegurar_semana_actual(db, c, hoy)
            creadas += 1
    db.commit()
    return {"rellenadas_en_0": rellenadas, "bloqueadas": bloqueadas, "semanas_nuevas": creadas}


def recordatorio_captura(db: Session, hoy: dt.date | None = None) -> dict:
    """Viernes 14:00: avisa a cada responsable (un solo aviso por día) de las campañas con la semana sin capturar."""
    hoy = hoy or hoy_mx()
    inicio, _ = cal.rango_semana(hoy)
    pendientes = db.scalars(
        select(Semana).join(Campana, Campana.id == Semana.campana_id).join(Cliente, Cliente.id == Campana.cliente_id)
        .where(Campana.estado == "activa", Cliente.estado == "activo", Semana.inicio == inicio,
               Semana.editable.is_(True), Semana.mensajes.is_(None))
        .options(selectinload(Semana.campana).selectinload(Campana.cliente))).all()
    por_usuario: dict[int, list[str]] = {}
    for s in pendientes:
        c = s.campana
        for uid in notificar.destinatarios(db, c.cliente):
            por_usuario.setdefault(uid, []).append(f"{c.cliente.nombre} — {c.nombre}")
    avisos = 0
    for uid, lista in por_usuario.items():
        texto = (f"Te falta capturar la semana de {lista[0]}." if len(lista) == 1
                 else f"Te faltan {len(lista)} campañas por capturar esta semana: {'; '.join(lista)}.")
        avisos += notificar.crear_para_usuario(db, uid, "recordatorio_captura", f"{texto} La fecha límite es hoy a las 3:00 pm.",
                                               f"captura:{uid}:{hoy.isoformat()}")
    db.commit()
    return {"avisos": avisos, "campanas_pendientes": len(pendientes)}


def cierre_ciclo_campanas(db: Session, hoy: dt.date | None = None) -> dict:
    """Diario 12:00: toda campaña activa cuya fecha de renovación ya llegó (o pasó, si el servidor estuvo caído)
    archiva su mensual y pasa a 'vencida' hasta que el CM resuelva."""
    hoy = hoy or hoy_mx()
    pendientes = db.scalars(select(Campana).where(Campana.estado == "activa", Campana.fecha_renovacion <= hoy)
                            .options(selectinload(Campana.cliente), selectinload(Campana.paquete_cliente))).all()
    for c in pendientes:
        svc.cerrar_ciclo_campana(db, c, hoy)
    db.commit()
    return {"campanas_cerradas": len(pendientes)}
