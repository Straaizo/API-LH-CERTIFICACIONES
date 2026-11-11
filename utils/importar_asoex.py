"""Lee la "Agenda de pesticidas" de ASOEX: límites máximos de residuos (ppm) y carencias por fruta, sustancia y país.

Formatos: la planilla general "LMR ASOEX dd-mm-aaaa.xlsx" (una hoja por fruta) o la "Agenda de pesticidas" de
Frutas de Chile por especie (AgendaPesticidasFdch_CEREZAS_20102026_….xlsx: hoja "Resultado" con "Fecha Descarga").
En ambos casos, cada hoja de fruta tiene: Fila de países (cada país ocupa dos columnas: ppm y días),
seguida de la fila "SUSTANCIA ACTIVA | TIPO PRODUCTO | ppm | dias | ...". Valores especiales:
  ST = sin tolerancia (no se acepta residuo) · EX = exento (sin límite) · "/" o vacío = sin información.
Las mezclas ("ABAMECTIN/CYANTRANILIPROLE" con "0,01/2") se separan por componente cuando no hay fila propia.
Al final de cada hoja puede venir "Próximos cambios" con los cambios anunciados.
"""
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import load_workbook

CONDICIONES = {"ST", "EX"}


@dataclass
class Limite:
    sustancia: str
    tipo_producto: str | None
    pais: str
    ppm: float | None
    condicion: str | None  # ST | EX
    carencia_dias: int | None


@dataclass
class FrutaAsoex:
    nombre: str  # CEREZAS, CIRUELAS / LOBESIA BOTRANA...
    hoja: str
    paises: list[str] = field(default_factory=list)
    limites: list[Limite] = field(default_factory=list)
    proximos_cambios: list[str] = field(default_factory=list)
    fecha: date | None = None  # "Fecha Descarga" de la agenda por especie


def normalizar(texto: str) -> str:
    """Para comparar nombres: sin tildes, mayúsculas, sin espacios ni signos."""
    plano = unicodedata.normalize("NFD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", plano.upper())


def _numero(texto: str) -> float | None:
    try:
        return float(texto.strip().replace(",", "."))
    except ValueError:
        return None


def _valor(celda) -> tuple[float | None, str | None] | None:
    """(ppm, condición) o None si no hay información."""
    if celda is None:
        return None
    if isinstance(celda, (int, float)):
        return float(celda), None
    texto = str(celda).strip().upper()
    if not texto or set(texto) <= {"/", "-"}:
        return None
    if texto in CONDICIONES:
        return None, texto
    numero = _numero(texto)
    return (numero, None) if numero is not None else None


def _dias(celda) -> int | None:
    if isinstance(celda, (int, float)):
        return int(celda)
    numero = _numero(str(celda)) if celda is not None else None
    return int(numero) if numero is not None else None


def _fecha_celda(celda) -> date | None:
    if isinstance(celda, datetime):
        return celda.date()
    if isinstance(celda, date):
        return celda
    return fecha_en_nombre(str(celda or ""))


def _leer_hoja(ws) -> FrutaAsoex | None:
    filas = list(ws.iter_rows(values_only=True))
    cabecera = next((i for i, f in enumerate(filas) if f and str(f[0] or "").strip().upper() == "SUSTANCIA ACTIVA"), None)
    if cabecera is None or cabecera == 0:
        return None
    fila_paises = filas[cabecera - 1]
    fruta = FrutaAsoex(nombre=str(fila_paises[0] or ws.title).strip().upper(), hoja=ws.title)
    for f in filas[:cabecera]:
        if f and str(f[0] or "").strip().lower().startswith("fecha descarga") and len(f) > 1:
            fruta.fecha = _fecha_celda(f[1])
    columnas = [(j, str(p).strip().upper()) for j, p in enumerate(fila_paises) if j >= 2 and p and str(p).strip()]
    fruta.paises = [p for _, p in columnas]

    unicos: dict[tuple[str, str], Limite] = {}
    de_mezcla: dict[tuple[str, str], Limite] = {}
    en_cambios = False
    for f in filas[cabecera + 1:]:
        primera = str(f[0] or "").strip() if f else ""
        if not primera:
            continue
        if primera.lower().startswith("próximos cambios") or primera.lower().startswith("proximos cambios"):
            en_cambios = True
            continue
        if en_cambios:
            fruta.proximos_cambios += [x.strip() for x in primera.splitlines() if x.strip()]
            continue
        nombre = primera.lstrip("+").strip().upper()
        tipo = str(f[1]).strip().upper() if len(f) > 1 and f[1] else None
        componentes = [c.strip() for c in nombre.split("/") if c.strip()]
        for j, pais in columnas:
            celda = f[j] if j < len(f) else None
            dias = _dias(f[j + 1]) if j + 1 < len(f) else None
            if len(componentes) == 1:
                v = _valor(celda)
                if v:
                    unicos[(componentes[0], pais)] = Limite(componentes[0], tipo, pais, v[0], v[1], dias)
                continue
            # Mezcla: "0,01/2" → un límite por componente (solo si la sustancia no tiene fila propia)
            partes = str(celda).split("/") if celda is not None else []
            if len(partes) != len(componentes):
                continue
            for componente, parte in zip(componentes, partes):
                v = _valor(parte)
                if v:
                    de_mezcla.setdefault((componente, pais), Limite(componente, tipo, pais, v[0], v[1], None))
    for clave, limite in de_mezcla.items():
        unicos.setdefault(clave, limite)
    fruta.limites = list(unicos.values())
    return fruta


def leer_asoex(contenido: bytes) -> list[FrutaAsoex]:
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError("No se pudo abrir la planilla: debe ser el Excel de LMR de ASOEX") from exc
    frutas = [f for f in (_leer_hoja(ws) for ws in libro.worksheets) if f and f.limites]
    if not frutas:
        raise ValueError("La planilla no tiene el formato de ASOEX (fila 'SUSTANCIA ACTIVA' con los países arriba)")
    return frutas


def fecha_en_nombre(nombre: str):
    """'LMR ASOEX 28-09-2026.xlsx' → 2026-09-28; 'AgendaPesticidasFdch_CEREZAS_20102026_163004.xlsx' → 2026-10-20."""
    m = (re.search(r"(\d{1,2})[-_.](\d{1,2})[-_.](\d{4})", nombre or "")
         or re.search(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", nombre or ""))
    if not m:
        return None
    try:
        return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None
