import datetime as dt
from decimal import Decimal

import psycopg2
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.migrations.run_migrations import run_migrations
from app.models import (ArchivoNoRenovado, CatalogoPaquete, CatalogoTipo, Cliente, Notificacion, PaqueteCliente,
                        Pago, Usuario)

H = dt.date(2026, 10, 1)


def _usuario(db, username="cm.x", rol="cm", **kw):
    u = Usuario(nombre="X", username=username, password_hash="h", rol=rol, **kw)
    db.add(u)
    db.flush()
    return u


def _ciclo(db, **kw):
    cm = _usuario(db, username=f"cm.{id(kw)}")
    c = Cliente(cm_id=cm.id, nombre="Cliente")
    db.add(c)
    db.flush()
    campos = dict(cliente_id=c.id, paquete_id=db.scalar(select(CatalogoPaquete.id).limit(1)),
                  tipo_id=db.scalar(select(CatalogoTipo.id).limit(1)), costo=Decimal(1500),
                  fecha_inicio=H, fecha_renovacion=H + dt.timedelta(days=30))
    campos.update(kw)
    p = PaqueteCliente(**campos)
    db.add(p)
    db.flush()
    return cm, c, p


def test_migraciones_son_idempotentes(test_db_url):
    assert run_migrations(test_db_url.replace("postgresql://", "postgresql+psycopg2://")) == []


def test_catalogos_sembrados(db):
    assert [p.nombre for p in db.scalars(select(CatalogoPaquete).order_by(CatalogoPaquete.orden))] == \
        ["Básico", "Estándar", "Élite", "Campaña"]
    assert [t.nombre for t in db.scalars(select(CatalogoTipo).order_by(CatalogoTipo.orden))] == \
        ["Normal", "Dinamita", "Fantasma", "Campaña"]


def test_prorroga_valida_hasta_5_dias(db):
    _, _, p = _ciclo(db, prorroga_registrada_en=H, prorroga_hasta=H + dt.timedelta(days=5))
    assert p.id


@pytest.mark.parametrize("hasta_dias", [6, 15, -1])
def test_prorroga_mayor_a_5_dias_o_anterior_se_rechaza(db, hasta_dias):
    with pytest.raises(IntegrityError):
        _ciclo(db, prorroga_registrada_en=H, prorroga_hasta=H + dt.timedelta(days=hasta_dias))
    db.rollback()


def test_prorroga_incompleta_se_rechaza(db):
    with pytest.raises(IntegrityError):
        _ciclo(db, prorroga_hasta=H + dt.timedelta(days=5))
    db.rollback()


def test_renovacion_antes_del_inicio_se_rechaza(db):
    with pytest.raises(IntegrityError):
        _ciclo(db, fecha_renovacion=H - dt.timedelta(days=1))
    db.rollback()


def test_estado_invalido_se_rechaza(db):
    with pytest.raises(IntegrityError):
        _ciclo(db, estado="por_vencer")
    db.rollback()


def test_pago_debe_ser_positivo(db):
    cm, _, p = _ciclo(db)
    with pytest.raises(IntegrityError):
        db.add(Pago(paquete_id=p.id, monto=Decimal(0), fecha=H, registrado_por=cm.id))
        db.flush()
    db.rollback()


def test_pagado_se_deriva_de_pagos_vista_y_modelo(db):
    cm, _, p = _ciclo(db)
    db.add_all([Pago(paquete_id=p.id, monto=Decimal(500), fecha=H, registrado_por=cm.id),
                Pago(paquete_id=p.id, monto=Decimal("250.50"), fecha=H, registrado_por=cm.id)])
    db.flush()
    db.refresh(p)
    assert p.pagado == Decimal("750.50") and p.restante == Decimal("749.50")
    pagado, restante = db.execute(
        text("SELECT pagado, restante FROM v_paquete_saldo WHERE paquete_id = :i"), {"i": p.id}).one()
    assert (pagado, restante) == (Decimal("750.50"), Decimal("749.50"))


def test_solo_lectura_exclusivo_de_admin(db):
    with pytest.raises(IntegrityError):
        _usuario(db, username="cm.ro", rol="cm", solo_lectura=True)
    db.rollback()


def test_username_unico(db):
    _usuario(db, username="repetido")
    with pytest.raises(IntegrityError):
        _usuario(db, username="repetido")
    db.rollback()


def test_dedupe_key_evita_notificaciones_duplicadas(db):
    cm = _usuario(db)
    db.add(Notificacion(usuario_id=cm.id, tipo="renovacion_3d", mensaje="a", dedupe_key="renov:1:2026-10-10"))
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(Notificacion(usuario_id=cm.id, tipo="renovacion_3d", mensaje="b", dedupe_key="renov:1:2026-10-10"))
        db.flush()
    db.rollback()


def test_borrar_cliente_borra_archivo_y_paquetes_sin_error(db):
    cm, c, p = _ciclo(db)
    db.add(ArchivoNoRenovado(cliente_id=c.id, cm_id=cm.id))
    db.flush()
    db.execute(text("DELETE FROM clientes WHERE id = :i"), {"i": c.id})
    assert db.scalar(text("SELECT count(*) FROM archivo_no_renovados WHERE cliente_id = :i"), {"i": c.id}) == 0
    assert db.scalar(text("SELECT count(*) FROM paquetes_cliente WHERE cliente_id = :i"), {"i": c.id}) == 0


def test_actualizado_en_se_mantiene_solo(db):
    _, c, _ = _ciclo(db)
    antes = db.scalar(text("SELECT actualizado_en FROM clientes WHERE id=:i"), {"i": c.id})
    db.execute(text("SELECT pg_sleep(0.05)"))
    db.execute(text("UPDATE clientes SET nombre='Otro' WHERE id=:i"), {"i": c.id})
    despues = db.scalar(text("SELECT actualizado_en FROM clientes WHERE id=:i"), {"i": c.id})
    assert despues >= antes
