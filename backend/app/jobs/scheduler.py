import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.jobs import tareas

log = logging.getLogger("jobs.scheduler")
_scheduler: BackgroundScheduler | None = None

# (hora, minuto, día de la semana o None = todos). Zona horaria del negocio.
HORARIOS = {
    "renovaciones": [(0, 5, None), (12, 0, None)],
    "prorrogas": [(0, 5, None), (12, 0, None)],
    "purga_no_renovados": [(12, 10, None)],
    "cierre_semana": [(0, 0, "sat")],           # bloquea la semana que terminó y abre la nueva
    "recordatorio_captura": [(14, 0, "fri")],   # aviso a los CM con semanas sin capturar
    "cierre_ciclo_campanas": [(12, 0, None)],   # campañas cuya fecha de renovación llegó
}


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    tz = ZoneInfo(get_settings().tz)
    s = BackgroundScheduler(timezone=tz)
    for nombre, horas in HORARIOS.items():
        trigger = OrTrigger([CronTrigger(hour=h, minute=m, day_of_week=d, timezone=tz) for h, m, d in horas])
        s.add_job(tareas.ejecutar, trigger, args=[nombre, "scheduler"], id=nombre, replace_existing=True,
                  misfire_grace_time=3600, coalesce=True)
    s.start()
    _scheduler = s
    log.info("Scheduler iniciado (tz=%s)", get_settings().tz)
    return s


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
