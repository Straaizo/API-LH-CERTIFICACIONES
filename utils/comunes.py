from datetime import date

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from utils.auth import unidades_permitidas
from utils.modelos import Temporada, Ubicacion, Unidad, Usuario


def temporada_para_fecha(db: Session, fecha: date) -> Temporada | None:
    return db.scalar(select(Temporada).where(Temporada.inicio <= fecha, Temporada.fin >= fecha))


def temporada_actual(db: Session) -> Temporada | None:
    return temporada_para_fecha(db, date.today())


def obtener(db: Session, modelo, id_: int):
    objeto = db.get(modelo, id_)
    if objeto is None:
        raise HTTPException(404, f"{modelo.__name__} {id_} no existe")
    return objeto


def filtrar_unidades(consulta: Select, columna_unidad, usuario: Usuario,
                     empresa_id: int | None = None, unidad_id: int | None = None) -> Select:
    """Aplica permisos por unidad y los filtros transversales de empresa y unidad."""
    permitidas = unidades_permitidas(usuario)
    if permitidas is not None:
        consulta = consulta.where(columna_unidad.in_(permitidas or {-1}))
    if unidad_id:
        consulta = consulta.where(columna_unidad == unidad_id)
    if empresa_id:
        sub = select(Unidad.id).join(Ubicacion).where(Ubicacion.empresa_id == empresa_id)
        consulta = consulta.where(columna_unidad.in_(sub))
    return consulta


def unidad_dict(u: Unidad | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "nombre": u.nombre, "tipo": u.tipo, "empresa_id": u.ubicacion.empresa_id}


def dias_para(fecha: date | None) -> int | None:
    return (fecha - date.today()).days if fecha else None
