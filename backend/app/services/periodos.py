import calendar
import datetime as dt
from dataclasses import dataclass

QUINCENAS = ("1", "2", "ambas")


def quincena_de(fecha: dt.date) -> int:
    return 1 if fecha.day <= 15 else 2


def ultimo_dia(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


@dataclass(frozen=True)
class Periodo:
    anio: int
    mes: int
    quincena: str
    desde: dt.date
    hasta: dt.date
    corte: dt.date
    cerrado: bool

    @property
    def etiqueta(self) -> str:
        q = {"1": "1ra quincena", "2": "2da quincena", "ambas": "Mes completo"}[self.quincena]
        return f"{q} de {MESES[self.mes - 1]} {self.anio}"

    @property
    def estado_texto(self) -> str:
        return "Periodo cerrado" if self.cerrado else f"Periodo parcial, corte al {self.corte.strftime('%d/%m/%Y')}"


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def construir_periodo(anio: int, mes: int, quincena: str, hoy: dt.date) -> Periodo:
    if quincena not in QUINCENAS:
        raise ValueError("quincena debe ser '1', '2' o 'ambas'")
    if not 1 <= mes <= 12 or not 2000 <= anio <= 2100:
        raise ValueError("mes/año fuera de rango")
    fin_mes = ultimo_dia(anio, mes)
    desde, hasta = {"1": (1, 15), "2": (16, fin_mes), "ambas": (1, fin_mes)}[quincena]
    desde_f, hasta_f = dt.date(anio, mes, desde), dt.date(anio, mes, hasta)
    cerrado = hoy > hasta_f
    return Periodo(anio, mes, quincena, desde_f, hasta_f, hoy, cerrado)


def sumar_dias(fecha: dt.date, dias: int) -> dt.date:
    return fecha + dt.timedelta(days=dias)


def restar_meses(momento: dt.datetime, meses: int) -> dt.datetime:
    total = momento.year * 12 + (momento.month - 1) - meses
    anio, mes = divmod(total, 12)
    mes += 1
    return momento.replace(year=anio, month=mes, day=min(momento.day, ultimo_dia(anio, mes)))
