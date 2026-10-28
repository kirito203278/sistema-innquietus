import datetime as dt
from decimal import Decimal

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _ts():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(Text)
    solo_lectura: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    primer_ingreso: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[dt.datetime] = _ts()


class CatalogoPaquete(Base):
    __tablename__ = "catalogo_paquetes"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, unique=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    costo: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CatalogoTipo(Base):
    __tablename__ = "catalogo_tipos"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, unique=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CuentaFb(Base):
    """Cuenta de Facebook que un CM comparte entre varios de sus clientes."""
    __tablename__ = "cuentas_fb"
    id: Mapped[int] = mapped_column(primary_key=True)
    cm_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    huella: Mapped[str] = mapped_column(Text)
    correo_enc: Mapped[str] = mapped_column(Text)
    password_enc: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[dt.datetime] = _ts()


class Cliente(Base):
    __tablename__ = "clientes"
    id: Mapped[int] = mapped_column(primary_key=True)
    cm_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    nombre: Mapped[str] = mapped_column(Text)
    correo_fb_enc: Mapped[str | None] = mapped_column(Text)
    password_fb_enc: Mapped[str | None] = mapped_column(Text)
    cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("cuentas_fb.id", ondelete="SET NULL"))
    correo_contacto: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    observaciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text, default="activo")
    tipo_cuenta: Mapped[str | None] = mapped_column(Text)
    metodo_pago: Mapped[str | None] = mapped_column(Text)
    forma_pago: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[dt.datetime] = _ts()
    actualizado_en: Mapped[dt.datetime] = _ts()

    cuenta: Mapped["CuentaFb | None"] = relationship()
    paquetes: Mapped[list["PaqueteCliente"]] = relationship(back_populates="cliente", cascade="all, delete-orphan", passive_deletes=True)
    campanas: Mapped[list["Campana"]] = relationship(back_populates="cliente", cascade="all, delete-orphan", passive_deletes=True,
                                                      order_by="Campana.fecha_inicio")


