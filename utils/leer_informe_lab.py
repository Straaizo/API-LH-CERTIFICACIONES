"""Lee un informe de laboratorio (PDF con texto, Excel, CSV o TXT) y propone los valores del análisis.

Solo completa lo que ya existe en la aplicación: los parámetros del tipo de análisis, la fecha de muestreo,
el laboratorio, el punto o cuartel y la especie del campo. Todo queda para revisión antes de guardar.
Las fotos o PDF escaneados (sin texto) no se pueden leer: se informa y se ingresa a mano.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

from utils.texto import normalizar

MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                     "septiembre", "octubre", "noviembre", "diciembre"], start=1)}
RE_FECHA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b|\b(\d{4})-(\d{2})-(\d{2})\b|"
                      r"\b(\d{1,2})\s+de\s+([a-z]+)\s+(?:de|del)\s+(\d{4})\b")
RE_VALOR = re.compile(r"([<>≤≥]\s*)?(\d+(?:[.,]\d+)?)")
PALABRAS_VALOR = {"ausencia": 0.0, "ausente": 0.0, "no detectado": 0.0, "n.d.": 0.0, "nd": 0.0, "presencia": None,
                  "presente": None}
# Nombres alternativos con que los laboratorios suelen informar cada parámetro
ALIAS = {
    "ph": ["ph"],
    "conductividad": ["conductividad electrica", "conductividad", "c.e."],
    "nitratos": ["nitratos", "nitrato", "no3"],
    "coliformes fecales": ["coliformes fecales", "coliformes termotolerantes", "termotolerantes"],
    "e. coli": ["e. coli", "e.coli", "escherichia coli"],
    "materia organica": ["materia organica", "m.o."],
    "nitrogeno": ["nitrogeno total", "nitrogeno", "n total"],
    "potasio": ["potasio"],
    "calcio": ["calcio"],
}
LABORATORIOS = ["agrolab", "andes analytical", "labser", "silob", "eurofins", "sgs", "bureau veritas", "als",
                "hidrolab", "agq", "ufrontera", "inia", "inacap", "analab", "laboratorio de suelos"]
PALABRAS_TIPO = {
    "Suelo": ["analisis de suelo", "suelo"],
    "Hoja": ["foliar", "hoja", "tejido vegetal"],
    "Fruta": ["fruto", "fruta"],
    "MRL": ["residuos de plaguicidas", "multirresiduo", "mrl", "lmr", "plaguicida"],
    "Agua microbiológica": ["coliformes", "microbiologic", "e. coli"],
    "Agua fisicoquímica": ["fisicoquimic", "conductividad", "nitrato"],
}
SINONIMOS_ESPECIE = {"cereza": "cerezo", "ciruela": "ciruelo", "nectarin": "nectarino", "durazno": "duraznero",
                     "arandano": "arandano", "manzana": "manzano", "uva": "vid", "pera": "peral", "kiwi": "kiwi",
                     "palta": "palto", "almendra": "almendro", "nuez": "nogal"}


@dataclass
class LecturaInforme:
    texto_leido: bool = False
    tipo_sugerido: str | None = None
    fecha_muestreo: str | None = None
    laboratorio: str | None = None
    punto: str | None = None
    especie: str | None = None
    resultados: list[dict] = field(default_factory=list)
    no_encontrados: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


def _lineas(contenido: bytes, nombre: str) -> list[str]:
    extension = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if extension == "pdf":
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(contenido))
        texto = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
        return [l.strip() for l in texto.splitlines() if l.strip()]
    if extension in ("xlsx", "xlsm"):
        import openpyxl
        libro = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
        lineas = []
        for hoja in libro.worksheets:
            for fila in hoja.iter_rows(values_only=True):
                celdas = [str(c).strip() for c in fila if c is not None and str(c).strip()]
                if celdas:
                    lineas.append(" ".join(celdas))
        return lineas
    if extension in ("csv", "txt"):
        try:
            texto = contenido.decode("utf-8")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
        if extension == "csv":
            return [" ".join(c.strip() for c in fila if c.strip()) for fila in csv.reader(io.StringIO(texto))
                    if any(c.strip() for c in fila)]
        return [l.strip() for l in texto.splitlines() if l.strip()]
    return []


def _fecha(texto: str) -> str | None:
    m = RE_FECHA.search(texto)
    if not m:
        return None
    try:
        if m.group(1):
            anio = int(m.group(3))
            anio += 2000 if anio < 100 else 0
            return date(anio, int(m.group(2)), int(m.group(1))).isoformat()
        if m.group(4):
            return date(int(m.group(4)), int(m.group(5)), int(m.group(6))).isoformat()
        mes = MESES.get(m.group(8))
        return date(int(m.group(9)), mes, int(m.group(7))).isoformat() if mes else None
    except ValueError:
        return None


def _alias(parametro: str) -> list[str]:
    base = normalizar(re.sub(r"\(.*?\)", "", parametro)).strip()
    return list(dict.fromkeys(ALIAS.get(base, []) + [base]))


def _buscar_valor(lineas_norm: list[str], originales: list[str], alias: list[str]) -> dict | None:
    for i, linea in enumerate(lineas_norm):
        for a in alias:
            m = re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", linea)
            if not m:
                continue
            resto = linea[m.end():]
            siguientes = [resto] + ([lineas_norm[i + 1]] if i + 1 < len(lineas_norm) else [])
            for texto in siguientes:
                for palabra, valor in PALABRAS_VALOR.items():
                    if re.match(rf"[\s:=|-]*{re.escape(palabra)}\b", texto):
                        return {"valor": valor, "valor_texto": palabra.capitalize(), "linea": originales[i][:120]}
                v = RE_VALOR.search(texto)
                if v and v.start() < 25:
                    numero = float(v.group(2).replace(",", "."))
                    signo = (v.group(1) or "").strip()
                    return {"valor": numero, "valor_texto": f"{signo} {v.group(2)}".strip() if signo else None,
                            "linea": originales[i][:120]}
    return None


def leer_informe(contenido: bytes, nombre: str, parametros: list[str], especies: list[str],
                 tipos: list[str]) -> LecturaInforme:
    lectura = LecturaInforme()
    try:
        originales = _lineas(contenido, nombre)
    except Exception as exc:
        lectura.advertencias.append(f"No se pudo abrir el archivo: {exc}")
        return lectura
    if not originales:
        lectura.advertencias.append(
            "No se encontró texto en el archivo (foto o PDF escaneado). Completa los valores a mano.")
        return lectura
    lectura.texto_leido = True
    normales = [normalizar(l) for l in originales]
    completo = " \n".join(normales)

    # Tipo de análisis sugerido (solo entre los tipos existentes)
    for tipo, palabras in PALABRAS_TIPO.items():
        if tipo in tipos and any(p in completo for p in palabras):
            lectura.tipo_sugerido = tipo
            break

    # Fecha de muestreo: primero una línea que la mencione; si no, la primera fecha del informe
    for linea in normales:
        if any(p in linea for p in ("muestreo", "toma de muestra", "fecha de muestra", "fecha muestra")):
            if fecha := _fecha(linea):
                lectura.fecha_muestreo = fecha
                break
    if not lectura.fecha_muestreo and (fecha := _fecha(completo)):
        lectura.fecha_muestreo = fecha
        lectura.advertencias.append("La fecha de muestreo no aparece rotulada: se usó la primera fecha del informe")

    lectura.laboratorio = next((l.title() for l in LABORATORIOS if l in completo), None)
    if not lectura.laboratorio:
        linea = next((o for o, n in zip(originales, normales) if "laboratorio" in n and len(o) <= 70), None)
        lectura.laboratorio = linea

    for o, n in zip(originales, normales):
        m = re.search(r"(cuartel|punto de muestreo|identificacion de (?:la )?muestra|sector)\s*[:\-]?\s*(.+)", n)
        if m and m.group(2).strip():
            inicio = len(o) - len(m.group(2))
            lectura.punto = o[max(inicio, 0):][:60].strip() or None
            break

    for especie in especies:
        e = normalizar(especie)
        claves = [e] + [k for k, v in SINONIMOS_ESPECIE.items() if v == e]
        if any(re.search(rf"\b{re.escape(c)}s?\b", completo) for c in claves):
            lectura.especie = especie
            break

    for parametro in parametros:
        encontrado = _buscar_valor(normales, originales, _alias(parametro))
        if encontrado:
            lectura.resultados.append({"parametro": parametro, **encontrado})
        else:
            lectura.no_encontrados.append(parametro)
    if parametros and not lectura.resultados:
        lectura.advertencias.append("No se reconocieron los parámetros de este tipo de análisis en el informe")
    return lectura
