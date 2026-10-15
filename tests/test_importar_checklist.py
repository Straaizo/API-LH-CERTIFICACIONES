"""Pruebas del lector de checklist con planillas sintéticas (sin datos reales)."""
import io
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.importar_checklist import leer_checklist  # noqa: E402


def _libro(hojas: dict[str, list[list]]) -> bytes:
    libro = openpyxl.Workbook()
    libro.remove(libro.active)
    for titulo, filas in hojas.items():
        hoja = libro.create_sheet(titulo)
        for fila in filas:
            hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def test_tabla_de_principios_y_criterios():
    contenido = _libro({
        "Portada": [["ADD-ON PRUEBA GROW"], ["VERSIÓN EN ESPAÑOL 3.1_JUL23"]],
        "M1": [
            ["Sección", "Principio", "Criterios", "Orientación", "Nivel"],
            ["1", "CONTROL DE PRUEBA"],
            ["1.1", "Principio uno", "Criterio uno", None, "Obligación Mayor"],
            ["1.2", "Principio dos", None, None, "Recom."],
            ["1.3", "Principio tres", None, None, "Nivel raro"],
        ],
    })
    leido = leer_checklist(contenido, "prueba.xlsx")
    assert leido.protocolo_sugerido == "GROW"
    assert leido.version == "v3.1_JUL23"
    assert [p.codigo for p in leido.puntos] == ["1.1", "1.2", "1.3"]
    assert leido.puntos[0].seccion_titulo == "CONTROL DE PRUEBA"
    assert "Criterio de cumplimiento: Criterio uno" in leido.puntos[0].texto
    assert [p.nivel for p in leido.puntos] == ["mayor", "recomendacion", "sin_nivel"]
    assert any("Nivel raro" in a for a in leido.advertencias)


def test_primus_convertido_desde_pdf():
    contenido = _libro({
        "Table 1": [
            ["PrimusGFS - Lista de Comprobación - v 3.2"],
            ["Sección", "P #", "Pregunta", "Puntos Totales", "Comentarios del Auditor"],
            # Código partido en dos filas y pregunta en varias líneas
            ["Sistema", "1.01.", "¿Existe una política", None, "Sí, firmada"],
            ["de Administración", "1", "documentada?", 5],
            # Código leído como fecha: 2002-01-01 = 1.01.02
            ["Sistema de Administración", datetime(2002, 1, 1), "¿Hay organigrama?", 10],
            # Código perdido en la conversión
            ["Sistema de Administración", None, "¿Hay comité?", 5],
        ],
        "Table 2": [["Historial de Revisión del Documento"], ["Fecha", "Rev.#"], [datetime(2021, 1, 19), "1"]],
    })
    leido = leer_checklist(contenido, "MOD1.xlsx")
    assert leido.protocolo_sugerido == "PRIMUSGFS"
    assert leido.version == "v3.2"
    assert [p.codigo for p in leido.puntos] == ["1.01.01", "1.01.02", "1.01.03"]
    assert leido.puntos[0].texto.startswith("¿Existe una política documentada?")
    assert leido.puntos[0].seccion_titulo == "Sistema de Administración"
    assert any("se asumió 1.01.03" in a for a in leido.advertencias)
    assert any("comentarios del auditor" in a for a in leido.advertencias)


def test_grasp():
    contenido = _libro({
        "Introduction": [["I2", "Lista de verificación GRASP - versión 1.3-1-i"]],
        "Calculation Preview": [
            ["translation_id"],
            ["118", None, None, "REPRESENTANTE DE LOS EMPLEADOS"],
            ["119", None, "1", "PC: ¿Hay representante?"],
            ["120", None, "1.1", "Procedimiento definido", 0],
            ["121", None, "1.2", "Elección documentada", 0],
            [None, None, None, "Puntos de control en total"],
        ],
    })
    leido = leer_checklist(contenido, "grasp.xlsx")
    assert leido.protocolo_sugerido == "GRASP"
    assert leido.version == "v1.3-1-i"
    assert [p.codigo for p in leido.puntos] == ["1.1", "1.2"]
    assert leido.puntos[0].seccion_titulo == "Representante de los empleados"
    assert "Punto de control: ¿Hay representante?" in leido.puntos[0].texto


def test_formato_desconocido():
    contenido = _libro({"Hoja": [["cualquier cosa"]]})
    try:
        leer_checklist(contenido, "x.xlsx")
    except ValueError as exc:
        assert "No se reconoce" in str(exc)
    else:
        raise AssertionError("Debía rechazar la planilla")
