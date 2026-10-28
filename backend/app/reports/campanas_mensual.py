"""Reporte mensual formal (especificación, sección 6): PDF con identidad de
la agencia, pensado para entregarse al cliente final. Consolida por default
todas las campañas del cliente (sección 9-b) — es como el cliente lo entiende,
aunque internamente haya varias campañas o se haya cerrado una y abierto otra
dentro del mismo ciclo.
"""
import datetime as dt
import io
from pathlib import Path

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.consolidacion import MesConsolidado
from app.reports.branding import BAD, BORDER, GOOD, INK, INK_LIGHT, LOGO_PATH, ORANGE, PURPLE, PURPLE_DARK, PURPLE_SOFT, WARN

MESES_LARGO = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


def _nombre_mes(periodo_inicio: dt.date) -> str:
    return f"{MESES_LARGO[periodo_inicio.month - 1]} {periodo_inicio.year}"


def _fmt_dinero(v: float) -> str:
    return f"${v:,.2f}"


def _generar_conclusion(actual: MesConsolidado, anterior: MesConsolidado | None) -> str:
    partes = []

    if actual.rendimiento == 'bueno':
        partes.append(
            f"Este mes la campaña tuvo un buen desempeño: se generaron {actual.mensajes_total} mensajes "
            f"con un costo promedio de {_fmt_dinero(actual.costo_por_mensaje)} por mensaje, dentro de lo esperado."
        )
    elif actual.rendimiento == 'regular':
        partes.append(
            f"Este mes la campaña tuvo un desempeño aceptable, con oportunidad de mejora: se generaron "
            f"{actual.mensajes_total} mensajes con un costo promedio de {_fmt_dinero(actual.costo_por_mensaje)} por "
            f"mensaje. Seguimos ajustando la segmentación y el contenido para mejorar ese costo."
        )
    elif actual.rendimiento == 'bajo':
        partes.append(
            f"Este mes el costo por mensaje estuvo por encima de lo que buscamos "
            f"({_fmt_dinero(actual.costo_por_mensaje)} por mensaje, {actual.mensajes_total} mensajes en total). "
            f"Ya identificamos ajustes concretos y los estamos aplicando para mejorar el resultado del próximo mes."
        )
    else:
        partes.append(
            f"Este mes se generaron {actual.mensajes_total} mensajes con una inversión de "
            f"{_fmt_dinero(actual.gasto_total)}, a un costo promedio de {_fmt_dinero(actual.costo_por_mensaje)} por mensaje."
        )

    if anterior is not None and anterior.mensajes_total > 0:
        cambio_pct = (actual.mensajes_total - anterior.mensajes_total) / anterior.mensajes_total * 100
        if cambio_pct >= 5:
            partes.append(f"Esto es un {cambio_pct:.0f}% más de mensajes que el mes anterior.")
        elif cambio_pct <= -5:
            partes.append(f"Esto es un {abs(cambio_pct):.0f}% menos de mensajes que el mes anterior; lo estamos monitoreando de cerca.")
        else:
            partes.append("Es un resultado similar al del mes anterior.")

    if actual.sobrante >= 0:
        partes.append(
            f"Del presupuesto contratado de {_fmt_dinero(actual.presupuesto)}, se invirtieron "
            f"{_fmt_dinero(actual.gasto_total)} y quedó un remanente de {_fmt_dinero(actual.sobrante)}."
        )
    else:
        partes.append(
            f"Se invirtió el presupuesto contratado de {_fmt_dinero(actual.presupuesto)} en su totalidad, "
            f"con un excedente de {_fmt_dinero(abs(actual.sobrante))}."
        )

    return " ".join(partes)


def _rendimiento_label(r: str | None) -> str:
    return {'bueno': 'Bueno', 'regular': 'Regular', 'bajo': 'Bajo'}.get(r, 'Sin calcular')


def _rendimiento_color(r: str | None):
    return {'bueno': GOOD, 'regular': WARN, 'bajo': BAD}.get(r, INK_LIGHT)


