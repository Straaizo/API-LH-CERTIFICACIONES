"""Residuos de plaguicidas (MRL) contra los límites de ASOEX por país de destino.

- leer_informe_mrl: lee un informe de residuos (PDF con texto, Excel, CSV) buscando las sustancias de ASOEX de la
  fruta, con su valor en ppm (= mg/kg). También detecta la fruta, la fecha, el laboratorio y la sucursal
  ("SOC AGRICOLA LA HORNILLA SPA (5)": el número es el código de la sucursal en esos informes).
- comparar: por país, cada residuo detectado no puede superar el límite; conclusión apto / no apto / revisar.
"""
import difflib
import re
from dataclasses import dataclass, field

from utils.importar_asoex import normalizar
from utils.leer_informe_lab import _fecha, _lineas, LABORATORIOS
from utils.texto import normalizar as normalizar_texto

# Código de sucursal con que los informes MRL (GESEX y otros) indican el huerto: "(5)" = Santa Victoria.
# Pendiente: lista completa (la entrega certificaciones).
CODIGOS_SUCURSAL = {5: 103}

# Palabras con que un informe nombra la fruta → hoja de ASOEX
FRUTAS = {
    "CEREZAS": ["cereza", "cerezas", "cherry", "cherries"],
    "CIRUELAS": ["ciruela", "ciruelas", "plum", "plums"],
    "NECTARINES": ["nectarin", "nectarines", "nectarina"],
    "DURAZNOS": ["durazno", "duraznos", "peach", "peaches"],
    "DAMASCOS": ["damasco", "damascos", "apricot", "apricots"],
    "KIWIS": ["kiwi", "kiwis"],
    "UVA DE MESA": ["uva de mesa", "uva", "table grapes", "grapes"],
}
NO_DETECTADO = re.compile(r"\b(n\.?\s?d\.?|no detectad[oa]|<\s*l\.?[dq]\.?|bajo (el )?l[ií]mite de detecci[oó]n)\b",
                          re.IGNORECASE)
NUMERO = re.compile(r"(<\s*)?(\d+(?:[.,]\d+)?)")


def fruta_de_especie(especie: str | None, frutas: list[str]) -> str | None:
    """'Cerezo' → 'CEREZAS' (mismas primeras 5 letras)."""
    if not especie:
        return None
    clave = normalizar(especie)[:5]
    return next((f for f in frutas if normalizar(f)[:5] == clave and "/" not in f), None)


@dataclass
class LecturaMRL:
    texto_leido: bool = False
    fruta: str | None = None
    variedad: str | None = None
    fecha_muestreo: str | None = None
    laboratorio: str | None = None
    productor: str | None = None
    codigo_sucursal: int | None = None
    unidad_id: int | None = None
    punto: str | None = None  # cuartel
    residuos: list[dict] = field(default_factory=list)  # {sustancia (como la escribe el informe), valor, valor_texto}
    advertencias: list[str] = field(default_factory=list)


def _valor(texto: str) -> float:
    return float(texto.replace(",", "."))


# Mérieux NutriSciences: " 0,340 0,010 LC_MSMSAcetamiprid  0,170 ±"  (resultado, LOQ, técnica+nombre, incertidumbre)
RE_MERIEUX = re.compile(r"^\s*(\d+[.,]\d+)\s+\d+[.,]\d+\s+(?:LC|GC)_MSMS\s*(.+?)\s+\d+[.,]\d+\s*±")
# Eurofins: "Acetamiprid mg/kg0,047LC(a)"; el nombre puede venir partido en varias líneas
RE_EUROFINS = re.compile(r"^(.*?)\s*mg/kg\s*(\d+[.,]\d+)")


def _detectados_merieux(lineas: list[str]) -> list[dict]:
    return [{"sustancia": m[2].strip(), "valor": _valor(m[1]), "valor_texto": None}
            for m in (RE_MERIEUX.match(l) for l in lineas) if m]


def _detectados_eurofins(lineas: list[str]) -> list[dict]:
    salida, dentro, nombre = [], False, ""
    for linea in lineas:
        if linea.replace(" ", "").lower().startswith("resultadosensayo"):
            dentro = True
            continue
        if not dentro:
            continue
        if "eurofins" in linea.lower() or linea.lower().startswith("opiniones"):
            break
        m = RE_EUROFINS.match(linea)
        if m:
            salida.append({"sustancia": f"{nombre} {m[1]}".strip(), "valor": _valor(m[2]), "valor_texto": None})
            nombre = ""
        else:
            nombre = f"{nombre} {linea}".strip()
    return salida


# Eurofins, análisis de una sola sustancia: "Etefon mg/kg(a) 0,260 0,005 0,01" (resultado, LOD, LOQ)
RE_EUROFINS_SIMPLE = re.compile(r"^([A-Za-zÁÉÍÓÚáéíóúñ][^\d]{2,60}?)\s*mg/kg(?:\(a+\))?\s+(\d+[.,]\d+)\s+\d+[.,]\d+\s+\d+[.,]\d+\s*$")


