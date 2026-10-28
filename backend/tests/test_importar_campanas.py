"""Importador de datos del sistema de Campañas antiguo (migración a la plataforma unificada)."""
import base64
import datetime as dt
import os
import uuid
from decimal import Decimal
from pathlib import Path

import psycopg2
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select

from app.migracion.importar_campanas import importar
from app.models import ArchivoNoRenovado, Campana, Cliente, Mensual, Observacion, Semana, Usuario
from app.security.crypto import decrypt_value

ESQUEMA = (Path(__file__).parent / "fixtures" / "campanas_legacy_schema.sql").read_text(encoding="utf-8")
CLAVE_ANTIGUA = AESGCM.generate_key(256)
CLAVE_B64 = base64.b64encode(CLAVE_ANTIGUA).decode()
D = dt.date


def _cifrar(texto: str) -> str:
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(CLAVE_ANTIGUA).encrypt(nonce, texto.encode(), None)).decode()


@pytest.fixture
def origen(test_db_url):
    """Base temporal con el esquema ANTIGUO de Campañas y datos de ejemplo."""
    server, _, _ = test_db_url.rpartition("/")
    nombre = f"camp_legacy_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(f"{server}/postgres")
    admin.autocommit = True
    admin.cursor().execute(f'CREATE DATABASE "{nombre}"')
    con = psycopg2.connect(f"{server}/{nombre}")
    cur = con.cursor()
    cur.execute(ESQUEMA)
    cur.execute("INSERT INTO usuarios (id,nombre,username,password_hash,rol) VALUES "
                "(1,'Ana Ruiz','ana.ruiz','$2b$hash-ana','cm'),(2,'Luz Nueva','luz.nueva','$2b$hash-luz','cm')")
    cur.execute("INSERT INTO cuentas_publicitarias (id,usuario_enc,password_enc,huella) VALUES (1,%s,%s,'h1')",
                (_cifrar("cafe@fb.test"), _cifrar("Secreta-123")))
    cur.execute("INSERT INTO clientes (id,cm_id,cuenta_id,nombre,estado,metodo_pago) VALUES "
                "(1,1,1,'Café Acento','activo','Tarjeta'),(2,2,NULL,'Tienda Nueva','activo',NULL),(3,1,NULL,'Cliente Viejo','no_renovado',NULL)")
    cur.execute("INSERT INTO archivo_no_renovados (cliente_id,cm_id,motivo) VALUES (3,1,'Ya no pauta')")
    cur.execute("INSERT INTO campanas (id,cliente_id,nombre,tipo,presupuesto,fecha_inicio,fecha_renovacion,estado) VALUES "
                "(1,1,'LOCAL ADV','local',3500,'2026-10-01','2026-10-31','activa'),"
                "(2,2,'PROMO','nacional',2000,'2026-08-01','2026-08-31','vencida'),"
                "(3,3,'VIEJA','local',1000,'2026-05-01','2026-05-31','vencida')")
    cur.execute("INSERT INTO semanas (campana_id,inicio,fin,mensajes,costo_por_resultado,importe_gastado,editable,capturado_por) VALUES "
                "(1,'2026-09-26','2026-10-02',80,12.5,1000,false,1),(1,'2026-10-03','2026-10-09',NULL,NULL,NULL,true,NULL)")
    cur.execute("INSERT INTO observaciones (campana_id,texto,autor_id) VALUES (1,'Subir presupuesto',1)")
    cur.execute("INSERT INTO mensuales (campana_id,periodo_inicio,periodo_fin,mensajes_total,gasto_total,costo_por_mensaje,presupuesto,sobrante,rendimiento,origen) VALUES "
                "(1,'2026-08-30','2026-09-29',246,3081.24,12.53,3500,418.76,'bueno','manual'),"
                "(2,'2026-08-01','2026-08-31',100,2500,25,2000,-500,'regular','calculado')")
    con.commit()
    con.close()
    yield f"postgresql+psycopg2://{server.split('://', 1)[1]}/{nombre}"
    admin.cursor().execute(f'DROP DATABASE "{nombre}" WITH (FORCE)')
    admin.close()


@pytest.fixture
def destino(db, crear_usuario, fabrica):
    ana = crear_usuario("ana.ruiz")                      # ya existe en la plataforma
    cafe = fabrica.cliente(ana, "CAFÉ acento")           # el mismo cliente, escrito distinto: debe emparejarse
    fabrica.ciclo(cafe, D(2026, 10, 20), costo=2500)
    return ana, cafe


