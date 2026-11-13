import hashlib
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, selectinload

from utils import almacenamiento
from utils.proteccion import MAX_MB_ARCHIVO
from utils.auth import LABORATORIO, requiere_permiso, requiere_ver, verificar_unidad
from utils.historial import registrar
from utils.duplicados import error_duplicado, existente
from utils.comunes import (
    TemporadaLogica, filtrar_temporada, filtrar_unidades, obtener, temporada_al_guardar, temporada_seleccionada, unidad_dict,
)
from utils.db import get_db
from utils.mrl import comparar, fruta_de_especie, leer_informe_mrl
from utils.importar_asoex import fecha_en_nombre, leer_asoex, normalizar
from utils.leer_carta_destino import especie_asoex, leer_carta_destino
from utils.leer_informe_lab import leer_informe
from utils.modelos import (
    TIPO_CAMPO, TIPO_PACKING, Analisis, Asoex, AsoexLimite, CartaDestino, Empresa, Especie, FuenteAgua, LimiteParametro, ResultadoAnalisis, TipoAnalisis, Unidad,
    Usuario,
)

router = APIRouter(prefix="/laboratorio")


class ResultadoEntrada(BaseModel):
    parametro: str = Field(min_length=1, max_length=120)
    valor: float | None = None
    valor_texto: str | None = None
    unidad_medida: str | None = None
    # Si no vienen, se toman del límite vigente del parámetro
    limite_min: float | None = None
    limite_max: float | None = None


class AnalisisEntrada(BaseModel):
    tipo_analisis_id: str
    unidad_id: int
    fuente_agua_id: str | None = None
    especie_id: str | None = None
    punto: str | None = None
    fecha_muestreo: date
    laboratorio: str | None = None
    archivo_key: str | None = None
    nombre_archivo: str | None = None
    resultados: list[ResultadoEntrada] = Field(min_length=1)


class LecturaEntrada(BaseModel):
    archivo_key: str
    nombre_archivo: str
    tipo_analisis_id: str | None = None
    unidad_id: int | None = None


def evaluar(valor: float | None, minimo: float | None, maximo: float | None) -> bool | None:
    """None si no hay valor numérico o límite contra el cual comparar."""
    if valor is None or (minimo is None and maximo is None):
        return None
    return (minimo is None or valor >= minimo) and (maximo is None or valor <= maximo)


def _analisis_dict(a: Analisis) -> dict:
    fuera = [r for r in a.resultados if r.cumple is False]
    return {
        "id": a.id, "tipo": {"id": a.tipo.id, "nombre": a.tipo.nombre, "ambito": a.tipo.ambito},
        "unidad": unidad_dict(a.unidad), "fuente_agua": a.fuente_agua.nombre if a.fuente_agua else None,
        "especie": {"id": a.especie.id, "nombre": a.especie.nombre} if a.especie else None,
        "punto": a.punto, "fecha_muestreo": a.fecha_muestreo, "laboratorio": a.laboratorio,
        "temporada_id": a.temporada_id, "nombre_archivo": a.nombre_archivo, "tiene_informe": bool(a.archivo_key),
        "cumple": None if all(r.cumple is None for r in a.resultados) else not fuera,
        "fuera_de_norma": [r.parametro for r in fuera],
        "resultados": [
            {"id": r.id, "parametro": r.parametro, "valor": r.valor, "valor_texto": r.valor_texto,
             "unidad_medida": r.unidad_medida, "limite_min": r.limite_min, "limite_max": r.limite_max,
             "cumple": r.cumple}
            for r in a.resultados
        ],
    }


@router.get("/analisis")
def listar(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
           tipo_analisis_id: str | None = None, solo_fuera_de_norma: bool = False, tipo_unidad: str | None = None,
           usuario: Usuario = Depends(requiere_ver("LABORATORIO")), db: Session = Depends(get_db)) -> list[dict]:
    """tipo_unidad: 'campo' o 'planta' para ver solo los análisis de ese tipo de sucursal."""
    consulta = filtrar_unidades(
        select(Analisis).options(selectinload(Analisis.resultados), selectinload(Analisis.tipo)),
        Analisis.unidad_id, usuario, empresa_id, unidad_id)
    consulta = filtrar_temporada(db, consulta, temporada_id, Analisis.fecha_muestreo, Analisis.unidad_id,
                                 Analisis.temporada)
    if tipo_analisis_id:
        consulta = consulta.where(Analisis.tipo_analisis_id == tipo_analisis_id)
    if tipo_unidad in ("campo", "planta"):
        tipo_id = TIPO_CAMPO if tipo_unidad == "campo" else TIPO_PACKING
        consulta = consulta.where(Analisis.unidad_id.in_(select(Unidad.id).where(Unidad.tipo_id == tipo_id)))
    datos = [_analisis_dict(a) for a in db.scalars(consulta.order_by(Analisis.fecha_muestreo.desc()))]
    return [d for d in datos if d["fuera_de_norma"]] if solo_fuera_de_norma else datos


