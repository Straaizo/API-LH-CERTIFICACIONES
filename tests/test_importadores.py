"""Pruebas del lector de planillas BRCGS con una planilla sintética (sin datos reales)."""
import io
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.importadores import leer_brcgs  # noqa: E402


def _planilla() -> bytes:
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "4 PRUEBA"
    hoja["C1"], hoja["E1"] = "LISTA DE VERIFICACIÓN", "#DIV/0!"
    hoja["C3"] = "LUGAR: PLANTA PRUEBA"
    hoja["C4"] = "AUDITOR: PERSONA DE PRUEBA"
    hoja["C5"] = "FECHA: 20-03-2026          HORA: 9:30"
    hoja["C6"] = 'ALCANCE: CLAUSULA 5 "OTRA"'
    hoja["A8"] = "4      Normas\n4.1     Normas externas"
    hoja.append(["Cláusula", None, "Requisitos", None, "SI", "NO", "N/A", "Comentarios"])
    hoja.append(["4.1.1", None, "Texto 1", None, "x", None, None, "se evidencia cumplimiento"])
    hoja.append(["4.1.2", None, "Texto 2", None, None, "x", None, "lockers en buen estado"])
    hoja.append(["4.1.3", None, "Texto 3", None, None, "x", "?", "moho en techo"])
    hoja.append(["4.2     Protección"])
    hoja.append([None, None, "Fundamental\nTexto"])
    hoja.append(["Cláusula", None, "Requisitos"])
    hoja.append(["4.2.1", None, "Texto 4", None, None, None, "x", "no aplica"])
    hoja.append(["4.2.2", None, "Texto 5"])
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_lee_encabezado_y_errores_conocidos():
    hoja = leer_brcgs(_planilla())[0]
    assert hoja.lugar == "PLANTA PRUEBA"
    assert hoja.fecha.isoformat() == "2026-03-20"
    assert any("#DIV/0!" in a for a in hoja.advertencias)
    assert any("alcance" in a.lower() for a in hoja.advertencias)


def test_resultados_y_advertencias_por_item():
    items = {i.codigo: i for i in leer_brcgs(_planilla())[0].items}
    assert items["4.1.1"].resultado == "si"
    assert items["4.1.2"].resultado == "no"
    assert any("indica cumplimiento" in a for a in items["4.1.2"].advertencias)
    assert items["4.1.3"].resultado == "no"
    assert any("dudosa" in a for a in items["4.1.3"].advertencias)
    assert items["4.2.1"].resultado == "na" and items["4.2.1"].fundamental
    assert items["4.2.2"].resultado is None and "Sin respuesta" in items["4.2.2"].advertencias


def test_cumplimiento_excluye_na():
    resumen = leer_brcgs(_planilla())[0].resumen()
    assert resumen["si"] == 1 and resumen["no"] == 2
    assert resumen["cumplimiento"] == round(1 / 3 * 100, 1)
