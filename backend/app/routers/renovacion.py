import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dates import hoy as hoy_mx
from app.deps import get_current_user, require_admin_write, require_writer
from app.models import Cliente, PaqueteCliente, Usuario
from app.routers.clientes import ficha_out
from app.services import bloqueo as bloqueo_svc, ciclos, renovacion, visibilidad
from app.services.periodos import construir_periodo, quincena_de
from app.services.scope import obtener_cliente, obtener_paquete, paquetes_q

router = APIRouter(prefix="/api", tags=["renovacion"])


class RenovarIn(BaseModel):
    paquete_id: int | None = None
    tipo_id: int | None = None
    costo: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class NoRenovarIn(BaseModel):
    accion: str
    confirmar_nombre: str | None = None
    eliminar_cliente: bool | None = None


class ReingresoIn(BaseModel):
    modo: str
    paquete_id: int | None = None
    tipo_id: int | None = None
    costo: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


@router.post("/paquetes/{paquete_id}/renovar")
def renovar(paquete_id: int, datos: RenovarIn, db: Session = Depends(get_db), user: Usuario = Depends(require_writer)):
    p = obtener_paquete(db, user, paquete_id)
    nuevo = renovacion.renovar(db, user, p, paquete_id=datos.paquete_id, tipo_id=datos.tipo_id, costo=datos.costo)
    db.commit()
    db.refresh(p), db.refresh(nuevo)
    hoy = hoy_mx()
    return {"anterior": visibilidad.paquete_visible(ciclos.paquete_out(p, hoy), user),
            "nuevo": {**visibilidad.paquete_visible(ciclos.paquete_out(nuevo, hoy), user),
                      "veces_renovado": ciclos.veces_renovado(db, nuevo)}}


@router.post("/paquetes/{paquete_id}/no-renovar")
def no_renovar(paquete_id: int, datos: NoRenovarIn, db: Session = Depends(get_db),
               user: Usuario = Depends(require_writer)):
    p = obtener_paquete(db, user, paquete_id)
    res = renovacion.no_renovar(db, user, p, accion=datos.accion, confirmar_nombre=datos.confirmar_nombre,
                                eliminar_cliente=datos.eliminar_cliente)
    db.commit()
    return res


@router.post("/paquetes/{paquete_id}/revertir-decision")
def revertir(paquete_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_writer)):
    p = obtener_paquete(db, user, paquete_id)
    renovacion.revertir_decision(db, user, p)
    db.commit()
    db.refresh(p)
    return visibilidad.paquete_visible(ciclos.paquete_out(p, hoy_mx()), user)


@router.post("/paquetes/{paquete_id}/confirmar-renovacion")
def confirmar_renovacion(paquete_id: int, datos: RenovarIn | None = None, db: Session = Depends(get_db),
                         user: Usuario = Depends(require_writer)):
    p = obtener_paquete(db, user, paquete_id)
    datos = datos or RenovarIn()
    if user.rol != "admin":
        datos = RenovarIn()
    nuevo = renovacion.confirmar_renovacion(db, user, p, paquete_id=datos.paquete_id, tipo_id=datos.tipo_id, costo=datos.costo)
    db.commit()
    db.refresh(p)
    hoy = hoy_mx()
    return {"paquete": visibilidad.paquete_visible(ciclos.paquete_out(p, hoy), user),
            "renovado_automaticamente": nuevo.id if nuevo else None}