@router.post("/analisis", status_code=201)
def crear(datos: AnalisisEntrada, reemplazar: bool = False, usuario: Usuario = Depends(requiere_permiso(LABORATORIO)),
          db: Session = Depends(get_db), temporada: TemporadaLogica = Depends(temporada_seleccionada)) -> dict:
    """Si ya hay un análisis de esa sucursal con el mismo informe, avisa; con reemplazar=true lo reemplaza."""
    verificar_unidad(usuario, datos.unidad_id)
    nombre_temporada = temporada_al_guardar(db, temporada, datos.fecha_muestreo,
                                            obtener(db, Unidad, datos.unidad_id).empresa_id)
    misma_muestra = (Analisis.tipo_analisis_id == datos.tipo_analisis_id) & (Analisis.fecha_muestreo == datos.fecha_muestreo) \
        & (func.coalesce(Analisis.punto, "") == (datos.punto or "").strip()) \
        & (func.coalesce(Analisis.fuente_agua_id, 0) == (datos.fuente_agua_id or 0))
    criterio = (Analisis.nombre_archivo == datos.nombre_archivo) | misma_muestra if datos.nombre_archivo else misma_muestra
    anteriores = list(db.scalars(select(Analisis).where(Analisis.unidad_id == datos.unidad_id, criterio)))
    if anteriores and not reemplazar:
        raise error_duplicado(
            "Ya hay un análisis de esta sucursal con el mismo informe o la misma muestra (tipo, fecha y punto).",
            [existente(a.nombre_archivo or "", a.creado_en, getattr(db.get(Usuario, a.creado_por_id), "nombre", None),
                       f"{a.tipo.nombre}, muestreo {a.fecha_muestreo:%d-%m-%Y}") for a in anteriores],
            "Reemplazar el análisis anterior")
    for a in anteriores:
        registrar(db, usuario, "reemplazar", "analisis", a.id, {"archivo": a.nombre_archivo})
        db.delete(a)
    tipo = obtener(db, TipoAnalisis, datos.tipo_analisis_id)
    if datos.fuente_agua_id:
        fuente = obtener(db, FuenteAgua, datos.fuente_agua_id)
        if fuente.unidad_id != datos.unidad_id:
            raise HTTPException(400, "La fuente de agua no es de esa sucursal")
    elif tipo.usa_fuente_agua:
        raise HTTPException(400, "Este análisis requiere indicar la fuente de agua")
    if datos.especie_id:
        obtener(db, Especie, datos.especie_id)
    elif tipo.usa_especie:
        raise HTTPException(400, "Este análisis requiere indicar la especie")
    if datos.archivo_key and not almacenamiento.existe(datos.archivo_key):
        raise HTTPException(400, "El informe no se subió correctamente")

    limites = {lp.parametro.lower(): lp for lp in
               db.scalars(select(LimiteParametro).where(LimiteParametro.tipo_analisis_id == tipo.id))}
    analisis = Analisis(**datos.model_dump(exclude={"resultados"}), creado_por_id=usuario.id, temporada=nombre_temporada)
    for r in datos.resultados:
        ref = limites.get(r.parametro.lower())
        # El límite se copia al resultado: un cambio de norma no altera el histórico
        minimo = r.limite_min if r.limite_min is not None else (ref.minimo if ref else None)
        maximo = r.limite_max if r.limite_max is not None else (ref.maximo if ref else None)
        analisis.resultados.append(ResultadoAnalisis(
            parametro=r.parametro, valor=r.valor, valor_texto=r.valor_texto,
            unidad_medida=r.unidad_medida or (ref.unidad_medida if ref else None),
            limite_min=minimo, limite_max=maximo, cumple=evaluar(r.valor, minimo, maximo),
        ))
    db.add(analisis)
    db.flush()
    fuera = [r.parametro for r in analisis.resultados if r.cumple is False]
    registrar(db, usuario, "crear", "analisis", analisis.id, {"tipo": tipo.nombre, "fuera_de_norma": fuera})
    db.commit()
    db.refresh(analisis)
    # TODO alerta por correo cuando se defina el servicio de correo (ver docs/preguntas-cliente.md)
    return _analisis_dict(analisis)


