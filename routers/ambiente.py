from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from utils.auth import AMBIENTE, requiere_permiso, solo_certificaciones, usuario_actual, verificar_unidad
from utils.bitacora import registrar
from utils.comunes import filtrar_temporada, filtrar_unidades, obtener, unidad_dict
from utils.db import get_db
from utils.modelos import ConceptoAmbiental, FactorEmision, RegistroAmbiental, Unidad, Usuario
from utils.temporadas import (
    TemporadaLogica, buscar_temporada, en_temporada, listar_temporadas, obtener_temporada, temporada_actual,
    temporada_anterior, temporada_para_fecha,
)

router = APIRouter(prefix="/ambiente")

RECICLAJE = "reciclaje"
# Administrativos y jefes de área (rol encargado) solo registran y ven combustibles
CATEGORIAS_ENCARGADO = ("combustible",)


class ConsumoEntrada(BaseModel):
    unidad_id: int
    fecha: date
    concepto: str  # código del concepto: combustible_diesel, electricidad...
    cantidad: float = Field(ge=0)
    unidad_medida: str | None = None  # la define el concepto; se acepta por compatibilidad


class ReciclajeEntrada(BaseModel):
    unidad_id: int
    fecha: date
    material_id: int  # concepto de categoría reciclaje
    kilos: float = Field(gt=0)


