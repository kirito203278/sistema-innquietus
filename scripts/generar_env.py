#!/usr/bin/env python3
import base64
import secrets
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
destino, plantilla = RAIZ / ".env", RAIZ / ".env.example"

if destino.exists():
    sys.exit(".env ya existe; no se sobrescribe. Bórralo a mano si de verdad quieres regenerarlo.")

pg = secrets.token_urlsafe(24)
valores = {
    "POSTGRES_PASSWORD": pg,
    "JWT_SECRET": secrets.token_urlsafe(48),
    "AES_KEY_B64": base64.b64encode(secrets.token_bytes(32)).decode(),
    "JOBS_SECRET": secrets.token_urlsafe(32),
}
salida = []
for linea in plantilla.read_text(encoding="utf-8").splitlines():
    clave = linea.split("=", 1)[0]
    if clave in valores:
        linea = f"{clave}={valores[clave]}"
    elif clave == "DATABASE_URL":
        linea = linea.replace("__GENERADA__", pg)
    salida.append(linea)
destino.write_text("\n".join(salida) + "\n", encoding="utf-8")
destino.chmod(0o600)
print(f"Creado {destino} (permisos 600) con secretos nuevos.")
