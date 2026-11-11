"""Tabla ASOEX (límites por país) y comparación de residuos MRL. Datos inventados."""
import io

from openpyxl import Workbook

from utils.importar_asoex import fecha_en_nombre, leer_asoex
from utils.mrl import comparar, fruta_de_especie, leer_informe_mrl


def _planilla() -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "CHERRIES"
    for fila in [
        ["AGENDA DE PESTICIDAS ASOEX"], [], [],
        ["CEREZAS", None, "USA", None, "UE", None, "CHINA", None],
        ["SUSTANCIA ACTIVA", "TIPO PRODUCTO", "ppm", "dias", "ppm", "dias", "ppm", "dias"],
        ["+ SULFUR", "ACARICIDA", "EX", None, "EX", None, "/", None],
        ["ACETAMIPRID", "INSECTICIDA", 1.5, 3, 0.8, None, 2, 2],
        ["CAPTAN", "FUNGICIDA", "ST", None, "3", None, None, None],
        ["ABAMECTIN/CYANTRANILIPROLE", "INSECTICIDA", "0,09/6", None, "0,01/0,01", None, "0,07/ST", None],
        [], ["Próximos cambios "], ["CEREZAS > UE > ACETAMIPRID > 0,5 desde 2027-03-01."],
    ]:
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _limites():
    return leer_asoex(_planilla())[0]


def test_lee_asoex():
    fruta = _limites()
    assert fruta.nombre == "CEREZAS" and fruta.paises == ["USA", "UE", "CHINA"]
    por = {(x.sustancia, x.pais): x for x in fruta.limites}
    assert por[("ACETAMIPRID", "UE")].ppm == 0.8 and por[("ACETAMIPRID", "USA")].carencia_dias == 3
    assert por[("CAPTAN", "USA")].condicion == "ST" and por[("CAPTAN", "UE")].ppm == 3
    assert ("CAPTAN", "CHINA") not in por and ("SULFUR", "CHINA") not in por  # vacío y "/" = sin información
    assert por[("SULFUR", "UE")].condicion == "EX"
    # Las mezclas se separan por componente
    assert por[("CYANTRANILIPROLE", "USA")].ppm == 6 and por[("ABAMECTIN", "CHINA")].ppm == 0.07
    assert por[("CYANTRANILIPROLE", "CHINA")].condicion == "ST"
    assert fruta.proximos_cambios == ["CEREZAS > UE > ACETAMIPRID > 0,5 desde 2027-03-01."]
    assert str(fecha_en_nombre("LMR ASOEX 28-09-2026.xlsx")) == "2026-09-28"


def test_lee_agenda_por_especie():
    """Agenda de pesticidas por especie: hoja de notas legales + hoja "Resultado" con la fecha de descarga."""
    libro = Workbook()
    libro.active.title = "AGENDA DE PESTICIDAS"
    libro.active.append(["Notas legales"])
    hoja = libro.create_sheet("Resultado")
    for fila in [
        ["AGENDA DE PESTICIDAS FRUTAS DE CHILE"], ["LÍMITES MÁXIMOS DE RESIDUOS DE PLAGUICIDAS Y CARENCIAS"],
        ["Fecha Descarga:", "20-10-2026"],
        ["DAMASCOS", None, "USA", None],
        ["SUSTANCIA ACTIVA", "TIPO PRODUCTO", "ppm", "dias"],
        ["BOSCALID", "FUN", 4, 7],
    ]:
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    [fruta] = leer_asoex(salida.getvalue())
    assert fruta.nombre == "DAMASCOS" and str(fruta.fecha) == "2026-10-20"
    assert fruta.limites[0].ppm == 4 and fruta.limites[0].carencia_dias == 7
    assert str(fecha_en_nombre("AgendaPesticidasFdch_DAMASCOS_20102026_154258.xlsx")) == "2026-10-20"


def test_compara_por_pais():
    residuos = [{"sustancia": "Acetamiprid", "valor": 1.1}, {"sustancia": "Captan", "valor": 0.4},
                {"sustancia": "Abamectin", "valor": None, "valor_texto": "N.D."},
                {"sustancia": "Sustancia desconocida", "valor": 0.02}]
    r = comparar("CEREZAS", ["USA", "UE", "CHINA"], residuos, _limites().limites)
    estados = {c["pais"]: c for c in r["conclusiones"]}
    # USA: captan sin tolerancia; UE: acetamiprid 1,1 > 0,8; China: captan sin límite informado → revisar
    assert estados["USA"]["estado"] == "no_apto" and "no tiene tolerancia" in estados["USA"]["motivos"][0]
    assert estados["UE"]["estado"] == "no_apto" and "supera el límite de 0,8 ppm" in estados["UE"]["motivos"][0]
    assert estados["CHINA"]["estado"] == "revisar"
    fila = next(f for f in r["filas"] if f["sustancia"] == "Abamectin")
    assert fila["por_pais"]["UE"]["estado"] == "no_detectado"


