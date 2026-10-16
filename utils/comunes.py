from datetime import date

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from utils.auth import unidades_permitidas
from utils.modelos import Unidad, Usuario
from utils.temporadas import (  # noqa: F401  reexportadas para los routers
    TemporadaLogica, buscar_temporada, en_temporada, obtener_temporada, temporada_actual, temporada_dict,
    temporada_para_fecha,
)


def obtener(db: Session, modelo, id_):
    objeto = db.get(modelo, id_)
    if objeto is None:
        raise HTTPException(404, f"{modelo.__name__} {id_} no existe")
    return objeto


def filtrar_unidades(consulta: Select, columna_unidad, usuario: Usuario,
                     empresa_id: int | None = None, unidad_id: int | None = None) -> Select:
    """Aplica permisos por sucursal y los filtros transversales de empresa y sucursal."""
    permitidas = unidades_permitidas(usuario)
    if permitidas is not None:
        consulta = consulta.where(columna_unidad.in_(permitidas or {-1}))
    if unidad_id:
        consulta = consulta.where(columna_unidad == unidad_id)
    if empresa_id:
        consulta = consulta.where(columna_unidad.in_(select(Unidad.id).where(Unidad.empresa_id == empresa_id)))
    return consulta


def filtrar_temporada(db: Session, consulta: Select, temporada_id: int | None, columna_fecha, columna_unidad) -> Select:
    """Filtra por temporada: la fecha cae en el rango de la empresa de la sucursal."""
    if not temporada_id:
        return consulta
    return consulta.where(en_temporada(buscar_temporada(db, temporada_id), columna_fecha, columna_unidad))


def unidad_dict(u: Unidad | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "nombre": u.etiqueta, "tipo": u.tipo, "tipo_nombre": u.tipo_nombre, "empresa_id": u.empresa_id}


def dias_para(fecha: date | None) -> int | None:
    return (fecha - date.today()).days if fecha else None
