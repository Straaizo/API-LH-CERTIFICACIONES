"""Lee un certificado en PDF (GLOBALG.A.P. y sus add-on, LEAF Marque, PrimusGFS) y propone su ficha.

Solo propone: norma y versión, número, vigencia, organismo certificador, empresa, sitios cubiertos,
productos y puntaje. Todo queda para revisión antes de guardar. Un PDF escaneado (sin texto) no se puede leer.
"""
import io
import re
from dataclasses import dataclass, field
from datetime import date

from utils.texto import normalizar

# Orden importa: los add-on de GLOBALG.A.P. también mencionan "GLOBALG.A.P." o "IFA"
PROTOCOLOS = [
    ("PRIMUSGFS", ["primusgfs"]),
    ("LEAF", ["leaf marque"]),
    ("FSMA_PSR", ["fsma"]),
    ("GRASP", ["grasp", "social practice"]),
    ("SPRING", ["spring add-on", "groundwater use"]),
    ("TESCO_NURTURE", ["nurture"]),
    ("GROW", ["grow add-on"]),
    ("BRCGS", ["brcgs", "brc global standard"]),
    ("SMETA", ["smeta"]),
    ("GLOBALGAP", ["integrated farm assurance", "ifa"]),
]
VERSION_NORMA = {
    "GLOBALGAP": r"(\d+\.\d+-GFS_[A-Z]{3}\d{2})",
    "FSMA_PSR": r"FSMA PSR add-on version\s*([\d.]+\d)",
    "GRASP": r"Social Practice\s*(v\d+)",
    "SPRING": r"SPRING add-on:\s*([\w.]+?)\.?\s",
    "TESCO_NURTURE": r"(v\d+_[A-Z]{3}\d{2,4})",
    "LEAF": r"LEAF MARQUE version\s*([\d.]+\d)",
    "PRIMUSGFS": r"PrimusGFS Versi[oó]n\s*([\d.]+\d)",
}
NUMERO = [r"(?:Certificate|LoC) No\.\s*(\d[\w-]*)", r"\b(PAO\s*\d+-\d+)", r"PRIMUSGFS:\s*(\d+)"]
PRODUCTOS = {"apricot": "Damasco", "cherr": "Cereza", "grape": "Uva de mesa", "uvas de mesa": "Uva de mesa",
             "nectarin": "Nectarín", "peach": "Durazno", "plum": "Ciruela"}
MESES = {"jan": 1, "ene": 1, "feb": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
         "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12, "dic": 12}
_MES = r"(?:Jan|Ene|Feb|Mar|Apr|Abr|May|Jun|Jul|Aug|Ago|Sep|Oct|Nov|Dec|Dic)[a-z]*"
FECHA = rf"(\d{{1,2}}\.\d{{1,2}}\.\d{{4}}|{_MES}\s+\d{{1,2}},\s*\d{{4}}|\d{{1,2}}\s+{_MES}\s+\d{{4}})"


@dataclass
class LecturaCertificado:
    texto_leido: bool = False
    protocolo: str | None = None
    norma_version: str | None = None
    numero: str | None = None
    entidad: str | None = None
    empresa: str | None = None  # código de empresa: LH o VS
    operacion: str | None = None  # PrimusGFS: el packing certificado
    vigente_desde: str | None = None
    vigente_hasta: str | None = None
    fecha_decision: str | None = None
    fecha_auditoria: str | None = None
    puntaje: str | None = None
    sitios: list[str] = field(default_factory=list)  # nombres de ubicación reconocidos
    productos: list[str] = field(default_factory=list)
    no_encontrados: list[str] = field(default_factory=list)


def _fecha(texto: str | None) -> str | None:
    if not texto:
        return None
    texto = texto.strip()
    try:
        if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", texto):
            return date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        if m := re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", texto):
            return date(int(m[3]), MESES[m[1][:3].lower()], int(m[2])).isoformat()
        if m := re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", texto):
            return date(int(m[3]), MESES[m[2][:3].lower()], int(m[1])).isoformat()
    except (KeyError, ValueError):
        return None
    return None


def _buscar(patrones: list[str], texto: str, flags: int = re.IGNORECASE) -> str | None:
    for patron in patrones:
        if m := re.search(patron, texto, flags):
            return m.group(1).strip()
    return None


def texto_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(contenido)).pages)


