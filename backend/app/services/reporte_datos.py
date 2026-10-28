import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Cliente, PaqueteCliente, Usuario
from app.services import ciclos
from app.services.periodos import Periodo
from app.services.scope import paquetes_q

CERO = Decimal("0")
POR_REASIGNAR = "Por reasignar"


def _pct(parte: Decimal, total: Decimal) -> float:
    return round(float(parte / total * 100), 1) if total > 0 else 0.0


def _cargar(db: Session, user: Usuario, per: Periodo, cm_id: int | None, estados: tuple[str, ...]) -> list[PaqueteCliente]:
    q = paquetes_q(user).where(PaqueteCliente.fecha_renovacion >= per.desde,
                               PaqueteCliente.fecha_renovacion <= per.hasta, PaqueteCliente.estado.in_(estados))
    if user.rol == "admin" and cm_id is not None:
        q = q.where(Cliente.cm_id == cm_id)
    return list(db.scalars(q.options(selectinload(PaqueteCliente.cliente), selectinload(PaqueteCliente.paquete),
                                     selectinload(PaqueteCliente.tipo), selectinload(PaqueteCliente.pagos))
                           .order_by(PaqueteCliente.fecha_renovacion, PaqueteCliente.id)))


def _cargar_abiertos(db: Session, user: Usuario, cm_id: int | None) -> list[PaqueteCliente]:
    q = paquetes_q(user).where(PaqueteCliente.estado.in_(ciclos.COBRABLES) |
                               ((PaqueteCliente.estado == "archivado") & PaqueteCliente.prorroga_hasta.is_not(None)))
    if user.rol == "admin" and cm_id is not None:
        q = q.where(Cliente.cm_id == cm_id)
    return list(db.scalars(q.options(selectinload(PaqueteCliente.cliente), selectinload(PaqueteCliente.paquete),
                                     selectinload(PaqueteCliente.tipo), selectinload(PaqueteCliente.pagos))))