class PaqueteCliente(Base):
    __tablename__ = "paquetes_cliente"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"))
    paquete_id: Mapped[int] = mapped_column(ForeignKey("catalogo_paquetes.id"))
    tipo_id: Mapped[int] = mapped_column(ForeignKey("catalogo_tipos.id"))
    costo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    fecha_inicio: Mapped[dt.date] = mapped_column(Date)
    fecha_renovacion: Mapped[dt.date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(Text, default="activo")
    renovacion_decision: Mapped[str] = mapped_column(Text, default="pendiente")
    renovacion_pagada: Mapped[bool] = mapped_column(Boolean, default=False)
    prorroga_hasta: Mapped[dt.date | None] = mapped_column(Date)
    prorroga_registrada_en: Mapped[dt.date | None] = mapped_column(Date)
    gracia_hasta: Mapped[dt.date | None] = mapped_column(Date)
    confirmado_en: Mapped[dt.date | None] = mapped_column(Date)
    renovara_paquete_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_paquetes.id"))
    renovara_tipo_id: Mapped[int | None] = mapped_column(ForeignKey("catalogo_tipos.id"))
    renovara_costo: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ciclo_anterior_id: Mapped[int | None] = mapped_column(ForeignKey("paquetes_cliente.id"))
    archivado_en: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[dt.datetime] = _ts()

    cliente: Mapped[Cliente] = relationship(back_populates="paquetes")
    paquete: Mapped[CatalogoPaquete] = relationship(foreign_keys=[paquete_id])
    tipo: Mapped[CatalogoTipo] = relationship(foreign_keys=[tipo_id])
    pagos: Mapped[list["Pago"]] = relationship(back_populates="paquete_cliente", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def pagado(self) -> Decimal:
        return sum((p.monto for p in self.pagos), Decimal("0"))

    @property
    def restante(self) -> Decimal:
        return self.costo - self.pagado


class Pago(Base):
    __tablename__ = "pagos"
    id: Mapped[int] = mapped_column(primary_key=True)
    paquete_id: Mapped[int] = mapped_column(ForeignKey("paquetes_cliente.id", ondelete="CASCADE"))
    monto: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    fecha: Mapped[dt.date] = mapped_column(Date)
    nota: Mapped[str | None] = mapped_column(Text)
    registrado_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[dt.datetime] = _ts()

    paquete_cliente: Mapped[PaqueteCliente] = relationship(back_populates="pagos")


class Renovacion(Base):
    __tablename__ = "renovaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    ciclo_anterior_id: Mapped[int] = mapped_column(ForeignKey("paquetes_cliente.id", ondelete="CASCADE"))
    ciclo_nuevo_id: Mapped[int] = mapped_column(ForeignKey("paquetes_cliente.id", ondelete="CASCADE"))
    paquete_anterior_id: Mapped[int] = mapped_column(ForeignKey("catalogo_paquetes.id"))
    paquete_nuevo_id: Mapped[int] = mapped_column(ForeignKey("catalogo_paquetes.id"))
    costo_anterior: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    costo_nuevo: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    fecha: Mapped[dt.date] = mapped_column(Date)
    registrado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[dt.datetime] = _ts()


class ArchivoNoRenovado(Base):
    __tablename__ = "archivo_no_renovados"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"))
    cm_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    motivo: Mapped[str | None] = mapped_column(Text)
    archivado_en: Mapped[dt.datetime] = _ts()
    reingresado_en: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class RecordatorioCliente(Base):
    __tablename__ = "recordatorios_cliente"
    id: Mapped[int] = mapped_column(primary_key=True)
    paquete_id: Mapped[int] = mapped_column(ForeignKey("paquetes_cliente.id", ondelete="CASCADE"))
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"))
    cm_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    telefono_destino: Mapped[str | None] = mapped_column(Text)
    texto: Mapped[str] = mapped_column(Text)
    generado_en: Mapped[dt.datetime] = _ts()
    enviado_en: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Notificacion(Base):
    __tablename__ = "notificaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[str] = mapped_column(Text)
    mensaje: Mapped[str] = mapped_column(Text)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"))
    paquete_id: Mapped[int | None] = mapped_column(ForeignKey("paquetes_cliente.id", ondelete="CASCADE"))
    requiere_respuesta: Mapped[bool] = mapped_column(Boolean, default=False)
    respuesta: Mapped[str | None] = mapped_column(Text)
    respondida_en: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    dedupe_key: Mapped[str | None] = mapped_column(Text, unique=True)
    creado_en: Mapped[dt.datetime] = _ts()


class Bitacora(Base):
    __tablename__ = "bitacora"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    accion: Mapped[str] = mapped_column(Text)
    detalle: Mapped[dict | None] = mapped_column(JSONB)
    creado_en: Mapped[dt.datetime] = _ts()


class JobEjecucion(Base):
    __tablename__ = "jobs_ejecuciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    origen: Mapped[str] = mapped_column(Text)
    ejecutado_en: Mapped[dt.datetime] = _ts()
    resultado: Mapped[dict | None] = mapped_column(JSONB)


# ======================= Módulo de campañas =======================
class Campana(Base):
    __tablename__ = "campanas"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"))
    paquete_cliente_id: Mapped[int | None] = mapped_column(ForeignKey("paquetes_cliente.id", ondelete="SET NULL"))
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    presupuesto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    presupuesto_esquema: Mapped[str] = mapped_column(Text, default="mensual")
    formato_post: Mapped[bool] = mapped_column(Boolean, default=False)
    formato_3d: Mapped[bool] = mapped_column(Boolean, default=False)
    formato_boton: Mapped[bool] = mapped_column(Boolean, default=False)
    formato_otro: Mapped[bool] = mapped_column(Boolean, default=False)
    lugar: Mapped[str | None] = mapped_column(Text)
    fecha_inicio: Mapped[dt.date] = mapped_column(Date)
    fecha_renovacion: Mapped[dt.date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(Text, default="activa")
    creado_en: Mapped[dt.datetime] = _ts()

    cliente: Mapped["Cliente"] = relationship(back_populates="campanas")
    paquete_cliente: Mapped["PaqueteCliente | None"] = relationship()
    semanas: Mapped[list["Semana"]] = relationship(back_populates="campana", cascade="all, delete-orphan",
                                                    passive_deletes=True, order_by="Semana.inicio")
    observaciones: Mapped[list["Observacion"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    mensuales: Mapped[list["Mensual"]] = relationship(cascade="all, delete-orphan", passive_deletes=True,
                                                       order_by="Mensual.periodo_inicio")


class Semana(Base):
    __tablename__ = "semanas"
    id: Mapped[int] = mapped_column(primary_key=True)
    campana_id: Mapped[int] = mapped_column(ForeignKey("campanas.id", ondelete="CASCADE"))
    inicio: Mapped[dt.date] = mapped_column(Date)
    fin: Mapped[dt.date] = mapped_column(Date)
    mensajes: Mapped[int | None] = mapped_column(Integer)
    costo_por_resultado: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    importe_gastado: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    editable: Mapped[bool] = mapped_column(Boolean, default=True)
    edicion_habilitada_hasta: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    capturado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_en: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    campana: Mapped["Campana"] = relationship(back_populates="semanas")


class Observacion(Base):
    __tablename__ = "observaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    campana_id: Mapped[int] = mapped_column(ForeignKey("campanas.id", ondelete="CASCADE"))
    texto: Mapped[str] = mapped_column(Text)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[dt.datetime] = _ts()


class Mensual(Base):
    __tablename__ = "mensuales"
    id: Mapped[int] = mapped_column(primary_key=True)
    campana_id: Mapped[int] = mapped_column(ForeignKey("campanas.id", ondelete="CASCADE"))
    periodo_inicio: Mapped[dt.date] = mapped_column(Date)
    periodo_fin: Mapped[dt.date] = mapped_column(Date)
    mensajes_total: Mapped[int] = mapped_column(Integer)
    gasto_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    costo_por_mensaje: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    presupuesto: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sobrante: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rendimiento: Mapped[str | None] = mapped_column(Text)
    origen: Mapped[str] = mapped_column(Text, default="calculado")
    creado_en: Mapped[dt.datetime] = _ts()


class MetricaConfig(Base):
    __tablename__ = "metricas_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(Text)
    paquete: Mapped[str | None] = mapped_column(Text)
    umbral_bueno: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    umbral_regular: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    caida_mensajes_alerta_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("30"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_en: Mapped[dt.datetime] = _ts()