def _detectados_eurofins_simple(lineas: list[str]) -> list[dict]:
    return [{"sustancia": m[1].strip(), "valor": _valor(m[2]), "valor_texto": None}
            for m in (RE_EUROFINS_SIMPLE.match(l) for l in lineas) if m]


def _detectados_por_asoex(lineas: list[str], candidatas: list[str]) -> list[dict]:
    """Formato desconocido: busca en cada línea una sustancia de ASOEX y el número que la sigue."""
    por_clave = {normalizar(s): s for s in candidatas if len(normalizar(s)) >= 4}
    salida, vistos = [], set()
    for linea in lineas:
        clave_linea = normalizar(linea)
        hallada = max((s for k, s in por_clave.items() if k in clave_linea), key=lambda s: len(normalizar(s)), default=None)
        if not hallada or hallada in vistos:
            continue
        partes = [re.escape(t) for t in re.split(r"[^A-Za-z0-9]+", hallada) if t]
        en_linea = re.search(r"[^A-Za-z0-9]*".join(partes), linea, re.IGNORECASE)
        resto = linea[en_linea.end():] if en_linea else linea
        m = NUMERO.search(resto)
        nd = NO_DETECTADO.search(resto)
        if nd and (not m or nd.start() < m.start()):
            salida.append({"sustancia": hallada, "valor": None, "valor_texto": "No detectado"})
        elif m and m[1]:
            salida.append({"sustancia": hallada, "valor": None, "valor_texto": f"< {m[2]}"})
        elif m:
            salida.append({"sustancia": hallada, "valor": _valor(m[2]), "valor_texto": None})
        else:
            continue
        vistos.add(hallada)
    return salida


def leer_informe_mrl(contenido: bytes, nombre: str, sustancias_por_fruta: dict[str, list[str]]) -> LecturaMRL:
    """Informes de Mérieux NutriSciences y Eurofins (los que envía GESEX); otros formatos, por nombres de ASOEX.
    Solo se leen los residuos detectados: los "< LOQ" se omiten."""
    r = LecturaMRL()
    # Algunos PDF separan la "T" mayúscula del resto de la palabra ("T ebuconazol")
    lineas = [re.sub(r"\bT (?=[a-záéíóú])", "T", l) for l in _lineas(contenido, nombre)]
    texto = "\n".join(lineas)
    r.texto_leido = bool(texto.strip())
    if not r.texto_leido:
        r.advertencias.append("El archivo no tiene texto (foto o PDF escaneado): ingresa los residuos a mano.")
        return r
    corrido = re.sub(r"\s+", " ", texto)
    plano = normalizar_texto(texto)

    if "merieux" in plano or "mérieux" in texto.lower():
        r.laboratorio = "Mérieux NutriSciences"
    elif "eurofins" in plano:
        r.laboratorio = "Eurofins"
    else:
        r.laboratorio = next((lab.title() for lab in LABORATORIOS if lab in plano), None)

    if m := re.search(r"FECHA:?\s*(\d{1,2})-(\d{1,2})-(\d{4})", corrido, re.IGNORECASE):
        r.fecha_muestreo = f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    else:
        r.fecha_muestreo = _fecha(plano)
    if m := re.search(r"(SOC\.?\s*AGR[IÍ]COLA.{0,60}?)\(\s*(\d+)\s*\)", corrido, re.IGNORECASE):
        r.productor, r.codigo_sucursal = m[1].strip(), int(m[2])
        r.unidad_id = CODIGOS_SUCURSAL.get(r.codigo_sucursal)
        if r.unidad_id is None:
            r.advertencias.append(f"El código de sucursal ({r.codigo_sucursal}) no está registrado: elige la sucursal.")
    if m := re.search(r"CUARTEL:?\s*(\w+)", corrido, re.IGNORECASE):
        r.punto = f"Cuartel {m[1]}"
    if m := re.search(r"Variedad\s+([A-Z][A-Z0-9 ]+?)\s+(?:\d|C[oó]digo|Productor)", corrido):
        r.variedad = m[1].strip().title()

    especie = re.search(r"(?:Especie|Tipo de Muestra)\s+([A-Za-zÁÉÍÓÚáéíóú ]{3,30}?)\s+(?:Variedad|Descripci|\d|Nombre|Comuna)", corrido)
    donde = normalizar_texto(especie[1]) if especie else plano
    r.fruta = next((f for f, palabras in FRUTAS.items()
                    if f in sustancias_por_fruta and any(re.search(rf"\b{p}\b", donde) for p in palabras)), None)

    r.residuos = _detectados_merieux(lineas) or _detectados_eurofins(lineas) or _detectados_eurofins_simple(lineas)
    if not r.residuos:
        candidatas = sustancias_por_fruta.get(r.fruta) or sorted({s for v in sustancias_por_fruta.values() for s in v})
        r.residuos = _detectados_por_asoex(lineas, candidatas)
    if not r.residuos:
        r.advertencias.append("No se encontraron residuos detectados: revisa el informe e ingrésalos a mano.")
    if not r.fruta:
        r.advertencias.append("No se reconoció la fruta: elígela antes de comparar.")
    return r


