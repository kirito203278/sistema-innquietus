import datetime as dt
from decimal import Decimal


def dinero(v) -> str:
    return f"${Decimal(v):,.2f}"


def fecha(f: dt.date | None) -> str:
    return f.strftime("%d/%m/%Y") if f else "—"


def dias_texto(d: int) -> str:
    if d > 0:
        return f"faltan {d} día{'s' if d != 1 else ''}"
    if d == 0:
        return "vence hoy"
    return f"{-d} día{'s' if d != -1 else ''} de retraso"
