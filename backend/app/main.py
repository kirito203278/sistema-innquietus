from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import (admin, auth, campanas, catalogos, clientes, ingresos, jobs, notificaciones, paquetes,
                         renovacion, reportes, usuarios)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.scheduler_enabled:
        start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="INNquietus · Plataforma", lifespan=lifespan,
              docs_url="/docs" if settings.enable_docs else None, redoc_url=None,
              openapi_url="/openapi.json" if settings.enable_docs else None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def cabeceras_de_seguridad(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


for r in (auth.router, usuarios.router, catalogos.router, admin.router, clientes.router, paquetes.router,
          renovacion.router, notificaciones.router, jobs.router, ingresos.router, reportes.router, campanas.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"ok": True}


STATIC = Path(__file__).parent / "static"
if (STATIC / "index.html").exists():
    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        if ruta.startswith("api/"):
            raise HTTPException(404, "No encontrado")
        archivo = (STATIC / ruta).resolve()
        if ruta and archivo.is_file() and STATIC.resolve() in archivo.parents:
            return FileResponse(archivo)
        return FileResponse(STATIC / "index.html")
