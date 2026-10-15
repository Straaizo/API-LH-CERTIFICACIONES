"""Lector de checklist de normas: reconoce el formato por el contenido de la planilla.

Formatos conocidos:
- Tabla de principios y criterios de GLOBALG.A.P. y sus add-on (IFA GFS, GROW, Nurture, FSMA PSR).
- GRASP (plantilla oficial con hoja 'Calculation Preview').
- PrimusGFS (lista de comprobación por módulo, convertida desde PDF: códigos leídos como fecha,
  preguntas partidas en varias filas y tablas cortadas por página).

Solo interpreta y reporta; lo dudoso queda en advertencias.
"""
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

import openpyxl

from utils.importadores import PuntoControl, _texto, leer_globalgap, orden_codigo
from utils.texto import normalizar

MAX_FILAS = 5000
MAX_COLUMNAS = 30
NIVELES = {
    "obligacion mayor": "mayor", "major must": "mayor",
    "obligacion menor": "menor", "minor must": "menor",
    "recom.": "recomendacion", "recom": "recomendacion", "recomendacion": "recomendacion",
}
RE_SECCION_TABLA = re.compile(r"^([A-Z]{1,5}(?:[- ][A-Z]+)?\s?\d+(?:\.\d+)*)\s+(.+)$")
RE_PRIMUS_INICIO = re.compile(r"^(\d+)\.(\d{1,2})\.(\d{1,2})?$")


@dataclass
class ChecklistLeido:
    formato: str
    protocolo_sugerido: str | None
    version: str
    puntos: list[PuntoControl] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


def _filas(ws) -> list[tuple]:
    return [tuple(f) for f in ws.iter_rows(max_row=MAX_FILAS, max_col=MAX_COLUMNAS, values_only=True)]


def _textos(filas: list[tuple], max_filas: int = 40) -> str:
    return " ".join(_texto(c) for f in filas[:max_filas] for c in f if c is not None)


def _con_formato(archivo: str) -> ValueError:
    return ValueError(f"No se pudo abrir '{archivo}': no es una planilla Excel válida (.xlsx)")


def leer_checklist(contenido: bytes, nombre_archivo: str) -> ChecklistLeido:
    try:
        libro = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception as exc:
        raise _con_formato(nombre_archivo) from exc
    hojas = {ws.title: _filas(ws) for ws in libro.worksheets}
    portada = _textos(hojas.get("Portada", []))

    if any(_encabezado_primus(f) for filas in hojas.values() for f in filas[:10]):
        return _leer_primus(hojas)
    if "Calculation Preview" in hojas:
        return _leer_grasp(hojas)
    modulos = [t for t in hojas if normalizar(t).startswith("p&c del modulo")]
    if "PI" in hojas and not modulos:
        version, puntos, advertencias = leer_globalgap(contenido)
        return ChecklistLeido("GLOBALG.A.P. IFA", "GLOBALGAP", version, puntos, advertencias)
    candidatas = modulos or [t for t, filas in hojas.items() if _encabezado_tabla(filas)]
    if candidatas:
        return _leer_tabla({t: hojas[t] for t in candidatas}, portada, nombre_archivo)
    raise ValueError("No se reconoce el formato de la planilla: no es un checklist GLOBALG.A.P., GRASP ni PrimusGFS")


# ---------- Tabla de principios y criterios (GLOBALG.A.P. y add-on) ----------

def _encabezado_tabla(filas: list[tuple]) -> tuple[int, dict[str, int]] | None:
    for n, fila in enumerate(filas[:10]):
        claves = [normalizar(_texto(c)) for c in fila]
        if "criterios" not in claves or "nivel" not in claves:
            continue
        columnas = {"criterios": claves.index("criterios"), "nivel": claves.index("nivel")}
        for i, c in enumerate(claves):
            if c in ("principio", "descripcion/principio"):
                columnas["texto"] = i
            elif c.startswith("requisito"):
                columnas["pregunta"] = i
            elif "codigo" not in columnas and (c in ("seccion", "number") or re.fullmatch(r"n\W{0,2}[o°]", c)):
                columnas["codigo"] = i
        if "texto" in columnas and "codigo" in columnas:
            return n, columnas
    return None


def _version_portada(portada: str, nombre_archivo: str) -> str:
    m = re.search(r"versi[oó]n\W*(?:en espa[nñ]ol\s*)?(?:versi[oó]n\s*)?(\d+(?:\.\d+)*(?:[_-][A-Za-z0-9]+)*)",
                  portada, re.IGNORECASE)
    if not m:
        m = re.search(r"v(\d+(?:[._]\d+)*(?:_[A-Za-z]{3}\d{2})?)", nombre_archivo)
    return f"v{m.group(1)}" if m else "sin versión"


def _protocolo_tabla(portada: str, titulos: list[str], nombre_archivo: str) -> str | None:
    texto = normalizar(" ".join([portada, *titulos, nombre_archivo]))
    if "nurture" in texto:
        return "TESCO_NURTURE"
    if "grow" in texto:
        return "GROW"
    if "psr" in texto or "fsma" in texto:
        return "FSMA_PSR"
    if "ifa" in texto or "gfs" in texto:
        return "GLOBALGAP"
    return None


