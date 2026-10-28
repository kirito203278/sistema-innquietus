import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import bitacora
from app.config import get_settings
from app.database import get_db
from app.dates import ahora, hoy as hoy_mx
from app.deps import get_current_user, require_admin_write, require_writer
from app.models import Pago, PaqueteCliente, RecordatorioCliente, Renovacion, Usuario
from app.routers.clientes import PaqueteNuevo, crear_ciclo, validar_catalogos
from app.services import bloqueo, ciclos, recordatorios, renovacion, visibilidad
from app.services import pagos as pagos_svc
from app.services.scope import obtener_cliente, obtener_pago, obtener_paquete, paquetes_q

router = APIRouter(prefix="/api", tags=["paquetes"])


class PaquetePatch(BaseModel):
    paquete_id: int | None = None
    tipo_id: int | None = None
    costo: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    fecha_inicio: dt.date | None = None


class PagoIn(BaseModel):
    monto: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    fecha: dt.date | None = None
    nota: str | None = Field(default=None, max_length=300)


def pago_out(g: Pago, nombres: dict[int, str]) -> dict:
    return {"id": g.id, "monto": g.monto, "fecha": g.fecha, "nota": g.nota, "registrado_por": g.registrado_por,
            "registrado_por_nombre": nombres.get(g.registrado_por), "creado_en": g.creado_en}


def _editable(p: PaqueteCliente) -> None:
    if p.estado not in ciclos.VIGENTES:
        raise HTTPException(409, "Este paquete ya no está vigente")


@router.post("/clientes/{cliente_id}/paquetes", status_code=status.HTTP_201_CREATED)
def agregar_paquete(cliente_id: int, datos: PaqueteNuevo, db: Session = Depends(get_db),
                    user: Usuario = Depends(require_writer)):
    c = obtener_cliente(db, user, cliente_id)
    if c.estado != "activo":
        raise HTTPException(409, "El cliente está en No renovados: usa el reingreso")
    if renovacion.vigentes_del_cliente(db, c.id) > 0:
        raise HTTPException(409, "Un cliente tiene un solo paquete. Para cambiar de paquete, hazlo al renovar.")
    bloqueo.exigir_libre(db, c.id, hoy_mx())
    p = crear_ciclo(db, c, datos, user)
    bitacora.registrar_si_admin(db, user, "alta_paquete_admin", {"cliente_id": c.id, "paquete_id": p.id})
    db.commit()
    return {"id": p.id}


@router.get("/paquetes/{paquete_id}")
def detalle(paquete_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    p = obtener_paquete(db, user, paquete_id)
    hoy = hoy_mx()
    nombres = {u.id: u.nombre for u in db.scalars(select(Usuario))}
    cadena, actual = [], p
    while actual is not None:
        cadena.append(actual)
        actual = db.get(PaqueteCliente, actual.ciclo_anterior_id) if actual.ciclo_anterior_id else None
    sig = db.scalars(paquetes_q(user).where(PaqueteCliente.ciclo_anterior_id == p.id)).first()
    while sig is not None:
        cadena.insert(0, sig)
        sig = db.scalars(paquetes_q(user).where(PaqueteCliente.ciclo_anterior_id == sig.id)).first()
    renov = db.scalars(select(Renovacion).where(Renovacion.ciclo_anterior_id.in_([x.id for x in cadena]))
                       .order_by(Renovacion.fecha.desc())).all()
    pagos = [] if visibilidad.oculta_montos(user) else [pago_out(g, nombres)
                                                       for g in sorted(p.pagos, key=lambda g: (g.fecha, g.id), reverse=True)]
    renov_out = [] if visibilidad.oculta_montos(user) else None
    return {**visibilidad.paquete_visible(ciclos.paquete_out(p, hoy), user),
            "veces_renovado": ciclos.veces_renovado(db, p),
            "pagos": pagos,
            "ciclos": visibilidad.paquetes_visibles([ciclos.paquete_out(x, hoy) for x in cadena], user),
            "renovaciones": [{"id": r.id, "fecha": r.fecha, "ciclo_anterior_id": r.ciclo_anterior_id,
                              "ciclo_nuevo_id": r.ciclo_nuevo_id, "costo_anterior": r.costo_anterior,
                              "costo_nuevo": r.costo_nuevo, "paquete_anterior_id": r.paquete_anterior_id,
                              "paquete_nuevo_id": r.paquete_nuevo_id} for r in renov] if renov_out is None else renov_out}


@router.patch("/paquetes/{paquete_id}")
def editar_paquete(paquete_id: int, datos: PaquetePatch, db: Session = Depends(get_db),
                   user: Usuario = Depends(require_writer)):
    p = obtener_paquete(db, user, paquete_id)
    _editable(p)
    bloqueo.exigir_libre(db, p.cliente_id, hoy_mx())
    campos = datos.model_dump(exclude_unset=True, exclude_none=True)
    if user.rol != "admin" and {"paquete_id", "tipo_id", "costo"} & set(campos):
        raise HTTPException(403, "El paquete, el tipo y el costo solo cambian al renovar (al confirmar que renueva o al registrar la renovación)")
    if "paquete_id" in campos or "tipo_id" in campos:
        validar_catalogos(db, campos.get("paquete_id", p.paquete_id), campos.get("tipo_id", p.tipo_id))
    antes = {k: str(getattr(p, k)) for k in campos}
    if "fecha_inicio" in campos:
        p.fecha_inicio = campos.pop("fecha_inicio")
        p.fecha_renovacion = p.fecha_inicio + dt.timedelta(days=get_settings().ciclo_dias)
        if p.estado == "vencido" and p.fecha_renovacion >= hoy_mx():
            p.estado = "activo"
    for k, v in campos.items():
        setattr(p, k, v)
    db.flush()
    ciclos.recalcular_pagada(p)
    bitacora.registrar(db, user, "editar_paquete", {"paquete_id": p.id, "antes": antes,
                                                    "despues": {k: str(getattr(p, k)) for k in antes}})
    db.commit()
    db.refresh(p)
    return visibilidad.paquete_visible(ciclos.paquete_out(p, hoy_mx()), user)


@router.post("/paquetes/{paquete_id}/pagos", status_code=status.HTTP_201_CREATED)
def registrar_pago(paquete_id: int, datos: PagoIn, db: Session = Depends(get_db),
                   user: Usuario = Depends(require_admin_write)):
    p = obtener_paquete(db, user, paquete_id)
    bloqueo.exigir_libre(db, p.cliente_id, hoy_mx())
    g = pagos_svc.registrar_pago(db, user, p, datos.monto, datos.fecha, datos.nota)
    nuevo = renovacion.renovar_si_confirmado_y_pagado(db, user, p)
    hoy = hoy_mx()
    db.commit()
    db.refresh(p)
    return {"pago_id": g.id, "paquete": ciclos.paquete_out(p, hoy), "renovado_automaticamente": nuevo.id if nuevo else None}


@router.delete("/pagos/{pago_id}")
def borrar_pago(pago_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_admin_write)):
    g = obtener_pago(db, user, pago_id)
    p = obtener_paquete(db, user, g.paquete_id)
    bloqueo.exigir_libre(db, p.cliente_id, hoy_mx())
    bitacora.registrar(db, user, "borrar_pago", {"pago_id": g.id, "paquete_id": p.id, "monto": str(g.monto),
                                                 "fecha": str(g.fecha)})
    db.delete(g)
    db.flush()
    db.refresh(p)
    ciclos.recalcular_pagada(p)
    db.commit()
    return {"ok": True}


