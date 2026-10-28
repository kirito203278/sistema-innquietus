from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Usuario
from app.security import rate_limit
from app.security.jwt import create_access_token
from app.security.passwords import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

_HASH_FALSO = hash_password("relleno-para-igualar-tiempos")


class LoginIn(BaseModel):
    username: str
    password: str


def usuario_out(u: Usuario) -> dict:
    return {"id": u.id, "nombre": u.nombre, "username": u.username, "rol": u.rol,
            "solo_lectura": u.solo_lectura, "activo": u.activo}


def _rate_key(request: Request, username: str) -> str:
    """Rate limit por (IP, usuario): así un tercero no puede bloquear la cuenta
    de un usuario legítimo fallando a propósito 5 veces con su username."""
    xff = request.headers.get("x-forwarded-for")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "desconocido")
    return f"{ip}|{username}"


@router.post("/login")
def login(datos: LoginIn, request: Request, db: Session = Depends(get_db)):
    username = datos.username.strip().lower()
    rate_key = _rate_key(request, username)
    if rate_limit.bloqueado(rate_key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo.")
    user = db.scalars(select(Usuario).where(Usuario.username == username)).first()
    ok = verify_password(datos.password, user.password_hash if user else _HASH_FALSO)
    if not user or not ok or not user.activo:
        rate_limit.registrar_intento_fallido(rate_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    rate_limit.limpiar_intentos(rate_key)
    token = create_access_token(user_id=user.id, rol=user.rol, solo_lectura=user.solo_lectura)
    return {"access_token": token, "token_type": "bearer", "usuario": usuario_out(user)}


@router.get("/me")
def me(user: Usuario = Depends(get_current_user)):
    return usuario_out(user)
