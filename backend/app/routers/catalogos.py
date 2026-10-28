from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import bitacora
from app.database import get_db
from app.deps import get_current_user, require_admin_write
from app.models import CatalogoPaquete, CatalogoTipo, Usuario

router = APIRouter(prefix="/api/catalogos", tags=["catalogos"])
TABLAS = {"paquetes": CatalogoPaquete, "tipos": CatalogoTipo}


class ItemIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    orden: int | None = None
    costo: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


class ItemPatch(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    orden: int | None = None
    activo: bool | None = None
    costo: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)


def _modelo(tabla: str):
    if tabla not in TABLAS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catálogo no encontrado")
    return TABLAS[tabla]


def _out(i) -> dict:
    datos = {"id": i.id, "nombre": i.nombre, "orden": i.orden, "activo": i.activo}
    if isinstance(i, CatalogoPaquete):
        datos["costo"] = i.costo
    return datos


def _log(i) -> dict:
    d = _out(i)
    if "costo" in d:
        d["costo"] = str(d["costo"])
    return d


@router.get("/{tabla}")
def listar(tabla: str, todos: bool = False, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    M = _modelo(tabla)
    q = select(M).order_by(M.orden, M.id)
    if not (todos and user.rol == "admin"):
        q = q.where(M.activo)
    return [_out(i) for i in db.scalars(q)]


@router.post("/{tabla}", status_code=status.HTTP_201_CREATED)
def crear(tabla: str, datos: ItemIn, db: Session = Depends(get_db), admin: Usuario = Depends(require_admin_write)):
    M = _modelo(tabla)
    orden = datos.orden if datos.orden is not None else (db.scalar(select(func.coalesce(func.max(M.orden), 0))) + 1)
    item = M(nombre=datos.nombre.strip(), orden=orden)
    if M is CatalogoPaquete and datos.costo is not None:
        item.costo = datos.costo
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un elemento con ese nombre")
    bitacora.registrar(db, admin, "editar_catalogo", {"catalogo": tabla, "accion": "alta", "nombre": item.nombre})
    db.commit()
    return _out(item)


@router.patch("/{tabla}/{item_id}")
def editar(tabla: str, item_id: int, datos: ItemPatch, db: Session = Depends(get_db),
           admin: Usuario = Depends(require_admin_write)):
    M = _modelo(tabla)
    item = db.get(M, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Elemento no encontrado")
    antes = _log(item)
    campos = datos.model_dump(exclude_none=True)
    if M is not CatalogoPaquete:
        campos.pop("costo", None)
    for campo, valor in campos.items():
        setattr(item, campo, valor.strip() if isinstance(valor, str) else valor)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un elemento con ese nombre")
    bitacora.registrar(db, admin, "editar_catalogo", {"catalogo": tabla, "accion": "edicion", "antes": antes,
                                                      "despues": _log(item)})
    db.commit()
    return _out(item)
