from pathlib import Path

from reportlab.lib.colors import HexColor

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"

PURPLE = HexColor("#4b2a82")
PURPLE_DARK = HexColor("#2b1749")
PURPLE_SOFT = HexColor("#f7f2fd")
YELLOW = HexColor("#ffde00")
ORANGE = HexColor("#ff6a1a")
INK = HexColor("#1c1524")
INK_LIGHT = HexColor("#7c7286")
BORDER = HexColor("#e3ddee")

GOOD = HexColor("#1f9d55")
WARN = HexColor("#e2530a")
BAD = HexColor("#c62828")
BAD_BG = HexColor("#fce8e6")
GOOD_BG = HexColor("#e7f8ee")
WARN_BG = HexColor("#ffe3d1")

SEMAFORO = {"verde": GOOD, "amarillo": HexColor("#e6b800"), "rojo": BAD, "gris": INK_LIGHT}
SEMAFORO_TEXTO = {"verde": "Verde · pagada", "amarillo": "Amarillo · sin pago", "rojo": "Rojo · vencido",
                  "gris": "Gris · pendiente"}
ESTADO_TEXTO = {"activo": "Activo", "por_vencer": "Por vencer", "vencido": "Vencido", "renovado": "Renovado",
                "archivado": "Archivado", "eliminado": "Eliminado"}
