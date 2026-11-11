"""Informe formal de medio ambiente en PDF: comparativa de la temporada contra la anterior al mismo período.

Lo usan certificaciones y las personas del campo (administrativos, encargados de aplicaciones).
"""
from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from config import BASE_DIR
from utils.hora import ahora

LOGO = BASE_DIR / "static" / "logo.png"
VERDE = (11, 122, 11)
VERDE_OSCURO = (9, 82, 14)
VERDE_SUAVE = (232, 244, 229)
GRIS = (90, 100, 85)
GRIS_CLARO = (226, 232, 222)
TINTA = (23, 32, 22)
ROJO = (190, 30, 30)
ANTERIOR = (176, 190, 170)


def _latin(texto) -> str:
    return (str(texto) if texto is not None else "").replace("–", "-").replace("·", "-").replace("≤", "<=") \
        .replace("₂", "2").encode("latin-1", "replace").decode("latin-1")


def _num(valor, decimales: int = 0) -> str:
    """Formato chileno: 12.345,6"""
    if valor is None:
        return "-"
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _var(valor) -> str:
    if valor is None:
        return "-"
    return f"{'+' if valor > 0 else ''}{_num(valor, 1)} %"


class _Informe(FPDF):
    def __init__(self, titulo: str, subtitulo: str, pie: str):
        super().__init__(orientation="P", format="Letter")
        self.titulo, self.subtitulo, self.pie = titulo, subtitulo, pie
        self.set_margins(14, 14, 14)
        self.set_auto_page_break(True, margin=18)
        self.alias_nb_pages()

    @property
    def ancho(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def header(self):
        self.set_fill_color(*VERDE)
        self.rect(0, 0, self.w, 24, style="F")
        self.set_fill_color(*VERDE_OSCURO)
        self.rect(0, 24, self.w, 1.2, style="F")
        if LOGO.exists():
            self.set_fill_color(255, 255, 255)
            self.rect(self.l_margin, 5, 14, 14, style="F", round_corners=True, corner_radius=2.5)
            self.image(str(LOGO), x=self.l_margin + 1, y=6, w=12, h=12, keep_aspect_ratio=True)
        self.set_text_color(255, 255, 255)
        self.set_xy(self.l_margin + 18, 6)
        self.set_font("Helvetica", "B", 14)
        self.cell(120, 7, _latin(self.titulo))
        self.set_xy(self.l_margin + 18, 13)
        self.set_font("Helvetica", "", 8.5)
        self.cell(120, 5, _latin(self.subtitulo))
        self.set_font("Helvetica", "", 8)
        self.set_xy(self.w - self.r_margin - 40, 9)
        self.cell(40, 5, f"Página {self.page_no()} de {{nb}}", align="R")
        self.set_text_color(*TINTA)
        self.set_y(32)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(*GRIS_CLARO)
        self.line(self.l_margin, self.get_y() - 1, self.w - self.r_margin, self.get_y() - 1)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*GRIS)
        self.cell(self.ancho, 5, _latin(self.pie), align="C")
        self.set_text_color(*TINTA)

    def seccion(self, titulo: str, ayuda: str | None = None, alto_minimo: float = 40):
        if self.get_y() + alto_minimo > self.h - self.b_margin:
            self.add_page()
        self.ln(3)
        self.set_font("Helvetica", "B", 11.5)
        self.set_text_color(*TINTA)
        self.cell(self.ancho, 7, _latin(titulo), new_x="LMARGIN", new_y="NEXT")
        if ayuda:
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*GRIS)
            self.multi_cell(self.ancho, 4, _latin(ayuda), new_x="LMARGIN", new_y="NEXT", align="L")
            self.set_text_color(*TINTA)
        self.ln(1.5)

    def ficha(self, pares: list[tuple[str, str]]):
        """Bloque de datos del informe: etiqueta arriba, valor abajo, en columnas."""
        ancho = self.ancho / len(pares)
        y = self.get_y()
        self.set_fill_color(*VERDE_SUAVE)
        self.rect(self.l_margin, y, self.ancho, 15, style="F", round_corners=True, corner_radius=2)
        for i, (etiqueta, valor) in enumerate(pares):
            x = self.l_margin + i * ancho + 4
            self.set_xy(x, y + 2.5)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*GRIS)
            self.cell(ancho - 6, 4, _latin(etiqueta.upper()))
            self.set_xy(x, y + 7)
            self.set_font("Helvetica", "B", 9.5)
            self.set_text_color(*TINTA)
            self.cell(ancho - 6, 5, _latin(valor))
        self.set_y(y + 19)

    def tarjetas(self, tarjetas: list[tuple[str, str, str, tuple[int, int, int] | None]]):
        """Indicadores: (etiqueta, valor, detalle, color del detalle)."""
        separacion = 3
        ancho = (self.ancho - separacion * (len(tarjetas) - 1)) / len(tarjetas)
        y = self.get_y()
        for i, (etiqueta, valor, detalle, color) in enumerate(tarjetas):
            x = self.l_margin + i * (ancho + separacion)
            self.set_draw_color(*GRIS_CLARO)
            self.set_fill_color(255, 255, 255)
            self.rect(x, y, ancho, 24, style="DF", round_corners=True, corner_radius=2)
            self.set_xy(x + 3.5, y + 3)
            self.set_font("Helvetica", "", 7.5)
            self.set_text_color(*GRIS)
            self.multi_cell(ancho - 7, 3.5, _latin(etiqueta), align="L")
            self.set_xy(x + 3.5, y + 11)
            self.set_font("Helvetica", "B", 15)
            self.set_text_color(*TINTA)
            self.cell(ancho - 7, 7, _latin(valor))
            self.set_xy(x + 3.5, y + 18.5)
            self.set_font("Helvetica", "B" if color else "", 7.5)
            self.set_text_color(*(color or GRIS))
            self.cell(ancho - 7, 4, _latin(detalle))
        self.set_text_color(*TINTA)
        self.set_y(y + 28)

    def barras(self, meses: list[str], actual: list[float], anterior: list[float], unidad: str,
               nombre_actual: str, nombre_anterior: str | None):
        """Barras agrupadas por mes: temporada actual (verde) y anterior (gris)."""
        alto, y0 = 52, self.get_y() + 6
        x0, ancho = self.l_margin + 12, self.ancho - 12
        maximo = max([*actual, *anterior, 0]) or 1
        # Leyenda
        self.set_font("Helvetica", "", 7.5)
        self.set_fill_color(*VERDE)
        self.rect(self.l_margin, y0 - 6, 3, 3, style="F")
        self.set_xy(self.l_margin + 4, y0 - 6.6)
        self.cell(40, 4, _latin(f"Temporada {nombre_actual}"))
        if nombre_anterior:
            self.set_fill_color(*ANTERIOR)
            self.rect(self.l_margin + 42, y0 - 6, 3, 3, style="F")
            self.set_xy(self.l_margin + 46, y0 - 6.6)
            self.cell(40, 4, _latin(f"Temporada {nombre_anterior}"))
        # Ejes y líneas guía
        self.set_draw_color(*GRIS_CLARO)
        self.set_text_color(*GRIS)
        self.set_font("Helvetica", "", 6.5)
        for paso in range(5):
            valor = maximo * paso / 4
            y = y0 + alto - alto * paso / 4
            self.line(x0, y, x0 + ancho, y)
            self.set_xy(self.l_margin - 2, y - 2)
            self.cell(13, 4, _num(valor, 0 if maximo >= 10 else 1), align="R")
        grupo = ancho / len(meses)
        barra = min(4.2, grupo * 0.32)
        for i, mes in enumerate(meses):
            cx = x0 + i * grupo + grupo / 2
            for desplazamiento, serie, color in ((-barra - 0.3, anterior, ANTERIOR), (0.3, actual, VERDE)):
                if i < len(serie) and serie[i] > 0:
                    h = alto * serie[i] / maximo
                    self.set_fill_color(*color)
                    self.rect(cx + desplazamiento, y0 + alto - h, barra, h, style="F")
            self.set_xy(cx - grupo / 2, y0 + alto + 1)
            self.cell(grupo, 4, _latin(mes), align="C")
        self.set_xy(self.l_margin, y0 + alto + 5.5)
        self.cell(self.ancho, 4, _latin(unidad), align="R")
        self.set_text_color(*TINTA)
        self.set_y(y0 + alto + 11)

    def tabla(self, encabezados: list[str], filas: list[list[str]], anchos: list[float],
              alineacion: list[str] | None = None, colores: list[list[tuple | None]] | None = None,
              tamano: float = 8.5):
        alineacion = alineacion or ["LEFT"] + ["RIGHT"] * (len(encabezados) - 1)
        self.set_font("Helvetica", "", tamano)
        self.set_draw_color(*GRIS_CLARO)
        self.set_fill_color(246, 249, 244)  # las filas alternas usan el color de relleno vigente
        cabecera = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=VERDE)
        with self.table(col_widths=anchos, text_align=alineacion, headings_style=cabecera, line_height=5.6,
                        borders_layout="HORIZONTAL_LINES", cell_fill_color=(246, 249, 244),
                        cell_fill_mode="ROWS", padding=(1, 1.5)) as t:
            fila = t.row()
            for e in encabezados:
                fila.cell(_latin(e))
            for i, valores in enumerate(filas):
                fila = t.row()
                for j, v in enumerate(valores):
                    color = colores[i][j] if colores else None
                    fila.cell(_latin(v), style=FontFace(color=color, emphasis="BOLD") if color else None)
        self.ln(2)


