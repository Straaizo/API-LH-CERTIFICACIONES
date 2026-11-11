"""Resumen de un informe de auditoría externa en PDF y Word (para consulta de certificaciones)."""
import io
from datetime import date

from docx import Document
from docx.shared import Pt, RGBColor

from utils.hora import ahora
from utils.informe_ambiente import GRIS, ROJO, VERDE, _Informe, _latin, _num


def _fecha(valor) -> str:
    if not valor:
        return "-"
    if isinstance(valor, str):
        valor = date.fromisoformat(valor[:10])
    return valor.strftime("%d-%m-%Y")


def _ficha(d: dict) -> list[tuple[str, str]]:
    r = d.get("resumen", {})
    return [
        ("Norma", d["protocolo"]["nombre"] if d["protocolo"] else "-"),
        ("Informe", d["tipo_nombre"]),
        ("Sucursales", ", ".join(s["nombre"] for s in d["sucursales"]) or "-"),
        ("Fecha", _fecha(d["fecha"])),
        ("Auditor", d["auditor"] or "-"),
        ("Certificadora", d["entidad"] or "-"),
        ("ID auditoría", d["numero"] or "-"),
        ("Productos", r.get("productos") or "-"),
    ]


def _puntajes(d: dict) -> list[str]:
    salida = []
    for p in d["puntajes"]:
        texto = f"{p['nivel']}: {_num(p['valor'], 2)} %"
        if p.get("despues_ac") is not None:
            texto += f" (después de acciones correctivas: {_num(p['despues_ac'], 2)} %)"
        salida.append(texto)
    return salida


def resumen_pdf(d: dict) -> bytes:
    r = d.get("resumen", {})
    pdf = _Informe("Resumen de auditoría externa", d["titulo"],
                   f"Generado el {ahora():%d-%m-%Y %H:%M} · Portal Certificaciones · Documento de consulta")
    pdf.add_page()
    ficha = _ficha(d)
    pdf.ficha(ficha[:4])
    pdf.ficha(ficha[4:7])

    tarjetas = [(f"Puntaje {p['nivel'].lower()}", f"{_num(p['valor'], 1)} %",
                 f"Después de AC: {_num(p['despues_ac'], 1)} %" if p.get("despues_ac") is not None else "", None)
                for p in d["puntajes"][:3]]
    preg = r.get("preguntas") or {}
    if preg.get("total"):
        tarjetas.append(("Preguntas", str(preg["total"]), f"Sí {preg['si']} · No {preg['no']} · N/A {preg['na']}",
                         ROJO if preg.get("no") else VERDE))
    if r.get("certificado_hasta"):
        tarjetas.append(("Certificado vigente hasta", _fecha(r["certificado_hasta"]), f"desde {_fecha(r.get('certificado_desde'))}", None))
    if tarjetas:
        pdf.tarjetas(tarjetas[:4])

    hallazgos = r.get("hallazgos", [])
    pdf.seccion(f"Hallazgos ({len(hallazgos)})",
                "Requisitos con respuesta No o con deficiencia, con el comentario del auditor." if hallazgos
                else "El informe no registra hallazgos.")
    for h in hallazgos:
        if pdf.get_y() > pdf.h - 50:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 9)
        nivel = f" · {h['nivel']}" if h.get("nivel") else ""
        pdf.multi_cell(pdf.ancho, 4.6, _latin(f"{h['codigo']}{nivel}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.multi_cell(pdf.ancho, 4.3, _latin(h["texto"]), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.set_text_color(*ROJO)
        pdf.multi_cell(pdf.ancho, 4.3, _latin(f"Auditor: {h['comentario']}"), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.set_text_color(*GRIS)
        if h.get("respuesta_auditado"):
            pdf.multi_cell(pdf.ancho, 4.3, _latin(f"Respuesta: {h['respuesta_auditado']}"), new_x="LMARGIN", new_y="NEXT", align="L")
        if h.get("respuesta_auditor"):
            pdf.multi_cell(pdf.ancho, 4.3, _latin(f"Acción correctiva: {h['respuesta_auditor']}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(23, 32, 22)
        pdf.ln(2.5)

    secciones = [s for s in r.get("secciones", []) if s.get("no")]
    if secciones:
        pdf.seccion("Secciones con hallazgos")
        pdf.tabla(["Sección", "Sí", "No", "N/A"],
                  [[f"{s['codigo']} {s.get('titulo') or ''}".strip(), str(s["si"]), str(s["no"]), str(s["na"])] for s in secciones],
                  [pdf.ancho - 60, 20, 20, 20])
    return bytes(pdf.output())


def resumen_docx(d: dict) -> bytes:
    r = d.get("resumen", {})
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = "Calibri"
    estilo.font.size = Pt(10)
    doc.add_heading("Resumen de auditoría externa", level=1)
    doc.add_paragraph(d["titulo"])
    tabla = doc.add_table(rows=0, cols=2)
    tabla.style = "Light Grid Accent 1"
    for etiqueta, valor in _ficha(d):
        fila = tabla.add_row().cells
        fila[0].text, fila[1].text = etiqueta, valor
    if d["puntajes"]:
        doc.add_heading("Puntaje", level=2)
        for linea in _puntajes(d):
            doc.add_paragraph(linea, style="List Bullet")
    preg = r.get("preguntas") or {}
    if preg.get("total"):
        doc.add_paragraph(f"Preguntas: {preg['total']} (Sí {preg['si']} · No {preg['no']} · N/A {preg['na']})")
    if r.get("certificado_hasta"):
        doc.add_paragraph(f"Certificado vigente del {_fecha(r.get('certificado_desde'))} al {_fecha(r['certificado_hasta'])}")
    hallazgos = r.get("hallazgos", [])
    doc.add_heading(f"Hallazgos ({len(hallazgos)})", level=2)
    if not hallazgos:
        doc.add_paragraph("El informe no registra hallazgos.")
    for h in hallazgos:
        p = doc.add_paragraph()
        p.add_run(f"{h['codigo']}" + (f" · {h['nivel']}" if h.get("nivel") else "")).bold = True
        doc.add_paragraph(h["texto"])
        auditor = doc.add_paragraph()
        corrida = auditor.add_run(f"Auditor: {h['comentario']}")
        corrida.font.color.rgb = RGBColor(0xBE, 0x1E, 0x1E)
        if h.get("respuesta_auditado"):
            doc.add_paragraph(f"Respuesta: {h['respuesta_auditado']}")
        if h.get("respuesta_auditor"):
            doc.add_paragraph(f"Acción correctiva: {h['respuesta_auditor']}")
    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()
