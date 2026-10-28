import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_NONCE_LEN = 12


def _aesgcm() -> AESGCM:
    key = base64.b64decode(get_settings().aes_key_b64)
    if len(key) != 32:
        raise RuntimeError(
            "AES_KEY_B64 debe decodificar a 32 bytes. Genera una con scripts/generar_env.py"
        )
    return AESGCM(key)


def encrypt_value(plaintext: str) -> str:
    nonce = os.urandom(_NONCE_LEN)
    return base64.b64encode(nonce + _aesgcm().encrypt(nonce, plaintext.encode("utf-8"), None)).decode()


def decrypt_value(token: str) -> str:
    raw = base64.b64decode(token)
    return _aesgcm().decrypt(raw[:_NONCE_LEN], raw[_NONCE_LEN:], None).decode("utf-8")


def huella_correo(correo: str) -> str:
    """Hash estable del correo (sin distinguir mayúsculas) para reconocer la misma cuenta sin descifrar."""
    import hashlib
    import hmac
    clave = base64.b64decode(get_settings().aes_key_b64)
    return hmac.new(clave, correo.strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()