def construir(db: Session, user: Usuario, per: Periodo, hoy: dt.date, cm_id: int | None = None) -> dict:
    cms = {u.id: u.nombre for u in db.scalars(select(Usuario).where(Usuario.rol == "cm"))}
    nombre_cm = lambda cid: cms.get(cid, "(CM dado de baja)") if cid else POR_REASIGNAR

    def fila(p: PaqueteCliente) -> dict:
        pagado = ciclos.pagado_hasta(p, per.corte)
        return {
            "paquete_id": p.id, "cliente_id": p.cliente_id, "cm_id": p.cliente.cm_id, "cm": nombre_cm(p.cliente.cm_id),
            "cliente": p.cliente.nombre, "paquete": p.paquete.nombre, "tipo": p.tipo.nombre, "costo": p.costo,
            "pagado": pagado, "restante": max(p.costo - pagado, CERO), "fecha_renovacion": p.fecha_renovacion,
            "estado": p.estado, "estado_efectivo": ciclos.estado_efectivo(p, hoy), "semaforo": ciclos.semaforo(p, hoy),
            "decision": p.renovacion_decision, "prorroga_hasta": p.prorroga_hasta,
            "prorroga_registrada_en": p.prorroga_registrada_en}

    orden_fila = lambda f: (f["cm"], f["cliente"].lower(), f["fecha_renovacion"], f["paquete_id"])
    filas = sorted((fila(p) for p in _cargar(db, user, per, cm_id, ("activo", "vencido", "renovado"))), key=orden_fila)
    abiertos = sorted((fila(p) for p in _cargar_abiertos(db, user, cm_id)), key=orden_fila)

    grupos: dict[int | None, dict] = {}
    if user.rol == "admin" and cm_id is None:
        for cid in cms:
            grupos[cid] = {"clientes": set(), "paquetes": 0, "proyeccion": CERO, "cobrado": CERO}
    elif user.rol == "cm":
        grupos[user.id] = {"clientes": set(), "paquetes": 0, "proyeccion": CERO, "cobrado": CERO}
    elif cm_id is not None:
        grupos[cm_id] = {"clientes": set(), "paquetes": 0, "proyeccion": CERO, "cobrado": CERO}
    for f in filas:
        g = grupos.setdefault(f["cm_id"], {"clientes": set(), "paquetes": 0, "proyeccion": CERO, "cobrado": CERO})
        g["clientes"].add(f["cliente_id"])
        g["paquetes"] += 1
        g["proyeccion"] += f["costo"]
        g["cobrado"] += f["pagado"]

    llegados = _cargar(db, user, per, cm_id, ("vencido", "renovado", "archivado", "eliminado"))
    tasa_g: dict[int | None, dict] = defaultdict(lambda: {"vencidos": 0, "renovados": 0})
    for p in llegados:
        if p.fecha_renovacion > per.corte:
            continue
        t = tasa_g[p.cliente.cm_id]
        t["vencidos"] += 1
        t["renovados"] += p.estado == "renovado"
    for p in (x for x in _cargar(db, user, per, cm_id, ("activo",)) if x.fecha_renovacion <= per.corte):
        tasa_g[p.cliente.cm_id]["vencidos"] += 1
    for cid in grupos:
        tasa_g[cid]

    orden = sorted(grupos, key=lambda cid: (cid is None, nombre_cm(cid).lower()))
    por_cm = []
    for cid in orden:
        g = grupos[cid]
        por_cm.append({"cm_id": cid, "cm": nombre_cm(cid), "clientes": len(g["clientes"]), "paquetes": g["paquetes"],
                       "proyeccion": g["proyeccion"], "cobrado": g["cobrado"],
                       "pendiente": g["proyeccion"] - g["cobrado"], "pct_cobrado": _pct(g["cobrado"], g["proyeccion"])})
    tot = {k: sum((c[k] for c in por_cm), CERO if k in ("proyeccion", "cobrado", "pendiente") else 0)
           for k in ("clientes", "paquetes", "proyeccion", "cobrado", "pendiente")}
    tot["pct_cobrado"] = _pct(tot["cobrado"], tot["proyeccion"])
    tasa = []
    for cid in orden:
        t = tasa_g[cid]
        tasa.append({"cm_id": cid, "cm": nombre_cm(cid), "vencidos": t["vencidos"], "renovados": t["renovados"],
                     "tasa": round(t["renovados"] / t["vencidos"] * 100, 1) if t["vencidos"] else 0.0})
    tv, tr = sum(t["vencidos"] for t in tasa), sum(t["renovados"] for t in tasa)

    prorrogas = []
    for f in abiertos:
        if f["prorroga_hasta"] is not None and f["restante"] > 0:
            dias = (f["prorroga_hasta"] - per.corte).days
            prorrogas.append({**{k: f[k] for k in ("cm", "cliente", "paquete", "tipo", "costo", "pagado", "restante")},
                              "fecha_limite": f["prorroga_hasta"], "dias": dias, "vencida": dias < 0})
    prorrogas.sort(key=lambda r: (r["dias"], r["cm"], r["cliente"]))

    pendientes = {"por_vencer": defaultdict(list), "vencidos": defaultdict(list), "renovados_sin_pago": defaultdict(list)}
    for f in abiertos:
        if f["estado_efectivo"] == "vencido":
            clave = "vencidos"
        elif f["estado"] == "renovado" and f["restante"] > 0:
            clave = "renovados_sin_pago"
        elif f["estado_efectivo"] == "por_vencer":
            clave = "por_vencer"
        else:
            continue
        pendientes[clave][f["cm"]].append(f)
    pend = {k: [{"cm": cm, "items": items} for cm, items in sorted(v.items(), key=lambda kv: (kv[0] == POR_REASIGNAR, kv[0]))]
            for k, v in pendientes.items()}

    return {
        "periodo": {"anio": per.anio, "mes": per.mes, "quincena": per.quincena, "desde": per.desde, "hasta": per.hasta,
                    "corte": per.corte, "cerrado": per.cerrado, "etiqueta": per.etiqueta, "estado_texto": per.estado_texto},
        "resumen": {"proyeccion": tot["proyeccion"], "cobrado": tot["cobrado"], "pendiente": tot["pendiente"],
                    "pct_cobrado": tot["pct_cobrado"], "clientes": tot["clientes"], "paquetes": tot["paquetes"]},
        "por_cm": por_cm, "total_cm": tot, "detalle": filas, "prorrogas": prorrogas, "pendientes": pend,
        "tasa_renovacion": tasa,
        "tasa_total": {"vencidos": tv, "renovados": tr, "tasa": round(tr / tv * 100, 1) if tv else 0.0},
        "alcance": "cartera propia" if user.rol == "cm" else ("todos los CM" if cm_id is None else nombre_cm(cm_id)),
    }


def ingresos_por_cliente(datos: dict) -> list[dict]:
    por: dict[int, dict] = {}
    for f in datos["detalle"]:
        r = por.setdefault(f["cliente_id"], {"cliente_id": f["cliente_id"], "cliente": f["cliente"], "cm": f["cm"],
                                             "paquetes": 0, "proyeccion": CERO, "actual": CERO})
        r["paquetes"] += 1
        r["proyeccion"] += f["costo"]
        r["actual"] += f["pagado"]
    filas = sorted(por.values(), key=lambda r: (r["cm"], r["cliente"].lower()))
    for r in filas:
        r["pendiente"] = r["proyeccion"] - r["actual"]
        r["pct_cobrado"] = _pct(r["actual"], r["proyeccion"])
    return filas
