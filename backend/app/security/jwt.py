import datetime as dt

import jwt

from app.config import get_settings


class InvalidTokenError(Exception):
    pass


def create_access_token(*, user_id: int, rol: str, solo_lectura: bool) -> str:
    s = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": str(user_id), "rol": rol, "solo_lectura": solo_lectura, "iat": now,
               "exp": now + dt.timedelta(minutes=s.jwt_expire_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
