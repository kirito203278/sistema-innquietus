"""Módulo de campañas. Un solo conjunto de endpoints para CM y admin:
el alcance (un CM solo ve las campañas de SUS clientes) lo da services/scope.py,
igual que en el resto de la plataforma, y las escrituras respetan la «ventana de
decisión» del cliente (si su contrato terminó sin decidir, el cliente está en pausa).
"""
import datetime as dt
import io
import re
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import bitacora
from app.database import get_db
from app.dates import ahora, hoy as hoy_mx
from app.deps import get_current_user, require_admin_write, require_writer
from app.models import Campana, Cliente, Mensual, MetricaConfig, Observacion, Usuario
from app.reports.campanas_mensual import generar_pdf_reporte_mensual
from app.reports.campanas_semanal import generar_pdf_reporte_semanal
from app.services import bloqueo, campanas as svc, consolidacion, notificar, rendimiento
from app.services import semanas as cal
from app.services.scope import campanas_q, obtener_campana, obtener_cliente, obtener_semana

router = APIRouter(prefix="/api", tags=["campanas"])

Tipo = Literal["local", "nacional", "otro"]
Esquema = Literal["mensual", "semanal", "diario"]


class CampanaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    tipo: Tipo
    presupuesto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    presupuesto_esquema: Esquema = "mensual"
    formato_post: bool = False
    formato_3d: bool = False
    formato_boton: bool = False
    formato_otro: bool = False
    lugar: str | None = Field(default=None, max_length=200)
    fecha_inicio: dt.date | None = None
    fecha_renovacion: dt.date | None = None
    paquete_cliente_id: int | None = None


class SemanaIn(BaseModel):
    mensajes: int = Field(ge=0)
    costo_por_resultado: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    importe_gastado: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class ObservacionIn(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)


class MensualManualIn(BaseModel):
    periodo_inicio: dt.date
    periodo_fin: dt.date
    mensajes_total: int = Field(ge=0)
    gasto_total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class RenovarIn(BaseModel):
    fecha_renovacion: dt.date


