from sqlalchemy.orm import Session

from utils.modelos import Bitacora, Usuario


def registrar(db: Session, usuario: Usuario | None, accion: str, entidad: str,
              entidad_id: int | None = None, detalle: dict | None = None) -> None:
    """Agrega una entrada a la bitácora; se confirma junto con el commit del cambio."""
    db.add(Bitacora(
        usuario_id=usuario.id if usuario else None,
        accion=accion, entidad=entidad, entidad_id=entidad_id, detalle=detalle,
    ))
