import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import bitacora
from app.config import get_settings
from app.dates import ahora, hoy as hoy_mx
from app.models import ArchivoNoRenovado, Campana, Cliente, PaqueteCliente, Renovacion, Usuario
from app.services import campanas as svc_campanas, ciclos, notificar
from app.services.catalogos import validar_catalogos
from app.services.periodos import restar_meses

TIPOS_AVISO = ("renovacion_3d", "paquete_vencido")


def _validar_cambio_catalogo(db: Session, p: PaqueteCliente, paquete_id: int, tipo_id: int) -> None:
    from app.models import CatalogoPaquete, CatalogoTipo
    if paquete_id != p.paquete_id:
        pq = db.get(CatalogoPaquete, paquete_id)
        if pq is None or not pq.activo:
            raise HTTPException(422, "Paquete inválido o desactivado")
    if tipo_id != p.tipo_id:
        tp = db.get(CatalogoTipo, tipo_id)
        if tp is None or not tp.activo:
            raise HTTPException(422, "Tipo inválido o desactivado")


def vigentes_del_cliente(db: Session, cliente_id: int, excepto: int | None = None) -> int:
    q = select(PaqueteCliente.id).where(PaqueteCliente.cliente_id == cliente_id,
                                        PaqueteCliente.estado.in_(ciclos.VIGENTES))
    if excepto is not None:
        q = q.where(PaqueteCliente.id != excepto)
    return len(db.scalars(q).all())


def enviar_a_no_renovados(db: Session, cliente: Cliente, motivo: str) -> None:
    cliente.estado = "no_renovado"
    db.add(ArchivoNoRenovado(cliente_id=cliente.id, cm_id=cliente.cm_id, motivo=motivo, archivado_en=ahora()))
    svc_campanas.cerrar_abiertas_de_cliente(db, cliente)  # sus campañas terminan; el histórico se conserva


def archivar(db: Session, p: PaqueteCliente, motivo: str) -> bool:
    es_ultimo = vigentes_del_cliente(db, p.cliente_id, excepto=p.id) == 0
    p.estado, p.renovacion_decision, p.archivado_en = "archivado", "no", ahora()
    notificar.marcar_leidas_de_paquete(db, p.id, TIPOS_AVISO)
    if es_ultimo and p.cliente.estado == "activo":
        enviar_a_no_renovados(db, p.cliente, motivo)
        return True
    return False


def renovar(db: Session, user: Usuario, p: PaqueteCliente, *, paquete_id: int | None, tipo_id: int | None,
            costo: Decimal | None) -> PaqueteCliente:
    if p.estado not in ciclos.VIGENTES:
        raise HTTPException(409, "Este paquete ya no está vigente")
    if p.cliente.estado != "activo":
        raise HTTPException(409, "El cliente está en No renovados: usa el reingreso")
    if not ciclos.pagado_completo(p):
        raise HTTPException(422, "Solo se puede registrar la renovación cuando el paquete está pagado por completo. "
                                 "Si el cliente aún debe, solicita una prórroga o márcalo como no renovado.")
    nuevo_pq = paquete_id or p.renovara_paquete_id or p.paquete_id
    nuevo_tp = tipo_id or p.renovara_tipo_id or p.tipo_id
    _validar_cambio_catalogo(db, p, nuevo_pq, nuevo_tp)
    if costo is not None:
        nuevo_costo = costo
    else:
        nuevo_costo = p.renovara_costo if p.renovara_costo is not None else p.costo
    hoy = hoy_mx()
    if p.prorroga_hasta is not None:
        inicio = p.fecha_renovacion
    else:
        inicio = min(p.confirmado_en or hoy, hoy)
    nuevo = PaqueteCliente(cliente_id=p.cliente_id, paquete_id=nuevo_pq, tipo_id=nuevo_tp, costo=nuevo_costo,
                           fecha_inicio=inicio, fecha_renovacion=inicio + dt.timedelta(days=get_settings().ciclo_dias),
                           ciclo_anterior_id=p.id)
    p.estado, p.renovacion_decision = "renovado", "si"
    db.add(nuevo)
    db.flush()
    ciclos.recalcular_pagada(p)
    db.add(Renovacion(ciclo_anterior_id=p.id, ciclo_nuevo_id=nuevo.id, paquete_anterior_id=p.paquete_id,
                      paquete_nuevo_id=nuevo_pq, costo_anterior=p.costo, costo_nuevo=nuevo_costo,
                      fecha=hoy, registrado_por=user.id))
    notificar.marcar_leidas_de_paquete(db, p.id, TIPOS_AVISO)
    bitacora.registrar_si_admin(db, user, "renovar_por_admin", {"paquete_id": p.id, "nuevo_id": nuevo.id})
    db.flush()
    db.refresh(nuevo)
    return nuevo