class CerrarIn(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


class MetricaPatch(BaseModel):
    umbral_bueno: Decimal | None = Field(default=None, ge=0)
    umbral_regular: Decimal | None = Field(default=None, ge=0)
    caida_mensajes_alerta_pct: Decimal | None = Field(default=None, ge=0, le=100)


def _cms(db: Session) -> dict[int, str]:
    return {u.id: u.nombre for u in db.scalars(select(Usuario).where(Usuario.rol == "cm"))}


def _detalle(db: Session, c: Campana, user: Usuario) -> dict:
    out = svc.campana_out(c, rendimiento.cargar_umbrales(db), hoy_mx(), _cms(db))
    out["cliente_bloqueado"] = bool(bloqueo.bloqueados_del_cliente(db, c.cliente_id, hoy_mx()))
    return out


def _libre(db: Session, c: Campana) -> None:
    bloqueo.exigir_libre(db, c.cliente_id, hoy_mx())


# ------------------------------------------------------------------ campañas
@router.get("/campanas")
def listar(cliente_id: int | None = None, cm_id: int | None = None, q: str | None = None,
           estado: Literal["abiertas", "activa", "vencida", "cerrada", "todas"] = "abiertas",
           db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    consulta = campanas_q(user).options(
        selectinload(Campana.semanas), selectinload(Campana.cliente), selectinload(Campana.paquete_cliente))
    if cliente_id is not None:
        consulta = consulta.where(Campana.cliente_id == cliente_id)
    if estado == "abiertas":
        consulta = consulta.where(Campana.estado.in_(svc.ABIERTAS))
    elif estado != "todas":
        consulta = consulta.where(Campana.estado == estado)
    if user.rol == "admin" and cm_id is not None:
        consulta = consulta.where(Cliente.cm_id == cm_id)
    if q:
        consulta = consulta.where(Campana.nombre.ilike(f"%{q.strip()}%"))
    umbrales, hoy, cms = rendimiento.cargar_umbrales(db), hoy_mx(), _cms(db)
    filas = [svc.campana_out(c, umbrales, hoy, cms) for c in db.scalars(consulta).all()]
    return sorted(filas, key=lambda f: (f["cliente_nombre"].lower(), f["nombre"].lower()))


@router.post("/clientes/{cliente_id}/campanas", status_code=201)
def crear(cliente_id: int, datos: CampanaIn, db: Session = Depends(get_db), user: Usuario = Depends(require_writer)):
    cliente = obtener_cliente(db, user, cliente_id)
    bloqueo.exigir_libre(db, cliente.id, hoy_mx())
    c = svc.crear_campana(db, user, cliente, datos.model_dump())
    db.commit()
    return _detalle(db, obtener_campana(db, user, c.id), user)


@router.get("/campanas/{campana_id}")
def detalle(campana_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    return _detalle(db, obtener_campana(db, user, campana_id), user)


@router.post("/campanas/{campana_id}/renovar")
def renovar(campana_id: int, datos: RenovarIn, db: Session = Depends(get_db), user: Usuario = Depends(require_writer)):
    c = obtener_campana(db, user, campana_id)
    _libre(db, c)
    svc.renovar_campana(db, user, c, datos.fecha_renovacion)
    db.commit()
    return _detalle(db, obtener_campana(db, user, campana_id), user)


@router.post("/campanas/{campana_id}/cerrar")
def cerrar(campana_id: int, datos: CerrarIn, db: Session = Depends(get_db), user: Usuario = Depends(require_writer)):
    c = obtener_campana(db, user, campana_id)
    svc.cerrar_campana(db, user, c, datos.motivo)
    db.commit()
    return _detalle(db, obtener_campana(db, user, campana_id), user)


# ------------------------------------------------------------- captura semanal
@router.get("/campanas/{campana_id}/semanas")
def semanas(campana_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    c = obtener_campana(db, user, campana_id)
    return svc.semanas_out(c, rendimiento.cargar_umbrales(db), hoy_mx(), ahora())


@router.put("/semanas/{semana_id}")
def capturar(semana_id: int, datos: SemanaIn, db: Session = Depends(get_db), user: Usuario = Depends(require_writer)):
    s = obtener_semana(db, user, semana_id)
    c = obtener_campana(db, user, s.campana_id)
    if c.estado != "activa":
        raise HTTPException(403, "Esta campaña no está activa; resuelve primero su renovación")
    _libre(db, c)
    svc.capturar_semana(db, user, s, datos.mensajes, datos.costo_por_resultado, datos.importe_gastado)
    db.commit()
    c = obtener_campana(db, user, c.id)
    return next(x for x in svc.semanas_out(c, rendimiento.cargar_umbrales(db), hoy_mx(), ahora()) if x["id"] == semana_id)


@router.post("/semanas/{semana_id}/habilitar-edicion")
def habilitar_edicion(semana_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(require_admin_write)):
    """El admin le da al CM 2 horas para corregir una semana ya cerrada (con aviso y bitácora)."""
    s = obtener_semana(db, admin, semana_id)
    if cal.semana_editable(s, hoy_mx()):
        raise HTTPException(400, "Esta semana está abierta: no necesita un permiso especial")
    if not cal.en_ventana_habilitacion(ahora()):
        raise HTTPException(400, "Fuera de la ventana permitida para habilitar ediciones (sábado 8:00 a viernes 15:00)")
    c = obtener_campana(db, admin, s.campana_id)
    s.edicion_habilitada_hasta = ahora() + dt.timedelta(hours=2)
    notificar.crear(db, c.cliente, "sistema",
                    f"Un administrador habilitó por 2 horas la edición de la semana del {s.inicio:%d/%m/%Y} al "
                    f"{s.fin:%d/%m/%Y} de «{c.nombre}» ({c.cliente.nombre}).", f"habilitar:{s.id}:{s.edicion_habilitada_hasta:%Y%m%d%H%M}")
    bitacora.registrar(db, admin, "habilitar_edicion_semana", {"semana_id": s.id, "campana_id": c.id})
    db.commit()
    return {"ok": True, "permiso_hasta": s.edicion_habilitada_hasta}


# --------------------------------------------------------------- observaciones
@router.get("/campanas/{campana_id}/observaciones")
def observaciones(campana_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    obtener_campana(db, user, campana_id)
    filas = db.scalars(select(Observacion).where(Observacion.campana_id == campana_id).order_by(Observacion.creado_en.desc()))
    nombres = {u.id: u.nombre for u in db.scalars(select(Usuario))}
    return [{"id": o.id, "texto": o.texto, "autor": nombres.get(o.autor_id), "creado_en": o.creado_en} for o in filas]


@router.post("/campanas/{campana_id}/observaciones", status_code=201)
def agregar_observacion(campana_id: int, datos: ObservacionIn, db: Session = Depends(get_db),
                        user: Usuario = Depends(require_writer)):
    c = obtener_campana(db, user, campana_id)
    if c.estado != "activa":
        raise HTTPException(403, "Esta campaña no está activa; resuelve primero su renovación")
    _libre(db, c)
    o = Observacion(campana_id=c.id, texto=datos.texto.strip(), autor_id=user.id)
    db.add(o)
    db.commit()
    return {"id": o.id, "texto": o.texto, "autor": user.nombre, "creado_en": o.creado_en}


# ------------------------------------------------------------------- mensuales
@router.get("/campanas/{campana_id}/mensuales")
def mensuales(campana_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    obtener_campana(db, user, campana_id)
    limite = 2 if user.rol == "cm" else 3  # comparativo: 2 meses para el CM, 3 para el admin
    filas = db.scalars(select(Mensual).where(Mensual.campana_id == campana_id)
                       .order_by(Mensual.periodo_inicio.desc()).limit(limite))
    return [svc.mensual_out(m) for m in filas]


@router.post("/campanas/{campana_id}/mensuales/manual", status_code=201)
def mensual_manual(campana_id: int, datos: MensualManualIn, db: Session = Depends(get_db),
                   user: Usuario = Depends(require_writer)):
    """El mensual del mes anterior a que la campaña entrara al sistema se captura a mano, una sola vez."""
    c = obtener_campana(db, user, campana_id)
    if datos.periodo_fin < datos.periodo_inicio:
        raise HTTPException(422, "El periodo termina antes de empezar")
    if db.scalars(select(Mensual).where(Mensual.campana_id == c.id)).first() is not None:
        raise HTTPException(409, "Esta campaña ya tiene un mensual registrado; la captura manual solo aplica una vez")
    gasto = datos.gasto_total
    costo = (gasto / datos.mensajes_total) if datos.mensajes_total else Decimal(0)
    cfg = rendimiento.buscar_umbral(rendimiento.cargar_umbrales(db), c.tipo, svc.nombre_paquete(c))
    m = Mensual(campana_id=c.id, periodo_inicio=datos.periodo_inicio, periodo_fin=datos.periodo_fin,
                mensajes_total=datos.mensajes_total, gasto_total=gasto, costo_por_mensaje=costo.quantize(Decimal("0.01")),
                presupuesto=c.presupuesto, sobrante=(c.presupuesto - gasto),
                rendimiento=rendimiento.nivel_ciclo(cfg, float(costo), []), origen="manual")
    db.add(m)
    bitacora.registrar(db, user, "mensual_manual", {"campana_id": c.id})
    db.commit()
    return svc.mensual_out(m)


# ---------------------------------------------- consolidado y reportes por cliente
@router.get("/clientes/{cliente_id}/campanas/consolidado")
def consolidado(cliente_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    cliente = obtener_cliente(db, user, cliente_id)
    return {"semanas": [vars(s) for s in consolidacion.semanas_consolidadas(db, cliente)],
            "mensuales": [vars(m) for m in consolidacion.mensuales_consolidados(db, cliente, limite=3)]}


def _pdf(contenido: bytes, nombre: str) -> Response:
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


@router.get("/clientes/{cliente_id}/campanas/reporte-mensual")
def reporte_mensual(cliente_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    cliente = obtener_cliente(db, user, cliente_id)
    meses = consolidacion.mensuales_consolidados(db, cliente, limite=3)
    if not meses:
        raise HTTPException(404, "Este cliente todavía no tiene ningún mes cerrado para reportar")
    buf = io.BytesIO()
    generar_pdf_reporte_mensual(cliente.nombre, [c.nombre for c in cliente.campanas], meses, buf)
    periodo = meses[0].periodo_inicio.strftime("%Y-%m")
    bitacora.registrar(db, user, "generar_reporte_mensual", {"cliente_id": cliente.id, "periodo": periodo})
    db.commit()
    return _pdf(buf.getvalue(), f"reporte-{_slug(cliente.nombre)}-{periodo}.pdf")


@router.get("/clientes/{cliente_id}/campanas/reporte-semanal")
def reporte_semanal(cliente_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    cliente = obtener_cliente(db, user, cliente_id)
    con_datos = [s for s in consolidacion.semanas_consolidadas(db, cliente) if s.mensajes > 0 or s.importe_gastado > 0]
    if not con_datos:
        raise HTTPException(404, "Este cliente todavía no tiene ninguna semana capturada para reportar")
    buf = io.BytesIO()
    generar_pdf_reporte_semanal(cliente.nombre, [c.nombre for c in cliente.campanas], con_datos, buf)
    periodo = con_datos[-1].inicio.strftime("%Y-%m-%d")
    bitacora.registrar(db, user, "generar_reporte_semanal", {"cliente_id": cliente.id, "periodo": periodo})
    db.commit()
    return _pdf(buf.getvalue(), f"reporte-semanal-{_slug(cliente.nombre)}-{periodo}.pdf")


# ------------------------------------------------------- umbrales del semáforo
@router.get("/metricas")
def listar_metricas(db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    return [{"id": m.id, "tipo": m.tipo, "paquete": m.paquete, "umbral_bueno": float(m.umbral_bueno),
             "umbral_regular": float(m.umbral_regular), "caida_mensajes_alerta_pct": float(m.caida_mensajes_alerta_pct)}
            for m in db.scalars(select(MetricaConfig).where(MetricaConfig.activo).order_by(MetricaConfig.tipo))]


@router.patch("/metricas/{metrica_id}")
def editar_metrica(metrica_id: int, datos: MetricaPatch, db: Session = Depends(get_db),
                   admin: Usuario = Depends(require_admin_write)):
    m = db.get(MetricaConfig, metrica_id)
    if m is None:
        raise HTTPException(404, "Umbral no encontrado")
    cambios = datos.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in cambios.items():
        setattr(m, k, v)
    if m.umbral_regular < m.umbral_bueno:
        raise HTTPException(422, "El umbral «regular» no puede ser menor que el «bueno»")
    m.actualizado_en = ahora()
    bitacora.registrar(db, admin, "editar_metrica", {"metrica_id": m.id, "cambios": {k: str(v) for k, v in cambios.items()}})
    db.commit()
    return {"ok": True}
