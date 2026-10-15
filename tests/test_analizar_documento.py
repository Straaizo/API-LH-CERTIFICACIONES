"""Analizador de documentos fijos con textos de ejemplo (ficticios)."""
from utils.analizar_documento import analizar_texto, formato_codigo


def test_procedimiento_con_codigo_y_titulo():
    texto = "Agrícola La Hornilla\nP OC CE 29 Procedimiento de control de plagas v3\nObjetivo: ..."
    a = analizar_texto(texto, "documento.pdf", [])
    assert (a.codigo, a.categoria, a.empresa) == ("P OC CE 29", "Procedimientos", "LH")
    assert a.titulo == "Procedimiento de control de plagas"
    assert a.certificado is None


def test_codigo_desde_el_nombre_del_archivo_y_categoria():
    a = analizar_texto("Instructivo de limpieza de líneas\nAgrícola Viento Sur", "DPL23_instructivo.docx", [])
    assert (a.codigo, a.categoria, a.empresa) == ("DPL 23", "Instructivos", "VS")


def test_procedimiento_que_nombra_una_norma_no_es_certificado():
    texto = "Procedimiento de trazabilidad según GLOBALG.A.P. IFA v6\nP OC VS 05"
    a = analizar_texto(texto, "x.pdf", [])
    assert a.certificado is None and a.codigo == "P OC VS 05"


def test_certificado_reconocido():
    texto = ("Issued to\nAgrícola Viento Sur SPA\nThe certification body Organismo Ejemplo declares that\n"
             "Integrated Farm Assurance (IFA) 6.0-GFS_AUG24\nValid from: 01.02.2026\n"
             "Valid to: 31.01.2027 Certificate No. 999001\n1 Campo Itahue Ruta 5 Sur")
    a = analizar_texto(texto, "cert.pdf", ["Itahue"])
    assert a.certificado and a.certificado.numero == "999001" and a.empresa == "VS"


def test_formato_codigo():
    assert formato_codigo("POCCE29") == "P OC CE 29"
    assert formato_codigo("dpl 7") == "DPL 7"
