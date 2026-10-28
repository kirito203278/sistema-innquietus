"""Semáforo de rendimiento de campañas (bueno / regular / bajo).

Compara el costo por resultado contra umbrales configurables (tabla
metricas_config, editables sin tocar código) y degrada un nivel si los mensajes
caen mucho o si el costo empeora semana tras semana. Las funciones de nivel son
PURAS (reciben el umbral ya cargado) para poder probarlas sin base de datos.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MetricaConfig, Semana

NIVELES = ("bueno", "regular", "bajo")
Umbrales = dict[tuple[str, str | None], MetricaConfig]


def cargar_umbrales(db: Session) -> Umbrales:
    """Todos los umbrales activos, indexados por (tipo, paquete). Una sola consulta."""
    return {(m.tipo, m.paquete): m for m in db.scalars(select(MetricaConfig).where(MetricaConfig.activo))}


def buscar_umbral(umbrales: Umbrales, tipo: str, paquete: str | None) -> MetricaConfig | None:
    """Umbral específico del paquete si existe; si no, el general del tipo."""
    if paquete and (tipo, paquete) in umbrales:
        return umbrales[(tipo, paquete)]
    return umbrales.get((tipo, None))


def nivel_por_costo(cfg: MetricaConfig, costo: float | Decimal) -> str:
    costo = float(costo)
    if costo <= float(cfg.umbral_bueno):
        return "bueno"
    if costo <= float(cfg.umbral_regular):
        return "regular"
    return "bajo"


def degradar(nivel: str) -> str:
    return NIVELES[min(NIVELES.index(nivel) + 1, len(NIVELES) - 1)]


def nivel_semana(cfg: MetricaConfig | None, semana: Semana, previas: list[Semana]) -> str | None:
    """Semáforo semanal: costo por resultado contra la tabla; baja un nivel si los
    mensajes caen >= X% contra el promedio de las semanas previas del ciclo."""
    if cfg is None or semana.costo_por_resultado is None:
        return None
    nivel = nivel_por_costo(cfg, semana.costo_por_resultado)
    con_datos = [s for s in previas if s.mensajes is not None]
    if con_datos and semana.mensajes is not None:
        promedio = sum(s.mensajes for s in con_datos) / len(con_datos)
        if promedio > 0:
            caida = (promedio - semana.mensajes) / promedio * 100
            if caida >= float(cfg.caida_mensajes_alerta_pct):
                nivel = degradar(nivel)
    return nivel


def nivel_ciclo(cfg: MetricaConfig | None, costo_por_mensaje: float, semanas: list[Semana]) -> str | None:
    """Mensual: costo por mensaje del ciclo contra la tabla; baja un nivel si las
    últimas 3 semanas empeoraron de forma continua."""
    if cfg is None:
        return None
    nivel = nivel_por_costo(cfg, costo_por_mensaje)
    costos = [float(s.costo_por_resultado) for s in semanas if s.costo_por_resultado is not None]
    if len(costos) >= 3 and costos[-1] > costos[-2] > costos[-3]:
        nivel = degradar(nivel)
    return nivel
