"""Reporte semanal en PDF, en lenguaje para el cliente final — pedido además
del reporte mensual formal (especificación, sección 6). Consolida por
default todas las campañas activas del cliente (sección 9-b), igual que el
mensual. No usa el semáforo bueno/regular/bajo: cuando se consolidan varias
campañas de distinto tipo (local/nacional), cada una tiene su propio umbral,
así que un semáforo único perdería sentido; en su lugar describe la
tendencia contra la semana anterior en español llano.
"""
import datetime as dt
from pathlib import Path

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.consolidacion import SemanaConsolidada as SemanaConsolidadaData
from app.reports.branding import BORDER, INK, INK_LIGHT, LOGO_PATH, PURPLE, PURPLE_DARK, PURPLE_SOFT, ORANGE


def _fmt_dinero(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_fecha(d: dt.date) -> str:
    return d.strftime("%d/%m/%Y")


def _generar_conclusion(actual: SemanaConsolidadaData, anterior: SemanaConsolidadaData | None) -> str:
    partes = [
        f"Esta semana se generaron {actual.mensajes} mensajes"
        + (f", con una inversión de {_fmt_dinero(actual.importe_gastado)}" if actual.importe_gastado else "")
        + (f" (costo promedio de {_fmt_dinero(actual.costo_por_resultado)} por mensaje)." if actual.costo_por_resultado else ".")
    ]

    if anterior is not None and anterior.mensajes > 0:
        cambio_pct = (actual.mensajes - anterior.mensajes) / anterior.mensajes * 100
        if cambio_pct >= 5:
            partes.append(f"Son {cambio_pct:.0f}% más mensajes que la semana pasada.")
        elif cambio_pct <= -5:
            partes.append(f"Son {abs(cambio_pct):.0f}% menos mensajes que la semana pasada; lo seguimos de cerca.")
        else:
            partes.append("Un resultado similar al de la semana pasada.")

    return " ".join(partes)


def generar_pdf_reporte_semanal(
    cliente_nombre: str,
    campanas_nombres: list[str],
    semanas: list[SemanaConsolidadaData],
    output_path,
) -> None:
    """semanas: en orden cronológico ascendente (más reciente al final), como
    las devuelve semanas_consolidadas_de_cliente."""
    if not semanas:
        raise ValueError("No hay semanas para generar el reporte")

    actual = semanas[-1]
    anterior = semanas[-2] if len(semanas) > 1 else None

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
        Paragraph(f"Reporte semanal — {cliente_nombre}", subtitle_style),
        Paragraph(f"Semana del {_fmt_fecha(actual.inicio)} al {_fmt_fecha(actual.fin)} · {campanas_txt}", subtitle_style),
    ]

    story.append(Paragraph('Resumen de la semana', section_style))
    stat_table = Table([
        [Paragraph('Mensajes', stat_label_style), Paragraph('Costo por resultado', stat_label_style), Paragraph('Importe gastado', stat_label_style)],
        [Paragraph(str(actual.mensajes), stat_value_style),
         Paragraph(_fmt_dinero(actual.costo_por_resultado) if actual.costo_por_resultado is not None else '—', stat_value_style),
         Paragraph(_fmt_dinero(actual.importe_gastado), stat_value_style)],
    ], colWidths=[55 * mm, 55 * mm, 55 * mm])
    stat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PURPLE_SOFT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(stat_table)

    if anterior is not None:
        story.append(Paragraph('Comparación con la semana anterior', section_style))
        comp_rows = [
            ['', f"{_fmt_fecha(anterior.inicio)} – {_fmt_fecha(anterior.fin)}", f"{_fmt_fecha(actual.inicio)} – {_fmt_fecha(actual.fin)}"],
            ['Mensajes', str(anterior.mensajes), str(actual.mensajes)],
            ['Costo por resultado', _fmt_dinero(anterior.costo_por_resultado) if anterior.costo_por_resultado is not None else '—',
             _fmt_dinero(actual.costo_por_resultado) if actual.costo_por_resultado is not None else '—'],
            ['Importe gastado', _fmt_dinero(anterior.importe_gastado), _fmt_dinero(actual.importe_gastado)],
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

    if len(semanas) > 1:
        story.append(Paragraph('Mensajes por semana', section_style))
        recientes = semanas[-6:]
        d = Drawing(360, 140)
        chart = VerticalBarChart()
        chart.x = 30
        chart.y = 20
        chart.width = 300
        chart.height = 100
        chart.data = [[s.mensajes for s in recientes]]
        chart.categoryAxis.categoryNames = [f"S{i + 1}" for i in range(len(recientes))]
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
        story.append(d)

    conclusion_table = Table([[Paragraph(_generar_conclusion(actual, anterior), body_style)]], colWidths=[165 * mm])
    conclusion_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PURPLE_SOFT),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(KeepTogether([
        Paragraph('En resumen', section_style),
        conclusion_table,
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
