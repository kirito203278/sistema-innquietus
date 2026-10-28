from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario
from app.security.jwt import InvalidTokenError, decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
                     db: Session = Depends(get_db)) -> Usuario:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No se proporcionó un token de acceso")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")
    user = db.get(Usuario, user_id)
    if user is None or not user.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inválido o dado de baja")
    return user


def require_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.rol != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta acción requiere una cuenta de administrador")
    return user


def require_admin_write(user: Usuario = Depends(require_admin)) -> Usuario:
    if user.solo_lectura:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta cuenta de administrador es de solo lectura")
    return user


def require_writer(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.rol == "admin" and user.solo_lectura:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta cuenta es de solo lectura")
    return user
