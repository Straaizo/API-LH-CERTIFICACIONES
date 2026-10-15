"""Interpreta un documento fijo recién subido (PDF o Word) para proponer cómo completar el formulario.

Reconoce certificados de protocolo (con su ficha, vía leer_certificado) y, en el resto, el código
(P OC CE 29, DPL 23), la categoría por sus palabras clave, la empresa y un título. Solo propone:
la aplicación pregunta antes de rellenar nada.
"""
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from utils.leer_certificado import LecturaCertificado, interpretar, texto_pdf
from utils.texto import normalizar

RE_CODIGO = re.compile(r"\b(P\s*OC\s*[A-Z]{2,3}\s*\d{1,3}|DPL\s*\d{1,3})\b")
# Orden importa: un análisis de riesgos puede mencionar "procedimiento"
CATEGORIAS = [
    ("Análisis de riesgos", ["analisis de riesgo", "evaluacion de riesgo", "evaluacion de peligro"]),
    ("Instructivos", ["instructivo"]),
    ("Planes de gestión", ["plan de gestion", "plan de control", "plan de "]),
    ("Procedimientos", ["procedimiento"]),
]


@dataclass
class AnalisisDocumento:
    texto_leido: bool = False
    certificado: LecturaCertificado | None = None
    codigo: str | None = None
    categoria: str | None = None  # nombre de la categoría propuesta
    empresa: str | None = None  # LH o VS
    titulo: str | None = None
    codigos_en_texto: list[str] = field(default_factory=list)


def formato_codigo(codigo: str) -> str:
    """'POCCE29' o 'P OC CE 29' → 'P OC CE 29'; 'DPL23' → 'DPL 23'."""
    c = re.sub(r"\s+", "", codigo.upper())
    if m := re.fullmatch(r"POC([A-Z]{2,3})(\d{1,3})", c):
        return f"P OC {m[1]} {m[2]}"
    if m := re.fullmatch(r"DPL(\d{1,3})", c):
        return f"DPL {m[1]}"
    return codigo.strip().upper()


def extraer_texto(contenido: bytes, nombre: str) -> str:
    extension = Path(nombre).suffix.lower()
    try:
        if extension == ".pdf":
            return texto_pdf(contenido)
        if extension == ".docx":
            from docx import Document
            return "\n".join(p.text for p in Document(io.BytesIO(contenido)).paragraphs)
    except Exception:
        return ""
    return ""


def _titulo(texto: str, codigo: str | None, nombre: str) -> str | None:
    if codigo:
        # La línea que trae el código suele traer también el título: "P OC CE 29 Procedimiento de ..."
        patron = re.compile(r"\s*".join(re.escape(x) for x in codigo.split()), re.IGNORECASE)
        for linea in texto.splitlines():
            if patron.search(linea):
                resto = patron.sub(" ", linea)
                resto = re.sub(r"\b(v|versi[oó]n)\s*\d+\b", " ", resto, flags=re.IGNORECASE)
                resto = re.sub(r"\s+", " ", resto).strip(" -–·:|")
                if len(resto.split()) >= 2:
                    return resto[:250]
    base = re.sub(r"[_]+", " ", Path(nombre).stem)
    base = re.sub(r"\s+", " ", base).strip()
    return base[:250] or None


def analizar(contenido: bytes, nombre: str, ubicaciones: list[str]) -> AnalisisDocumento:
    texto = extraer_texto(contenido, nombre)
    return analizar_texto(texto, nombre, ubicaciones)


def analizar_texto(texto: str, nombre: str, ubicaciones: list[str]) -> AnalisisDocumento:
    r = AnalisisDocumento(texto_leido=bool(texto.strip()))
    plano = normalizar(f"{texto} {Path(nombre).stem.replace('_', ' ')}")
    r.empresa = "VS" if "viento sur" in plano else "LH" if "hornilla" in plano else None
    if r.texto_leido:
        cert = interpretar(texto, ubicaciones)
        # Es certificado solo si trae norma, número y vencimiento (un procedimiento puede nombrar la norma)
        if cert.protocolo and cert.numero and cert.vigente_hasta:
            r.certificado = cert
            r.empresa = cert.empresa or r.empresa
            return r
    r.codigos_en_texto = list(dict.fromkeys(formato_codigo(c) for c in RE_CODIGO.findall(texto)))
    nombre_codigos = [formato_codigo(c) for c in RE_CODIGO.findall(Path(nombre).stem.replace("_", " "))]
    r.codigo = (nombre_codigos or r.codigos_en_texto or [None])[0]
    inicio = normalizar(texto[:3000]) or plano
    r.categoria = next((cat for cat, claves in CATEGORIAS if any(c in inicio for c in claves)), None)
    r.titulo = _titulo(texto, r.codigo, nombre)
    return r