def confirmar_renovacion(db: Session, user: Usuario, p: PaqueteCliente, *, paquete_id: int | None = None,
                         tipo_id: int | None = None, costo: Decimal | None = None) -> PaqueteCliente | None:
    if p.estado not in ciclos.VIGENTES or p.cliente.estado != "activo":
        raise HTTPException(409, "Este paquete ya no está vigente")
    if p.renovacion_decision == "no":
        raise HTTPException(409, "Está marcado como «no renovará»: deshaz esa marca primero")
    hoy = hoy_mx()
    if paquete_id or tipo_id or costo is not None:
        _validar_cambio_catalogo(db, p, paquete_id or p.paquete_id, tipo_id or p.tipo_id)
        cambia = (paquete_id and paquete_id != p.paquete_id) or (tipo_id and tipo_id != p.tipo_id) or \
            (costo is not None and costo != p.costo)
        p.renovara_paquete_id = paquete_id if cambia else None
        p.renovara_tipo_id = tipo_id if cambia else None
        p.renovara_costo = costo if cambia else None
    if ciclos.pagado_completo(p):
        return renovar(db, user, p, paquete_id=None, tipo_id=None, costo=None)
    if p.renovacion_decision == "si" and not ciclos.bloqueado(p, hoy):
        return None
    if p.renovacion_decision == "si" and ciclos.bloqueado(p, hoy):
        raise HTTPException(409, "Ya confirmaste la renovación y sigue sin pagar: solicita la prórroga o marca que no renovó")
    en_ventana = ciclos.es_vencido(p, hoy)
    p.renovacion_decision = "si"
    p.confirmado_en = hoy
    if en_ventana:
        p.gracia_hasta = hoy
    notificar.marcar_leidas_de_paquete(db, p.id, TIPOS_AVISO)
    bitacora.registrar(db, user, "confirmar_renovacion", {"paquete_id": p.id, "en_ventana": en_ventana,
                                                          "gracia_hasta": str(p.gracia_hasta) if p.gracia_hasta else None})
    db.flush()
    return None


def renovar_si_confirmado_y_pagado(db: Session, user: Usuario, p: PaqueteCliente) -> PaqueteCliente | None:
    if confirmo_renovacion_activa(p) and ciclos.pagado_completo(p):
        return renovar(db, user, p, paquete_id=None, tipo_id=None, costo=None)
    return None


def confirmo_renovacion_activa(p: PaqueteCliente) -> bool:
    return p.estado in ciclos.VIGENTES and p.renovacion_decision == "si"


def solicitar_prorroga(db: Session, user: Usuario, p: PaqueteCliente) -> PaqueteCliente:
    hoy = hoy_mx()
    if not ciclos.es_vencido(p, hoy):
        raise HTTPException(422, "La prórroga solo se solicita cuando ya pasó la fecha de renovación sin pagar")
    if p.renovacion_decision != "si":
        raise HTTPException(422, "Primero confirma que el cliente va a renovar; la prórroga se pide si aún no ha pagado")
    if ciclos.pagado_completo(p):
        raise HTTPException(422, "El paquete no tiene saldo pendiente: no necesita prórroga")
    if p.prorroga_hasta is not None:
        raise HTTPException(409, "Este paquete ya usó su prórroga")
    p.prorroga_registrada_en = hoy
    p.prorroga_hasta = hoy + dt.timedelta(days=get_settings().prorroga_max_dias)
    p.gracia_hasta = None
    notificar.marcar_leidas_de_paquete(db, p.id, TIPOS_AVISO)
    bitacora.registrar(db, user, "prorroga_solicitada", {"paquete_id": p.id, "hasta": str(p.prorroga_hasta)})
    db.flush()
    return p


