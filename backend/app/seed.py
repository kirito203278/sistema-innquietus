import datetime as dt
import os
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dates import ahora, hoy
from app.database import get_sessionmaker
from app.models import (ArchivoNoRenovado, Bitacora, CatalogoPaquete, CatalogoTipo, Cliente, PaqueteCliente, Pago,
                        Renovacion, Usuario)
from app.services import cuentas as svc_cuentas
from app.security.passwords import hash_password

CREDENCIALES_PATH = Path(__file__).resolve().parent.parent / "seed_credentials.txt"

USUARIOS = [
    ("Admin Demo", "admin.demo", "admin", False, "10000001"),
    ("Lectura Demo", "lectura.demo", "admin", True, "10000002"),
    ("Ana Ruiz", "ana.ruiz", "cm", False, "10000003"),
    ("Beto Luna", "beto.luna", "cm", False, "10000004"),
    ("Carla Soto", "carla.soto", "cm", False, "10000005"),
]


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", ".", t.lower()).strip(".")


def vaciar(db: Session) -> None:
    db.execute(text(
        "TRUNCATE cuentas_fb, notificaciones, bitacora, jobs_ejecuciones, recordatorios_cliente, renovaciones, pagos, "
        "mensuales, observaciones, semanas, campanas, "
        "archivo_no_renovados, paquetes_cliente, clientes, usuarios RESTART IDENTITY CASCADE"
    ))