@router.get("/bloqueos")
def bloqueos(db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    hoy = hoy_mx()
    return [{**visibilidad.paquete_visible(ciclos.paquete_out(p, hoy), user), "cliente_nombre": p.cliente.nombre,
             "cm_id": p.cliente.cm_id} for p in bloqueo_svc.bloqueos_visibles(db, user, hoy)]


@router.post("/clientes/{cliente_id}/reingreso")
def reingreso(cliente_id: int, datos: ReingresoIn, db: Session = Depends(get_db),
              user: Usuario = Depends(require_writer)):
    c = obtener_cliente(db, user, cliente_id)
    renovacion.reingresar(db, user, c, modo=datos.modo, paquete_id=datos.paquete_id, tipo_id=datos.tipo_id,
                          costo=datos.costo)
    db.commit()
    db.refresh(c)
    return ficha_out(c, hoy_mx(), db, user)


@router.get("/clientes/{cliente_id}/reingreso-info")
def reingreso_info(cliente_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    from app.config import get_settings
    from app.dates import ahora
    from app.models import ArchivoNoRenovado
    from app.services.periodos import restar_meses
    c = obtener_cliente(db, user, cliente_id)
    a = db.scalars(select(ArchivoNoRenovado).where(ArchivoNoRenovado.cliente_id == c.id,
                                                   ArchivoNoRenovado.reingresado_en.is_(None))).first()
    if c.estado != "no_renovado" or a is None:
        raise HTTPException(409, "El cliente no está en No renovados")
    s = get_settings()
    return {"archivado_en": a.archivado_en, "forzar_nuevo": a.archivado_en <= restar_meses(ahora(), s.reingreso_meses),
            "reingreso_meses": s.reingreso_meses, "purga_meses": s.purga_meses,
            "se_elimina_el": restar_meses(a.archivado_en, -s.purga_meses).date()}


def _tarjeta(p: PaqueteCliente, hoy: dt.date, cms: dict[int, str], desde: dt.date, user: Usuario) -> dict:
    return {**visibilidad.paquete_visible(ciclos.paquete_out(p, hoy), user),
            "cliente_nombre": p.cliente.nombre, "cm_id": p.cliente.cm_id,
            "cm_nombre": cms.get(p.cliente.cm_id) if p.cliente.cm_id else None,
            "arrastrado": p.fecha_renovacion < desde}


@router.get("/renovaciones/tablero")
def tablero(anio: int | None = None, mes: int | None = None, quincena: str | None = None, cm_id: int | None = None,
            db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    hoy = hoy_mx()
    q = quincena or str(quincena_de(hoy))
    if q not in ("1", "2", "ambas"):
        raise HTTPException(422, "quincena debe ser '1', '2' o 'ambas'")
    per = construir_periodo(anio or hoy.year, mes or hoy.month, q, hoy)
    consulta = paquetes_q(user).where(PaqueteCliente.estado.in_(ciclos.COBRABLES), Cliente.estado == "activo",
                                      PaqueteCliente.fecha_renovacion <= per.hasta)
    if user.rol == "admin" and cm_id is not None:
        consulta = consulta.where(Cliente.cm_id == cm_id)
    paquetes = db.scalars(consulta.options(selectinload(PaqueteCliente.cliente), selectinload(PaqueteCliente.paquete),
                                           selectinload(PaqueteCliente.tipo),
                                           selectinload(PaqueteCliente.pagos))).all()
    cms = {u.id: u.nombre for u in db.scalars(select(Usuario).where(Usuario.rol == "cm"))}
    cols = {"por_vencer": [], "en_prorroga": [], "vencidos": [], "renovados_sin_pago": [], "completos": []}
    en_plazo = 0
    for p in sorted(paquetes, key=lambda p: (p.fecha_renovacion, p.id)):
        en_periodo = p.fecha_renovacion >= per.desde
        pagado = ciclos.pagado_hasta(p) >= p.costo
        if ciclos.prorroga_activa(p, hoy):
            cols["en_prorroga"].append(_tarjeta(p, hoy, cms, per.desde, user))
        elif ciclos.es_vencido(p, hoy):
            cols["vencidos"].append(_tarjeta(p, hoy, cms, per.desde, user))
        elif p.estado == "renovado" and not pagado:
            cols["renovados_sin_pago"].append(_tarjeta(p, hoy, cms, per.desde, user))
        elif not en_periodo:
            continue
        elif p.estado == "renovado" and pagado:
            cols["completos"].append(_tarjeta(p, hoy, cms, per.desde, user))
        elif ciclos.estado_efectivo(p, hoy) == "por_vencer":
            cols["por_vencer"].append(_tarjeta(p, hoy, cms, per.desde, user))
        else:
            en_plazo += 1
    return {"periodo": {"anio": per.anio, "mes": per.mes, "quincena": per.quincena, "desde": per.desde,
                        "hasta": per.hasta, "etiqueta": per.etiqueta},
            "columnas": cols, "en_plazo": en_plazo}
