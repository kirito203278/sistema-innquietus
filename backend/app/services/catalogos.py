"""Validación de catálogos (paquete/tipo). Vive en la capa de servicios para
que otros servicios (p. ej. renovacion.py) no tengan que importar desde los
routers, evitando el acoplamiento service→router."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import CatalogoPaquete, CatalogoTipo


def validar_catalogos(db: Session, paquete_id: int, tipo_id: int) -> None:
    pq, tp = db.get(CatalogoPaquete, paquete_id), db.get(CatalogoTipo, tipo_id)
    if pq is None or not pq.activo:
        raise HTTPException(422, "Paquete inválido o desactivado")
    if tp is None or not tp.activo:
        raise HTTPException(422, "Tipo inválido o desactivado")
