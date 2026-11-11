"""Lee la carta de mercados de destino de GESEX: países de exportación por especie para una temporada.

Formato (2025 Carta destino 0723.pdf):
    Para: 0723 Agricola Viento Sur SPA
    ... durante la temporada 2025-2026 serán:
    • Ciruelas: Estados Unidos, U.E., Inglaterra, Canadá y China.
    • Cerezas: Estados Unidos, U.E., Inglaterra, Canadá, China, Taiwán, Japón,
    Corea.
El PDF trae espacios cortando palabras ("Chin a", "202 5"): se compara sin espacios.
Los países se traducen a los nombres de las columnas de ASOEX (USA, UE, UK…).
"""
import io
import re
from dataclasses import dataclass, field
from datetime import date

from utils.importar_asoex import normalizar

# Nombre en la carta (sin tildes ni espacios) → columna de ASOEX
PAISES = {
    "ESTADOSUNIDOS": "USA", "EEUU": "USA", "USA": "USA", "UE": "UE", "UNIONEUROPEA": "UE", "EUROPA": "UE",
    "INGLATERRA": "UK", "REINOUNIDO": "UK", "UK": "UK", "CANADA": "CANADA", "CHINA": "CHINA", "TAIWAN": "TAIWAN",
    "JAPON": "JAPON", "COREA": "COREA", "COREADELSUR": "COREA", "HONGKONG": "HONG KONG", "INDIA": "INDIA",
    "BRASIL": "BRASIL", "MEXICO": "MEXICO", "ARGENTINA": "ARGENTINA", "RUSIA": "RUSIA", "TAILANDIA": "TAILANDIA",
    "VIETNAM": "VIETNAM", "INDONESIA": "INDONESIA", "FILIPINAS": "FILIPINAS", "SINGAPUR": "SINGAPUR",
    "MALASIA": "MALASIA", "ARABIASAUDITA": "ARABIA SAUDITA", "EMIRATOSARABESUNIDOS": "EAU", "EAU": "EAU",
    "AUSTRALIA": "AUSTRALIA", "NUEVAZELANDA": "NUEVA ZELANDA", "COLOMBIA": "COLOMBIA", "PERU": "PERU",
    "ECUADOR": "ECUADOR", "COSTARICA": "COSTA RICA",
}
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


@dataclass
class CartaDestino:
    destinatario: str | None = None  # "0723 Agricola Viento Sur SPA"
    temporada: str | None = None  # "25-26"
    fecha: date | None = None
    destinos: dict[str, list[str]] = field(default_factory=dict)  # {"CEREZAS": ["USA", "UE", ...]}
    sin_traducir: list[str] = field(default_factory=list)  # países que no se pudieron llevar a ASOEX


def _texto(contenido: bytes) -> str:
    from pypdf import PdfReader
    texto = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(contenido)).pages)
    return re.sub(r"(?<=\d) (?=\d)", "", texto)  # "202 5" → "2025"


def leer_carta_destino(contenido: bytes) -> CartaDestino:
    try:
        texto = _texto(contenido)
    except Exception as exc:
        raise ValueError("No se pudo leer el PDF de la carta de destino") from exc
    carta = CartaDestino()
    if m := re.search(r"Para\s*:\s*(.+)", texto):
        carta.destinatario = re.sub(r"\s+", " ", m[1]).strip()
    if m := re.search(r"(\d{4})\s*-\s*(\d{4})", re.sub(r"\s+", " ", texto.split("•")[0])):
        carta.temporada = f"{m[1][2:]}-{m[2][2:]}"
    if m := re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", texto, re.I):
        mes = MESES.get(normalizar(m[2]).lower())
        if mes:
            carta.fecha = date(int(m[3]), mes, int(m[1]))

    # Cada viñeta "• Especie: países" puede seguir en la línea siguiente
    cuerpo = re.split(r"Se extiende|Saluda", texto)[0]
    for bloque in cuerpo.split("•")[1:]:
        if ":" not in bloque:
            continue
        especie, paises = bloque.split(":", 1)
        especie = normalizar(especie)
        if not especie:
            continue
        lista = []
        for parte in re.split(r",|\by\b|\n", paises.replace(".", "").strip()):
            clave = normalizar(parte)
            if not clave:
                continue
            pais = PAISES.get(clave)
            if pais is None:
                carta.sin_traducir.append(parte.strip())
                pais = clave
            if pais not in lista:
                lista.append(pais)
        if lista:
            carta.destinos[especie] = lista
    if not carta.destinos:
        raise ValueError("La carta no tiene el formato esperado: viñetas '• Especie: países'")
    return carta


def especie_asoex(clave: str, frutas_asoex: list[str]) -> str:
    """'CIRUELAS' (de la carta, sin espacios) → el nombre de la hoja de ASOEX ('CIRUELAS'; 'UVADEMESA' → 'UVA DE MESA')."""
    return next((f for f in frutas_asoex if normalizar(f) == clave), clave)
