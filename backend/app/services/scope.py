from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models import Campana, Cliente, Pago, PaqueteCliente, Semana, Usuario


def clientes_q(user: Usuario) -> Select:
    q = select(Cliente)
    if user.rol == "cm":
        q = q.where(Cliente.cm_id == user.id)
    return q


def paquetes_q(user: Usuario) -> Select:
    q = select(PaqueteCliente).join(Cliente, Cliente.id == PaqueteCliente.cliente_id)
    if user.rol == "cm":
        q = q.where(Cliente.cm_id == user.id)
    return q


def obtener_cliente(db: Session, user: Usuario, cliente_id: int) -> Cliente:
    c = db.scalars(clientes_q(user).where(Cliente.id == cliente_id)).first()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    return c


def obtener_paquete(db: Session, user: Usuario, paquete_id: int) -> PaqueteCliente:
    p = db.scalars(paquetes_q(user).where(PaqueteCliente.id == paquete_id)
                   .options(selectinload(PaqueteCliente.pagos))).first()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paquete no encontrado")
    return p


def obtener_pago(db: Session, user: Usuario, pago_id: int) -> Pago:
    pago = db.get(Pago, pago_id)
    if pago is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pago no encontrado")
    obtener_paquete(db, user, pago.paquete_id)
    return pago


def campanas_q(user: Usuario) -> Select:
    """Campañas visibles: un CM solo ve las de SUS clientes; el admin ve todas."""
    q = select(Campana).join(Cliente, Cliente.id == Campana.cliente_id)
    if user.rol == "cm":
        q = q.where(Cliente.cm_id == user.id)
    return q


def obtener_campana(db: Session, user: Usuario, campana_id: int) -> Campana:
    c = db.scalars(campanas_q(user).where(Campana.id == campana_id).options(
        selectinload(Campana.semanas), selectinload(Campana.cliente), selectinload(Campana.paquete_cliente))).first()
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaña no encontrada")
    return c


def obtener_semana(db: Session, user: Usuario, semana_id: int) -> Semana:
    s = db.get(Semana, semana_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Semana no encontrada")
    obtener_campana(db, user, s.campana_id)  # verifica pertenencia al CM
    return s
