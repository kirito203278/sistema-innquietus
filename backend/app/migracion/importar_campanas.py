"""Importa los datos del sistema de CAMPAÑAS antiguo a la plataforma unificada.

Control de Clientes ya es un subconjunto exacto de la plataforma (solo se le aplica la migración 008),
así que esa base se adopta tal cual. Este script trae lo que vivía en la base de Campañas respetando la
FICHA ÚNICA del cliente:

  * usuarios: se emparejan por username; los que no existen se crean con su mismo hash de contraseña.
  * clientes: se emparejan por (CM, nombre) sin importar acentos/mayúsculas. Si el cliente ya existe en
    Control de Clientes, la campaña se cuelga de ESE cliente (no se duplica); si no, se crea.
  * cuenta publicitaria -> credenciales de Facebook del cliente (se descifra con la clave AES ANTIGUA y se
    vuelve a cifrar con la clave de la plataforma). Solo se llenan si el cliente no las tenía.
  * campañas con sus semanas, observaciones y mensuales (el histórico inmutable se conserva).
  * si el cliente está en «No renovados» en la plataforma, sus campañas abiertas quedan «cerradas».

Por defecto SIMULA (no guarda nada). Es idempotente: una campaña ya importada se omite.
No se importan notificaciones ni bitácora del sistema anterior (son efímeras).
"""
import argparse
import base64
import os
import sys
import unicodedata
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.services import cuentas as svc_cuentas
from app.models import ArchivoNoRenovado, Campana, Cliente, Mensual, Observacion, PaqueteCliente, Semana, Usuario
from app.services import ciclos
from app.services.campanas import ABIERTAS


def _norm(t: str) -> str:
    s = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _descifrar(token: str, clave: bytes) -> str:
    raw = base64.b64decode(token)
    return AESGCM(clave).decrypt(raw[:12], raw[12:], None).decode("utf-8")


@dataclass
class Resumen:
    usuarios_creados: int = 0
    usuarios_coincidentes: int = 0
    clientes_creados: int = 0
    clientes_coincidentes: int = 0
    credenciales_copiadas: int = 0
    campanas_importadas: int = 0
    campanas_omitidas_ya_existian: int = 0
    campanas_cerradas_por_no_renovado: int = 0
    semanas: int = 0
    observaciones: int = 0
    mensuales: int = 0
    avisos: list[str] = field(default_factory=list)