def _color(variacion, menos_es_mejor: bool = True):
    if variacion is None or abs(variacion) < 0.05:
        return None
    mejora = variacion < 0 if menos_es_mejor else variacion > 0
    return VERDE if mejora else ROJO


def informe_pdf(d: dict, alcance: str, solo_combustibles: bool, emitido_por: str) -> bytes:
    actual, anterior = d["actual"], d["anterior"]
    n = d["meses_comparados"]
    meses = d["meses"]
    momento: datetime = ahora()
    pdf = _Informe(
        "Informe de medio ambiente" + (" · combustibles" if solo_combustibles else ""),
        "Portal Certificaciones · La Hornilla · Viento Sur",
        f"Generado el {momento:%d-%m-%Y %H:%M} por {emitido_por} · Portal Certificaciones",
    )
    pdf.add_page()

    periodo = f"{meses[0]} a {meses[n - 1]} ({n} {'mes' if n == 1 else 'meses'})" if n else "Sin datos aún"
    pdf.ficha([
        ("Alcance", alcance),
        ("Temporada", f"{actual['nombre']}" + (f" vs {anterior['nombre']}" if anterior else "")),
        ("Período comparado", periodo),
        ("Emitido", f"{momento:%d-%m-%Y}"),
    ])

    h = d["huella"]
    etiqueta_huella = "Huella de combustibles" if solo_combustibles else "Huella de carbono"
    pdf.tarjetas([
        (f"{etiqueta_huella} a la fecha (t CO2e)", _num(h["actual_a_la_fecha"], 1),
         f"{_var(h['variacion'])} vs mismo período" if h["variacion"] is not None else "Sin período anterior",
         _color(h["variacion"])),
        (f"Temporada {anterior['nombre']}, mismo período" if anterior else "Temporada anterior",
         _num(h["anterior_mismo_periodo"], 1), "t CO2e", None),
        (f"Temporada {anterior['nombre']} completa" if anterior else "Anterior completa",
         _num(h["anterior_total"], 1), "t CO2e", None),
        ("Proyección al cierre (t CO2e)", _num(h["proyeccion_cierre"], 1),
         _var(h["variacion_proyeccion"]) + " vs anterior" if h["variacion_proyeccion"] is not None else "Sin datos para proyectar",
         _color(h["variacion_proyeccion"])),
    ])

    pdf.seccion("Huella mensual", "Toneladas de CO2 equivalente por mes, con el factor de emisión de cada temporada.",
                alto_minimo=75)
    pdf.barras(meses, h["mensual_actual"], h["mensual_anterior"], "t CO2e", actual["nombre"],
               anterior["nombre"] if anterior else None)

    if d["conceptos"]:
        pdf.seccion("Consumos por concepto",
                    f"Totales del período comparado, {periodo}. Variación contra el mismo período de la temporada anterior.")
        filas, colores = [], []
        for c in d["conceptos"]:
            filas.append([c["nombre"], c["unidad_medida"], _num(c["actual"]), _num(c["anterior"]), _var(c["variacion"]),
                          _num(c["tco2e_actual"], 2)])
            colores.append([None, None, None, None, _color(c["variacion"]), None])
        pdf.tabla(["Concepto", "Unidad", actual["nombre"], anterior["nombre"] if anterior else "Anterior",
                   "Variación", "t CO2e"], filas, [62, 18, 27, 27, 25, 27], ["LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"],
                  colores)

        if n:
            pdf.seccion(f"Consumo mensual, temporada {actual['nombre']}", "Cantidad registrada cada mes, en la unidad de cada concepto.",
                        alto_minimo=30 + 6 * len(d["conceptos"]))
            ancho_mes = min(16.0, (pdf.ancho - 46) / n)
            pdf.tabla(["Concepto"] + meses[:n],
                      [[c["nombre"]] + [_num(v) for v in c["mensual_actual"]] for c in d["conceptos"]],
                      [pdf.ancho - ancho_mes * n] + [ancho_mes] * n, tamano=7 if n > 8 else 8)

    if d["sucursales"]:
        pdf.seccion("Huella por sucursal", "Ordenadas de la que más bajó a la que más subió.")
        pdf.tabla(["Sucursal", f"{actual['nombre']} (t CO2e)", f"{anterior['nombre'] if anterior else 'Anterior'} (t CO2e)",
                   "Variación"],
                  [[s["unidad"]["nombre"], _num(s["tco2e_actual"], 2), _num(s["tco2e_anterior"], 2), _var(s["variacion"])]
                   for s in d["sucursales"]],
                  [76, 40, 40, 30], colores=[[None, None, None, _color(s["variacion"])] for s in d["sucursales"]])

    if d["reciclaje_materiales"]:
        pdf.seccion("Reciclaje por material", "Kilos reciclados en el período comparado. Aquí subir es mejor.")
        pdf.tabla(["Material", f"{actual['nombre']} (kg)", f"{anterior['nombre'] if anterior else 'Anterior'} (kg)", "Variación"],
                  [[m["nombre"], _num(m["actual"]), _num(m["anterior"]), _var(m["variacion"])] for m in d["reciclaje_materiales"]],
                  [76, 40, 40, 30], colores=[[None, None, None, _color(m["variacion"], menos_es_mejor=False)]
                                             for m in d["reciclaje_materiales"]])

    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*GRIS)
    pdf.multi_cell(pdf.ancho, 4, _latin(
        "La comparación usa los mismos meses en ambas temporadas: si la actual lleva " + str(n) + " meses con datos, "
        "se compara con esos mismos meses de la anterior. La proyección al cierre aplica a la temporada actual la "
        "proporción que tuvo la anterior entre ese período y su total. Verde: mejora; rojo: empeora."))
    return bytes(pdf.output())


