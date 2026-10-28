import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.dates import hoy as hoy_mx
from app.database import get_sessionmaker
from app.models import JobEjecucion, PaqueteCliente
from app.services import ciclos, notificar, recordatorios
from app.jobs import tareas_campanas
from app.services.renovacion import archivar, purgar_no_renovados

log = logging.getLogger("jobs")


def _fmt(f: dt.date) -> str:
    return f.strftime("%d/%m/%Y")


def _paquetes(db: Session, *condiciones):
    return db.scalars(select(PaqueteCliente).where(*condiciones).options(
        selectinload(PaqueteCliente.cliente), selectinload(PaqueteCliente.paquete), selectinload(PaqueteCliente.pagos)))


def avisos_renovacion(db: Session, hoy: dt.date | None = None) -> dict:
    hoy = hoy or hoy_mx()
    s = get_settings()
    avisos = vencidos = auto_no_renueva = programados = 0
    for p in _paquetes(db, PaqueteCliente.estado.in_(ciclos.VIGENTES),
                       PaqueteCliente.fecha_renovacion <= hoy + dt.timedelta(days=s.aviso_dias_antes_renovacion)).all():
        c = p.cliente
        if c.estado != "activo":
            continue
        dias = (p.fecha_renovacion - hoy).days
        if p.renovacion_decision == "no":
            if hoy > p.fecha_renovacion:
                archivar(db, p, "No renovó (marcado por el CM)")
                programados += 1
            continue
        confirmado = p.renovacion_decision == "si"
        if dias >= 0:
            if p.estado == "activo" and not confirmado:
                avisos += notificar.crear(
                    db, c, "renovacion_3d",
                    f"{c.nombre}: el paquete {p.paquete.nombre} renueva el {_fmt(p.fecha_renovacion)} "
                    f"({'hoy' if dias == 0 else 'mañana' if dias == 1 else f'en {dias} días'}). ¿Renueva?",
                    f"renov:{p.id}", paquete_id=p.id)
            continue
        if ciclos.prorroga_activa(p, hoy) or ciclos.gracia_activa(p, hoy):
            continue
        limite = ciclos.limite_decision(p)
        if limite is not None and hoy > limite:
            archivar(db, p, "No renovó: sin decisión")
            auto_no_renueva += 1
            continue
        if p.estado != "vencido":
            p.estado = "vencido"
        if confirmado:
            texto = (f"{c.nombre}: terminó el contrato del paquete {p.paquete.nombre} y aún no paga. "
                     f"Indica si solicita prórroga o si no renovó.")
            clave = f"vencido-si:{p.id}:{p.gracia_hasta}"
        else:
            texto = (f"{c.nombre}: terminó el contrato del paquete {p.paquete.nombre} ({_fmt(p.fecha_renovacion)}). "
                     f"Indica si va a renovar o no; si no decides pasa a No renovados el {_fmt(limite + dt.timedelta(days=1))}.")
            clave = f"vencido:{p.id}"
        vencidos += notificar.crear(db, c, "paquete_vencido", texto, clave, paquete_id=p.id)
    db.commit()
    return {"avisos": avisos, "marcados_vencidos": vencidos, "pasaron_a_no_renovados": auto_no_renueva + programados}


def avisos_prorroga(db: Session, hoy: dt.date | None = None) -> dict:
    hoy = hoy or hoy_mx()
    margen = get_settings().aviso_prorroga_dias
    proximas = vencidas = 0
    for p in _paquetes(db, PaqueteCliente.prorroga_hasta.is_not(None), PaqueteCliente.estado.in_(ciclos.VIGENTES),
                       PaqueteCliente.prorroga_hasta <= hoy + dt.timedelta(days=margen)).all():
        if ciclos.pagado_completo(p):
            continue
        c, resta = p.cliente, p.costo - ciclos.pagado_hasta(p)
        if p.prorroga_hasta < hoy:
            a_no_ren = archivar(db, p, "La prórroga venció sin pago completo")
            recordatorios.crear_para_paquete(db, p, c.cm_id)
            vencidas += notificar.crear(
                db, c, "prorroga_vencida",
                f"{c.nombre}: la prórroga del paquete {p.paquete.nombre} venció el {_fmt(p.prorroga_hasta)} sin pago completo "
                f"(faltan ${resta:,.2f}). {'El cliente pasó a No renovados. ' if a_no_ren else ''}"
                f"Tienes listo el mensaje para el cliente: envíalo y márcalo como enviado.",
                f"prorroga-venc:{p.id}:{p.prorroga_hasta}", paquete_id=p.id)
        else:
            d = (p.prorroga_hasta - hoy).days
            proximas += notificar.crear(
                db, c, "prorroga_3d",
                f"{c.nombre}: la prórroga del paquete {p.paquete.nombre} vence el {_fmt(p.prorroga_hasta)} "
                f"({'hoy' if d == 0 else f'en {d} días'}); faltan ${resta:,.2f}.",
                f"prorroga-3d:{p.id}:{p.prorroga_hasta}", paquete_id=p.id)
    db.commit()
    return {"avisos_prorroga": proximas, "prorrogas_vencidas": vencidas}


def purga_no_renovados(db: Session) -> dict:
    eliminados = purgar_no_renovados(db)
    db.commit()
    return {"eliminados": len(eliminados)}


JOBS = {"renovaciones": avisos_renovacion, "prorrogas": avisos_prorroga, "purga_no_renovados": purga_no_renovados,
        "cierre_semana": tareas_campanas.cierre_semana, "recordatorio_captura": tareas_campanas.recordatorio_captura,
        "cierre_ciclo_campanas": tareas_campanas.cierre_ciclo_campanas}


def ejecutar(nombre: str, origen: str = "manual") -> dict:
    with get_sessionmaker()() as db:
        try:
            resultado = JOBS[nombre](db)
        except Exception:
            db.rollback()
            log.exception("Falló el job %s", nombre)
            raise
        db.add(JobEjecucion(nombre=nombre, origen=origen, resultado=resultado))
        db.commit()
        return resultado