@router.post("/leer-informe")
def leer_informe_subido(datos: LecturaEntrada, usuario: Usuario = Depends(requiere_permiso(LABORATORIO)),
                        db: Session = Depends(get_db)) -> dict:
    """Lee el informe ya subido (URL firmada) y propone los valores; no guarda nada."""
    if datos.unidad_id:
        verificar_unidad(usuario, datos.unidad_id)
    if not almacenamiento.existe(datos.archivo_key):
        raise HTTPException(400, "El informe no se subió correctamente")
    tipos = list(db.scalars(select(TipoAnalisis).where(TipoAnalisis.ambito == "campo")))
    tipo = db.get(TipoAnalisis, datos.tipo_analisis_id) if datos.tipo_analisis_id else None
    especies = list(db.scalars(select(Especie).order_by(Especie.nombre)))

    def parametros(t: TipoAnalisis) -> list[str]:
        return [lp.parametro for lp in db.scalars(select(LimiteParametro).where(LimiteParametro.tipo_analisis_id == t.id))]

    try:
        contenido = almacenamiento.leer(datos.archivo_key)
    except Exception as exc:
        raise HTTPException(400, "No se pudo leer el informe") from exc
    lectura = leer_informe(contenido, datos.nombre_archivo, parametros(tipo) if tipo else [],
                           [e.nombre for e in especies], [t.nombre for t in tipos])
    # Sin tipo elegido: se usa el sugerido por el contenido del informe
    if tipo is None and lectura.tipo_sugerido:
        tipo = next(t for t in tipos if t.nombre == lectura.tipo_sugerido)
        lectura = leer_informe(contenido, datos.nombre_archivo, parametros(tipo),
                               [e.nombre for e in especies], [t.nombre for t in tipos])
    elif tipo is None:
        # Sin pistas en el texto: el tipo cuyos parámetros aparecen más en el informe
        candidatas = [(t, leer_informe(contenido, datos.nombre_archivo, parametros(t),
                                       [e.nombre for e in especies], [x.nombre for x in tipos])) for t in tipos]
        t, mejor = max(candidatas, key=lambda par: len(par[1].resultados))
        if mejor.resultados:
            tipo, lectura = t, mejor
    especie = next((e for e in especies if e.nombre == lectura.especie), None)
    return {
        "texto_leido": lectura.texto_leido,
        "tipo_analisis_id": tipo.id if tipo else None,
        "tipo_sugerido": lectura.tipo_sugerido,
        "fecha_muestreo": lectura.fecha_muestreo,
        "laboratorio": lectura.laboratorio,
        "punto": lectura.punto,
        "especie_id": especie.id if especie else None,
        "resultados": lectura.resultados,
        "no_encontrados": lectura.no_encontrados,
        "advertencias": lectura.advertencias,
    }


@router.get("/analisis/{analisis_id}/informe")
def informe(analisis_id: str, usuario: Usuario = Depends(requiere_ver("LABORATORIO")), db: Session = Depends(get_db)) -> dict:
    analisis = obtener(db, Analisis, analisis_id)
    verificar_unidad(usuario, analisis.unidad_id)
    if not analisis.archivo_key:
        raise HTTPException(404, "El análisis no tiene informe")
    return {"url": almacenamiento.url_descarga(analisis.archivo_key, analisis.nombre_archivo)}


# ---------- Residuos (MRL) y destinos según ASOEX ----------

MAX_ARCHIVO = MAX_MB_ARCHIVO * 1024 * 1024


class ResiduoEntrada(BaseModel):
    sustancia: str = Field(min_length=1, max_length=120)
    valor: float | None = Field(default=None, ge=0)  # ppm (mg/kg)
    valor_texto: str | None = Field(default=None, max_length=40)  # "No detectado", "< 0,01"


