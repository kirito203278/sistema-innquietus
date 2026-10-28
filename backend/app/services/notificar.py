from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Cliente, Notificacion, Usuario


def destinatarios(db: Session, cliente: Cliente) -> list[int]:
    if cliente.cm_id is not None:
        cm = db.get(Usuario, cliente.cm_id)
        if cm is not None and cm.activo:
            return [cm.id]
    return list(db.scalars(select(Usuario.id).where(Usuario.rol == "admin", Usuario.activo)))


def crear(db: Session, cliente: Cliente, tipo: str, mensaje: str, dedupe_base: str, paquete_id: int | None = None,
          requiere_respuesta: bool = False) -> int:
    nuevas = 0
    for uid in destinatarios(db, cliente):
        res = db.execute(insert(Notificacion).values(
            usuario_id=uid, tipo=tipo, mensaje=mensaje, cliente_id=cliente.id, paquete_id=paquete_id,
            requiere_respuesta=requiere_respuesta, dedupe_key=f"{dedupe_base}:{uid}")
            .on_conflict_do_nothing(index_elements=["dedupe_key"]))
        nuevas += res.rowcount
    return nuevas


def marcar_leidas_de_paquete(db: Session, paquete_id: int, tipos: tuple[str, ...]) -> None:
    for n in db.scalars(select(Notificacion).where(Notificacion.paquete_id == paquete_id,
                                                   Notificacion.tipo.in_(tipos), Notificacion.leida.is_(False))):
        n.leida = True


def crear_para_usuario(db: Session, usuario_id: int, tipo: str, mensaje: str, dedupe_key: str,
                       cliente_id: int | None = None) -> int:
    """Aviso dirigido a un usuario concreto (p. ej. recordatorio de captura agrupado por CM). Sin duplicados."""
    res = db.execute(insert(Notificacion).values(
        usuario_id=usuario_id, tipo=tipo, mensaje=mensaje, cliente_id=cliente_id, dedupe_key=dedupe_key)
        .on_conflict_do_nothing(index_elements=["dedupe_key"]))
    return res.rowcount