def test_todo_bajo_el_limite_es_apto():
    r = comparar("CEREZAS", ["USA"], [{"sustancia": "ACETAMIPRID", "valor": 1.5}], _limites().limites)
    assert r["conclusiones"][0]["estado"] == "apto"  # igual al límite: cumple


def test_lee_informe_mrl():
    texto = ("Productor: SOC AGRICOLA LA HORNILLA SPA (5)\nEspecie: Cerezas\nFecha de muestreo: 05-10-2026\n"
             "Analito;Resultado mg/kg\nAcetamiprid;0,92\nCaptan;N.D.\n")
    r = leer_informe_mrl(texto.encode(), "informe.txt", {"CEREZAS": ["ACETAMIPRID", "CAPTAN"]})
    assert r.fruta == "CEREZAS" and r.codigo_sucursal == 5 and r.unidad_id == 103
    assert r.fecha_muestreo == "2026-10-05"
    assert {x["sustancia"]: x["valor"] for x in r.residuos} == {"ACETAMIPRID": 0.92, "CAPTAN": None}
    assert fruta_de_especie("Cerezo", ["CEREZAS", "CIRUELAS"]) == "CEREZAS"


def test_formatos_de_laboratorio_y_nombres_en_espanol():
    from utils.mrl import _detectados_eurofins, _detectados_eurofins_simple, _detectados_merieux, clave_sustancia
    merieux = _detectados_merieux([" 0,340 0,010 LC_MSMSAcetamiprid  0,170 ±", "0,010< LOQ LC_MSMSBoscalid 0,010< LOQ"])
    assert merieux == [{"sustancia": "Acetamiprid", "valor": 0.34, "valor_texto": None}]
    eurofins = _detectados_eurofins(["ResultadosEnsayo Técnica", "Pirimetanil mg/kg1,307GC - LC(a)",
                                     "Miclobutanilo(suma de los ", "isómeros constituyentes)", "mg/kg0,015GC - LC(a)",
                                     "Eurofins Testing Chile S.A"])
    assert [(x["sustancia"], x["valor"]) for x in eurofins] == [
        ("Pirimetanil", 1.307), ("Miclobutanilo(suma de los isómeros constituyentes)", 0.015)]
    assert _detectados_eurofins_simple(["Etefon mg/kg(a) 0,260 0,005 0,01"])[0]["valor"] == 0.26
    for es, en in (("Ciprodinilo", "CYPRODINIL"), ("Pirimetanil", "PYRIMETHANIL"), ("Azoxistrobina", "AZOXYSTROBIN"),
                   ("Clorantraniliprole", "CHLORANTRANILIPROLE"), ("Espirotetramat (Suma)", "SPIROTETRAMAT"),
                   ("Etefon", "ETHEPHON"), ("Miclobutanilo(suma de los isómeros)", "MYCLOBUTANIL"),
                   ("Metoxifenocida", "METHOXYFENOZIDE"), ("Lambda Cihalotrina", "LAMBDA-CYHALOTHRIN")):
        assert clave_sustancia(es) == clave_sustancia(en), (es, en)


def test_carta_destino_traduce_paises(monkeypatch):
    """Texto de la carta tal como lo entrega pypdf, con espacios cortando palabras y años."""
    import re

    from utils import leer_carta_destino as m
    texto = ("GESEX S.A.\n01 de diciembre  de 202 5\nPara : 0723 Agricola Viento Sur SPA\n"
             "siguientes especie s durante  la temporada 202 5-20 26 serán:\n"
             "• Ciruelas: Estados Unidos, U.E., Inglaterra, Canadá  y China .\n"
             "• Cerezas:  Estados Unidos, U.E.,  Inglaterra, Canadá, China, Taiwán , Japón,\nCorea .\n"
             "Se extiende esta carta aclaratoria")
    monkeypatch.setattr(m, "_texto", lambda _: re.sub(r"(?<=\d) (?=\d)", "", texto))
    carta = m.leer_carta_destino(b"")
    assert carta.temporada == "25-26" and str(carta.fecha) == "2025-12-01"
    assert carta.destinatario == "0723 Agricola Viento Sur SPA"
    assert carta.destinos["CIRUELAS"] == ["USA", "UE", "UK", "CANADA", "CHINA"]
    assert carta.destinos["CEREZAS"][-3:] == ["TAIWAN", "JAPON", "COREA"] and not carta.sin_traducir
    assert m.especie_asoex("UVADEMESA", ["CEREZAS", "UVA DE MESA"]) == "UVA DE MESA"
