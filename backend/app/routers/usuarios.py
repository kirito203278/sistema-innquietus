import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import bitacora
from app.database import get_db
from app.deps import require_admin, require_admin_write
from app.models import ArchivoNoRenovado, Cliente, Notificacion, Usuario
from app.routers.auth import usuario_out
from app.security.passwords import hash_password

router = APIRouter(prefix="/api/usuarios", tags=["equipo"])


def _password_valida(v: str) -> str:
    if len(v) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    if len(v.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede pasar de 72 caracteres")
    if v != v.strip():
        raise ValueError("La contraseña no puede empezar ni terminar con espacios")
    return v


class AltaIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    rol: str = Field(pattern="^(cm|admin)$")
    solo_lectura: bool = False
    password: str

    _val = field_validator("password")(_password_valida)


class ResetIn(BaseModel):
    password: str

    _val = field_validator("password")(_password_valida)


class BajaIn(BaseModel):
    migrar_a_cm_id: int | None = None


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def username_disponible(db: Session, nombre: str) -> str:
    partes = [_slug(p) for p in nombre.split() if _slug(p)]
    if not partes:
        raise HTTPException(422, "El nombre no genera un usuario válido")
    base = ".".join([partes[0], partes[1]]) if len(partes) > 1 else partes[0]
    candidato, n = base, 1
    while db.scalar(select(Usuario.id).where(Usuario.username == candidato)):
        n += 1
        candidato = f"{base}{n}"
    return candidato


def _cm_activo(db: Session, cm_id: int) -> Usuario:
    cm = db.get(Usuario, cm_id)
    if cm is None or cm.rol != "cm" or not cm.activo:
        raise HTTPException(422, "El CM destino no existe o está dado de baja")
    return cm


@router.get("")
def listar(db: Session = Depends(get_db), _=Depends(require_admin)):
    conteo = dict(db.execute(select(Cliente.cm_id, func.count()).where(Cliente.estado == "activo")
                             .group_by(Cliente.cm_id)).all())
    no_ren = dict(db.execute(select(Cliente.cm_id, func.count()).where(Cliente.estado == "no_renovado")
                             .group_by(Cliente.cm_id)).all())
    usuarios = db.scalars(select(Usuario).order_by(Usuario.activo.desc(), Usuario.rol, Usuario.nombre)).all()
    return [{**usuario_out(u), "creado_en": u.creado_en, "clientes_activos": conteo.get(u.id, 0),
             "clientes_no_renovados": no_ren.get(u.id, 0)} for u in usuarios]


@router.post("", status_code=status.HTTP_201_CREATED)
def alta(datos: AltaIn, db: Session = Depends(get_db), admin: Usuario = Depends(require_admin_write)):
    if datos.rol == "cm" and datos.solo_lectura:
        raise HTTPException(422, "Solo un administrador puede ser de solo lectura")
    u = Usuario(nombre=datos.nombre.strip(), username=username_disponible(db, datos.nombre), rol=datos.rol,
                solo_lectura=datos.solo_lectura, password_hash=hash_password(datos.password))
    db.add(u)
    db.flush()
    bitacora.registrar(db, admin, "alta_usuario", {"usuario_id": u.id, "username": u.username, "rol": u.rol,
                                                   "solo_lectura": u.solo_lectura})
    db.commit()
    return usuario_out(u)


@router.post("/{usuario_id}/reset-password")
def reset_password(usuario_id: int, datos: ResetIn, db: Session = Depends(get_db),
                   admin: Usuario = Depends(require_admin_write)):
    u = db.get(Usuario, usuario_id)
    if u is None or not u.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    u.password_hash = hash_password(datos.password)
    bitacora.registrar(db, admin, "reset_password", {"usuario_id": u.id, "username": u.username})
    db.commit()
    return {"username": u.username}


@router.post("/{usuario_id}/baja")
def baja(usuario_id: int, datos: BajaIn, db: Session = Depends(get_db),
         admin: Usuario = Depends(require_admin_write)):
    u = db.get(Usuario, usuario_id)
    if u is None or not u.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    if u.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No puedes darte de baja a ti mismo")

    migrados = 0
    if u.rol == "admin":
        otros = db.scalar(select(func.count()).select_from(Usuario).where(
            Usuario.rol == "admin", Usuario.activo, Usuario.solo_lectura.is_(False), Usuario.id != u.id))
        if not u.solo_lectura and otros == 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "Debe quedar al menos un administrador con escritura")
    else:
        clientes = db.scalars(select(Cliente.id).where(Cliente.cm_id == u.id)).all()
        if clientes:
            if datos.migrar_a_cm_id is None:
                raise HTTPException(status.HTTP_409_CONFLICT, {
                    "code": "requiere_destino", "clientes": len(clientes),
                    "mensaje": "El CM todavía tiene clientes: elige a qué CM pasan todos. Si quieres repartirlos "
                               "entre varios, reasígnalos antes desde Cartera y vuelve aquí."})
            destino = _cm_activo(db, datos.migrar_a_cm_id)
            if destino.id == u.id:
                raise HTTPException(422, "El destino no puede ser el mismo CM")
            nuevo_id = destino.id
            db.execute(update(Cliente).where(Cliente.id.in_(clientes)).values(cm_id=nuevo_id))
            db.execute(update(ArchivoNoRenovado).where(ArchivoNoRenovado.cliente_id.in_(clientes))
                       .values(cm_id=nuevo_id))
            if nuevo_id is not None:
                db.execute(update(Notificacion).where(
                    Notificacion.usuario_id == u.id, Notificacion.cliente_id.in_(clientes),
                    Notificacion.requiere_respuesta, Notificacion.respondida_en.is_(None))
                    .values(usuario_id=nuevo_id))
            migrados = len(clientes)
    u.activo = False
    bitacora.registrar(db, admin, "baja_usuario", {
        "usuario_id": u.id, "username": u.username, "rol": u.rol, "clientes_migrados": migrados,
        "destino_cm_id": datos.migrar_a_cm_id})
    db.commit()
    return {"ok": True, "clientes_migrados": migrados}