class ComparacionEntrada(BaseModel):
    fruta: str = Field(min_length=1, max_length=60)
    paises: list[str] = Field(min_length=1, max_length=40)
    residuos: list[ResiduoEntrada] = Field(min_length=1, max_length=300)


def _vigentes(db: Session) -> dict[str, Asoex]:
    """Carga vigente de cada especie: la más reciente (por fecha de la planilla) que la trae.

    Así conviven la planilla general de ASOEX y las agendas por especie: si llega la agenda de cerezas más nueva,
    cerezas sale de ella y el resto sigue saliendo de la planilla general.
    """
    cargas = sorted(db.scalars(select(Asoex)), key=lambda a: (a.fecha or date.min, a.created_at), reverse=True)
    vigentes: dict[str, Asoex] = {}
    for carga in cargas:
        for fruta in carga.resumen:
            vigentes.setdefault(fruta, carga)
    return vigentes


def _estado_asoex(db: Session) -> dict:
    vigentes = _vigentes(db)
    frutas = [{"nombre": f, **c.resumen[f], "carga_id": c.id, "nombre_archivo": c.nombre_archivo, "fecha": c.fecha}
              for f, c in sorted(vigentes.items())]
    historial = [{"id": a.id, "nombre_archivo": a.nombre_archivo, "fecha": a.fecha, "cargado_en": a.cargado_en,
                  "frutas": sorted(a.resumen)} for a in db.scalars(select(Asoex).order_by(Asoex.created_at.desc()))]
    cartas = sorted(db.scalars(select(CartaDestino)), key=lambda c: (c.fecha or date.min, c.created_at), reverse=True)
    return {"frutas": frutas, "historial": historial, "cartas": [_carta_dict(c) for c in cartas]}


def _carta_dict(c: CartaDestino) -> dict:
    return {"id": c.id, "empresa_id": c.empresa_id, "empresa": c.empresa.nombre if c.empresa else None,
            "temporada": c.temporada, "destinatario": c.destinatario, "fecha": c.fecha, "destinos": c.destinos,
            "nombre_archivo": c.nombre_archivo}


def guardar_carta(db: Session, contenido: bytes, nombre: str, usuario: Usuario, reemplazar: bool = False) -> CartaDestino:
    """Lee la carta de destino de GESEX y la guarda. La empresa sale del destinatario ("0723 Agricola Viento Sur SPA")."""
    try:
        leida = leer_carta_destino(contenido)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    destino_norm = normalizar(leida.destinatario or "")
    empresa = next((e for e in db.scalars(select(Empresa))
                    if normalizar(e.nombre).replace("SPA", "") and normalizar(e.nombre).replace("SPA", "") in destino_norm), None)
    anteriores = [c for c in db.scalars(select(CartaDestino))
                  if c.nombre_archivo == nombre or (empresa and c.empresa_id == empresa.id and c.temporada == leida.temporada)]
    if anteriores and not reemplazar:
        quien = f"{empresa.nombre} para la temporada {leida.temporada}" if empresa else "con ese nombre"
        raise error_duplicado(f"Ya hay una carta de destino de {quien}.",
                              [existente(c.nombre_archivo, c.cargado_en, None, f"temporada {c.temporada}") for c in anteriores])
    for c in anteriores:
        registrar(db, usuario, "reemplazar", "carta_destino", c.id, {"archivo": c.nombre_archivo})
        db.delete(c)
    frutas = list(_vigentes(db))
    clave = almacenamiento.nueva_clave("destinos", nombre)
    almacenamiento.escribir(clave, contenido, "application/pdf")
    carta = CartaDestino(
        empresa_id=empresa.id if empresa else None, temporada=leida.temporada, destinatario=leida.destinatario,
        fecha=leida.fecha, nombre_archivo=nombre, archivo_key=clave, cargado_por_id=usuario.id,
        destinos={especie_asoex(e, frutas): paises for e, paises in leida.destinos.items()},
    )
    db.add(carta)
    db.flush()
    registrar(db, usuario, "cargar", "carta_destino", carta.id,
              {"archivo": nombre, "temporada": leida.temporada, "especies": sorted(carta.destinos)})
    return carta


