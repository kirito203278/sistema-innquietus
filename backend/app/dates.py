import datetime as dt
from zoneinfo import ZoneInfo

from app.config import get_settings

_hoy_fijo: dt.date | None = None


def fijar_hoy(fecha: dt.date | None) -> None:
    global _hoy_fijo
    _hoy_fijo = fecha


def ahora() -> dt.datetime:
    tz = ZoneInfo(get_settings().tz)
    if _hoy_fijo is not None:
        return dt.datetime.combine(_hoy_fijo, dt.time(12, 0), tzinfo=tz)
    return dt.datetime.now(tz)


def hoy() -> dt.date:
    return ahora().date()
