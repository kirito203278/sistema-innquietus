"""Cuentas de Facebook compartidas entre los clientes de un mismo CM."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cliente, CuentaFb
from app.security.crypto import decrypt_value, encrypt_value, huella_correo


def _del_cm(cm_id: int | None):
    return CuentaFb.cm_id.is_(None) if cm_id is None else CuentaFb.cm_id == cm_id


def correo_de(c: Cliente) -> str | None:
    """Correo efectivo: el de su cuenta compartida o, en clientes antiguos, el propio."""
    enc = c.cuenta.correo_enc if c.cuenta else c.correo_fb_enc
    return decrypt_value(enc) if enc else None


def password_enc_de(c: Cliente) -> str | None:
    return c.cuenta.password_enc if c.cuenta else c.password_fb_enc


def asignar(db: Session, c: Cliente, correo: str | None, password: str | None = None) -> None:
    """Liga al cliente con la cuenta de ese correo (del mismo CM), creándola si no existe.

    Un correo ya usado por otro cliente del CM reutiliza la misma cuenta; si llega contraseña, se actualiza
    para todos los que la comparten. Sin correo, el cliente queda sin cuenta."""
    correo = (correo or "").strip()
    anterior = c.cuenta
    if not correo:
        c.cuenta = None
        c.correo_fb_enc = c.password_fb_enc = None
    else:
        h = huella_correo(correo)
        cuenta = db.scalars(select(CuentaFb).where(CuentaFb.huella == h, _del_cm(c.cm_id))).first()
        if cuenta is None:
            # al cambiar el correo de un cliente sin más compañeros se reutiliza su cuenta; si no, se crea otra
            pwd_previa = password_enc_de(c)
            cuenta = CuentaFb(cm_id=c.cm_id, huella=h, correo_enc=encrypt_value(correo), password_enc=pwd_previa)
            db.add(cuenta)
            db.flush()
        if password:
            cuenta.password_enc = encrypt_value(password)
        c.cuenta = cuenta
        c.correo_fb_enc = c.password_fb_enc = None
    db.flush()
    limpiar_huerfana(db, anterior)


def limpiar_huerfana(db: Session, cuenta: CuentaFb | None) -> None:
    if cuenta is not None and not db.scalars(select(Cliente.id).where(Cliente.cuenta_id == cuenta.id)).first():
        db.delete(cuenta)
        db.flush()


def compartida_con(db: Session, c: Cliente) -> list[dict]:
    if c.cuenta_id is None:
        return []
    otros = db.scalars(select(Cliente).where(Cliente.cuenta_id == c.cuenta_id, Cliente.id != c.id).order_by(Cliente.nombre))
    return [{"id": o.id, "nombre": o.nombre} for o in otros]


def del_cm(db: Session, cm_id: int | None) -> list[dict]:
    """Cuentas del CM con cuántos clientes las usan (para sugerirlas al capturar un cliente nuevo)."""
    filas = db.scalars(select(CuentaFb).where(_del_cm(cm_id)).order_by(CuentaFb.id)).all()
    out = []
    for f in filas:
        n = len(db.scalars(select(Cliente.id).where(Cliente.cuenta_id == f.id)).all())
        out.append({"id": f.id, "correo": decrypt_value(f.correo_enc), "clientes": n, "tiene_password": bool(f.password_enc)})
    return out
