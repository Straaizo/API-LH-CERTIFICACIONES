"""Lector de certificados con textos de ejemplo (datos ficticios, con el formato de cada organismo)."""
from utils.leer_certificado import interpretar

UBICACIONES = ["Chocalán", "Santa Victoria", "Itahue", "San Manuel"]

GLOBALGAP = """CERTIFICATE
Issued to
Sociedad Agricola La Hornilla SPA
Fundo San Manuel S/N
The certification body Organismo Ejemplo declares that the production of the
products mentioned in this certificate meets the requirements set out in the standard:
Integrated Farm Assurance (IFA) GFS Plants; Principles and Criteria for Fruit &
Vegetables; 6.0-GFS_AUG24
Valid from: 01.02.2026 Date of certificate decision: 30.01.2026
Valid to: 31.01.2027 Certificate No. 999001
1 Campo Chocalan Ruta G60 Cherry
2 Fundo Sta Victoria General Baquedano Plum
"""

LEAF = """LEAF MARQUE
CERTIFICATE NO.
ORGANISMO EJEMPLO declares that the producer has been found to be compliant
LEAF MARQUE version 16.1
Agrícola Viento Sur SPA
Valid from: 08 January 2026
January 07, 2027Valid to:
Date of Certification Decision: 03 December 2025
PAO 99999-1
1 Fundo Itahue Ruta 5 Sur Nectarine-Plum
"""

PRIMUS = """NÚMERO DE AUDITORÍA
PRIMUSGFS:
123456
FECHA DE AUDITORÍA:
Feb 26, 2026
Sociedad Agricola La Hornilla SPA
OPERACIÓN
Packing Santa Victoria
CERTIFICADO VÁLIDO DESDE:
Abr 16, 2026 A Abr 15, 2027
PUNTUACIÓN FINAL DE LA AUDITORÍA:
97%
Organismo Ejemplo certifica que esta operación ha cumplido con los requisitos aplicables de PrimusGFS Versión 3.2
Uvas de mesa
"""


def test_globalgap_sitios_del_anexo_y_no_del_encabezado():
    r = interpretar(GLOBALGAP, UBICACIONES)
    assert (r.protocolo, r.norma_version, r.numero, r.empresa) == ("GLOBALGAP", "6.0-GFS_AUG24", "999001", "LH")
    assert (r.vigente_desde, r.vigente_hasta, r.fecha_decision) == ("2026-02-01", "2027-01-31", "2026-01-30")
    assert r.entidad == "Organismo Ejemplo"
    # San Manuel solo aparece como dirección de la empresa: no es un sitio cubierto
    assert r.sitios == ["Chocalán", "Santa Victoria"]
    assert r.productos == ["Cereza", "Ciruela"]


def test_leaf_fechas_en_ingles_y_numero_pao():
    r = interpretar(LEAF, UBICACIONES)
    assert (r.protocolo, r.norma_version, r.numero, r.empresa) == ("LEAF", "16.1", "PAO 99999-1", "VS")
    assert (r.vigente_desde, r.vigente_hasta, r.fecha_decision) == ("2026-01-08", "2027-01-07", "2025-12-03")
    assert r.sitios == ["Itahue"]


def test_primus_operacion_puntaje_y_meses_en_espanol():
    r = interpretar(PRIMUS, UBICACIONES)
    assert (r.protocolo, r.norma_version, r.numero) == ("PRIMUSGFS", "3.2", "123456")
    assert (r.vigente_desde, r.vigente_hasta, r.fecha_auditoria) == ("2026-04-16", "2027-04-15", "2026-02-26")
    assert (r.puntaje, r.operacion, r.sitios) == ("97%", "Packing Santa Victoria", ["Santa Victoria"])
    assert r.productos == ["Uva de mesa"]


def test_pdf_sin_texto():
    r = interpretar("   ", UBICACIONES)
    assert not r.texto_leido and r.protocolo is None