def no_renovar(db: Session, user: Usuario, p: PaqueteCliente, *, accion: str, confirmar_nombre: str | None,
               eliminar_cliente: bool | None) -> dict:
    if p.estado not in ciclos.VIGENTES:
        raise HTTPException(409, "Este paquete ya no está vigente")
    cliente, hoy = p.cliente, hoy_mx()
    es_ultimo = vigentes_del_cliente(db, cliente.id, excepto=p.id) == 0
    if accion == "borrar" and user.rol != "admin":
        raise HTTPException(403, "Borrar el paquete y eliminar al cliente solo lo hace un administrador, y desde "
                                 "No renovados. Marca «no renovó» para conservar su información.")
    if accion == "borrar":
        if confirmar_nombre != p.paquete.nombre:
            raise HTTPException(422, f"Escribe el nombre exacto del paquete ({p.paquete.nombre}) para confirmar")
        if es_ultimo and eliminar_cliente is None:
            raise HTTPException(409, {"code": "ultimo_paquete",
                                      "mensaje": "Es el último paquete del cliente: ¿también se elimina el cliente?"})
    elif accion != "conservar":
        raise HTTPException(422, "accion debe ser 'conservar' o 'borrar'")

    detalle = {"paquete_id": p.id, "cliente_id": cliente.id, "accion": accion}
    if accion == "conservar" and hoy <= p.fecha_renovacion:
        p.renovacion_decision = "no"
        notificar.marcar_leidas_de_paquete(db, p.id, TIPOS_AVISO)
        bitacora.registrar(db, user, "programar_no_renovara", detalle)
        db.flush()
        return {"cliente_eliminado": False, "cliente_a_no_renovados": False, "programado": True,
                "se_archiva_el": p.fecha_renovacion + dt.timedelta(days=1)}

    if accion == "borrar" and es_ultimo and eliminar_cliente:
        bitacora.registrar(db, user, "borrar_paquete_y_cliente", {**detalle, "nombre": cliente.nombre})
        db.delete(cliente)
        db.flush()
        return {"cliente_eliminado": True, "cliente_a_no_renovados": False, "programado": False}

    if accion == "conservar":
        a_no_ren = archivar(db, p, "Decidió no renovar")
    else:
        p.estado, p.renovacion_decision, p.archivado_en = "eliminado", "no", ahora()
        notificar.marcar_leidas_de_paquete(db, p.id, TIPOS_AVISO)
        a_no_ren = False
        if es_ultimo:
            enviar_a_no_renovados(db, cliente, "Paquete eliminado")
            a_no_ren = True
    bitacora.registrar(db, user, "no_renovar" if accion == "conservar" else "borrar_paquete",
                       {**detalle, "cliente_a_no_renovados": a_no_ren})
    db.flush()
    return {"cliente_eliminado": False, "cliente_a_no_renovados": a_no_ren, "programado": False}


def revertir_decision(db: Session, user: Usuario, p: PaqueteCliente) -> None:
    if p.estado != "activo" or p.renovacion_decision not in ("no", "si") or hoy_mx() > p.fecha_renovacion:
        raise HTTPException(409, "No hay una marca que se pueda deshacer en este paquete")
    anterior = p.renovacion_decision
    p.renovacion_decision = "pendiente"
    p.confirmado_en = None
    p.gracia_hasta = None
    p.renovara_paquete_id = p.renovara_tipo_id = p.renovara_costo = None
    bitacora.registrar(db, user, "revertir_decision", {"paquete_id": p.id, "era": anterior})
    db.flush()


