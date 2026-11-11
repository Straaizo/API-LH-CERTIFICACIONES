"""Lee los informes de auditorías externas (PDF de la certificadora) y arma su resumen.

Formatos (Primus Auditing Ops, temporada 25-26):
- GLOBALG.A.P. (IFA v6 GFS, Tesco Nurture, addendum FSMA): "Reporte Final de Auditoría" o "Reporte de No
  Conformidades", con puntaje por nivel (Mayor, Menor, Recomendable) antes y después de las acciones correctivas,
  el conteo de preguntas Sí / No / N/A y cada pregunta con el comentario del auditor.
- "RESPUESTA DE ACCIONES CORRECTIVAS": cada No con la respuesta del auditado y si el auditor la aceptó.
- PrimusGFS (empaque): puntaje preliminar y final, vigencia del certificado y cada pregunta con su clasificación
  (Cumple totalmente, Deficiencia menor o mayor, No cumple, No aplicable).
"""
import io
import re
from dataclasses import dataclass, field
from datetime import date

MESES = {"ene": 1, "jan": 1, "feb": 2, "mar": 3, "abr": 4, "apr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "aug": 8,
         "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}

NORMAS = [  # (código de protocolo, señales en el encabezado; el alcance suele nombrar otras normas)
    ("PRIMUSGFS", ["primusgfs versión", "primusgfs version", "número de auditoría primusgfs"]),
    ("TESCO_NURTURE", ["nurture module"]),
    ("FSMA_PSR", ["addendum sobre las reglas de inocuidad alimentaria de fsma"]),
    ("GLOBALGAP", ["globalg.a.p. ifa", "ifa version 6"]),
    ("GRASP", ["| grasp", "grasp module"]),
]
PREFIJO_SITIO = r"(?:Fundo|Campo|Packing|Planta|Huerto|Empaque)"
TIPOS = {"final": "Reporte final", "no_conformidades": "Reporte de no conformidades",
         "acciones_correctivas": "Respuesta de acciones correctivas"}


@dataclass
class Hallazgo:
    codigo: str
    texto: str
    comentario: str
    nivel: str | None = None  # menor | mayor (PrimusGFS)
    respuesta_auditado: str | None = None
    respuesta_auditor: str | None = None  # Aceptado | Rechazado...


@dataclass
class LecturaAuditoriaExterna:
    texto_leido: bool = False
    protocolo: str | None = None
    tipo_informe: str = "final"
    version_informe: str | None = None
    numero: str | None = None
    entidad: str | None = None
    auditor: str | None = None
    organizacion: str | None = None
    empresa: str | None = None  # LH | VS
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    sitios: list[str] = field(default_factory=list)
    productos: str | None = None
    puntajes: list[dict] = field(default_factory=list)  # {nivel, valor, despues_ac}
    certificado_desde: date | None = None
    certificado_hasta: date | None = None
    preguntas: dict = field(default_factory=lambda: {"total": 0, "si": 0, "no": 0, "na": 0})
    secciones: list[dict] = field(default_factory=list)  # {codigo, titulo, si, no, na}
    hallazgos: list[Hallazgo] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)


def _texto_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(contenido)).pages)


def _fecha_texto(texto: str | None) -> date | None:
    """'Ene 14, 2026', '14/Jan/2026', '06 Mar 2026', '05 May 2026'."""
    if not texto:
        return None
    for patron, orden in ((r"([A-Za-z]{3})\w*\.? (\d{1,2}), (\d{4})", "mda"), (r"(\d{1,2})[/ ]([A-Za-z]{3})\w*[/ ](\d{4})", "dma")):
        if m := re.search(patron, texto):
            partes = dict(zip(orden, m.groups()))
            mes = MESES.get(partes["m"].lower()[:3])
            if mes:
                try:
                    return date(int(partes["a"]), mes, int(partes["d"]))
                except ValueError:
                    return None
    return None


def _porcentaje(texto: str) -> float | None:
    try:
        return float(texto.replace(",", ".").rstrip("%"))
    except ValueError:
        return None


def _limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def _seccion(codigo: str) -> str:
    """'FV-GFS 10.02' → 'FV 10'; 'FSMA 01.03' → 'FSMA 01'; '1.01.05' → '1.01'."""
    if m := re.match(r"([A-Za-z]+)[-A-Za-z]*\s?(\d+)", codigo):
        return f"{m[1].upper()} {m[2]}"
    return ".".join(codigo.split(".")[:2])


