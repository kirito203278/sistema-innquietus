from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import Bitacora, Usuario

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/bitacora")
def bitacora_lista(limite: int = 200, db: Session = Depends(get_db), _=Depends(require_admin)):
    filas = db.execute(select(Bitacora, Usuario.username).outerjoin(Usuario, Usuario.id == Bitacora.usuario_id)
                       .order_by(Bitacora.id.desc()).limit(min(limite, 1000))).all()
    return [{"id": b.id, "usuario": u or "sistema", "accion": b.accion, "detalle": b.detalle, "creado_en": b.creado_en}
            for b, u in filas]
