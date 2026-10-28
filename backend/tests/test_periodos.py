import datetime as dt

import pytest

from app.services.periodos import construir_periodo, quincena_de, restar_meses

D = dt.date


@pytest.mark.parametrize("anio,mes,ultimo", [(2026, 2, 28), (2028, 2, 29), (2100, 2, 28), (2026, 4, 30), (2026, 10, 31),
                                              (2026, 1, 31), (2026, 6, 30), (2026, 12, 31)])
def test_2da_quincena_termina_el_ultimo_dia_real_del_mes(anio, mes, ultimo):
    hoy = D(2200, 1, 1)
    q2 = construir_periodo(anio, mes, "2", hoy)
    assert (q2.desde, q2.hasta) == (D(anio, mes, 16), D(anio, mes, ultimo))
    assert construir_periodo(anio, mes, "ambas", hoy).hasta == D(anio, mes, ultimo)
    assert construir_periodo(anio, mes, "1", hoy).hasta == D(anio, mes, 15)


def test_la_1ra_quincena_siempre_es_1_a_15_y_las_dos_no_se_traslapan():
    q1, q2 = construir_periodo(2026, 2, "1", D(2027, 1, 1)), construir_periodo(2026, 2, "2", D(2027, 1, 1))
    assert (q1.desde, q1.hasta) == (D(2026, 2, 1), D(2026, 2, 15)) and q2.desde == q1.hasta + dt.timedelta(days=1)


@pytest.mark.parametrize("dia,q", [(1, 1), (15, 1), (16, 2), (28, 2), (31, 2)])
def test_quincena_de_una_fecha(dia, q):
    assert quincena_de(D(2026, 1, dia)) == q


def test_periodo_cerrado_se_reporta_completo():
    p = construir_periodo(2026, 9, "ambas", D(2026, 10, 1))
    assert p.cerrado and p.estado_texto == "Periodo cerrado"


def test_periodo_en_curso_es_parcial_con_corte_a_hoy():
    p = construir_periodo(2026, 10, "ambas", D(2026, 10, 12))
    assert not p.cerrado and p.corte == D(2026, 10, 12) and p.hasta == D(2026, 10, 31)
    assert p.estado_texto == "Periodo parcial, corte al 12/10/2026"


def test_quincena_a_medias_y_ultimo_dia_aun_es_parcial():
    assert not construir_periodo(2026, 10, "1", D(2026, 10, 15)).cerrado
    assert construir_periodo(2026, 10, "1", D(2026, 10, 16)).cerrado
    assert not construir_periodo(2026, 10, "2", D(2026, 10, 31)).cerrado
    assert construir_periodo(2026, 10, "2", D(2026, 11, 1)).cerrado


def test_1ra_quincena_cerrada_mientras_el_mes_sigue_en_curso():
    hoy = D(2026, 10, 20)
    assert construir_periodo(2026, 10, "1", hoy).cerrado
    assert not construir_periodo(2026, 10, "2", hoy).cerrado
    assert not construir_periodo(2026, 10, "ambas", hoy).cerrado


def test_periodo_futuro_es_parcial():
    p = construir_periodo(2027, 1, "ambas", D(2026, 10, 1))
    assert not p.cerrado and p.corte == D(2026, 10, 1)


def test_validaciones():
    for args in ((2026, 13, "1"), (2026, 0, "1"), (2026, 5, "3"), (1999, 5, "1")):
        with pytest.raises(ValueError):
            construir_periodo(*args, D(2026, 1, 1))


def test_restar_meses_ajusta_fin_de_mes():
    tz = dt.timezone.utc
    assert restar_meses(dt.datetime(2026, 3, 31, tzinfo=tz), 1) == dt.datetime(2026, 2, 28, tzinfo=tz)
    assert restar_meses(dt.datetime(2028, 3, 31, tzinfo=tz), 1) == dt.datetime(2028, 2, 29, tzinfo=tz)
    assert restar_meses(dt.datetime(2026, 1, 15, tzinfo=tz), 2) == dt.datetime(2025, 11, 15, tzinfo=tz)
    assert restar_meses(dt.datetime(2026, 10, 1, tzinfo=tz), 3) == dt.datetime(2026, 7, 1, tzinfo=tz)