def _leer_tabla(hojas: dict[str, list[tuple]], portada: str, nombre_archivo: str) -> ChecklistLeido:
    advertencias: list[str] = []
    puntos: dict[str, PuntoControl] = {}
    for titulo, filas in hojas.items():
        n_enc, col = _encabezado_tabla(filas)
        seccion, seccion_titulo = "", ""
        for n, fila in enumerate(filas[n_enc + 1:], start=n_enc + 2):
            celdas = [_texto(c) for c in fila]
            codigo = celdas[col["codigo"]] if col["codigo"] < len(celdas) else ""
            siguiente = celdas[col["codigo"] + 1] if col["codigo"] + 1 < len(celdas) else ""
            if not codigo and len(siguiente) > 10 and siguiente.isupper():
                # Título de sección sin código (p. ej. "SISTEMA DE GESTIÓN DE CALIDAD" en FSMA)
                seccion, seccion_titulo = "", siguiente
                continue
            if not codigo or codigo == "-" or codigo.startswith("#"):
                continue
            nivel_original = celdas[col["nivel"]] if col["nivel"] < len(celdas) else ""
            if not nivel_original:
                # Fila de sección: el título viene en la misma celda o en la siguiente con texto
                m = RE_SECCION_TABLA.match(codigo)
                if m:
                    seccion, seccion_titulo = m.group(1), m.group(2).strip()
                else:
                    resto = [c for c in celdas[col["codigo"] + 1:] if c and c != "-" and not c.startswith("#")]
                    seccion, seccion_titulo = codigo, resto[0] if resto else ""
                continue
            nivel = NIVELES.get(normalizar(nivel_original))
            if not nivel:
                advertencias.append(f"{titulo} fila {n}: nivel desconocido '{nivel_original}' en {codigo}")
            texto = celdas[col["texto"]]
            if "pregunta" in col and celdas[col["pregunta"]]:
                texto = f"{celdas[col['pregunta']]}\n\n{texto}"
            criterio = celdas[col["criterios"]]
            if criterio:
                texto += f"\n\nCriterio de cumplimiento: {criterio}"
            if codigo in puntos:
                advertencias.append(f"{titulo} fila {n}: {codigo} repetido, se usa la primera aparición")
                continue
            if not seccion:
                # Hoja sin filas de sección (p. ej. módulo Nurture): un solo grupo con el nombre de la hoja
                seccion, seccion_titulo = re.sub(r"[\s\d.]+$", "", codigo) or codigo, seccion_titulo or titulo
            puntos[codigo] = PuntoControl(codigo, seccion, seccion_titulo, texto, nivel or "sin_nivel",
                                          orden_codigo(codigo))
    protocolo = _protocolo_tabla(portada, list(hojas), nombre_archivo)
    lista = sorted(puntos.values(), key=lambda p: p.orden)
    return ChecklistLeido("Tabla de principios y criterios", protocolo, _version_portada(portada, nombre_archivo),
                          lista, advertencias)


# ---------- GRASP ----------

def _leer_grasp(hojas: dict[str, list[tuple]]) -> ChecklistLeido:
    advertencias: list[str] = []
    m = re.search(r"versi[oó]n\s*([\w.\-]+)", _textos(hojas.get("Introduction", [])), re.IGNORECASE)
    version = f"v{m.group(1)}" if m else "sin versión"
    puntos: dict[str, PuntoControl] = {}
    titulo_actual, pc_actual, pc_texto = "", "", ""
    for n, fila in enumerate(hojas["Calculation Preview"], start=1):
        celdas = [_texto(c) for c in fila] + [""] * 4
        codigo, texto = celdas[2], celdas[3]
        if not texto or not celdas[0].isdigit():
            continue
        if not codigo:
            titulo_actual = texto.capitalize()
        elif "." not in codigo:
            pc_actual, pc_texto = codigo, re.sub(r"^PC:\s*", "", texto)
        elif codigo in puntos:
            advertencias.append(f"fila {n}: {codigo} repetido, se usa la primera aparición")
        else:
            puntos[codigo] = PuntoControl(codigo, pc_actual, titulo_actual,
                                          f"{texto}\n\nPunto de control: {pc_texto}", "sin_nivel", orden_codigo(codigo))
    if not puntos:
        raise ValueError("La hoja 'Calculation Preview' de GRASP no trae criterios")
    return ChecklistLeido("GRASP", "GRASP", version, sorted(puntos.values(), key=lambda p: p.orden), advertencias)


# ---------- PrimusGFS ----------

def _encabezado_primus(fila: tuple) -> dict[str, int] | None:
    claves = [normalizar(_texto(c)) for c in fila]
    if "pregunta" in claves and "puntos totales" in claves:
        i = claves.index("pregunta")
        return {"seccion": max(i - 2, 0), "codigo": i - 1, "pregunta": i, "puntos": claves.index("puntos totales"),
                "comentario": claves.index("comentarios del auditor") if "comentarios del auditor" in claves else -1}
    return None


