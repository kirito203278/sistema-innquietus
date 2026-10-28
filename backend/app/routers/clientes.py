import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import bitacora
from app.config import get_settings
from app.database import get_db
from app.dates import hoy as hoy_mx
from app.deps import get_current_user, require_admin_write, require_writer
from app.models import (ArchivoNoRenovado, CatalogoPaquete, Cliente, PaqueteCliente, Usuario)
from app.security.crypto import decrypt_value
from app.services import bloqueo, ciclos, cuentas, rendimiento, visibilidad
from app.services import campanas as svc_campanas
from app.services.catalogos import validar_catalogos
from app.services.scope import clientes_q, obtener_cliente

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


class PaqueteNuevo(BaseModel):
    paquete_id: int
    tipo_id: int
    costo: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    fecha_inicio: dt.date | None = None


class ClienteIn(BaseModel):
    tipo_cuenta: str | None = Field(default=None, max_length=80)
    metodo_pago: str | None = Field(default=None, max_length=80)
    forma_pago: str | None = Field(default=None, max_length=80)
    nombre: str = Field(min_length=1, max_length=160)
    correo_fb: str | None = None
    password_fb: str | None = None
    correo_contacto: str | None = None
    telefono: str | None = None
    observaciones: str | None = None
    cm_id: int | None = None
    paquetes: list[PaqueteNuevo] = []


class ClientePatch(BaseModel):
    tipo_cuenta: str | None = Field(default=None, max_length=80)
    metodo_pago: str | None = Field(default=None, max_length=80)
    forma_pago: str | None = Field(default=None, max_length=80)
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    correo_fb: str | None = None
    password_fb: str | None = None
    correo_contacto: str | None = None
    telefono: str | None = None
    observaciones: str | None = None


class ReasignarIn(BaseModel):
    cm_id: int | None = None


def tipo_id_ok(datos: PaqueteNuevo) -> int:
    return datos.tipo_id


def costo_de_alta(db: Session, user: Usuario, datos: PaqueteNuevo) -> Decimal:
    if user.rol == "admin" and datos.costo is not None:
        return datos.costo
    return db.get(CatalogoPaquete, datos.paquete_id).costo


def crear_ciclo(db: Session, cliente: Cliente, datos: PaqueteNuevo, user: Usuario) -> PaqueteCliente:
    validar_catalogos(db, datos.paquete_id, datos.tipo_id)
    inicio = datos.fecha_inicio or hoy_mx()
    p = PaqueteCliente(cliente_id=cliente.id, paquete_id=datos.paquete_id, tipo_id=tipo_id_ok(datos),
                       costo=costo_de_alta(db, user, datos),
                       fecha_inicio=inicio, fecha_renovacion=inicio + dt.timedelta(days=get_settings().ciclo_dias))
    db.add(p)
    db.flush()
    return p


def _cargar(db: Session, q):
    return db.scalars(q.options(selectinload(Cliente.paquetes).selectinload(PaqueteCliente.pagos),
                                selectinload(Cliente.paquetes).selectinload(PaqueteCliente.paquete),
                                selectinload(Cliente.paquetes).selectinload(PaqueteCliente.tipo),
                                selectinload(Cliente.campanas))).all()


def _resumen(c: Cliente, hoy: dt.date, cms: dict[int, str]) -> dict:
    vig = [p for p in c.paquetes if p.estado in ciclos.VIGENTES]
    sem = min((ciclos.semaforo(p, hoy) for p in vig), key=lambda s: ciclos.ORDEN_SEMAFORO[s], default=None)
    return {"id": c.id, "nombre": c.nombre, "estado": c.estado, "cm_id": c.cm_id,
            "cm_nombre": cms.get(c.cm_id) if c.cm_id else None, "telefono": c.telefono,
            "paquetes_vigentes": len(vig), "semaforo": sem,
            "campanas_abiertas": sum(1 for k in c.campanas if k.estado in svc_campanas.ABIERTAS),
            "pendiente_decision": any(ciclos.bloqueado(p, hoy) for p in vig),
            "quincenas": sorted({ciclos.quincena_de(p.fecha_renovacion) for p in vig}),
            "proxima_renovacion": min((p.fecha_renovacion for p in vig), default=None)}


