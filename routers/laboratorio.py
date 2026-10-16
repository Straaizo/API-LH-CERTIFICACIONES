from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from utils import almacenamiento
from utils.auth import LABORATORIO, requiere_permiso, usuario_actual, verificar_unidad
from utils.bitacora import registrar
from utils.comunes import filtrar_temporada, filtrar_unidades, obtener, unidad_dict
from utils.db import get_db
from utils.leer_informe_lab import leer_informe
from utils.modelos import (
    TIPO_CAMPO, TIPO_PACKING, Analisis, Especie, FuenteAgua, LimiteParametro, ResultadoAnalisis, TipoAnalisis, Unidad,
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
    tipo_analisis_id: int
    unidad_id: int
    fuente_agua_id: int | None = None
    especie_id: int | None = None
    punto: str | None = None
    fecha_muestreo: date
    laboratorio: str | None = None
    archivo_key: str | None = None
    nombre_archivo: str | None = None
    resultados: list[ResultadoEntrada] = Field(min_length=1)


class LecturaEntrada(BaseModel):
    archivo_key: str
    nombre_archivo: str
    tipo_analisis_id: int | None = None
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
           tipo_analisis_id: int | None = None, solo_fuera_de_norma: bool = False, tipo_unidad: str | None = None,
           usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> list[dict]:
    """tipo_unidad: 'campo' o 'planta' para ver solo los análisis de ese tipo de sucursal."""
    consulta = filtrar_unidades(
        select(Analisis).options(selectinload(Analisis.resultados), selectinload(Analisis.tipo)),
        Analisis.unidad_id, usuario, empresa_id, unidad_id)
    consulta = filtrar_temporada(db, consulta, temporada_id, Analisis.fecha_muestreo, Analisis.unidad_id)
    if tipo_analisis_id:
        consulta = consulta.where(Analisis.tipo_analisis_id == tipo_analisis_id)
    if tipo_unidad in ("campo", "planta"):
        tipo_id = TIPO_CAMPO if tipo_unidad == "campo" else TIPO_PACKING
        consulta = consulta.where(Analisis.unidad_id.in_(select(Unidad.id).where(Unidad.tipo_id == tipo_id)))
    datos = [_analisis_dict(a) for a in db.scalars(consulta.order_by(Analisis.fecha_muestreo.desc()))]
    return [d for d in datos if d["fuera_de_norma"]] if solo_fuera_de_norma else datos


@router.post("/analisis", status_code=201)
def crear(datos: AnalisisEntrada, usuario: Usuario = Depends(requiere_permiso(LABORATORIO)),
          db: Session = Depends(get_db)) -> dict:
    verificar_unidad(usuario, datos.unidad_id)
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
    analisis = Analisis(**datos.model_dump(exclude={"resultados"}), creado_por_id=usuario.id)
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
def informe(analisis_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    analisis = obtener(db, Analisis, analisis_id)
    verificar_unidad(usuario, analisis.unidad_id)
    if not analisis.archivo_key:
        raise HTTPException(404, "El análisis no tiene informe")
    return {"url": almacenamiento.url_descarga(analisis.archivo_key, analisis.nombre_archivo)}