def _sitios(corrido: str) -> list[str]:
    """Sitios auditados del encabezado (sin el domicilio de la organización, que nombra la casa matriz)."""
    cortes = [i for i in (corrido.find("RESUMEN DE PUNTUACI"), corrido.find("Pregunta:"), corrido.find("RESUMEN DE RESPUESTA A LA PREGUNTA Coordenadas"),
                          corrido.find("Coordenadas GPS")) if i > 0]
    encabezado = corrido[:min(cortes) if cortes else len(corrido)]
    nombre = r"(?:[A-ZÁÉÍÓÚ][a-záéíóúñ]+ ?){1,3}?"
    encontrados = (
        # "Sitio de producción: Campo Chocalan Contactos..." / "...: Fundo Hospital Uvas de mesa,Ciruelas"
        re.findall(rf"Sitio de\s*producción:\s*({PREFIJO_SITIO}\s+{nombre})(?=\s*(?:Contactos|Sitio|Domicilio|"
                   rf"[A-ZÁÉÍÓÚ][a-záéíóúñ]+(?: de [a-z]+)?,|$))", encabezado)
        # Tabla "Sitio auditado": "04/Feb/2026 04/Feb/2026 09:00 19:00 Fundo Santa Ines"
        + re.findall(rf"\d{{2}}:\d{{2}} \d{{2}}:\d{{2}} ({PREFIJO_SITIO} {nombre})(?=\s*(?:\d{{1,2}}/|Productos|RESUMEN|$))", encabezado)
        # PrimusGFS: "Operación Packing Maiten Gigante Contacto(s)"
        + re.findall(rf"Operación\s+({PREFIJO_SITIO}\s+.+?)\s+Contacto", encabezado)
    )
    unicos: dict[str, str] = {}
    for sitio in (_limpiar(x) for x in encontrados):
        clave = re.sub(r"[^a-z]", "", sitio.lower().translate(str.maketrans("áéíóúñ", "aeioun")))
        unicos.setdefault(clave, sitio)
    return list(unicos.values())


