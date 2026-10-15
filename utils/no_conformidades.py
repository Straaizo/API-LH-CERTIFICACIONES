from sqlalchemy import select
from sqlalchemy.orm import Session

from utils.modelos import Auditoria, NoConformidad, Respuesta


def recalcular_reincidencias(db: Session, requisito_id: int, unidad_id: int) -> None:
    """Enlaza cada NC de un requisito y unidad con la NC anterior de una auditoría previa."""
    ncs = db.scalars(
        select(NoConformidad)
        .where(NoConformidad.requisito_id == requisito_id, NoConformidad.unidad_id == unidad_id)
        .order_by(NoConformidad.fecha_deteccion, NoConformidad.id)
    ).all()
    anterior: NoConformidad | None = None
    for nc in ncs:
        if anterior and anterior.auditoria_id != nc.auditoria_id and anterior.fecha_deteccion < nc.fecha_deteccion:
            nc.reincidente_de_id = anterior.id
        else:
            nc.reincidente_de_id = None
        anterior = nc


def sincronizar_nc(db: Session, auditoria: Auditoria, respuesta: Respuesta) -> NoConformidad | None:
    """Cada 'No' tiene su NC. Si la respuesta deja de ser 'No' y la NC no tiene levantamientos, se elimina."""
    nc = db.scalar(select(NoConformidad).where(NoConformidad.respuesta_id == respuesta.id))
    if respuesta.resultado == "no":
        if nc is None:
            nc = NoConformidad(
                auditoria_id=auditoria.id, respuesta_id=respuesta.id, requisito_id=respuesta.requisito_id,
                unidad_id=auditoria.unidad_id, area_id=respuesta.area_id, fecha_deteccion=auditoria.fecha,
                descripcion=respuesta.comentario or "Sin descripción", estado="abierta",
            )
            db.add(nc)
            db.flush()
        else:
            nc.descripcion = respuesta.comentario or nc.descripcion
            nc.area_id = respuesta.area_id or nc.area_id
        recalcular_reincidencias(db, respuesta.requisito_id, auditoria.unidad_id)
        return nc
    if nc is not None and not nc.acciones and nc.estado != "cerrada":
        db.delete(nc)
        db.flush()
        recalcular_reincidencias(db, respuesta.requisito_id, auditoria.unidad_id)
    return None
