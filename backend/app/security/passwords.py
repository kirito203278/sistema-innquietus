import secrets
import string

import bcrypt

_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_LOWER = "abcdefghijkmnopqrstuvwxyz"
_DIGITS = "23456789"
_SYMBOLS = "!@#$%&*?-_"
LONGITUD_CONTRASENA = 18
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def generate_secure_password(length: int = LONGITUD_CONTRASENA) -> str:
    length = max(length, 16)
    pools = [_UPPER, _LOWER, _DIGITS, _SYMBOLS]
    chars = [secrets.choice(p) for p in pools]
    todo = "".join(pools)
    chars += [secrets.choice(todo) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