def _globalgap(texto: str, r: LecturaAuditoriaExterna) -> None:
    corrido = _limpiar(texto)
    r.entidad = (m[1].strip() if (m := re.search(r"Compañía de Auditoría:\s*(.+?)\s+ID de Auditoría", corrido)) else None)
    r.numero = m[1] if (m := re.search(r"ID de Auditoría:\s*(\d+)", corrido)) else None
    r.version_informe = m[1] if (m := re.search(r"\bVersion (\d+)", corrido)) else None
    r.auditor = m[1].strip() if (m := re.search(r"Auditor:\s*(.+?)\s+(?:Puntuación|Plantilla|Entidades)", corrido)) else None
    r.fecha_inicio = _fecha_texto(m[1]) if (m := re.search(r"Fecha Inicial:\s*([A-Za-z]{3}\w* \d{1,2}, \d{4})", corrido)) else None
    r.fecha_fin = _fecha_texto(m[1]) if (m := re.search(r"Fecha Final:\s*([A-Za-z]{3}\w* \d{1,2}, \d{4})", corrido)) else None
    if r.fecha_inicio is None and (m := re.search(r"Fecha de\s+Auditoría.*?([A-Za-z]{3} \d{1,2}, \d{4})", corrido)):
        r.fecha_inicio = _fecha_texto(m[1])
    r.productos = m[1].strip() if (m := re.search(r"Productos:?\s+(.+?)\s+(?:Auditor:|Coordenadas|Observado)", corrido)) else None
    r.sitios = _sitios(corrido)
    for nivel in ("Mayor", "Menor", "Recomendable"):
        if m := re.search(rf"{nivel}:?\s*([\d.,]+)%\s*(?:{nivel})?\s*Después de\s*(?:CA|AC):?\s*([\d.,]+)%", corrido):
            r.puntajes.append({"nivel": nivel, "valor": _porcentaje(m[1]), "despues_ac": _porcentaje(m[2])})
        elif m := re.search(rf"{nivel}:([\d.,]+)%", corrido):  # respuesta de acciones correctivas
            despues = re.search(rf"{nivel}\s+Después de\s+AC:\s*([\d.,]+)%", corrido)
            r.puntajes.append({"nivel": nivel, "valor": _porcentaje(m[1]),
                               "despues_ac": _porcentaje(despues[1]) if despues else None})
        elif m := re.search(rf"Resumen de puntuación de la Auditoría.*?{nivel}\s+Puntos Posibles:.*?Porcentaje de Puntuación:\s*([\d.,]+)%", corrido):
            r.puntajes.append({"nivel": nivel, "valor": _porcentaje(m[1]), "despues_ac": None})
    if r.numero is None and (m := re.search(r"Productos\s+(\d{4,})\s", corrido)):
        r.numero = m[1]
    if r.auditor is None and (m := re.search(r"\d{1,2}, \d{4}\s+([A-ZÁÉÍÓÚ][a-záéíóúñ]+(?: [A-ZÁÉÍÓÚ][a-záéíóúñ]+){1,3})\s+Sitio", corrido)):
        r.auditor = m[1]
    if r.fecha_inicio is None and (m := re.search(r"([A-Za-z]{3} \d{1,2}, \d{4})", corrido)):
        r.fecha_inicio = _fecha_texto(m[1])
    if m := re.search(r"# de Preguntas\s+((?:(?:Si|No|N/A)\s+){3})(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", corrido):
        etiquetas = m[1].split()
        valores = dict(zip(etiquetas, map(int, m.groups()[2:])))
        r.preguntas = {"total": int(m[2]), "si": valores.get("Si", 0), "no": valores.get("No", 0), "na": valores.get("N/A", 0)}
    titulos = {f"{a.upper()} {int(b):02d}": _limpiar(t).title()
               for a, b, t in re.findall(r"^\s*(F[Vv]|FSMA|NT|GR)\s?(\d+)\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ,.()/-]{3,})$", texto, re.M)}

    if "RESPUESTA DE ACCIONES CORRECTIVAS" in texto.upper():
        r.tipo_informe = "acciones_correctivas"
        patron = re.compile(r"^([A-Z]{2,6}[-A-Z]*\s?\d(?:[\d.]*\d)?)\s+(.+?)\nRespuesta:\s*\n?\s*(No|Si|Sí|N/A)\s*\n"
                            r"Comentario del Auditor:\s*(.*?)\nRespuesta del Auditado:\s*(.*?)\nRespuesta del Auditor:\s*\n?\s*(\w+)",
                            re.M | re.S)
        for m in patron.finditer(texto):
            r.hallazgos.append(Hallazgo(codigo=m[1].strip(), texto=_limpiar(m[2]), comentario=_limpiar(m[4]),
                                        respuesta_auditado=_limpiar(m[5])[:600], respuesta_auditor=m[6]))
        return
    if "Reporte de No Conformidades" in corrido and "Reporte Final de Auditoría Organización" not in corrido:
        r.tipo_informe = "no_conformidades"
    patron = re.compile(r"^([A-Z]{2,6}[-A-Z]*\s?\d(?:[\d.]*\d)?)\s*\|\s*(.+?)\nComentarios del Auditor:\s*(.*?)\n"
                        r"Puntos Posibles:.*?Respuesta:\s*\n?\s*(Si|Sí|No|N/A)\b", re.M | re.S)
    conteo: dict[str, dict] = {}
    for m in patron.finditer(texto):
        codigo, respuesta = m[1].strip(), m[4].replace("Sí", "Si")
        clave = _seccion(codigo)
        sec = conteo.setdefault(clave, {"codigo": clave, "titulo": titulos.get(clave, ""), "si": 0, "no": 0, "na": 0})
        sec[{"Si": "si", "No": "no", "N/A": "na"}[respuesta]] += 1
        if respuesta == "No":
            r.hallazgos.append(Hallazgo(codigo=codigo, texto=_limpiar(m[2]), comentario=_limpiar(m[3])[:800]))
    r.secciones = list(conteo.values())
    if not r.preguntas["total"] and conteo:
        r.preguntas = {"si": sum(s["si"] for s in conteo.values()), "no": sum(s["no"] for s in conteo.values()),
                       "na": sum(s["na"] for s in conteo.values())}
        r.preguntas["total"] = sum(r.preguntas.values())


NIVELES_PRIMUS = {"cumple totalmente": "si", "deficiencia menor": "menor", "deficiencia mayor": "mayor",
                  "no cumple": "no_cumple", "no aplicable": "na"}