@router.post("/paquetes/{paquete_id}/prorroga")
def solicitar_prorroga(paquete_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_admin_write)):
    p = obtener_paquete(db, user, paquete_id)
    renovacion.solicitar_prorroga(db, user, p)
    db.commit()
    db.refresh(p)
    return visibilidad.paquete_visible(ciclos.paquete_out(p, hoy_mx()), user)


def recordatorio_out(r: RecordatorioCliente, telefono: str | None) -> dict:
    return {"id": r.id, "paquete_id": r.paquete_id, "texto": r.texto, "wa_url": recordatorios.wa_url(telefono, r.texto),
            "telefono": telefono, "generado_en": r.generado_en, "enviado_en": r.enviado_en}


@router.post("/paquetes/{paquete_id}/recordatorio", status_code=status.HTTP_201_CREATED)
def crear_recordatorio(paquete_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_admin_write)):
    p = obtener_paquete(db, user, paquete_id)
    bloqueo.exigir_libre(db, p.cliente_id, hoy_mx())
    if p.costo - ciclos.pagado_hasta(p) <= 0:
        raise HTTPException(422, "El paquete no tiene saldo pendiente")
    try:
        r, _ = recordatorios.crear_para_paquete(db, p, p.cliente.cm_id)
    except recordatorios.YaEnviado:
        raise HTTPException(409, "El mensaje de este paquete ya se envió: no se puede enviar de nuevo")
    db.commit()
    return recordatorio_out(r, p.cliente.telefono)


@router.get("/paquetes/{paquete_id}/recordatorios")
def listar_recordatorios(paquete_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_admin_write)):
    p = obtener_paquete(db, user, paquete_id)
    filas = db.scalars(select(RecordatorioCliente).where(RecordatorioCliente.paquete_id == p.id)
                       .order_by(RecordatorioCliente.id.desc())).all()
    return [recordatorio_out(r, p.cliente.telefono) for r in filas]


@router.post("/recordatorios/{recordatorio_id}/marcar-enviado")
def marcar_enviado(recordatorio_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_admin_write)):
    r = db.get(RecordatorioCliente, recordatorio_id)
    if r is None:
        raise HTTPException(404, "Recordatorio no encontrado")
    p = obtener_paquete(db, user, r.paquete_id)
    if r.enviado_en is not None:
        raise HTTPException(409, "Este mensaje ya estaba marcado como enviado")
    r.enviado_en = ahora()
    db.commit()
    return recordatorio_out(r, p.cliente.telefono)