def test_la_simulacion_no_guarda_nada(db, origen, destino):
    r = importar(db, origen, CLAVE_B64, aplicar=False)
    assert r.campanas_importadas == 3
    assert db.scalar(select(func.count()).select_from(Campana)) == 0
    assert db.scalars(select(Usuario).where(Usuario.username == "luz.nueva")).first() is None


def test_une_en_una_sola_ficha_los_clientes_que_existian_en_ambos_sistemas(db, origen, destino):
    ana, cafe = destino
    r = importar(db, origen, CLAVE_B64, aplicar=True)
    assert (r.usuarios_coincidentes, r.usuarios_creados) == (1, 1)
    assert (r.clientes_coincidentes, r.clientes_creados) == (1, 2)
    assert db.scalar(select(func.count()).select_from(Cliente).where(Cliente.nombre.ilike("café acento"))) == 1  # NO se duplicó
    db.refresh(cafe)
    assert cafe.metodo_pago == "Tarjeta"
    assert decrypt_value(cafe.cuenta.correo_enc) == "cafe@fb.test" and decrypt_value(cafe.cuenta.password_enc) == "Secreta-123"
    assert [c.nombre for c in cafe.campanas] == ["LOCAL ADV"]
    assert cafe.campanas[0].paquete_cliente_id is not None   # ligada a su paquete vigente


def test_usuarios_nuevos_conservan_su_hash_de_contrasena(db, origen, destino):
    importar(db, origen, CLAVE_B64, aplicar=True)
    luz = db.scalars(select(Usuario).where(Usuario.username == "luz.nueva")).one()
    assert luz.password_hash == "$2b$hash-luz" and luz.rol == "cm"


def test_importa_el_historico_completo_y_conserva_los_mensuales(db, origen, destino):
    r = importar(db, origen, CLAVE_B64, aplicar=True)
    assert (r.semanas, r.observaciones, r.mensuales) == (2, 1, 2)
    m = db.scalars(select(Mensual).join(Campana).where(Campana.nombre == "LOCAL ADV")).one()
    assert (m.origen, m.mensajes_total, m.gasto_total) == ("manual", 246, Decimal("3081.24"))
    s = db.scalars(select(Semana).join(Campana).where(Campana.nombre == "LOCAL ADV", Semana.mensajes == 80)).one()
    assert (s.importe_gastado, s.editable) == (Decimal("1000.00"), False)
    assert db.scalars(select(Observacion)).one().autor_id == db.scalars(select(Usuario).where(Usuario.username == "ana.ruiz")).one().id


def test_clientes_no_renovados_llegan_con_su_archivo_y_sus_campanas_cerradas(db, origen, destino):
    r = importar(db, origen, CLAVE_B64, aplicar=True)
    viejo = db.scalars(select(Cliente).where(Cliente.nombre == "Cliente Viejo")).one()
    assert viejo.estado == "no_renovado" and [k.estado for k in viejo.campanas] == ["cerrada"]
    assert r.campanas_cerradas_por_no_renovado == 1
    assert db.scalars(select(ArchivoNoRenovado).where(ArchivoNoRenovado.cliente_id == viejo.id)).one().motivo == "Ya no pauta"


def test_es_idempotente(db, origen, destino):
    importar(db, origen, CLAVE_B64, aplicar=True)
    r = importar(db, origen, CLAVE_B64, aplicar=True)
    assert (r.campanas_importadas, r.campanas_omitidas_ya_existian, r.semanas, r.mensuales) == (0, 3, 0, 0)
    assert db.scalar(select(func.count()).select_from(Campana)) == 3


def test_avisa_si_el_mismo_cliente_lo_atiende_otro_cm(db, origen, destino, crear_usuario):
    ana, cafe = destino
    otro = crear_usuario("otro.cm")
    cafe.cm_id = otro.id
    db.flush()
    r = importar(db, origen, CLAVE_B64, aplicar=False)
    assert any("Café Acento" in a and "se conserva el de la plataforma" in a for a in r.avisos)


def test_rechaza_una_clave_antigua_invalida(db, origen):
    with pytest.raises(ValueError):
        importar(db, origen, base64.b64encode(b"corta").decode())