@router.get("")
def listar(quincena: int | None = Query(default=None, ge=1, le=2), estado: str = "activo", q: str | None = None,
           cm_id: int | None = None, por_reasignar: bool = False, db: Session = Depends(get_db),
           user: Usuario = Depends(get_current_user)):
    if estado not in ("activo", "no_renovado", "todos"):
        raise HTTPException(422, "estado inválido")
    consulta = clientes_q(user).order_by(Cliente.nombre)
    if estado != "todos":
        consulta = consulta.where(Cliente.estado == estado)
    if user.rol == "admin":
        if por_reasignar:
            consulta = consulta.where(Cliente.cm_id.is_(None))
        elif cm_id is not None:
            consulta = consulta.where(Cliente.cm_id == cm_id)
    if q:
        consulta = consulta.where(Cliente.nombre.ilike(f"%{q.strip()}%"))
    hoy = hoy_mx()
    cms = {u.id: u.nombre for u in db.scalars(select(Usuario).where(Usuario.rol == "cm"))}
    filas = [_resumen(c, hoy, cms) for c in _cargar(db, consulta)]
    if quincena is not None and estado == "activo":
        filas = [f for f in filas if quincena in f["quincenas"]]
    return filas


@router.post("", status_code=status.HTTP_201_CREATED)
def crear(datos: ClienteIn, db: Session = Depends(get_db), user: Usuario = Depends(require_writer)):
    if user.rol == "cm":
        cm_id = user.id
    else:
        cm_id = datos.cm_id
        if cm_id is not None:
            cm = db.get(Usuario, cm_id)
            if cm is None or cm.rol != "cm" or not cm.activo:
                raise HTTPException(422, "El CM indicado no existe o está dado de baja")
    if len(datos.paquetes) > 1:
        raise HTTPException(422, "Un cliente tiene un solo paquete")
    c = Cliente(cm_id=cm_id, nombre=datos.nombre.strip(), correo_contacto=datos.correo_contacto,
                tipo_cuenta=datos.tipo_cuenta, metodo_pago=datos.metodo_pago, forma_pago=datos.forma_pago,
                telefono=datos.telefono, observaciones=datos.observaciones)
    db.add(c)
    db.flush()
    if datos.correo_fb:
        cuentas.asignar(db, c, datos.correo_fb, datos.password_fb)
    for pq in datos.paquetes:
        crear_ciclo(db, c, pq, user)
    if user.rol == "admin":
        bitacora.registrar(db, user, "alta_cliente_admin", {"cliente_id": c.id, "cm_id": cm_id})
    db.commit()
    return {"id": c.id}


def password_enc_de_plano(c: Cliente) -> str | None:
    enc = cuentas.password_enc_de(c)
    return decrypt_value(enc) if enc else None


def ficha_out(c: Cliente, hoy: dt.date, db: Session, user: Usuario | None = None) -> dict:
    ordenados = sorted(c.paquetes, key=lambda p: (p.fecha_renovacion, p.id), reverse=True)
    vigentes = [ciclos.paquete_out(p, hoy) for p in sorted(c.paquetes, key=lambda p: p.fecha_renovacion)
                if p.estado in ciclos.VIGENTES]
    historial = [ciclos.paquete_out(p, hoy) for p in ordenados if p.estado not in ciclos.VIGENTES
                 and p.estado != "eliminado"]
    archivo = db.scalars(select(ArchivoNoRenovado).where(ArchivoNoRenovado.cliente_id == c.id,
                                                         ArchivoNoRenovado.reingresado_en.is_(None))).first()
    umbrales = rendimiento.cargar_umbrales(db)
    return {"id": c.id, "nombre": c.nombre, "estado": c.estado, "cm_id": c.cm_id,
            "correo_fb": cuentas.correo_de(c),
            "tiene_password_fb": bool(cuentas.password_enc_de(c)),
            "cuenta_compartida_con": cuentas.compartida_con(db, c),
            "correo_contacto": c.correo_contacto, "telefono": c.telefono, "observaciones": c.observaciones,
            "tipo_cuenta": c.tipo_cuenta, "metodo_pago": c.metodo_pago, "forma_pago": c.forma_pago,
            "campanas": [svc_campanas.campana_out(k, umbrales, hoy) for k in c.campanas],
            "paquetes": vigentes if user is None else visibilidad.paquetes_visibles(vigentes, user),
            "historial": historial if user is None else visibilidad.paquetes_visibles(historial, user),
            "no_renovado_desde": archivo.archivado_en if archivo else None}