def sembrar(db: Session, credenciales_path: Path | None = CREDENCIALES_PATH) -> dict:
    if db.scalar(select(Usuario.id).limit(1)) is not None:
        raise RuntimeError("Ya hay usuarios en la base. Usa FORCE_SEED=true solo en desarrollo.")

    H = hoy()
    ts_ahora = ahora()
    ciclo_dias = get_settings().ciclo_dias
    costos_catalogo = {"Básico": 1500, "Estándar": 2500, "Élite": 4500, "Campaña": 6000}
    paq = {}
    for p in db.scalars(select(CatalogoPaquete)):
        paq[p.nombre] = p.id
        if p.nombre in costos_catalogo:
            p.costo = Decimal(costos_catalogo[p.nombre])
    db.flush()
    tipo = {t.nombre: t.id for t in db.scalars(select(CatalogoTipo))}

    lineas, users = [], {}
    for nombre, username, rol, ro, pwd in USUARIOS:
        u = Usuario(nombre=nombre, username=username, password_hash=hash_password(pwd),
                    rol=rol, solo_lectura=ro, primer_ingreso=False)
        db.add(u)
        users[username] = u
        lineas.append(f"{username}\t{rol}{' (solo lectura)' if ro else ''}\t{pwd}")
    db.flush()
    admin, ana, beto, carla = (users[k] for k in ("admin.demo", "ana.ruiz", "beto.luna", "carla.soto"))

    n_cliente = 0

    def cliente(cm: Usuario | None, nombre: str, estado: str = "activo", obs: str | None = None) -> Cliente:
        nonlocal n_cliente
        n_cliente += 1
        c = Cliente(cm_id=cm.id if cm else None, nombre=nombre, estado=estado, observaciones=obs,
                    correo_contacto=f"contacto@{_slug(nombre)}.ejemplo.test",
                    telefono=f"55550{n_cliente:05d}")
        db.add(c)
        db.flush()
        # Beto maneja tres clientes con una misma cuenta de Facebook; los demás tienen cuenta propia
        compartida = nombre in ("Gimnasio FuerzaMX", "Café Tlalli", "Papelería El Lápiz")
        svc_cuentas.asignar(db, c, "beto.agencia@fb.ejemplo.test" if compartida else f"{_slug(nombre)}@fb.ejemplo.test",
                            "FbBeto-Compartida!1" if compartida else f"FbDemo-{n_cliente:02d}!x")
        return c

    def ciclo(c: Cliente, paquete: str, tp: str, costo: int, renov: int, *, estado="activo", decision="pendiente",
              pagos: list[tuple[int, int]] = (), prorroga: tuple[int, int] | None = None,
              anterior: PaqueteCliente | None = None, por: Usuario | None = None) -> PaqueteCliente:
        f_ren = H + dt.timedelta(days=renov)
        p = PaqueteCliente(
            cliente_id=c.id, paquete_id=paq[paquete], tipo_id=tipo[tp], costo=Decimal(costo),
            fecha_inicio=f_ren - dt.timedelta(days=ciclo_dias), fecha_renovacion=f_ren, estado=estado,
            renovacion_decision=decision, ciclo_anterior_id=anterior.id if anterior else None,
            prorroga_registrada_en=H + dt.timedelta(days=prorroga[0]) if prorroga else None,
            prorroga_hasta=H + dt.timedelta(days=prorroga[1]) if prorroga else None,
        )
        db.add(p)
        db.flush()
        quien = por or db.get(Usuario, c.cm_id) or admin
        total = 0
        for monto, dias in pagos:
            db.add(Pago(paquete_id=p.id, monto=Decimal(monto), fecha=H + dt.timedelta(days=dias),
                        registrado_por=quien.id))
            total += monto
        p.renovacion_pagada = total >= costo
        return p

    def no_renovado(c: Cliente, dias: int, paquete: str, tp: str, costo: int) -> None:
        c.estado = "no_renovado"
        p = ciclo(c, paquete, tp, costo, -dias - 1, estado="archivado", decision="no",
                  pagos=[(costo, -dias - 10)])
        p.archivado_en = ts_ahora - dt.timedelta(days=dias)
        db.add(ArchivoNoRenovado(cliente_id=c.id, cm_id=c.cm_id, motivo="Decidió no renovar",
                                 archivado_en=ts_ahora - dt.timedelta(days=dias)))

    ciclo(cliente(ana, "Panadería La Espiga"), "Básico", "Normal", 1500, 12)
    mv = cliente(ana, "Dra. Mariana Vélez", obs="Prefiere contacto por WhatsApp por las tardes.")
    ciclo(mv, "Estándar", "Normal", 2500, 4, pagos=[(1000, -3)])
    th = cliente(ana, "Taller Hermanos Ríos")
    th_viejo = ciclo(th, "Élite", "Dinamita", 4500, 2, estado="renovado", decision="si",
                     pagos=[(4500, -1)])
    ciclo(th, "Élite", "Dinamita", 4500, 30, anterior=th_viejo)
    ciclo(cliente(ana, "Estética Bella Vista"), "Básico", "Fantasma", 1200, 1, decision="si", pagos=[(600, -2)])
    ciclo(cliente(beto, "Gimnasio FuerzaMX"), "Estándar", "Normal", 2500, -2, estado="vencido")
    cafe = ciclo(cliente(beto, "Café Tlalli"), "Básico", "Normal", 1500, -6, estado="vencido", decision="si",
                 pagos=[(700, -5)], prorroga=(-2, 3))
    cafe.confirmado_en = H - dt.timedelta(days=7)
    pl = cliente(beto, "Papelería El Lápiz")
    viejo = ciclo(pl, "Estándar", "Normal", 2500, -10, estado="renovado", decision="si",
                  pagos=[(2500, -12)])
    nuevo = ciclo(pl, "Élite", "Normal", 4500, 20, anterior=viejo)
    db.add(Renovacion(ciclo_anterior_id=viejo.id, ciclo_nuevo_id=nuevo.id, paquete_anterior_id=paq["Estándar"],
                      paquete_nuevo_id=paq["Élite"], costo_anterior=Decimal(2500), costo_nuevo=Decimal(4500),
                      fecha=H - dt.timedelta(days=10), registrado_por=beto.id))
    ic = cliente(beto, "Imprenta Central", estado="no_renovado")
    p_ic = ciclo(ic, "Estándar", "Normal", 2500, -12, estado="archivado", decision="no", pagos=[(1500, -11)], prorroga=(-12, -7))
    p_ic.archivado_en = ts_ahora - dt.timedelta(days=6)
    db.add(ArchivoNoRenovado(cliente_id=ic.id, cm_id=beto.id, motivo="La prórroga venció sin pago completo",
                             archivado_en=ts_ahora - dt.timedelta(days=6)))
    ciclo(cliente(beto, "Constructora Peña"), "Campaña", "Campaña", 6000, 9, pagos=[(3000, -2)])
    ciclo(cliente(carla, "Florería Jazmín"), "Básico", "Normal", 1500, 15, decision="no", pagos=[(1500, -4)])
    ciclo(cliente(carla, "Despacho Contable Orozco"), "Élite", "Normal", 4500, 25)
    ciclo(cliente(carla, "Hotel Casa Azul"), "Estándar", "Dinamita", 2500, 6, pagos=[(1000, -1)])
    no_renovado(cliente(carla, "Veterinaria PatiTas"), 20, "Estándar", "Dinamita", 2500)
    no_renovado(cliente(beto, "Abarrotes Doña Lucha"), 70, "Básico", "Normal", 1500)
    no_renovado(cliente(ana, "Refaccionaria Del Valle"), 370, "Básico", "Normal", 1500)
    ciclo(cliente(None, "Escuela de Baile Ritmo"), "Básico", "Normal", 1500, 7, por=admin)

    def con_historial(cm, nombre, paquete, tp, costo, renov, previos=2, antes=None, **actual):
        """Cliente con ciclos anteriores ya renovados y pagados (alimentan ingresos, reportes y tasa de renovación)."""
        c = cliente(cm, nombre)
        pq0, tp0, costo0 = antes or (paquete, tp, costo)
        anterior = None
        for k in range(previos, 0, -1):
            r = renov - ciclo_dias * k
            viejo = ciclo(c, pq0, tp0, costo0, r, estado="renovado", decision="si", pagos=[(costo0, r - 4)], anterior=anterior)
            if anterior is not None:
                db.add(Renovacion(ciclo_anterior_id=anterior.id, ciclo_nuevo_id=viejo.id, paquete_anterior_id=paq[pq0],
                                  paquete_nuevo_id=paq[pq0], costo_anterior=Decimal(costo0), costo_nuevo=Decimal(costo0),
                                  fecha=H + dt.timedelta(days=r - ciclo_dias), registrado_por=cm.id))
            anterior = viejo
        p = ciclo(c, paquete, tp, costo, renov, anterior=anterior, **actual)
        if anterior is not None:
            db.add(Renovacion(ciclo_anterior_id=anterior.id, ciclo_nuevo_id=p.id, paquete_anterior_id=paq[pq0],
                              paquete_nuevo_id=paq[paquete], costo_anterior=Decimal(costo0), costo_nuevo=Decimal(costo),
                              fecha=H + dt.timedelta(days=renov - ciclo_dias), registrado_por=cm.id))
        return c, p

    # ---- Más clientes para ver todas las pantallas (ana)
    con_historial(ana, "Ferretería El Tornillo", "Estándar", "Normal", 2500, 9, previos=3, pagos=[(1000, -1)])
    con_historial(ana, "Clínica Vital", "Élite", "Normal", 4500, 14, previos=2, antes=("Estándar", "Normal", 2500), pagos=[(4500, -2)])
    con_historial(ana, "Librería Cervantes", "Básico", "Normal", 1500, 22, previos=1)
    _, p_tq = con_historial(ana, "Taquería Los Compadres", "Básico", "Dinamita", 1800, 3, previos=2, decision="si", pagos=[(900, -1)])
    p_tq.confirmado_en = H - dt.timedelta(days=1)                                  # confirmó que renueva, pero con otro paquete
    p_tq.renovara_paquete_id, p_tq.renovara_tipo_id, p_tq.renovara_costo = paq["Estándar"], tipo["Dinamita"], Decimal(2500)
    # ---- beto
    con_historial(beto, "Óptica Visión Clara", "Estándar", "Normal", 2500, 6, previos=2)
    _, p_bo = con_historial(beto, "Boutique Aurora", "Básico", "Fantasma", 1200, -1, previos=2, decision="si", pagos=[(400, -3)])
    p_bo.confirmado_en = H - dt.timedelta(days=8)                                  # confirmó, no pagó: hoy toca prórroga o no renovó
    con_historial(beto, "Lavandería Burbuja", "Básico", "Normal", 1500, 27, previos=3, pagos=[(1500, -3)])
    _, p_ab = con_historial(beto, "Abarrotes La Esquina", "Estándar", "Normal", 2500, -3, previos=2, decision="si",
                            pagos=[(1000, -2)], prorroga=(-1, 4))
    p_ab.confirmado_en = H - dt.timedelta(days=4)                                  # prórroga corriendo con pago parcial
    # ---- carla
    con_historial(carla, "Estudio Fotográfico Lumen", "Élite", "Normal", 4500, 12, previos=2)
    con_historial(carla, "Pastelería Dulce Hogar", "Básico", "Normal", 1500, 5, previos=1, decision="no", pagos=[(1500, -5)])
    con_historial(carla, "Dentista Sonríe", "Estándar", "Normal", 2500, -2, previos=2, pagos=[(2500, -4)])   # pagó y falta decidir
    con_historial(carla, "Cafetería Aroma", "Básico", "Normal", 1500, 18, previos=2, pagos=[(500, -2)])
    con_historial(carla, "Spa Zen", "Élite", "Dinamita", 4500, 28, previos=2)
    no_renovado(cliente(ana, "Zapatería El Paso"), 30, "Básico", "Normal", 1500)
    no_renovado(cliente(carla, "Papelería Escolar"), 45, "Estándar", "Normal", 2500)

    def renovado_sin_pago(cm, nombre, paquete, tp, costo, pagado, renov_anterior, nota):
        c = cliente(cm, nombre, obs=nota)
        viejo = ciclo(c, paquete, tp, costo, renov_anterior, estado="renovado", decision="si",
                      pagos=[(pagado, renov_anterior - 3)])
        nuevo = ciclo(c, paquete, tp, costo, renov_anterior + ciclo_dias, anterior=viejo)
        db.add(Renovacion(ciclo_anterior_id=viejo.id, ciclo_nuevo_id=nuevo.id, paquete_anterior_id=paq[paquete],
                          paquete_nuevo_id=paq[paquete], costo_anterior=Decimal(costo), costo_nuevo=Decimal(costo),
                          fecha=H + dt.timedelta(days=renov_anterior), registrado_por=cm.id))
        db.add(Bitacora(usuario_id=admin.id, accion="editar_paquete",
                        detalle={"paquete_id": viejo.id, "antes": {"costo": str(pagado)},
                                 "despues": {"costo": str(costo)}}))
        return c, viejo, nuevo

    renovado_sin_pago(beto, "Mueblería Don Rafa", "Estándar", "Normal", 2500, 1800, -8,
                      "El admin corrigió el costo del ciclo anterior después de renovar: quedó con saldo.")
    renovado_sin_pago(carla, "Barbería El Corte", "Básico", "Normal", 1500, 900, -4,
                      "Se borró un pago mal capturado de un ciclo ya renovado: quedó con saldo.")

    # ---- Mensaje al cliente ya listo para Imprenta Central (su prórroga venció sin pago completo)
    from app import bitacora
    from app.jobs import tareas
    from app.services import notificar, recordatorios
    recordatorios.crear_para_paquete(db, p_ic, beto.id)
    notificar.crear(db, ic, "prorroga_vencida",
                    "Imprenta Central: la prórroga del paquete Estándar venció sin pago completo (faltan $1,000.00). "
                    "El cliente pasó a No renovados. Tienes listo el mensaje para el cliente: envíalo y márcalo como enviado.",
                    f"prorroga-venc:{p_ic.id}:{p_ic.prorroga_hasta}", paquete_id=p_ic.id)

    # ---- Rastro en la bitácora
    for _, uname, rol, ro, _ in USUARIOS:
        bitacora.registrar(db, admin, "alta_usuario", {"username": uname, "rol": rol, "solo_lectura": ro})
    bitacora.registrar(db, admin, "editar_catalogo", {"catalogo": "paquetes", "accion": "alta", "nombre": "Élite"})
    bitacora.registrar(db, beto, "prorroga_solicitada", {"paquete_id": cafe.id, "hasta": str(cafe.prorroga_hasta)})
    bitacora.registrar(db, ana, "confirmar_renovacion", {"paquete_id": p_tq.id, "en_ventana": False})
    bitacora.registrar(db, carla, "programar_no_renovara", {"cliente": "Pastelería Dulce Hogar"})
    bitacora.registrar(db, admin, "reasignar_cliente", {"cliente": "Escuela de Baile Ritmo", "de": ana.id, "a": None})
    db.flush()
    from app.seed_campanas import sembrar_campanas
    n_campanas = sembrar_campanas(db, H)
    tareas.avisos_renovacion(db, H)
    tareas.avisos_prorroga(db, H)

    db.commit()
    if credenciales_path:
        credenciales_path.write_text(
            "# Credenciales de prueba generadas por el seed (ignorado por git)\n# usuario\trol\tcontraseña\n"
            + "\n".join(lineas) + "\n", encoding="utf-8")
        os.chmod(credenciales_path, 0o600)
    return {"usuarios": len(USUARIOS), "clientes": n_cliente, "campanas": n_campanas}


if __name__ == "__main__":
    SessionLocal = get_sessionmaker()
    with SessionLocal() as db:
        if os.getenv("FORCE_SEED", "").lower() == "true":
            vaciar(db)
            db.commit()
        resumen = sembrar(db)
    print(f"[seed] {resumen['usuarios']} usuarios, {resumen['clientes']} clientes y {resumen['campanas']} campañas de ejemplo. "
          f"Credenciales en {CREDENCIALES_PATH}")
