import pytest
from sqlalchemy import func, select, text

from app.models import ArchivoNoRenovado, Campana, Cliente, Mensual, PaqueteCliente, Usuario
from app.security.crypto import decrypt_value, encrypt_value
from app.security.passwords import generate_secure_password, hash_password, verify_password
from app.dates import hoy
from app.seed import sembrar


def test_cifrado_aes_gcm_ida_y_vuelta_y_nonce_aleatorio():
    a, b = encrypt_value("secreto"), encrypt_value("secreto")
    assert a != b and "secreto" not in a
    assert decrypt_value(a) == decrypt_value(b) == "secreto"


def test_cifrado_detecta_manipulacion():
    token = encrypt_value("secreto")
    roto = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    with pytest.raises(Exception):
        decrypt_value(roto)


def test_contrasena_generada_18_caracteres_y_bcrypt():
    pwd = generate_secure_password()
    assert len(pwd) == 18
    assert any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and any(c.isdigit() for c in pwd)
    assert verify_password(pwd, hash_password(pwd)) and not verify_password(pwd + "x", hash_password(pwd))
    assert generate_secure_password() != pwd


def test_seed(db, tmp_path):
    cred = tmp_path / "cred.txt"
    resumen = sembrar(db, credenciales_path=cred)
    assert resumen == {"usuarios": 5, "clientes": 33, "campanas": 22}

    texto = cred.read_text()
    for u in db.scalars(select(Usuario)):
        assert u.password_hash.startswith("$2") and u.password_hash not in texto
        pwd = next(l.split("\t")[2] for l in texto.splitlines() if l.startswith(u.username + "\t"))
        assert verify_password(pwd, u.password_hash)

    c = db.scalars(select(Cliente).where(Cliente.nombre == "Panadería La Espiga")).one()
    assert "@" not in c.cuenta.correo_enc and decrypt_value(c.cuenta.correo_enc).endswith("@fb.ejemplo.test")

    assert db.scalar(select(func.count()).select_from(Cliente).where(Cliente.cm_id.is_(None))) == 1
    assert db.scalar(select(func.count()).select_from(ArchivoNoRenovado)) == 6
    multi = db.scalars(select(Cliente).where(Cliente.nombre == "Dra. Mariana Vélez")).one()
    assert len(multi.paquetes) == 1
    ic = db.scalars(select(PaqueteCliente).join(Cliente).where(Cliente.nombre == "Imprenta Central")).one()
    assert ic.restante == 1000 and ic.prorroga_hasta < hoy()

    # las campañas de ejemplo cuelgan de los MISMOS clientes (una sola ficha), ligadas a su paquete vigente
    campanas = db.scalars(select(Campana)).all()
    assert len(campanas) == 22 and all(k.cliente.estado == "activo" for k in campanas)
    assert sum(1 for k in campanas if k.estado == "vencida") == 1
    vencida = next(k for k in campanas if k.estado == "vencida")
    assert db.scalar(select(func.count()).select_from(Mensual).where(Mensual.campana_id == vencida.id)) == 1
    assert any(k.paquete_cliente_id is not None for k in campanas)

    renovados_sin_pago = [p for p in db.scalars(select(PaqueteCliente).where(PaqueteCliente.estado == "renovado"))
                          if p.restante > 0]
    nombres = {p.cliente.nombre for p in renovados_sin_pago}
    assert {"Mueblería Don Rafa", "Barbería El Corte"} <= nombres


def test_seed_se_niega_si_ya_hay_usuarios(db, tmp_path):
    sembrar(db, credenciales_path=tmp_path / "c.txt")
    with pytest.raises(RuntimeError):
        sembrar(db, credenciales_path=tmp_path / "c.txt")


def test_el_seed_deja_contrasenas_de_ejemplo_fijas(db, tmp_path):
    cred = tmp_path / "c.txt"
    sembrar(db, credenciales_path=cred)
    filas = {l.split("\t")[0]: l.split("\t")[2].strip() for l in cred.read_text().splitlines() if not l.startswith("#")}
    assert filas["admin.demo"] == "10000001" and filas["ana.ruiz"] == "10000003"
    u = db.scalars(select(Usuario).where(Usuario.username == "ana.ruiz")).one()
    assert verify_password("10000003", u.password_hash)
