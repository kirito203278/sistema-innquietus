from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Cliente, PaqueteCliente, Usuario
from app.services import ciclos
from app.services.scope import paquetes_q


def bloqueados_del_cliente(db: Session, cliente_id: int, hoy) -> list[PaqueteCliente]:
    q = select(PaqueteCliente).where(PaqueteCliente.cliente_id == cliente_id,
                                     PaqueteCliente.estado.in_(ciclos.VIGENTES)).options(selectinload(PaqueteCliente.pagos))
    return [p for p in db.scalars(q) if ciclos.bloqueado(p, hoy)]


def exigir_libre(db: Session, cliente_id: int, hoy) -> None:
    b = bloqueados_del_cliente(db, cliente_id, hoy)
    if b:
        raise HTTPException(409, {"code": "bloqueado", "paquete_id": b[0].id,
                                  "mensaje": "La fecha de renovación de un paquete de este cliente ya pasó. Primero indica si "
                                             "renovó, no renovó o solicitó una prórroga."})


def bloqueos_visibles(db: Session, user: Usuario, hoy) -> list[PaqueteCliente]:
    q = paquetes_q(user).where(PaqueteCliente.estado.in_(ciclos.VIGENTES), Cliente.estado == "activo").options(
        selectinload(PaqueteCliente.cliente), selectinload(PaqueteCliente.paquete), selectinload(PaqueteCliente.tipo),
        selectinload(PaqueteCliente.pagos)).order_by(PaqueteCliente.fecha_renovacion, PaqueteCliente.id)
    return [p for p in db.scalars(q) if ciclos.bloqueado(p, hoy)]