def no_encargado(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol == "encargado":
        raise HTTPException(403, "Los encargados solo ven los consumos de combustible")
    return usuario


def _conceptos_consumo(db: Session, usuario: Usuario) -> list[ConceptoAmbiental]:
    consulta = select(ConceptoAmbiental).where(ConceptoAmbiental.categoria != RECICLAJE, ConceptoAmbiental.activo)
    if usuario.rol == "encargado":
        consulta = consulta.where(ConceptoAmbiental.categoria.in_(CATEGORIAS_ENCARGADO))
    return list(db.scalars(consulta.order_by(ConceptoAmbiental.id)))


def _validar_fecha(db: Session, fecha: date, unidad_id: int) -> None:
    unidad = obtener(db, Unidad, unidad_id)
    if not temporada_para_fecha(db, fecha, unidad.empresa_id):
        raise HTTPException(400, "La fecha no cae en ninguna temporada registrada")


def _registros(db: Session, usuario: Usuario, empresa_id, unidad_id, temporada_id, reciclaje: bool):
    consulta = select(RegistroAmbiental).join(ConceptoAmbiental).options(
        selectinload(RegistroAmbiental.unidad), selectinload(RegistroAmbiental.concepto))
    consulta = consulta.where((ConceptoAmbiental.categoria == RECICLAJE) if reciclaje
                              else (ConceptoAmbiental.categoria != RECICLAJE))
    consulta = filtrar_unidades(consulta, RegistroAmbiental.unidad_id, usuario, empresa_id, unidad_id)
    return filtrar_temporada(db, consulta, temporada_id, RegistroAmbiental.fecha, RegistroAmbiental.unidad_id)


@router.get("/conceptos")
def conceptos(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> list[dict]:
    return [{"codigo": c.codigo, "nombre": c.nombre, "unidad_medida": c.unidad_medida}
            for c in _conceptos_consumo(db, usuario)]


@router.get("/factores")
def factores(temporada_id: int | None = None, _: Usuario = Depends(no_encargado),
             db: Session = Depends(get_db)) -> list[dict]:
    consulta = select(FactorEmision).options(selectinload(FactorEmision.concepto))
    if temporada_id:
        consulta = consulta.where(FactorEmision.temporada == obtener_temporada(db, temporada_id).nombre)
    ids = {t.nombre: t.id for t in listar_temporadas(db)}
    return [{"id": f.id, "temporada_id": ids.get(f.temporada), "temporada": f.temporada, "concepto": f.concepto.codigo,
             "unidad_medida": f.concepto.unidad_medida, "factor_kgco2e": f.factor_kgco2e, "fuente": f.fuente}
            for f in db.scalars(consulta)]


@router.get("/consumos")
def listar_consumos(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
                    usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> list[dict]:
    visibles = {c.id for c in _conceptos_consumo(db, usuario)}
    consulta = _registros(db, usuario, empresa_id, unidad_id, temporada_id, reciclaje=False)
    consulta = consulta.where(RegistroAmbiental.concepto_id.in_(visibles or {-1}))
    return [{"id": r.id, "fecha": r.fecha, "concepto": r.concepto.codigo, "concepto_nombre": r.concepto.nombre,
             "cantidad": r.cantidad, "unidad_medida": r.concepto.unidad_medida, "unidad": unidad_dict(r.unidad)}
            for r in db.scalars(consulta.order_by(RegistroAmbiental.fecha.desc()))]


@router.post("/consumos", status_code=201)
def crear_consumo(datos: ConsumoEntrada, usuario: Usuario = Depends(requiere_permiso(AMBIENTE)),
                  db: Session = Depends(get_db)) -> dict:
    verificar_unidad(usuario, datos.unidad_id)
    concepto = next((c for c in _conceptos_consumo(db, usuario) if c.codigo == datos.concepto), None)
    if concepto is None:
        raise HTTPException(400, "Concepto inválido")
    _validar_fecha(db, datos.fecha, datos.unidad_id)
    registro = RegistroAmbiental(unidad_id=datos.unidad_id, concepto_id=concepto.id, fecha=datos.fecha,
                                 cantidad=datos.cantidad, creado_por_id=usuario.id)
    db.add(registro)
    db.flush()
    registrar(db, usuario, "crear", "consumo", registro.id, datos.model_dump(mode="json", exclude={"unidad_medida"}))
    db.commit()
    return {"id": registro.id}


@router.get("/reciclaje")
def listar_reciclaje(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
                     usuario: Usuario = Depends(no_encargado), db: Session = Depends(get_db)) -> list[dict]:
    consulta = _registros(db, usuario, empresa_id, unidad_id, temporada_id, reciclaje=True)
    return [{"id": r.id, "fecha": r.fecha, "material": r.concepto.nombre, "kilos": r.cantidad,
             "unidad": unidad_dict(r.unidad)} for r in db.scalars(consulta.order_by(RegistroAmbiental.fecha.desc()))]


@router.post("/reciclaje", status_code=201)
def crear_reciclaje(datos: ReciclajeEntrada, usuario: Usuario = Depends(solo_certificaciones),
                    db: Session = Depends(get_db)) -> dict:
    verificar_unidad(usuario, datos.unidad_id)
    material = obtener(db, ConceptoAmbiental, datos.material_id)
    if material.categoria != RECICLAJE:
        raise HTTPException(400, "Material de reciclaje inválido")
    _validar_fecha(db, datos.fecha, datos.unidad_id)
    registro = RegistroAmbiental(unidad_id=datos.unidad_id, concepto_id=material.id, fecha=datos.fecha,
                                 cantidad=datos.kilos, creado_por_id=usuario.id)
    db.add(registro)
    db.flush()
    registrar(db, usuario, "crear", "reciclaje", registro.id, datos.model_dump(mode="json"))
    db.commit()
    return {"id": registro.id}


def _factores(db: Session) -> dict[tuple[str, int], float]:
    """(nombre de temporada, concepto_id) -> kg CO2e por unidad del concepto."""
    return {(f.temporada, f.concepto_id): f.factor_kgco2e for f in db.scalars(select(FactorEmision))}


def _factor(db: Session, factores: dict, r: RegistroAmbiental) -> float | None:
    t = temporada_para_fecha(db, r.fecha, r.unidad.empresa_id)
    return factores.get((t.nombre, r.concepto_id)) if t else None


def calcular_huella(db: Session, registros: list[RegistroAmbiental]) -> dict:
    """kg CO2e por concepto y por mes, con el factor de la temporada de cada registro."""
    factores = _factores(db)
    por_concepto: dict[str, float] = {}
    por_mes: dict[str, float] = {}
    sin_factor: set[str] = set()
    for r in registros:
        factor = _factor(db, factores, r)
        if factor is None:
            sin_factor.add(r.concepto.nombre)
            continue
        kg = r.cantidad * factor
        por_concepto[r.concepto.nombre] = por_concepto.get(r.concepto.nombre, 0) + kg
        mes = r.fecha.strftime("%Y-%m")
        por_mes[mes] = por_mes.get(mes, 0) + kg
    return {
        "total_tco2e": round(sum(por_concepto.values()) / 1000, 2),
        "por_concepto": [{"concepto": c, "tco2e": round(v / 1000, 2)} for c, v in por_concepto.items()],
        "por_mes": [{"mes": m, "tco2e": round(v / 1000, 2)} for m, v in sorted(por_mes.items())],
        "conceptos_sin_factor": sorted(sin_factor),
    }


@router.get("/huella")
def huella(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
           usuario: Usuario = Depends(no_encargado), db: Session = Depends(get_db)) -> dict:
    consulta = _registros(db, usuario, empresa_id, unidad_id, temporada_id, reciclaje=False)
    return calcular_huella(db, list(db.scalars(consulta)))


# ---------- Comparativa entre temporadas ----------

MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
# Agrupación de conceptos (por código) para los indicadores del panel
GRUPOS_CONCEPTO = {
    "combustibles": ("combustible_diesel", "combustible_gasolina"),
    "gas": ("combustible_gas",),
    "electricidad": ("electricidad",),
    "fertilizantes": ("fertilizante_n", "fertilizante_no_n"),
}


def _meses_temporada(t: TemporadaLogica) -> list[tuple[int, int]]:
    """Los 12 (año, mes) de una temporada, desde su inicio."""
    meses, anio, mes = [], t.inicio.year, t.inicio.month
    for _ in range(12):
        meses.append((anio, mes))
        mes += 1
        if mes > 12:
            anio, mes = anio + 1, 1
    return meses


def _variacion(actual: float, anterior: float) -> float | None:
    return round((actual - anterior) / anterior * 100, 1) if anterior else None


def _por_mes(registros, indices: dict, valor) -> list[float]:
    serie = [0.0] * 12
    for r in registros:
        i = indices.get((r.fecha.year, r.fecha.month))
        if i is not None:
            serie[i] += valor(r)
    return serie


def _acumulado(serie: list[float]) -> list[float]:
    total, salida = 0.0, []
    for v in serie:
        total += v
        salida.append(round(total, 2))
    return salida


@router.get("/comparativa")
def comparativa(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
                anterior_id: int | None = None, usuario: Usuario = Depends(no_encargado),
                db: Session = Depends(get_db)) -> dict:
    """Temporada elegida (o la actual) contra la anterior al mismo período: si la actual lleva 3 meses con
    datos, se compara con los mismos 3 meses de la anterior. Incluye la anterior completa y una proyección."""
    actual = buscar_temporada(db, temporada_id) if temporada_id else temporada_actual(db)
    if actual is None:
        raise HTTPException(404, "No hay una temporada para comparar")
    if anterior_id:
        # Comparación elegida por el usuario: cualquier otra temporada
        if anterior_id == actual.id:
            raise HTTPException(400, "Elige dos temporadas distintas")
        anterior = obtener_temporada(db, anterior_id)
    else:
        anterior = temporada_anterior(db, actual)
    factores = _factores(db)

    def registros(t: TemporadaLogica | None, reciclaje: bool) -> list[RegistroAmbiental]:
        if t is None:
            return []
        consulta = _registros(db, usuario, empresa_id, unidad_id, None, reciclaje)
        return list(db.scalars(consulta.where(en_temporada(t, RegistroAmbiental.fecha, RegistroAmbiental.unidad_id))))

    idx_act = {m: i for i, m in enumerate(_meses_temporada(actual))}
    idx_ant = {m: i for i, m in enumerate(_meses_temporada(anterior))} if anterior else {}
    reg_act, reg_ant = registros(actual, False), registros(anterior, False)
    rec_act, rec_ant = registros(actual, True), registros(anterior, True)

    # Meses con datos en la temporada actual: definen el "mismo período" de la comparación
    con_datos = [idx_act[(r.fecha.year, r.fecha.month)] for r in reg_act + rec_act
                 if (r.fecha.year, r.fecha.month) in idx_act]
    n = max(con_datos) + 1 if con_datos else 0

    def tco2e(r: RegistroAmbiental) -> float:
        return r.cantidad * (_factor(db, factores, r) or 0) / 1000

    def cantidad(r: RegistroAmbiental) -> float:
        return r.cantidad

    def comparar(sel_act, sel_ant, valor) -> tuple[list[float], list[float], float, float]:
        m_act, m_ant = _por_mes(sel_act, idx_act, valor), _por_mes(sel_ant, idx_ant, valor)
        return m_act, m_ant, sum(m_act[:n]), sum(m_ant[:n])

    h_act, h_ant, huella_fecha, huella_mismo = comparar(reg_act, reg_ant, tco2e)
    huella_total_ant = sum(h_ant)
    if n == 12:
        proyeccion = huella_fecha
    elif huella_mismo:
        proyeccion = huella_fecha * huella_total_ant / huella_mismo
    else:
        proyeccion = None

    catalogo = list(db.scalars(select(ConceptoAmbiental).order_by(ConceptoAmbiental.id)))
    conceptos = []
    for c in catalogo:
        if c.categoria == RECICLAJE:
            continue
        sel_act = [r for r in reg_act if r.concepto_id == c.id]
        sel_ant = [r for r in reg_ant if r.concepto_id == c.id]
        _, _, c_act, c_ant = comparar(sel_act, sel_ant, cantidad)
        _, _, t_act, t_ant = comparar(sel_act, sel_ant, tco2e)
        if c_act or c_ant:
            conceptos.append({"codigo": c.codigo, "nombre": c.nombre, "unidad_medida": c.unidad_medida,
                              "actual": round(c_act), "anterior": round(c_ant),
                              "tco2e_actual": round(t_act, 2), "tco2e_anterior": round(t_ant, 2),
                              "variacion": _variacion(c_act, c_ant)})

    def indicador(m_act, m_ant, total_act, total_ant, unidad_medida) -> dict:
        return {"unidad_medida": unidad_medida, "actual": round(total_act), "anterior": round(total_ant),
                "variacion": _variacion(total_act, total_ant),
                "mensual_actual": [round(v) for v in m_act[:n]], "mensual_anterior": [round(v) for v in m_ant]}

    unidades_medida = {c.codigo: c.unidad_medida for c in catalogo}
    indicadores = {}
    for clave, codigos in GRUPOS_CONCEPTO.items():
        res = comparar([r for r in reg_act if r.concepto.codigo in codigos],
                       [r for r in reg_ant if r.concepto.codigo in codigos], cantidad)
        indicadores[clave] = indicador(*res, unidades_medida.get(codigos[0], ""))
    indicadores["reciclaje"] = indicador(*comparar(rec_act, rec_ant, cantidad), "kg")

    materiales = []
    for material in catalogo:
        if material.categoria != RECICLAJE:
            continue
        _, _, k_act, k_ant = comparar([r for r in rec_act if r.concepto_id == material.id],
                                      [r for r in rec_ant if r.concepto_id == material.id], cantidad)
        if k_act or k_ant:
            materiales.append({"nombre": material.nombre, "actual": round(k_act), "anterior": round(k_ant),
                               "variacion": _variacion(k_act, k_ant)})

    sucursales = []
    for id_unidad in sorted({r.unidad_id for r in reg_act + reg_ant}):
        _, _, u_act, u_ant = comparar([r for r in reg_act if r.unidad_id == id_unidad],
                                      [r for r in reg_ant if r.unidad_id == id_unidad], tco2e)
        unidad = next(r.unidad for r in reg_act + reg_ant if r.unidad_id == id_unidad)
        sucursales.append({"unidad": unidad_dict(unidad), "tco2e_actual": round(u_act, 2),
                           "tco2e_anterior": round(u_ant, 2), "variacion": _variacion(u_act, u_ant)})
    sucursales.sort(key=lambda s: (s["variacion"] is None, s["variacion"] or 0))

    return {
        "actual": {"id": actual.id, "nombre": actual.nombre, "inicio": actual.inicio, "fin": actual.fin},
        "anterior": {"id": anterior.id, "nombre": anterior.nombre} if anterior else None,
        "meses": [MESES_CORTOS[m - 1] for _, m in _meses_temporada(actual)],
        "meses_comparados": n,
        "huella": {
            "actual_a_la_fecha": round(huella_fecha, 2), "anterior_mismo_periodo": round(huella_mismo, 2),
            "anterior_total": round(huella_total_ant, 2), "variacion": _variacion(huella_fecha, huella_mismo),
            "proyeccion_cierre": round(proyeccion, 1) if proyeccion is not None else None,
            "variacion_proyeccion": _variacion(proyeccion, huella_total_ant) if proyeccion is not None else None,
            "mensual_actual": [round(v, 2) for v in h_act[:n]], "mensual_anterior": [round(v, 2) for v in h_ant],
            "acumulado_actual": _acumulado(h_act)[:n], "acumulado_anterior": _acumulado(h_ant),
        },
        "indicadores": indicadores,
        "conceptos": conceptos,
        "sucursales": sucursales,
        "reciclaje_materiales": materiales,
    }
