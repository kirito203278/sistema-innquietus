import datetime as dt
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from app.config import get_settings
from app.reports import branding as b
from app.reports.formato import dias_texto, dinero, fecha

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontName="Helvetica-Bold", fontSize=20, textColor=b.PURPLE_DARK, spaceAfter=2)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=b.PURPLE, spaceBefore=14, spaceAfter=6)
H3 = ParagraphStyle("h3", parent=_ss["Heading3"], fontName="Helvetica-Bold", fontSize=10, textColor=b.PURPLE_DARK, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("body", parent=_ss["BodyText"], fontName="Helvetica", fontSize=9, textColor=b.INK, leading=12)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, textColor=b.INK_LIGHT)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8, leading=10)
CELL_R = ParagraphStyle("cellr", parent=CELL, alignment=TA_RIGHT)
EMPTY = ParagraphStyle("empty", parent=BODY, textColor=b.INK_LIGHT, fontName="Helvetica-Oblique")

ANCHO = landscape(A4)[0] - 3 * cm


def _tabla(encabezados, filas, anchos, derecha=(), total=None, estilos_extra=()):
    def celda(v, col):
        return v if not isinstance(v, str) else Paragraph(v, CELL_R if col in derecha else CELL)
    cabecera = [Paragraph(f"<b>{h}</b>", ParagraphStyle("th", parent=CELL_R if i in derecha else CELL, textColor=colors.white))
                for i, h in enumerate(encabezados)]
    datos = [cabecera] + [[celda(v, i) for i, v in enumerate(f)] for f in filas]
    if total:
        datos.append([Paragraph(f"<b>{v}</b>", CELL_R if i in derecha else CELL) for i, v in enumerate(total)])
    t = Table(datos, colWidths=[a * ANCHO for a in anchos], repeatRows=1)
    est = [("BACKGROUND", (0, 0), (-1, 0), b.PURPLE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
           ("LINEBELOW", (0, 0), (-1, -1), 0.25, b.BORDER), ("TOPPADDING", (0, 0), (-1, -1), 4),
           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("ROWBACKGROUNDS", (0, 1), (-1, -1 if not total else -2), [colors.white, b.PURPLE_SOFT])]
    if total:
        est += [("BACKGROUND", (0, -1), (-1, -1), b.YELLOW), ("LINEABOVE", (0, -1), (-1, -1), 1, b.PURPLE_DARK)]
    t.setStyle(TableStyle(est + list(estilos_extra)))
    return t


def _vacio(texto="Sin registros en este periodo."):
    return Paragraph(texto, EMPTY)


def _semaforo(s: str) -> str:
    col = b.SEMAFORO[s].hexval()[2:]
    return f'<font color="#{col}"><b>●</b></font> {b.SEMAFORO_TEXTO[s].split(" · ")[0]}'


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(b.INK_LIGHT)
    canvas.drawString(1.5 * cm, 0.9 * cm, f"{get_settings().agencia_nombre} · Control de clientes y paquetes")
    canvas.drawRightString(landscape(A4)[0] - 1.5 * cm, 0.9 * cm, f"Página {doc.page}")
    canvas.setStrokeColor(b.YELLOW)
    canvas.setLineWidth(2)
    canvas.line(1.5 * cm, 1.3 * cm, landscape(A4)[0] - 1.5 * cm, 1.3 * cm)
    canvas.restoreState()


def generar_pdf(datos: dict, generado: dt.datetime) -> bytes:
    per, res = datos["periodo"], datos["resumen"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.3 * cm,
                            bottomMargin=1.8 * cm, title=f"Reporte {per['etiqueta']}", author=get_settings().agencia_nombre)
    el = []

    logo = Image(str(b.LOGO_PATH), width=2.2 * cm, height=2.2 * cm, kind="proportional") if b.LOGO_PATH.exists() else ""
    titulo = [Paragraph("Reporte de ingresos y renovaciones", H1), Paragraph(per["etiqueta"].capitalize(), ParagraphStyle(
        "sub", parent=BODY, fontSize=12, textColor=b.PURPLE)), Paragraph(
        f"Alcance: {datos['alcance']} · Generado el {generado.strftime('%d/%m/%Y %H:%M')}", SMALL)]
    cab = Table([[logo, titulo]], colWidths=[2.8 * cm, ANCHO - 2.8 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    el += [cab, Spacer(1, 6)]
    color, fondo = (b.GOOD, b.GOOD_BG) if per["cerrado"] else (b.WARN, b.WARN_BG)
    banda = Table([[Paragraph(f"<b>{per['estado_texto']}</b>", ParagraphStyle("e", parent=BODY, textColor=color, fontSize=10))]],
                  colWidths=[ANCHO])
    banda.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fondo), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el.append(banda)

    el.append(Paragraph("1. Resumen general", H2))
    tarjetas = [("Proyección", dinero(res["proyeccion"]), b.PURPLE), ("Cobrado", dinero(res["cobrado"]), b.GOOD),
                ("Pendiente", dinero(res["pendiente"]), b.WARN), ("% cobrado", f"{res['pct_cobrado']:.1f}%", b.PURPLE_DARK)]
    fila = [[Paragraph(f'<font size="8" color="#7c7286">{t}</font><br/><font size="15" color="#{c.hexval()[2:]}"><b>{v}</b></font>',
                       ParagraphStyle("k", parent=BODY, leading=19)) for t, v, c in tarjetas]]
    kpi = Table(fila, colWidths=[ANCHO / 4] * 4)
    kpi.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, b.BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.5, b.BORDER),
                             ("BACKGROUND", (0, 0), (-1, -1), b.PURPLE_SOFT), ("TOPPADDING", (0, 0), (-1, -1), 8),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
    el += [kpi, Spacer(1, 4), Paragraph(
        f"{res['clientes']} cliente(s) y {res['paquetes']} paquete(s) con renovación del {fecha(per['desde'])} al "
        f"{fecha(per['hasta'])}. Cobrado cuenta hasta el {fecha(per['corte'])}; la proyección es la del periodo completo.", SMALL)]

    el.append(Paragraph("2. Por CM", H2))
    t = datos["total_cm"]
    filas = [[c["cm"], str(c["clientes"]), str(c["paquetes"]), dinero(c["proyeccion"]), dinero(c["cobrado"]),
              dinero(c["pendiente"]), f"{c['pct_cobrado']:.1f}%"] for c in datos["por_cm"]]
    el.append(_tabla(["CM", "Clientes", "Paquetes", "Proyección", "Cobrado", "Pendiente", "% cobrado"], filas,
                     [.27, .1, .1, .15, .15, .15, .08], derecha=(1, 2, 3, 4, 5, 6),
                     total=["Total", str(t["clientes"]), str(t["paquetes"]), dinero(t["proyeccion"]), dinero(t["cobrado"]),
                            dinero(t["pendiente"]), f"{t['pct_cobrado']:.1f}%"]) if filas else _vacio())

    el.append(PageBreak())
    el.append(Paragraph("3. Detalle por paquete", H2))
    det = datos["detalle"]
    if det:
        filas = [[f["cm"], f["cliente"], f["paquete"], f["tipo"], dinero(f["costo"]), dinero(f["pagado"]),
                  dinero(f["restante"]), fecha(f["fecha_renovacion"]), b.ESTADO_TEXTO.get(f["estado_efectivo"], f["estado_efectivo"]),
                  _semaforo(f["semaforo"])] for f in det]
        el.append(_tabla(["CM", "Cliente", "Paquete", "Tipo", "Costo", "Pagado", "Restante", "Renovación", "Estado", "Semáforo"],
                         filas, [.12, .19, .09, .08, .09, .09, .09, .09, .08, .08], derecha=(4, 5, 6),
                         total=["", "Total", "", "", dinero(sum(f["costo"] for f in det)), dinero(sum(f["pagado"] for f in det)),
                                dinero(sum(f["restante"] for f in det)), "", "", ""]))
    else:
        el.append(_vacio())

    el.append(Paragraph("4. Prórrogas", H2))
    pr = datos["prorrogas"]
    if pr:
        filas = [[r["cm"], r["cliente"], r["paquete"], dinero(r["restante"]), fecha(r["fecha_limite"]),
                  ("<b>VENCIDA</b> · " if r["vencida"] else "") + dias_texto(r["dias"])] for r in pr]
        rojos = [("BACKGROUND", (0, i + 1), (-1, i + 1), b.BAD_BG) for i, r in enumerate(pr) if r["vencida"]]
        rojos += [("TEXTCOLOR", (0, i + 1), (-1, i + 1), b.BAD) for i, r in enumerate(pr) if r["vencida"]]
        el.append(_tabla(["CM", "Cliente", "Paquete", "Restante por cobrar", "Fecha límite", "Situación"], filas,
                         [.15, .24, .12, .15, .12, .22], derecha=(3,),
                         total=["", "Total por cobrar", "", dinero(sum(r["restante"] for r in pr)), "", ""],
                         estilos_extra=rojos))
        el.append(Paragraph("Las prórrogas vencidas aparecen resaltadas en rojo. Esta sección incluye todas las prórrogas "
                            "con saldo a la fecha de corte, sin importar el periodo elegido.", SMALL))
    else:
        el.append(_vacio("No hay prórrogas activas ni vencidas con saldo pendiente."))

    el.append(PageBreak())
    el.append(Paragraph("5. Pendientes de renovar", H2))
    hay = False
    for clave, titulo_ in (("por_vencer", "Por vencer"), ("vencidos", "Vencidos sin decisión"),
                           ("renovados_sin_pago", "Renovados sin pago")):
        grupos = datos["pendientes"][clave]
        if not grupos:
            continue
        hay = True
        bloques = [Paragraph(titulo_, H3)]
        for g in grupos:
            filas = [[f["cliente"], f["paquete"], dinero(f["restante"]), fecha(f["fecha_renovacion"]), _semaforo(f["semaforo"])]
                     for f in g["items"]]
            bloques += [Paragraph(f"<b>{g['cm']}</b>", SMALL), _tabla(["Cliente", "Paquete", "Restante", "Renovación", "Semáforo"],
                                                                      filas, [.34, .16, .16, .17, .17], derecha=(2,)), Spacer(1, 4)]
        el.append(KeepTogether(bloques[:3]))
        el.extend(bloques[3:])
    if hay:
        el.append(Paragraph("Situación a la fecha de corte; incluye pendientes de periodos anteriores.", SMALL))
    else:
        el.append(_vacio("Sin pendientes de renovación."))

    el.append(Paragraph("6. Tasa de renovación por CM", H2))
    tr, tt = datos["tasa_renovacion"], datos["tasa_total"]
    if tr:
        el.append(_tabla(["CM", "Vencidos del periodo", "Renovados", "Tasa de renovación"],
                         [[r["cm"], str(r["vencidos"]), str(r["renovados"]), f"{r['tasa']:.1f}%"] for r in tr],
                         [.4, .2, .2, .2], derecha=(1, 2, 3),
                         total=["Total", str(tt["vencidos"]), str(tt["renovados"]), f"{tt['tasa']:.1f}%"]))
        el.append(Paragraph("Tasa = paquetes renovados entre paquetes que llegaron a su fecha de renovación en el periodo.", SMALL))
    else:
        el.append(_vacio())

    doc.build(el, onFirstPage=_pie, onLaterPages=_pie)
    return buf.getvalue()