def generar_pdf_reporte_mensual(
    cliente_nombre: str,
    campanas_nombres: list[str],
    meses: list[MesConsolidado],
    output_path: str | Path | io.IOBase,
) -> None:
    """meses: más reciente primero, como los devuelve mensuales_consolidados_de_cliente.
    output_path acepta una ruta o un objeto tipo archivo (p. ej. io.BytesIO) — no
    convertir este último a str, o reportlab escribiría en un nombre de archivo
    literal como "<_io.BytesIO object at ...>" en vez de escribir en el buffer."""
    if not meses:
        raise ValueError("No hay mensuales para generar el reporte")

    actual = meses[0]
    anterior = meses[1] if len(meses) > 1 else None

    destino = output_path if hasattr(output_path, "write") else str(output_path)
    doc = SimpleDocTemplate(
        destino, pagesize=letter,
        topMargin=20 * mm, bottomMargin=18 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleInn', parent=styles['Title'], textColor=PURPLE_DARK, fontSize=19, spaceAfter=2)
    subtitle_style = ParagraphStyle('SubtitleInn', parent=styles['Normal'], textColor=INK_LIGHT, fontSize=11, spaceAfter=4)
    section_style = ParagraphStyle('SectionInn', parent=styles['Heading2'], textColor=PURPLE_DARK, fontSize=13, spaceBefore=18, spaceAfter=8)
    body_style = ParagraphStyle('BodyInn', parent=styles['Normal'], textColor=INK, fontSize=10.5, leading=16)
    stat_label_style = ParagraphStyle('StatLabel', parent=styles['Normal'], textColor=INK_LIGHT, fontSize=9)
    stat_value_style = ParagraphStyle('StatValue', parent=styles['Normal'], textColor=PURPLE_DARK, fontSize=20, fontName='Helvetica-Bold')

    logo = Image(str(LOGO_PATH), width=16 * mm, height=16 * mm) if LOGO_PATH.exists() else Spacer(1, 1)
    encabezado = Table([[logo, Paragraph('INNquietus', title_style)]], colWidths=[20 * mm, None])
    encabezado.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    campanas_txt = ', '.join(campanas_nombres) if len(campanas_nombres) <= 3 else f"{len(campanas_nombres)} campañas"

    story = [
        encabezado,
        Paragraph(f"Reporte mensual — {cliente_nombre}", subtitle_style),
        Paragraph(f"{_nombre_mes(actual.periodo_inicio)} · {campanas_txt}", subtitle_style),
    ]

    # ---------------------------------------------------------- resumen
    story.append(Paragraph('Resumen del mes', section_style))
    stat_table = Table([
        [Paragraph('Mensajes', stat_label_style), Paragraph('Gasto', stat_label_style), Paragraph('Costo por mensaje', stat_label_style)],
        [Paragraph(str(actual.mensajes_total), stat_value_style),
         Paragraph(_fmt_dinero(actual.gasto_total), stat_value_style),
         Paragraph(_fmt_dinero(actual.costo_por_mensaje), stat_value_style)],
    ], colWidths=[55 * mm, 55 * mm, 55 * mm])
    stat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PURPLE_SOFT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(stat_table)

    # ------------------------------------------------- comparación mes anterior
    if anterior is not None:
        story.append(Paragraph('Comparación con el mes anterior', section_style))
        comp_rows = [
            ['', _nombre_mes(anterior.periodo_inicio), _nombre_mes(actual.periodo_inicio)],
            ['Mensajes', str(anterior.mensajes_total), str(actual.mensajes_total)],
            ['Costo por mensaje', _fmt_dinero(anterior.costo_por_mensaje), _fmt_dinero(actual.costo_por_mensaje)],
            ['Gasto total', _fmt_dinero(anterior.gasto_total), _fmt_dinero(actual.gasto_total)],
        ]
        comp_table = Table(comp_rows, colWidths=[45 * mm, 55 * mm, 55 * mm])
        comp_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PURPLE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PURPLE_SOFT]),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(comp_table)

    # --------------------------------------------------------- presupuesto
    story.append(Paragraph('Presupuesto contratado vs. consumido', section_style))
    pct_consumido = min(100, (actual.gasto_total / actual.presupuesto * 100) if actual.presupuesto else 0)
    barra = Drawing(360, 26)
    barra.add(_barra_presupuesto(pct_consumido))
    story.append(barra)
    presupuesto_rows = [['Presupuesto contratado', 'Consumido', 'Sobrante']]
    presupuesto_rows.append([_fmt_dinero(actual.presupuesto), _fmt_dinero(actual.gasto_total), _fmt_dinero(actual.sobrante)])
    presupuesto_table = Table(presupuesto_rows, colWidths=[55 * mm, 55 * mm, 55 * mm])
    presupuesto_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, 0), INK_LIGHT), ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, 1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(presupuesto_table)

    # --------------------------------------------------------------- gráfica
    if len(meses) > 1:
        story.append(Paragraph('Mensajes por mes', section_style))
        story.append(_grafica_mensual(meses))

    # ------------------------------------------------------------ conclusión
    story.append(KeepTogether([
        Paragraph('En resumen', section_style),
        Paragraph(_generar_conclusion(actual, anterior), body_style),
    ]))

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFillColor(ORANGE)
        canvas.rect(0, 0, doc_.pagesize[0], 4, fill=1, stroke=0)
        canvas.setFillColor(INK_LIGHT)
        canvas.setFont('Helvetica', 8)
        canvas.drawString(20 * mm, 10 * mm, f"INNquietus · Reporte generado el {dt.date.today().strftime('%d/%m/%Y')}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


def _barra_presupuesto(pct_consumido: float) -> Drawing:
    from reportlab.graphics.shapes import Rect
    ancho_total = 360
    alto = 16
    d = Drawing(ancho_total, 26)
    d.add(Rect(0, 4, ancho_total, alto, fillColor=PURPLE_SOFT, strokeColor=BORDER, strokeWidth=0.5, rx=4, ry=4))
    ancho_consumido = ancho_total * (pct_consumido / 100)
    color = GOOD if pct_consumido < 85 else (WARN if pct_consumido < 100 else BAD)
    if ancho_consumido > 2:
        d.add(Rect(0, 4, ancho_consumido, alto, fillColor=color, strokeColor=None, rx=4, ry=4))
    d.add(String(ancho_total, alto + 10, f"{pct_consumido:.0f}% consumido", fontSize=8, fillColor=INK_LIGHT, textAnchor='end'))
    return d


def _grafica_mensual(meses: list[MesConsolidado]) -> Drawing:
    ordenados = list(reversed(meses))  # más antiguo primero, para leer izquierda -> derecha
    valores = [m.mensajes_total for m in ordenados]
    etiquetas = [_nombre_mes(m.periodo_inicio).split(' ')[0][:3] for m in ordenados]

    d = Drawing(360, 140)
    chart = VerticalBarChart()
    chart.x = 30
    chart.y = 20
    chart.width = 300
    chart.height = 100
    chart.data = [valores]
    chart.categoryAxis.categoryNames = etiquetas
    chart.categoryAxis.labels.fontSize = 9
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = PURPLE
    chart.barWidth = 10
    chart.groupSpacing = 20
    chart.barLabels.fontSize = 8
    chart.barLabelFormat = '%d'
    chart.barLabels.nudge = 8
    d.add(chart)
    return d
