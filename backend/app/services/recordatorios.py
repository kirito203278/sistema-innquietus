import datetime as dt
import re
from decimal import Decimal
from urllib.parse import quote

from app.config import get_settings


def normalizar_telefono(telefono: str | None) -> str | None:
    if not telefono:
        return None
    d = re.sub(r"\D", "", telefono)
    if len(d) == 10:
        return "52" + d
    if len(d) == 13 and d.startswith("521"):
        return "52" + d[3:]
    if len(d) == 12 and d.startswith("52"):
        return d
    return d if len(d) >= 11 else None


def armar_texto(cliente_nombre: str, paquete: str, restante: Decimal, fecha_limite: dt.date | None) -> str:
    agencia = get_settings().agencia_nombre
    plazo = f" El plazo acordado venció el {fecha_limite.strftime('%d/%m/%Y')}." if fecha_limite else ""
    return (f"Hola, {cliente_nombre}. Te escribimos de {agencia}. Te recordamos que tu paquete {paquete} "
            f"tiene un saldo pendiente de ${restante:,.2f}.{plazo} ¿Nos confirmas cuándo podrías realizar "
            f"tu pago? Si ya lo hiciste, ¡mil gracias y perdona la molestia!")


def wa_url(telefono: str | None, texto: str) -> str | None:
    tel = normalizar_telefono(telefono)
    return f"https://wa.me/{tel}?text={quote(texto)}" if tel else None


def crear_para_paquete(db, p, cm_id):
    from sqlalchemy import select

    from app.models import RecordatorioCliente
    from app.services import ciclos

    previos = db.scalars(select(RecordatorioCliente).where(RecordatorioCliente.paquete_id == p.id)
                         .order_by(RecordatorioCliente.id.desc())).all()
    if any(r.enviado_en for r in previos):
        raise YaEnviado()
    if previos:
        return previos[0], False
    restante = p.costo - ciclos.pagado_hasta(p)
    texto = armar_texto(p.cliente.nombre, p.paquete.nombre, restante, p.prorroga_hasta)
    r = RecordatorioCliente(paquete_id=p.id, cliente_id=p.cliente_id, cm_id=cm_id,
                            telefono_destino=normalizar_telefono(p.cliente.telefono), texto=texto)
    db.add(r)
    db.flush()
    return r, True


class YaEnviado(Exception):
    pass