def importar(dest: Session, origen_url: str, clave_aes_antigua_b64: str, aplicar: bool = False) -> Resumen:
    clave = base64.b64decode(clave_aes_antigua_b64)
    if len(clave) != 32:
        raise ValueError("La clave AES antigua debe ser de 32 bytes en base64")
    r = Resumen()
    origen = create_engine(origen_url)
    with origen.connect() as sc:
        leer = lambda sql: [dict(f) for f in sc.execute(text(sql)).mappings()]
        u_org, c_org = leer("SELECT * FROM usuarios ORDER BY id"), leer("SELECT * FROM clientes ORDER BY id")
        cuentas_legacy = {c["id"]: c for c in leer("SELECT * FROM cuentas_publicitarias")}
        k_org = leer("SELECT * FROM campanas ORDER BY id")
        semanas = leer("SELECT * FROM semanas ORDER BY campana_id, inicio")
        obs = leer("SELECT * FROM observaciones ORDER BY campana_id, id")
        mens = leer("SELECT * FROM mensuales ORDER BY campana_id, creado_en, id")
        archivo = leer("SELECT * FROM archivo_no_renovados ORDER BY id")

    # ---- usuarios
    por_username = {u.username: u for u in dest.scalars(select(Usuario))}
    mapa_u: dict[int, Usuario] = {}
    for u in u_org:
        d = por_username.get(u["username"])
        if d is None:
            d = Usuario(nombre=u["nombre"], username=u["username"], password_hash=u["password_hash"], rol=u["rol"],
                        solo_lectura=u["solo_lectura"], activo=u["activo"], primer_ingreso=u["primer_ingreso"])
            dest.add(d)
            dest.flush()
            por_username[d.username] = d
            r.usuarios_creados += 1
        else:
            r.usuarios_coincidentes += 1
            if d.rol != u["rol"]:
                r.avisos.append(f"Usuario «{u['username']}»: rol «{u['rol']}» en Campañas y «{d.rol}» en la plataforma; se conserva el de la plataforma.")
        mapa_u[u["id"]] = d

    # ---- clientes (ficha única)
    existentes = list(dest.scalars(select(Cliente)))
    mapa_c: dict[int, Cliente] = {}
    for c in c_org:
        cm = mapa_u[c["cm_id"]]
        clave_c = _norm(c["nombre"])
        candidatos = [e for e in existentes if _norm(e.nombre) == clave_c and e.cm_id == cm.id] \
            or [e for e in existentes if _norm(e.nombre) == clave_c]
        if len(candidatos) > 1:
            r.avisos.append(f"Cliente «{c['nombre']}»: hay {len(candidatos)} coincidencias en la plataforma; se usa la primera. Revísalo.")
        if candidatos:
            cli = candidatos[0]
            r.clientes_coincidentes += 1
            if cli.cm_id != cm.id:
                r.avisos.append(f"Cliente «{c['nombre']}»: lo atiende {cm.username} en Campañas y otro CM en la plataforma; se conserva el de la plataforma.")
        else:
            cli = Cliente(cm_id=cm.id, nombre=c["nombre"].strip(), estado=c["estado"])
            dest.add(cli)
            dest.flush()
            existentes.append(cli)
            r.clientes_creados += 1
            if c["estado"] == "no_renovado":
                for a in [x for x in archivo if x["cliente_id"] == c["id"]]:
                    dest.add(ArchivoNoRenovado(cliente_id=cli.id, cm_id=cm.id, motivo=a["motivo"], archivado_en=a["archivado_en"]))
        for campo in ("tipo_cuenta", "metodo_pago", "forma_pago"):
            if c.get(campo) and not getattr(cli, campo):
                setattr(cli, campo, c[campo])
        cuenta = cuentas_legacy.get(c.get("cuenta_id"))
        if cuenta and not svc_cuentas.correo_de(cli):
            # clientes que en Campañas compartían cuenta terminan en la misma cuenta compartida (mismo CM + correo)
            svc_cuentas.asignar(dest, cli, _descifrar(cuenta["usuario_enc"], clave), _descifrar(cuenta["password_enc"], clave))
            r.credenciales_copiadas += 1
        mapa_c[c["id"]] = cli
    dest.flush()

    # ---- campañas y su histórico
    for k in k_org:
        cli = mapa_c[k["cliente_id"]]
        ya = dest.scalars(select(Campana).where(Campana.cliente_id == cli.id, Campana.fecha_inicio == k["fecha_inicio"])).all()
        if any(_norm(x.nombre) == _norm(k["nombre"]) for x in ya):
            r.campanas_omitidas_ya_existian += 1
            continue
        vigentes = [p for p in dest.scalars(select(PaqueteCliente).where(PaqueteCliente.cliente_id == cli.id)) if p.estado in ciclos.VIGENTES]
        estado = k["estado"]
        if cli.estado == "no_renovado" and estado in ABIERTAS:
            estado = "cerrada"
            r.campanas_cerradas_por_no_renovado += 1
        camp = Campana(cliente_id=cli.id, paquete_cliente_id=vigentes[0].id if len(vigentes) == 1 else None,
                       nombre=k["nombre"], tipo=k["tipo"], presupuesto=k["presupuesto"],
                       presupuesto_esquema=k["presupuesto_esquema"], formato_post=k["formato_post"], formato_3d=k["formato_3d"],
                       formato_boton=k["formato_boton"], formato_otro=k["formato_otro"], lugar=k["lugar"],
                       fecha_inicio=k["fecha_inicio"], fecha_renovacion=k["fecha_renovacion"], estado=estado, creado_en=k["creado_en"])
        dest.add(camp)
        dest.flush()
        r.campanas_importadas += 1
        for s in [x for x in semanas if x["campana_id"] == k["id"]]:
            dest.add(Semana(campana_id=camp.id, inicio=s["inicio"], fin=s["fin"], mensajes=s["mensajes"],
                            costo_por_resultado=s["costo_por_resultado"], importe_gastado=s.get("importe_gastado"),
                            editable=s["editable"], edicion_habilitada_hasta=s.get("edicion_habilitada_hasta"),
                            capturado_por=mapa_u[s["capturado_por"]].id if s["capturado_por"] in mapa_u else None,
                            actualizado_en=s["actualizado_en"]))
            r.semanas += 1
        for o in [x for x in obs if x["campana_id"] == k["id"]]:
            dest.add(Observacion(campana_id=camp.id, texto=o["texto"], creado_en=o["creado_en"],
                                 autor_id=mapa_u[o["autor_id"]].id if o["autor_id"] in mapa_u else None))
            r.observaciones += 1
        for m in [x for x in mens if x["campana_id"] == k["id"]]:
            dest.flush()  # el trigger «manual solo si es el primero» consulta la base
            dest.add(Mensual(campana_id=camp.id, periodo_inicio=m["periodo_inicio"], periodo_fin=m["periodo_fin"],
                             mensajes_total=m["mensajes_total"], gasto_total=m["gasto_total"],
                             costo_por_mensaje=m["costo_por_mensaje"], presupuesto=m["presupuesto"], sobrante=m["sobrante"],
                             rendimiento=m["rendimiento"], origen=m["origen"], creado_en=m["creado_en"]))
            r.mensuales += 1
    dest.flush()
    if aplicar:
        dest.commit()
    else:
        dest.rollback()
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", required=True, help="URL de la base del sistema de Campañas antiguo (postgresql+psycopg2://...)")
    ap.add_argument("--clave-aes-antigua", default=os.getenv("ANTIGUA_AES_KEY_B64"),
                    help="AES_KEY_B64 que usaba Campañas (o variable ANTIGUA_AES_KEY_B64)")
    ap.add_argument("--aplicar", action="store_true", help="Guardar los cambios. Sin esto solo simula y muestra el resumen.")
    args = ap.parse_args(argv)
    if not args.clave_aes_antigua:
        ap.error("falta --clave-aes-antigua (necesaria para re-cifrar las credenciales)")
    from app.database import get_sessionmaker
    with get_sessionmaker()() as db:
        r = importar(db, args.origen, args.clave_aes_antigua, aplicar=args.aplicar)
    print(("APLICADO" if args.aplicar else "SIMULACIÓN (no se guardó nada; usa --aplicar)") + "\n")
    for k, v in vars(r).items():
        if k != "avisos":
            print(f"  {k.replace('_', ' '):38} {v}")
    if r.avisos:
        print("\nAvisos a revisar:")
        for a in r.avisos:
            print("  -", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