def reingresar(db: Session, user: Usuario, cliente: Cliente, *, modo: str, paquete_id: int | None,
               tipo_id: int | None, costo: Decimal | None) -> PaqueteCliente:
    s = get_settings()
    if cliente.estado != "no_renovado":
        raise HTTPException(409, "El cliente no está en No renovados")
    archivo = db.scalars(select(ArchivoNoRenovado).where(
        ArchivoNoRenovado.cliente_id == cliente.id, ArchivoNoRenovado.reingresado_en.is_(None))
        .order_by(ArchivoNoRenovado.archivado_en.desc())).first()
    if modo not in ("continuar", "nuevo"):
        raise HTTPException(422, "modo debe ser 'continuar' o 'nuevo'")
    ahora_ = ahora()
    forzar_nuevo = archivo is not None and archivo.archivado_en <= restar_meses(ahora_, s.reingreso_meses)
    hoy = hoy_mx()

    if costo is None or user.rol != "admin":
        costo = None

    def costo_catalogo(pq_id: int | None):
        from app.models import CatalogoPaquete
        pq = db.get(CatalogoPaquete, pq_id) if pq_id is not None else None
        return pq.costo if pq is not None else None

    anterior = None
    if forzar_nuevo:
        if modo == "continuar":
            raise HTTPException(422, f"Pasaron {s.reingreso_meses} meses o más: debes crear un paquete nuevo "
                                     "(el historial anterior se borrará)")
        costo = costo if costo is not None else costo_catalogo(paquete_id)
        if paquete_id is None or tipo_id is None or costo is None:
            raise HTTPException(422, "Indica paquete y tipo del paquete nuevo")
        db.execute(delete(PaqueteCliente).where(PaqueteCliente.cliente_id == cliente.id))
        db.execute(delete(Campana).where(Campana.cliente_id == cliente.id))  # «borrón y cuenta nueva» incluye campañas
        db.expire(cliente, ["paquetes", "campanas"])
        historial_borrado = True
    else:
        historial_borrado = False
        if modo == "continuar":
            anterior = db.scalars(select(PaqueteCliente).where(
                PaqueteCliente.cliente_id == cliente.id, PaqueteCliente.estado == "archivado")
                .order_by(PaqueteCliente.archivado_en.desc())).first()
            if anterior is None:
                raise HTTPException(422, "No hay un paquete anterior que continuar: crea uno nuevo")
            paquete_id, tipo_id = anterior.paquete_id, anterior.tipo_id
            costo = anterior.costo if costo is None else costo
        else:
            costo = costo if costo is not None else costo_catalogo(paquete_id)
            if paquete_id is None or tipo_id is None or costo is None:
                raise HTTPException(422, "Indica paquete y tipo del paquete nuevo")

    if not (modo == "continuar" and anterior is not None):
        validar_catalogos(db, paquete_id, tipo_id)
    nuevo = PaqueteCliente(cliente_id=cliente.id, paquete_id=paquete_id, tipo_id=tipo_id, costo=costo,
                           fecha_inicio=hoy, fecha_renovacion=hoy + dt.timedelta(days=s.ciclo_dias),
                           ciclo_anterior_id=anterior.id if anterior else None)
    db.add(nuevo)
    cliente.estado = "activo"
    if archivo is not None:
        archivo.reingresado_en = ahora_
    bitacora.registrar(db, user, "reingreso", {"cliente_id": cliente.id, "modo": modo,
                                               "historial_borrado": historial_borrado})
    db.flush()
    db.refresh(nuevo)
    return nuevo


def purgar_no_renovados(db: Session, ahora_: dt.datetime | None = None) -> list[str]:
    ahora_ = ahora_ or ahora()
    limite = restar_meses(ahora_, get_settings().purga_meses)
    filas = db.execute(select(ArchivoNoRenovado, Cliente).join(Cliente, Cliente.id == ArchivoNoRenovado.cliente_id)
                       .where(ArchivoNoRenovado.reingresado_en.is_(None), ArchivoNoRenovado.archivado_en <= limite,
                              Cliente.estado == "no_renovado")).all()
    eliminados = []
    for archivo, cliente in filas:
        if vigentes_del_cliente(db, cliente.id) > 0:
            continue
        eliminados.append(cliente.nombre)
        bitacora.registrar(db, None, "purga_no_renovados", {"cliente_id": cliente.id, "nombre": cliente.nombre,
                                                            "archivado_en": archivo.archivado_en.isoformat()})
        db.delete(cliente)
    db.flush()
    return eliminados
