from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dates import hoy as hoy_mx
from app.deps import require_admin
from app.models import Usuario
from app.services import reporte_datos
from app.services.periodos import construir_periodo, quincena_de

router = APIRouter(prefix="/api", tags=["ingresos"])


def resolver_periodo(anio: int | None, mes: int | None, quincena: str | None):
    hoy = hoy_mx()
    try:
        return hoy, construir_periodo(anio or hoy.year, mes or hoy.month, quincena or str(quincena_de(hoy)), hoy)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/ingresos")
def ingresos(anio: int | None = None, mes: int | None = None, quincena: str | None = None, cm_id: int | None = None,
             db: Session = Depends(get_db), user: Usuario = Depends(require_admin)):
    hoy, per = resolver_periodo(anio, mes, quincena)
    datos = reporte_datos.construir(db, user, per, hoy, cm_id)
    salida = {"periodo": datos["periodo"], "totales": datos["resumen"],
              "clientes": reporte_datos.ingresos_por_cliente(datos)}
    if user.rol == "admin":
        salida.update(por_cm=datos["por_cm"], total_general=datos["total_cm"], tasa_renovacion=datos["tasa_renovacion"],
                      tasa_total=datos["tasa_total"])
    else:
        salida["tasa_total"] = datos["tasa_total"]
    return salida
