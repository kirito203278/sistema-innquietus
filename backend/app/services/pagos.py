import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import bitacora
from app.dates import hoy as hoy_mx
from app.models import Pago, PaqueteCliente, Usuario
from app.services import ciclos


def registrar_pago(db: Session, user: Usuario, p: PaqueteCliente, monto: Decimal, fecha: dt.date | None,
                   nota: str | None) -> Pago:
    if p.estado not in ciclos.COBRABLES:
        raise HTTPException(409, "Este paquete ya no admite pagos")
    hoy = hoy_mx()
    fecha = fecha or hoy
    if fecha > hoy:
        raise HTTPException(422, "La fecha del pago no puede ser futura")
    restante = p.costo - ciclos.pagado_hasta(p)
    if monto > restante:
        raise HTTPException(422, f"El pago excede el saldo pendiente (${restante:,.2f})")
    g = Pago(paquete_id=p.id, monto=monto, fecha=fecha, nota=nota, registrado_por=user.id)
    db.add(g)
    db.flush()
    db.refresh(p)
    ciclos.recalcular_pagada(p)
    bitacora.registrar_si_admin(db, user, "pago_por_admin", {"paquete_id": p.id, "monto": str(monto)})
    return g