@router.post("/destinos", status_code=201)
async def cargar_carta_destino(archivo: UploadFile = File(...), reemplazar: bool = Form(False),
                               usuario: Usuario = Depends(requiere_permiso(LABORATORIO)),
                               db: Session = Depends(get_db)) -> dict:
    """Carga la carta de mercados de destino (PDF de GESEX). Con ella se preseleccionan los países por especie."""
    nombre = archivo.filename or "carta_destino.pdf"
    if not nombre.lower().endswith(".pdf"):
        raise HTTPException(400, "Se espera la carta de destino en PDF")
    contenido = await archivo.read()
    if len(contenido) > MAX_ARCHIVO:
        raise HTTPException(413, "Archivo demasiado grande")
    carta = guardar_carta(db, contenido, nombre, usuario, reemplazar)
    db.commit()
    return {"carta": _carta_dict(carta), **_estado_asoex(db)}


@router.get("/asoex")
def asoex(_: Usuario = Depends(requiere_ver("LABORATORIO")), db: Session = Depends(get_db)) -> dict:
    """Límites ASOEX vigentes por especie (de qué planilla salen) y todas las cargas."""
    return _estado_asoex(db)


def guardar_asoex(db: Session, contenido: bytes, nombre: str, usuario: Usuario) -> Asoex:
    try:
        frutas = leer_asoex(contenido)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    clave = almacenamiento.nueva_clave("asoex", nombre)
    almacenamiento.escribir(clave, contenido,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    fecha = next((f.fecha for f in frutas if f.fecha), None) or fecha_en_nombre(nombre)
    carga = Asoex(
        nombre_archivo=nombre, archivo_key=clave, fecha=fecha, cargado_por_id=usuario.id,
        resumen={f.nombre: {"paises": f.paises, "sustancias": len({x.sustancia for x in f.limites}),
                            "proximos_cambios": f.proximos_cambios} for f in frutas},
    )
    db.add(carga)
    db.flush()
    db.execute(insert(AsoexLimite), [
        {"asoex_id": carga.id, "fruta": f.nombre, "sustancia": x.sustancia, "tipo_producto": x.tipo_producto,
         "pais": x.pais, "ppm": x.ppm, "condicion": x.condicion, "carencia_dias": x.carencia_dias}
        for f in frutas for x in f.limites
    ])
    registrar(db, usuario, "cargar", "asoex", carga.id,
              {"archivo": nombre, "frutas": len(frutas), "limites": sum(len(f.limites) for f in frutas)})
    return carga


@router.post("/asoex", status_code=201)
async def cargar_asoex(archivos: list[UploadFile] = File(...), reemplazar: bool = Form(False),
                       usuario: Usuario = Depends(requiere_permiso(LABORATORIO)), db: Session = Depends(get_db)) -> dict:
    """Carga una o varias planillas de ASOEX (la general o las agendas por especie). Ninguna carga se borra:
    para cada especie se usa la planilla más reciente que la trae."""
    # Se leen primero: una planilla repetida puede venir con otro nombre (el navegador agrega "(2)", "(3)"…)
    leidas = []
    for archivo in archivos:
        nombre = archivo.filename or "asoex.xlsx"
        if not nombre.lower().endswith((".xlsx", ".xlsm")):
            raise HTTPException(400, f"{nombre}: se espera la planilla de ASOEX en Excel (.xlsx)")
        contenido = await archivo.read()
        if len(contenido) > MAX_ARCHIVO:
            raise HTTPException(413, f"{nombre}: archivo demasiado grande")
        try:
            frutas = leer_asoex(contenido)
        except ValueError as exc:
            raise HTTPException(400, f"{nombre}: {exc}") from exc
        fecha = next((f.fecha for f in frutas if f.fecha), None) or fecha_en_nombre(nombre)
        leidas.append((nombre, contenido, frozenset(f.nombre for f in frutas), fecha))
    cargas = list(db.scalars(select(Asoex)))
    anteriores = {a.id: a for nombre, _, especies, fecha in leidas for a in cargas
                  if a.nombre_archivo == nombre or (frozenset(a.resumen) == especies and a.fecha == fecha)}
    if anteriores and not reemplazar:
        raise error_duplicado(
            "Estas planillas ya están cargadas." if len(anteriores) > 1
            else "Esta planilla ya está cargada (mismas especies y misma fecha de descarga).",
            [existente(a.nombre_archivo, a.cargado_en, None,
                       f"{', '.join(sorted(a.resumen)).title()} · descargada el {a.fecha:%d-%m-%Y}" if a.fecha
                       else ", ".join(sorted(a.resumen)).title()) for a in anteriores.values()])
    for a in anteriores.values():
        registrar(db, usuario, "reemplazar", "asoex", a.id, {"archivo": a.nombre_archivo})
        db.delete(a)
    db.flush()
    resultados, vistos = [], set()
    for nombre, contenido, especies, fecha in leidas:
        # Dentro de la misma carga: la misma planilla dos veces (igual contenido, o mismas especies y fecha)
        if (huella := hashlib.md5(contenido).hexdigest()) in vistos or (especies, fecha) in vistos:
            resultados.append({"nombre_archivo": nombre, "repetido": True, "frutas": [], "fecha": None})
            continue
        vistos.update({huella, (especies, fecha)})
        try:
            carga = guardar_asoex(db, contenido, nombre, usuario)
        except HTTPException as exc:
            raise HTTPException(exc.status_code, f"{nombre}: {exc.detail}") from exc
        resultados.append({"nombre_archivo": nombre, "repetido": False, "frutas": sorted(carga.resumen), "fecha": carga.fecha})
    db.commit()
    return {"cargas": resultados, **_estado_asoex(db)}


def _sustancias_por_fruta(db: Session, vigentes: dict[str, Asoex]) -> dict[str, list[str]]:
    salida: dict[str, list[str]] = {}
    for fruta, carga in vigentes.items():
        salida[fruta] = list(db.scalars(select(AsoexLimite.sustancia).distinct()
                                        .where(AsoexLimite.asoex_id == carga.id, AsoexLimite.fruta == fruta)))
    return salida


@router.post("/mrl/leer")
async def leer_mrl(archivo: UploadFile = File(...), usuario: Usuario = Depends(requiere_permiso(LABORATORIO)),
                   db: Session = Depends(get_db)) -> dict:
    """Lee un informe de residuos y propone fruta, sucursal, fecha y residuos (ppm). No guarda nada, ni el archivo."""
    vigentes = _vigentes(db)
    if not vigentes:
        raise HTTPException(400, "Primero carga la tabla de ASOEX")
    contenido = await archivo.read()
    if len(contenido) > MAX_ARCHIVO:
        raise HTTPException(413, "Archivo demasiado grande")
    try:
        lectura = leer_informe_mrl(contenido, archivo.filename or "informe", _sustancias_por_fruta(db, vigentes))
    except Exception as exc:
        raise HTTPException(400, "No se pudo leer el informe") from exc
    if lectura.unidad_id is not None:
        try:
            verificar_unidad(usuario, lectura.unidad_id)
        except HTTPException:
            lectura.advertencias.append("El informe es de una sucursal a la que no tienes acceso.")
            lectura.unidad_id = None
    especie = next((e for e in db.scalars(select(Especie)) if fruta_de_especie(e.nombre, [lectura.fruta or ""])), None)
    return {**lectura.__dict__, "especie_id": especie.id if especie else None}


@router.post("/mrl/comparar")
def comparar_mrl(datos: ComparacionEntrada, _: Usuario = Depends(requiere_ver("LABORATORIO")), db: Session = Depends(get_db)) -> dict:
    """Por país elegido: cada residuo detectado contra el límite de ASOEX de la fruta. No guarda nada."""
    vigente = _vigentes(db).get(datos.fruta)
    if vigente is None:
        raise HTTPException(400, f"No hay límites de ASOEX cargados para {datos.fruta}")
    disponibles = set(vigente.resumen[datos.fruta]["paises"])
    paises = [p for p in datos.paises if p in disponibles]
    if not paises:
        raise HTTPException(400, "Elige al menos un país de la tabla ASOEX de esa fruta")
    limites = list(db.scalars(select(AsoexLimite).where(AsoexLimite.asoex_id == vigente.id,
                                                        AsoexLimite.fruta == datos.fruta)))
    resultado = comparar(datos.fruta, paises, [r.model_dump() for r in datos.residuos], limites)
    cambios = [c for c in vigente.resumen[datos.fruta].get("proximos_cambios", [])
               if any(f"> {p} >" in c.upper() for p in paises)]
    return {**resultado, "asoex": {"nombre_archivo": vigente.nombre_archivo, "fecha": vigente.fecha},
            "proximos_cambios": cambios}
