from sqlalchemy.orm import Session

from app.models import Bitacora, Usuario


def registrar(db: Session, usuario: Usuario | None, accion: str, detalle: dict | None = None) -> None:
    db.add(Bitacora(usuario_id=usuario.id if usuario else None, accion=accion, detalle=detalle))


def registrar_si_admin(db: Session, usuario: Usuario, accion: str, detalle: dict | None = None) -> None:
    if usuario.rol == "admin":
        registrar(db, usuario, accion, detalle)