# ---------- Comparación ----------

ORDEN = {"no_apto": 0, "revisar": 1, "apto": 2}


def clave_sustancia(nombre: str) -> str:
    """Clave para emparejar el nombre en español del informe con el inglés de ASOEX:
    Ciprodinilo ↔ CYPRODINIL, Pirimetanil ↔ PYRIMETHANIL, Azoxistrobina ↔ AZOXYSTROBIN, Clorantraniliprole ↔
    CHLORANTRANILIPROLE. Se quita lo que va entre paréntesis ("Captan (Captan+THPI)")."""
    texto = re.sub(r"\(.*?\)", " ", nombre or "")
    clave = normalizar(texto)
    for de, a in (("PH", "F"), ("TH", "T"), ("CH", "C"), ("Y", "I"), ("K", "C"), ("Z", "S"), ("QU", "C")):
        clave = clave.replace(de, a)
    clave = re.sub(r"^ES(?=[^AEIOU])", "S", clave)  # Espirotetramat ↔ SPIROTETRAMAT
    clave = re.sub(r"C(?=[EI])", "S", clave)
    clave = re.sub(r"(.)\1+", r"\1", clave)
    return re.sub(r"[AEO]+$", "", clave)


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def comparar(fruta: str, paises: list[str], residuos: list[dict], limites: list) -> dict:
    """limites: AsoexLimite de la fruta (todos los países). residuos: {sustancia, valor (ppm), valor_texto}."""
    # Los informes nombran las sustancias en español y ASOEX en inglés: se comparan por cómo suenan
    por_sustancia: dict[str, dict[str, object]] = {}
    for lim in limites:
        por_sustancia.setdefault(clave_sustancia(lim.sustancia), {})[lim.pais] = lim
    nombres = {clave_sustancia(lim.sustancia): lim.sustancia for lim in limites}

    filas, motivos = [], {p: {"no_apto": [], "revisar": []} for p in paises}
    for res in residuos:
        sustancia = (res.get("sustancia") or "").strip()
        if not sustancia:
            continue
        clave = clave_sustancia(sustancia)
        aproximada = False
        if clave not in por_sustancia:
            parecida = difflib.get_close_matches(clave, list(por_sustancia), n=1, cutoff=0.86)
            if parecida:
                clave, aproximada = parecida[0], True
        valor = res.get("valor")
        detectado = valor is not None and valor > 0
        celdas = {}
        for pais in paises:
            lim = por_sustancia.get(clave, {}).get(pais)
            celda = {"ppm": lim.ppm if lim else None, "condicion": lim.condicion if lim else None,
                     "carencia_dias": lim.carencia_dias if lim else None}
            nombre = nombres.get(clave, sustancia)
            if not detectado:
                celda["estado"] = "no_detectado"
            elif clave not in por_sustancia:
                celda["estado"] = "sin_lmr"
                motivos[pais]["revisar"].append(f"{sustancia} no figura en ASOEX para {fruta.lower()}")
            elif lim is None:
                celda["estado"] = "sin_lmr"
                motivos[pais]["revisar"].append(f"{nombre}: ASOEX no informa límite para {pais}")
            elif lim.condicion == "EX":
                celda["estado"] = "exento"
            elif lim.condicion == "ST":
                celda["estado"] = "sin_tolerancia"
                motivos[pais]["no_apto"].append(f"{nombre} ({_num(valor)} ppm) no tiene tolerancia en {pais}")
            elif lim.ppm is not None and valor > lim.ppm:
                celda["estado"] = "excede"
                motivos[pais]["no_apto"].append(
                    f"{nombre}: {_num(valor)} ppm supera el límite de {_num(lim.ppm)} ppm")
            else:
                celda["estado"] = "cumple"
            celdas[pais] = celda
        filas.append({"sustancia": sustancia, "sustancia_asoex": nombres.get(clave) if clave in por_sustancia else None,
                      "aproximada": aproximada, "valor": valor, "valor_texto": res.get("valor_texto"),
                      "detectado": detectado, "por_pais": celdas})

    conclusiones = []
    for pais in paises:
        m = motivos[pais]
        if m["no_apto"]:
            estado, texto = "no_apto", "No se puede enviar: supera la normativa de ASOEX."
        elif m["revisar"]:
            estado, texto = "revisar", "Sin residuos sobre el límite, pero hay sustancias sin límite en ASOEX: confirmar con el exportador."
        else:
            estado, texto = "apto", "Se puede enviar: todos los residuos detectados están dentro del límite."
        conclusiones.append({"pais": pais, "estado": estado, "texto": texto, "motivos": m["no_apto"] + m["revisar"]})
    conclusiones.sort(key=lambda c: (ORDEN[c["estado"]], c["pais"]))
    return {
        "fruta": fruta, "paises": paises, "filas": filas, "conclusiones": conclusiones,
        "resumen": {e: [c["pais"] for c in conclusiones if c["estado"] == e] for e in ORDEN},
        "detectados": sum(1 for f in filas if f["detectado"]),
    }
