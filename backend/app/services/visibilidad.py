from app.models import Usuario

CAMPOS_MONTO = ("costo", "pagado", "restante", "avance_pct")


def oculta_montos(user: Usuario) -> bool:
    return user.rol == "cm"


def paquete_visible(datos: dict, user: Usuario) -> dict:
    if not oculta_montos(user):
        return datos
    limpio = {k: v for k, v in datos.items() if k not in CAMPOS_MONTO}
    if limpio.get("renovara_con"):
        limpio["renovara_con"] = {k: v for k, v in limpio["renovara_con"].items() if k != "costo"}
    return limpio


def paquetes_visibles(filas: list[dict], user: Usuario) -> list[dict]:
    return [paquete_visible(f, user) for f in filas]