@router.get("/cuentas-fb")
def mis_cuentas(cm_id: int | None = None, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    """Cuentas de Facebook ya registradas por el CM, para reutilizarlas al dar de alta otro cliente."""
    return cuentas.del_cm(db, user.id if user.rol == "cm" else cm_id)


@router.get("/{cliente_id}")
def ficha(cliente_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    c = obtener_cliente(db, user, cliente_id)
    return ficha_out(c, hoy_mx(), db, user)


@router.patch("/{cliente_id}")
def editar(cliente_id: int, datos: ClientePatch, db: Session = Depends(get_db),
           user: Usuario = Depends(require_writer)):
    c = obtener_cliente(db, user, cliente_id)
    bloqueo.exigir_libre(db, c.id, hoy_mx())
    campos = datos.model_dump(exclude_unset=True)
    if "nombre" in campos and campos["nombre"]:
        c.nombre = campos["nombre"].strip()
    for k in ("correo_contacto", "telefono", "observaciones", "tipo_cuenta", "metodo_pago", "forma_pago"):
        if k in campos:
            setattr(c, k, campos[k] or None)
    if "correo_fb" in campos or campos.get("password_fb"):
        correo = campos["correo_fb"] if "correo_fb" in campos else cuentas.correo_de(c)
        if campos.get("password_fb") and not (correo or "").strip():
            raise HTTPException(422, "Escribe el correo de Facebook: la contraseña se guarda en esa cuenta")
        cuentas.asignar(db, c, correo, campos.get("password_fb"))
    if user.rol == "admin":
        bitacora.registrar(db, user, "editar_cliente_admin", {"cliente_id": c.id, "campos": sorted(campos)})
    db.commit()
    return ficha_out(c, hoy_mx(), db, user)


@router.post("/{cliente_id}/password-fb/ver")
def ver_password(cliente_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    c = obtener_cliente(db, user, cliente_id)
    pwd = cuentas.password_enc_de(c)
    if not pwd:
        raise HTTPException(404, "El cliente no tiene contraseña de Facebook guardada")
    bitacora.registrar(db, user, "ver_password_fb", {"cliente_id": c.id})
    db.commit()
    return {"password": decrypt_value(pwd)}


@router.delete("/{cliente_id}")
def eliminar(cliente_id: int, confirmar_nombre: str, db: Session = Depends(get_db),
             user: Usuario = Depends(require_admin_write)):
    c = obtener_cliente(db, user, cliente_id)
    if c.estado != "no_renovado":
        raise HTTPException(409, "Solo se eliminan clientes que están en No renovados. Si ya no sigue, márcalo "
                                 "como «no renovó» y después elimínalo desde No renovados.")
    bloqueo.exigir_libre(db, c.id, hoy_mx())
    if confirmar_nombre != c.nombre:
        raise HTTPException(422, "El nombre escrito no coincide con el del cliente")
    bitacora.registrar(db, user, "borrar_cliente", {"cliente_id": c.id, "nombre": c.nombre, "cm_id": c.cm_id})
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/{cliente_id}/reasignar")
def reasignar(cliente_id: int, datos: ReasignarIn, db: Session = Depends(get_db),
              admin: Usuario = Depends(require_admin_write)):
    c = obtener_cliente(db, admin, cliente_id)
    if datos.cm_id is not None:
        cm = db.get(Usuario, datos.cm_id)
        if cm is None or cm.rol != "cm" or not cm.activo:
            raise HTTPException(422, "El CM destino no existe o está dado de baja")
    anterior = c.cm_id
    correo, pwd = cuentas.correo_de(c), password_enc_de_plano(c)
    c.cm_id = datos.cm_id
    if correo:   # la cuenta compartida es del CM: el cliente se lleva su acceso a la cuenta del CM nuevo
        cuentas.asignar(db, c, correo, pwd)
    for a in db.scalars(select(ArchivoNoRenovado).where(ArchivoNoRenovado.cliente_id == c.id)):
        a.cm_id = datos.cm_id
    bitacora.registrar(db, admin, "reasignar_cliente", {"cliente_id": c.id, "de": anterior, "a": datos.cm_id})
    db.commit()
    return {"ok": True}
