from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from config import Config
from utils.auth import unidades_permitidas, usuario_actual, verificar_clave_demo
from utils.comunes import obtener, temporada_actual, unidad_dict
from utils.db import get_db
from utils.modelos import (
    Area, CategoriaDocumento, ConceptoAmbiental, Empresa, Especie, FuenteAgua, LimiteParametro, Protocolo, TipoAnalisis,
    Unidad, Usuario, VersionNorma, sucursal_protocolos, usuario_apps,
)
from utils.temporadas import listar_temporadas

router = APIRouter()


@router.get("/usuarios-demo", dependencies=[Depends(verificar_clave_demo)])
def usuarios_demo(db: Session = Depends(get_db)) -> list[dict]:
    """Solo en modo demo: lista de usuarios para elegir en la pantalla de ingreso."""
    if Config.AUTH_MODO != "demo":
        return []
    return [_usuario_dict(u) for u in _usuarios_app(db)]


def _usuarios_app(db: Session) -> list[Usuario]:
    """Usuarios activos con acceso a Certificaciones."""
    return list(db.scalars(
        select(Usuario).where(Usuario.id_estado == 1, Usuario.id.in_(
            select(usuario_apps.c.id_usuario).where(usuario_apps.c.id_app == Config.APP_ID)))
        .options(selectinload(Usuario.unidades), selectinload(Usuario.permisos)).order_by(Usuario.nombre)))


def _usuario_dict(u: Usuario) -> dict:
    return {"id": u.id, "nombre": u.nombre or u.usuario, "usuario": u.usuario, "email": u.email, "rol": u.rol,
            "permisos": sorted(u.codigos_permiso), "unidades": [unidad_dict(x) for x in u.unidades]}


@router.get("/yo")
def yo(usuario: Usuario = Depends(usuario_actual)) -> dict:
    return _usuario_dict(usuario)


@router.get("/catalogos")
def catalogos(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    permitidas = unidades_permitidas(usuario)
    # Sucursales que tienen alguna norma (las demás no participan en certificaciones)
    unidades = [u for u in db.scalars(select(Unidad).where(Unidad.id.in_(
        select(sucursal_protocolos.c.sucursal_id))).order_by(Unidad.empresa_id, Unidad.id))]
    if permitidas is not None:
        unidades = [u for u in unidades if u.id in permitidas]
    ids = {u.id for u in unidades}
    actual = temporada_actual(db)
    return {
        "empresas": [{"id": e.id, "codigo": e.codigo, "nombre": e.nombre}
                     for e in db.scalars(select(Empresa).order_by(Empresa.id))],
        "unidades": [unidad_dict(u) for u in unidades],
        "areas": [{"id": a.id, "nombre": a.nombre, "unidad_id": a.unidad_id}
                  for a in db.scalars(select(Area).order_by(Area.id)) if a.unidad_id in ids],
        "temporadas": [{"id": t.id, "nombre": t.nombre, "inicio": t.inicio, "fin": t.fin,
                        "actual": actual is not None and t.id == actual.id} for t in listar_temporadas(db)],
        "protocolos": [
            {"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "ambito": p.ambito,
             "unidades_aplica": [u.id for u in unidades if p.aplica_a(u)],
             "solo_unidades": [u.id for u in p.unidades if u.id in ids],
             "versiones": [{"id": v.id, "nombre": v.nombre, "vigente": v.vigente, "requisitos": len(v.requisitos),
                            "cargada_en": v.cargada_en, "archivo": v.archivo}
                           for v in sorted(p.versiones, key=lambda v: (not v.vigente, -(v.id or 0)))]}
            for p in db.scalars(select(Protocolo).order_by(Protocolo.ambito, Protocolo.id))
        ],
        "categorias": [{"id": c.id, "nombre": c.nombre, "ambito": c.ambito,
                        "requiere_vencimiento": c.requiere_vencimiento, "requiere_codigo": c.requiere_codigo}
                       for c in db.scalars(select(CategoriaDocumento).order_by(CategoriaDocumento.orden))],
        "tipos_analisis": [
            {"id": t.id, "nombre": t.nombre, "ambito": t.ambito, "usa_fuente_agua": t.usa_fuente_agua,
             "usa_especie": t.usa_especie}
            for t in db.scalars(select(TipoAnalisis).order_by(TipoAnalisis.ambito, TipoAnalisis.id))
        ],
        "limites": [{"id": lp.id, "tipo_analisis_id": lp.tipo_analisis_id, "parametro": lp.parametro,
                     "unidad_medida": lp.unidad_medida, "minimo": lp.minimo, "maximo": lp.maximo, "norma": lp.norma}
                    for lp in db.scalars(select(LimiteParametro))],
        "fuentes_agua": [{"id": f.id, "nombre": f.nombre, "unidades": [u.id for u in f.unidades]}
                         for f in db.scalars(select(FuenteAgua)) if any(u.id in ids for u in f.unidades)],
        "especies": [{"id": e.id, "nombre": e.nombre} for e in db.scalars(select(Especie).order_by(Especie.nombre))],
        "materiales_reciclaje": [{"id": c.id, "nombre": c.nombre} for c in db.scalars(
            select(ConceptoAmbiental).where(ConceptoAmbiental.categoria == "reciclaje", ConceptoAmbiental.activo)
            .order_by(ConceptoAmbiental.nombre))],
        "usuarios": [{"id": u.id, "nombre": u.nombre or u.usuario, "rol": u.rol}
                     for u in _usuarios_app(db) if u.rol != "lectura"],
    }


@router.get("/versiones/{version_id}/requisitos")
def requisitos_version(version_id: int, _: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    """Puntos de control de una versión de norma, para revisarla antes de usarla en una auditoría."""
    version = obtener(db, VersionNorma, version_id)
    return {
        "id": version.id, "nombre": version.nombre, "vigente": version.vigente, "cargada_en": version.cargada_en,
        "archivo": version.archivo, "protocolo": {"codigo": version.protocolo.codigo, "nombre": version.protocolo.nombre},
        "secciones": version.secciones or [],
        "requisitos": [{"id": r.id, "codigo": r.codigo, "seccion": r.seccion, "seccion_titulo": r.seccion_titulo,
                        "texto": r.texto, "nivel": r.nivel} for r in version.requisitos],
    }
