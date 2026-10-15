import re
import unicodedata


def sin_tildes(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def nombre_archivo_seguro(texto: str, largo: int = 120) -> str:
    """Nombre apto para ZIP: sin tildes ni caracteres especiales."""
    limpio = re.sub(r"[^A-Za-z0-9._ ()-]+", "_", sin_tildes(texto)).strip(" ._")
    return (limpio or "archivo")[:largo]


def normalizar(texto: str | None) -> str:
    return re.sub(r"\s+", " ", sin_tildes(texto or "").lower()).strip()
