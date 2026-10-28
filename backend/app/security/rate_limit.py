import datetime as dt
import threading

LIMITE_INTENTOS = 5
VENTANA = dt.timedelta(minutes=15)

_intentos: dict[str, list[dt.datetime]] = {}
_lock = threading.Lock()


def _vigentes(historial, ahora):
    return [t for t in historial if ahora - t < VENTANA]


def registrar_intento_fallido(username: str, ahora: dt.datetime | None = None) -> None:
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    with _lock:
        h = _vigentes(_intentos.get(username, []), ahora)
        h.append(ahora)
        _intentos[username] = h


def limpiar_intentos(username: str) -> None:
    with _lock:
        _intentos.pop(username, None)


def bloqueado(username: str, ahora: dt.datetime | None = None) -> bool:
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    with _lock:
        h = _vigentes(_intentos.get(username, []), ahora)
        _intentos[username] = h
        return len(h) >= LIMITE_INTENTOS


def reiniciar_todo() -> None:
    with _lock:
        _intentos.clear()
