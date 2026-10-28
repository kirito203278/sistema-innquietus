from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dates import ahora
from app.deps import require_admin
from app.models import Usuario
from app.reports.excel import generar_excel
from app.reports.pdf import generar_pdf
from app.routers.ingresos import resolver_periodo
from app.services import reporte_datos

router = APIRouter(prefix="/api/reportes", tags=["reportes"])
NOMBRE_Q = {"1": "1ra-quincena", "2": "2da-quincena", "ambas": "mes-completo"}


def _datos(db, user, anio, mes, quincena, cm_id):
    hoy, per = resolver_periodo(anio, mes, quincena)
    return reporte_datos.construir(db, user, per, hoy, cm_id), per


@router.get("/datos")
def datos(anio: int | None = None, mes: int | None = None, quincena: str | None = None, cm_id: int | None = None,
          db: Session = Depends(get_db), user: Usuario = Depends(require_admin)):
    return _datos(db, user, anio, mes, quincena, cm_id)[0]


@router.get("/pdf")
def pdf(anio: int | None = None, mes: int | None = None, quincena: str | None = None, cm_id: int | None = None,
        db: Session = Depends(get_db), user: Usuario = Depends(require_admin)):
    d, per = _datos(db, user, anio, mes, quincena, cm_id)
    nombre = f"reporte-{per.anio}-{per.mes:02d}-{NOMBRE_Q[per.quincena]}.pdf"
    return Response(generar_pdf(d, ahora()), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/excel")
def excel(anio: int | None = None, mes: int | None = None, quincena: str | None = None, cm_id: int | None = None,
          db: Session = Depends(get_db), user: Usuario = Depends(require_admin)):
    d, per = _datos(db, user, anio, mes, quincena, cm_id)
    nombre = f"reporte-{per.anio}-{per.mes:02d}-{NOMBRE_Q[per.quincena]}.xlsx"
    return Response(generar_excel(d, ahora()),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