def _primus(texto: str, r: LecturaAuditoriaExterna) -> None:
    corrido = _limpiar(texto)
    r.entidad = (m[1].strip() if (m := re.search(r"Auditado por:\s*(.+?)\s+PrimusGFS", corrido)) else "Primus Auditing Operations")
    r.numero = m[1] if (m := re.search(r"Número de Auditoría PrimusGFS #?(\d+)", corrido)) else None
    r.version_informe = m[1] if (m := re.search(r"Revisión (\d+)", corrido)) else None
    r.auditor = m[1].strip() if (m := re.search(r"Auditor:\s*(.+?)\s*\(", corrido)) else None
    r.fecha_inicio = _fecha_texto(m[1]) if (m := re.search(r"Fecha de Inicio de la Revisión de la\s*Documentación:\s*(\d{1,2} [A-Za-z]{3} \d{4})", corrido)) else None
    r.fecha_fin = _fecha_texto(m[1]) if (m := re.search(r"Fecha Final de la Revisión de la\s*Documentación:\s*(\d{1,2} [A-Za-z]{3} \d{4})", corrido)) else None
    r.sitios = _sitios(corrido)
    r.productos = m[1].strip() if (m := re.search(r"Producto\(s\) observado\(s\) durante la\s*auditoría:\s*(.+?)\s+Producto", corrido)) else None
    for nivel, etiqueta in (("Preliminar", "Puntuación Preliminar de la Auditoría"), ("Final", "Puntuación Final de la Auditoría")):
        if m := re.search(rf"{etiqueta}:\s*([\d.,]+)%", corrido):
            r.puntajes.append({"nivel": nivel, "valor": _porcentaje(m[1]), "despues_ac": None})
    if m := re.search(r"Certificado Válido desde:\s*(\d{1,2} [A-Za-z]{3} \d{4})\s*a\s*(\d{1,2} [A-Za-z]{3} \d{4})", corrido):
        r.certificado_desde, r.certificado_hasta = _fecha_texto(m[1]), _fecha_texto(m[2])

    patron = re.compile(r"^(\d+\.\d+\.\d+)\s*\nPregunta:\s*(.+?)\nPosibles\s*puntos:.*?Puntuación:\s*\n?(.+?)\n"
                        r"Comentarios del Auditor:\s*(.+?)(?=^\d+\.\d+\.\d+\s*\nPregunta:|\Z)", re.M | re.S)
    conteo: dict[str, dict] = {}
    for m in patron.finditer(texto):
        codigo = m[1]
        # La clasificación puede venir partida en dos líneas ("Cumple\nTotalmente")
        bloque = _limpiar(m[3] + " " + m[4][:40]).lower()
        estado = next((v for k, v in NIVELES_PRIMUS.items() if bloque.startswith(k)), None)
        if estado is None:
            continue
        clave = _seccion(codigo)
        sec = conteo.setdefault(clave, {"codigo": clave, "titulo": "", "si": 0, "no": 0, "na": 0})
        sec["si" if estado == "si" else "na" if estado == "na" else "no"] += 1
        if estado in ("menor", "mayor", "no_cumple"):
            comentarios = m[4]
            auditado = re.search(r"Comentarios del auditado:\s*(.+?)(?:\nAC Aceptada\?|\nComentarios de OC|\Z)", comentarios, re.S)
            revisor = re.search(r"Comentarios de OC/Auditor:\s*(.+?)(?:\n(Sí|Si|No)\s*$|\Z)", comentarios, re.S | re.M)
            comentario = re.split(r"\nComentarios del auditado:", comentarios)[0]
            comentario = re.sub(r"^(Totalmente|Menor|Mayor|Aplicable)\s*\n", "", comentario)
            r.hallazgos.append(Hallazgo(
                codigo=codigo, texto=_limpiar(m[2]), comentario=_limpiar(comentario)[:800],
                nivel={"menor": "deficiencia menor", "mayor": "deficiencia mayor", "no_cumple": "no cumple"}[estado],
                respuesta_auditado=_limpiar(auditado[1])[:600] if auditado else None,
                respuesta_auditor=(("Aceptado" if revisor[2] in ("Sí", "Si") else "Rechazado") if revisor and revisor[2]
                                   else None)))
    r.secciones = list(conteo.values())
    r.preguntas = {"si": sum(s["si"] for s in r.secciones), "no": sum(s["no"] for s in r.secciones),
                   "na": sum(s["na"] for s in r.secciones)}
    r.preguntas["total"] = sum(r.preguntas.values())


def leer_auditoria_externa(contenido: bytes, nombre: str) -> LecturaAuditoriaExterna:
    r = LecturaAuditoriaExterna()
    if not nombre.lower().endswith(".pdf"):
        r.advertencias.append("Solo se leen informes en PDF: completa los datos a mano.")
        return r
    try:
        texto = _texto_pdf(contenido)
    except Exception:
        r.advertencias.append("No se pudo leer el PDF: completa los datos a mano.")
        return r
    r.texto_leido = bool(texto.strip())
    if not r.texto_leido:
        r.advertencias.append("El PDF no tiene texto (escaneado): completa los datos a mano.")
        return r
    encabezado = _limpiar(texto[:1500]).lower()
    r.protocolo = next((codigo for codigo, señales in NORMAS if any(s in encabezado for s in señales)), None)
    r.organizacion = m[1].strip() if (m := re.search(r"Organización:\s*(.+?)\s+Contacto", _limpiar(texto))) else None
    org = (r.organizacion or "").lower()
    r.empresa = "VS" if "viento sur" in org else "LH" if "hornilla" in org else None
    if r.protocolo == "PRIMUSGFS":
        _primus(texto, r)
    else:
        _globalgap(texto, r)
    if not r.protocolo:
        r.advertencias.append("No se reconoció la norma: elígela.")
    if not r.sitios:
        r.advertencias.append("No se reconocieron los sitios auditados: elige las sucursales.")
    if not r.fecha_inicio:
        r.advertencias.append("No se reconoció la fecha de la auditoría.")
    return r
