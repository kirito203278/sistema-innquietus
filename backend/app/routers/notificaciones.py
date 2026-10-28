from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Notificacion, Usuario

router = APIRouter(prefix="/api/notificaciones", tags=["notificaciones"])


def _out(n: Notificacion) -> dict:
    return {"id": n.id, "tipo": n.tipo, "mensaje": n.mensaje, "cliente_id": n.cliente_id, "paquete_id": n.paquete_id,
            "requiere_respuesta": n.requiere_respuesta, "respuesta": n.respuesta, "respondida_en": n.respondida_en,
            "leida": n.leida, "creado_en": n.creado_en}


def _propia(db: Session, user: Usuario, nid: int) -> Notificacion:
    n = db.get(Notificacion, nid)
    if n is None or n.usuario_id != user.id:
        raise HTTPException(404, "Notificación no encontrada")
    return n


@router.get("")
def listar(solo_no_leidas: bool = False, limite: int = 50, db: Session = Depends(get_db),
           user: Usuario = Depends(get_current_user)):
    q = select(Notificacion).where(Notificacion.usuario_id == user.id)
    if solo_no_leidas:
        q = q.where(Notificacion.leida.is_(False))
    filas = db.scalars(q.order_by(Notificacion.id.desc()).limit(min(limite, 200))).all()
    no_leidas = db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.usuario_id == user.id, Notificacion.leida.is_(False)))
    pendientes = db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.usuario_id == user.id, Notificacion.requiere_respuesta, Notificacion.respondida_en.is_(None)))
    return {"no_leidas": no_leidas, "preguntas_pendientes": pendientes, "items": [_out(n) for n in filas]}


@router.post("/leer-todas")
def leer_todas(db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    db.execute(update(Notificacion).where(Notificacion.usuario_id == user.id, Notificacion.leida.is_(False),
                                          Notificacion.requiere_respuesta.is_(False)).values(leida=True))
    db.commit()
    return {"ok": True}


@router.post("/{nid}/leer")
def leer(nid: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    n = _propia(db, user, nid)
    n.leida = True
    db.commit()
    return _out(n)