def _codigo_primus(valor) -> tuple[str | None, bool]:
    """(código, completo). La conversión desde PDF deja '5.01.01' como fecha 2001-05-01."""
    if isinstance(valor, datetime):
        return f"{valor.month}.{valor.day:02d}.{valor.year % 100:02d}", True
    m = RE_PRIMUS_INICIO.match(_texto(valor))
    if not m:
        return None, False
    if m.group(3):
        return f"{m.group(1)}.{int(m.group(2)):02d}.{int(m.group(3)):02d}", True
    return f"{m.group(1)}.{int(m.group(2)):02d}.", False


def _leer_primus(hojas: dict[str, list[tuple]]) -> ChecklistLeido:
    advertencias: list[str] = []
    textos = " ".join(_textos(filas, 3) for filas in hojas.values())
    m = re.search(r"v\s*(\d+(?:\.\d+)*)", textos)
    version = f"v{m.group(1)}" if m else "sin versión"
    preguntas: list[dict] = []
    actual: dict | None = None
    col: dict[str, int] | None = None
    for titulo, filas in hojas.items():
        if "historial de revision del documento" in normalizar(_textos(filas, 5)):
            continue
        for n, fila in enumerate(filas, start=1):
            encabezado = _encabezado_primus(fila)
            if encabezado:
                col = encabezado
                continue
            if col is None:
                continue
            celdas = list(fila) + [None] * MAX_COLUMNAS
            seccion = _texto(celdas[col["seccion"]])
            pregunta = _texto(celdas[col["pregunta"]])
            puntos = _texto(celdas[col["puntos"]])
            comentario = _texto(celdas[col["comentario"]]) if col["comentario"] >= 0 else ""
            codigo, completo = _codigo_primus(celdas[col["codigo"]])
            sufijo = _texto(celdas[col["codigo"]])
            if codigo:
                actual = {"codigo": codigo, "completo": completo, "seccion": [], "texto": [], "puntos": "",
                          "comentario": []}
                preguntas.append(actual)
            elif actual and not actual["completo"] and sufijo.isdigit():
                actual["codigo"] += f"{int(sufijo):02d}"
                actual["completo"] = True
            elif actual and pregunta.startswith("¿") and puntos and actual["puntos"]:
                # Pregunta sin código (se perdió al convertir): se asume la siguiente de la sección
                base, numero = actual["codigo"].rsplit(".", 1)
                actual = {"codigo": f"{base}.{int(numero) + 1:02d}", "completo": True, "seccion": [], "texto": [],
                          "puntos": "", "comentario": []}
                preguntas.append(actual)
                advertencias.append(f"{titulo} fila {n}: pregunta sin código, se asumió {actual['codigo']}")
            if actual is None:
                continue
            for clave, valor in (("seccion", seccion), ("texto", pregunta), ("comentario", comentario)):
                if valor:
                    actual[clave].append(valor)
            if puntos and not actual["puntos"]:
                actual["puntos"] = puntos

    titulos: dict[str, Counter] = {}
    puntos_control: dict[str, PuntoControl] = {}
    con_comentario = 0
    for p in preguntas:
        if not p["completo"]:
            advertencias.append(f"{p['codigo']}: código incompleto, se omite")
            continue
        seccion = p["codigo"].rsplit(".", 1)[0]
        titulo = re.sub(r"\s+", " ", " ".join(p["seccion"])).strip()
        titulo = re.sub(r"(\w) (s|nto)\b", r"\1\2", titulo)  # palabras cortadas por el PDF: "Operacionale s"
        if titulo:
            titulos.setdefault(seccion, Counter())[titulo] += 1
        texto = re.sub(r"\s+", " ", " ".join(p["texto"])).strip()
        if p["puntos"]:
            texto += f"\n\nPuntos totales: {p['puntos']}"
        con_comentario += bool(p["comentario"])
        if p["codigo"] in puntos_control:
            advertencias.append(f"{p['codigo']} repetido, se usa la primera aparición")
            continue
        puntos_control[p["codigo"]] = PuntoControl(p["codigo"], seccion, "", texto, "sin_nivel",
                                                   orden_codigo(p["codigo"]))
    for punto in puntos_control.values():
        if punto.seccion in titulos:
            punto.seccion_titulo = titulos[punto.seccion].most_common(1)[0][0]
    if not puntos_control:
        raise ValueError("No se encontraron preguntas de PrimusGFS (columnas 'Pregunta' y 'Puntos Totales')")
    if con_comentario:
        advertencias.insert(0, f"La planilla trae {con_comentario} respuestas con comentarios del auditor: "
                               "se importan solo las preguntas, no las respuestas.")
    return ChecklistLeido("PrimusGFS", "PRIMUSGFS", version,
                          sorted(puntos_control.values(), key=lambda p: p.orden), advertencias)
