import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import bitacora
from app.database import get_sessionmaker
from app.models import Usuario
from app.routers.usuarios import username_disponible
from app.security.passwords import generate_secure_password, hash_password


USO = """Uso:
  python -m app.cli crear-admin \"Nombre Apellido\"   crea un administrador con una contraseña temporal (se muestra una vez)
  python -m app.cli reset-password usuario         genera una contraseña nueva para un usuario existente"""


def crear_admin(db: Session, nombre: str) -> tuple[str, str]:
    password = generate_secure_password()
    u = Usuario(nombre=nombre.strip(), username=username_disponible(db, nombre), rol="admin", solo_lectura=False,
                password_hash=hash_password(password))
    db.add(u)
    db.flush()
    bitacora.registrar(db, None, "alta_usuario", {"usuario_id": u.id, "username": u.username, "rol": "admin", "via": "cli"})
    db.commit()
    return u.username, password


def reset_password(db: Session, username: str) -> str | None:
    u = db.scalars(select(Usuario).where(Usuario.username == username.strip().lower())).first()
    if u is None:
        return None
    password = generate_secure_password()
    u.password_hash = hash_password(password)
    u.activo = True
    bitacora.registrar(db, None, "reset_password", {"usuario_id": u.id, "username": u.username, "via": "cli"})
    db.commit()
    return password


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "crear-admin":
        with get_sessionmaker()() as db:
            usuario, password = crear_admin(db, argv[2])
        print(f"Administrador creado.\n  Usuario:    {usuario}\n  Contraseña: {password}\n"
              "Guárdala ahora: no se puede volver a mostrar.")
        return 0
    if len(argv) == 3 and argv[1] == "reset-password":
        with get_sessionmaker()() as db:
            password = reset_password(db, argv[2])
        if password is None:
            print("No existe ese usuario.")
            return 1
        print(f"Contraseña nueva para {argv[2]}: {password}\nGuárdala ahora: no se puede volver a mostrar.")
        return 0
    print(USO)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
