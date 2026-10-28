"""Datos de ejemplo del módulo de campañas: cuelgan de los MISMOS clientes que siembra seed.py."""
import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Campana, Cliente, Mensual, Observacion, Semana, Usuario
from app.services import campanas as svc
from app.services import ciclos, rendimiento
from app.services import semanas as cal

NOMBRES = ["LOCAL ADV", "MENSAJES FB", "PROMO MES", "NACIONAL ADV"]
OBSERVACIONES = ["Se subió el presupuesto diario por la promo del fin de semana.",
                 "El cliente pidió probar un nuevo creativo en carrusel.",
                 "Buen costo por mensaje; mantener la segmentación."]


def sembrar_campanas(db: Session, hoy: dt.date) -> int:
    umbrales = rendimiento.cargar_umbrales(db)
    clientes = db.scalars(select(Cliente).where(Cliente.estado == "activo").order_by(Cliente.id)).all()
    cm_ids = {u.id for u in db.scalars(select(Usuario).where(Usuario.rol == "cm"))}
    creadas = 0
    for i, c in enumerate(clientes):
        if i % 4 == 3:  # algunos clientes quedan sin campaña para ver ese estado
            continue
        tipo = "nacional" if i % 5 == 0 else "local"
        vigentes = [p for p in c.paquetes if p.estado in ciclos.VIGENTES]
        inicio = hoy - dt.timedelta(days=21 + (i % 7))
        renov = inicio + dt.timedelta(days=30)
        camp = Campana(
            cliente_id=c.id, paquete_cliente_id=vigentes[0].id if vigentes else None,
            nombre=f"{NOMBRES[i % 3]} - {c.nombre.split()[0].upper()}", tipo=tipo,
            presupuesto=Decimal([3500, 4800, 6000, 2500][i % 4]), formato_post=True, formato_3d=i % 3 == 0,
            formato_boton=i % 4 == 1, lugar=["Culiacán", "Mazatlán", "Los Mochis"][i % 3],
            fecha_inicio=inicio, fecha_renovacion=renov, estado="activa")
        db.add(camp)
        db.flush()

        # semanas desde el inicio hasta la actual, con datos variados (verde / amarillo / rojo)
        s0, _ = cal.rango_semana(inicio)
        s_act, _ = cal.rango_semana(hoy)
        k = 0
        while s0 <= s_act:
            actual = s0 == s_act
            if actual and i % 2 == 0:  # la semana en curso queda sin capturar en la mitad de las campañas
                db.add(Semana(campana_id=camp.id, inicio=s0, fin=s0 + dt.timedelta(days=6), editable=True))
            else:
                mensajes = 52 + (i * 7 + k * 11) % 45
                base = 9 + (i * 5 + k * 3) % (14 if tipo == "nacional" else 24)
                costo = Decimal(base) + Decimal((i + k) % 100) / 100
                db.add(Semana(campana_id=camp.id, inicio=s0, fin=s0 + dt.timedelta(days=6), mensajes=mensajes,
                              costo_por_resultado=costo, importe_gastado=(costo * mensajes).quantize(Decimal("0.01")),
                              editable=actual, capturado_por=c.cm_id if c.cm_id in cm_ids else None))
            s0 += dt.timedelta(days=7)
            k += 1

        # mensual del ciclo anterior (el primero de una campaña nueva se captura a mano)
        if i % 3 == 0:
            gasto, mensajes = Decimal(3000 + (i * 130) % 900), 230 + (i * 9) % 60
            costo_pm = (gasto / mensajes).quantize(Decimal("0.01"))
            cfg = rendimiento.buscar_umbral(umbrales, tipo, svc.nombre_paquete(camp))
            db.add(Mensual(campana_id=camp.id, periodo_inicio=inicio - dt.timedelta(days=30),
                           periodo_fin=inicio - dt.timedelta(days=1), mensajes_total=mensajes, gasto_total=gasto,
                           costo_por_mensaje=costo_pm, presupuesto=camp.presupuesto,
                           sobrante=camp.presupuesto - gasto, rendimiento=rendimiento.nivel_ciclo(cfg, float(costo_pm), []),
                           origen="manual" if i % 6 == 0 else "calculado"))
        if i % 3 == 1:
            db.add(Observacion(campana_id=camp.id, texto=OBSERVACIONES[i % 3], autor_id=c.cm_id if c.cm_id in cm_ids else None))
        creadas += 1

    # una campaña que ya llegó a su fecha de renovación: queda 'vencida' con su mensual archivado y el aviso al CM
    candidatos = [c for c in clientes if c.cm_id in cm_ids and not any(k.estado == "vencida" for k in c.campanas)]
    if candidatos:
        c = candidatos[0]
        v = Campana(cliente_id=c.id, nombre="PROMO TEMPORADA", tipo="local", presupuesto=Decimal(3000), formato_post=True,
                    lugar="Culiacán", fecha_inicio=hoy - dt.timedelta(days=31), fecha_renovacion=hoy - dt.timedelta(days=1),
                    estado="activa")
        db.add(v)
        db.flush()
        s0, _ = cal.rango_semana(v.fecha_inicio)
        for k in range(4):
            ini = s0 + dt.timedelta(days=7 * k)
            db.add(Semana(campana_id=v.id, inicio=ini, fin=ini + dt.timedelta(days=6), mensajes=60 + k * 5,
                          costo_por_resultado=Decimal(14 + k), importe_gastado=Decimal((60 + k * 5) * (14 + k)), editable=False))
        db.flush()
        svc.cerrar_ciclo_campana(db, v, hoy)
        creadas += 1
    db.flush()
    return creadas