def interpretar(texto: str, ubicaciones: list[str]) -> LecturaCertificado:
    """Interpreta el texto ya extraído. `ubicaciones`: nombres de ubicación conocidos (Chocalán, Itahue...)."""
    r = LecturaCertificado(texto_leido=bool(texto.strip()))
    if not r.texto_leido:
        return r
    plano = normalizar(texto)
    r.protocolo = next((codigo for codigo, claves in PROTOCOLOS if any(re.search(rf"\b{re.escape(c)}\b", plano)
                                                                          for c in claves)), None)
    if r.protocolo in VERSION_NORMA:
        r.norma_version = _buscar([VERSION_NORMA[r.protocolo]], texto, 0)
    r.numero = _buscar(NUMERO, texto)
    r.entidad = _buscar([r"certification body\s+(.+?)\s+declares", r"\n\s*([A-Z][A-Za-z .]+?)\s+declares that",
                         r"\n\s*([A-Z][A-Za-z .]+?)\s+certifica que"], texto)
    if r.entidad and r.entidad.isupper():
        r.entidad = r.entidad.title()
    r.empresa = "VS" if "viento sur" in plano else "LH" if "hornilla" in plano else None
    r.operacion = _buscar([r"OPERACI[OÓ]N\s*\n\s*(.+)"], texto)

    if m := re.search(rf"V[AÁ]LIDO DESDE:\s*{FECHA}\s*A\s*{FECHA}", texto, re.IGNORECASE):
        r.vigente_desde, r.vigente_hasta = _fecha(m[1]), _fecha(m[2])
    else:
        r.vigente_desde = _fecha(_buscar([rf"Valid from:\s*{FECHA}"], texto))
        r.vigente_hasta = _fecha(_buscar([rf"Valid to:\s*{FECHA}", rf"{FECHA}\s*Valid to:"], texto))
    r.fecha_decision = _fecha(_buscar([rf"decision:\s*{FECHA}"], texto))
    r.fecha_auditoria = _fecha(_buscar([rf"FECHA DE AUDITOR[IÍ]A:\s*{FECHA}"], texto))
    r.puntaje = _buscar([r"PUNTUACI[OÓ]N FINAL DE LA AUDITOR[IÍ]A:\s*(\d+\s*%)"], texto)

    # Sitios: en PrimusGFS solo la operación certificada; en el resto, los que nombra el anexo
    # (sin el encabezado "Issued to": ahí va la dirección de la empresa, que no es un sitio cubierto)
    donde = (normalizar(r.operacion) if r.protocolo == "PRIMUSGFS" and r.operacion
             else re.sub(r"issued to.*?declares", " ", plano))
    for nombre in ubicaciones:
        clave = normalizar(nombre)
        alias = {clave, clave.replace("santa ", "sta ")}
        if any(re.search(rf"\b{re.escape(a)}\b", donde) for a in alias):
            r.sitios.append(nombre)
    r.productos = sorted({v for k, v in PRODUCTOS.items() if k in plano})

    for campo, etiqueta in (("protocolo", "norma"), ("numero", "número de certificado"),
                            ("vigente_hasta", "vencimiento"), ("vigente_desde", "inicio de vigencia"),
                            ("empresa", "empresa"), ("sitios", "sitios cubiertos")):
        if not getattr(r, campo):
            r.no_encontrados.append(etiqueta)
    return r


def leer_certificado(contenido: bytes, nombre: str, ubicaciones: list[str]) -> LecturaCertificado:
    if not nombre.lower().endswith(".pdf"):
        return LecturaCertificado()
    try:
        texto = texto_pdf(contenido)
    except Exception:
        return LecturaCertificado()
    return interpretar(texto, ubicaciones)
