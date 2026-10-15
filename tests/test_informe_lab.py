"""Pruebas del lector de informes de laboratorio con informes sintéticos (sin datos reales)."""
import io
import sys
from pathlib import Path

import openpyxl
from fpdf import FPDF

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.leer_informe_lab import leer_informe  # noqa: E402

TIPOS = ["Agua fisicoquímica", "Agua microbiológica", "Suelo", "Hoja", "Fruta", "MRL"]


def _pdf(lineas: list[str]) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for linea in lineas:
        pdf.cell(0, 6, linea.encode("latin-1", "replace").decode("latin-1"), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_informe_foliar_pdf():
    contenido = _pdf([
        "AGROLAB - Informe de análisis foliar",
        "Fecha de emisión: 10/10/2026",
        "Fecha de muestreo: 03/10/2026",
        "Identificación de la muestra: Cuartel 4",
        "Especie: Cerezo   Variedad: Lapins",
        "Parámetro      Resultado   Unidad",
        "Nitrógeno total   2,85   %",
        "Potasio   1,4   %",
    ])
    r = leer_informe(contenido, "informe.pdf", ["Nitrógeno", "Potasio"], ["Cerezo", "Ciruelo"], TIPOS)
    assert r.texto_leido and r.tipo_sugerido == "Hoja"
    assert r.fecha_muestreo == "2026-10-03"
    assert r.laboratorio == "Agrolab"
    assert r.punto and r.punto.startswith("Cuartel 4")
    assert r.especie == "Cerezo"
    assert {x["parametro"]: x["valor"] for x in r.resultados} == {"Nitrógeno": 2.85, "Potasio": 1.4}


def test_informe_agua_con_menor_que_y_ausencia():
    contenido = _pdf([
        "Laboratorio Hidrolab",
        "Toma de muestra: 1 de septiembre de 2026",
        "Punto de muestreo: Bocatoma canal",
        "Coliformes termotolerantes  < 1,8  NMP/100 mL",
        "Escherichia coli   Ausencia",
    ])
    r = leer_informe(contenido, "agua.pdf", ["Coliformes fecales", "E. coli"], [], TIPOS)
    assert r.tipo_sugerido == "Agua microbiológica"
    assert r.fecha_muestreo == "2026-09-01"
    res = {x["parametro"]: x for x in r.resultados}
    assert res["Coliformes fecales"]["valor"] == 1.8 and res["Coliformes fecales"]["valor_texto"] == "< 1,8"
    assert res["E. coli"]["valor"] == 0.0 and res["E. coli"]["valor_texto"] == "Ausencia"


def test_informe_excel_y_parametro_no_encontrado():
    libro = openpyxl.Workbook()
    hoja = libro.active
    for fila in (["Análisis de suelo"], ["Fecha muestreo", "2026-08-20"], ["Cuartel", "Cuartel 2"],
                 ["pH", 6.8], ["Fósforo", 22]):
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    r = leer_informe(salida.getvalue(), "suelo.xlsx", ["pH", "Materia orgánica"], ["Ciruelo"], TIPOS)
    assert r.tipo_sugerido == "Suelo"
    assert r.fecha_muestreo == "2026-08-20"
    assert [x["parametro"] for x in r.resultados] == ["pH"] and r.resultados[0]["valor"] == 6.8
    assert r.no_encontrados == ["Materia orgánica"]


def test_imagen_sin_texto():
    r = leer_informe(b"\x89PNG...", "foto.jpg", ["pH"], [], TIPOS)
    assert not r.texto_leido and r.advertencias
