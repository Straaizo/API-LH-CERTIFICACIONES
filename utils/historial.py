from sqlalchemy.orm import Session

from utils.modelos import Historial, Usuario


def registrar(db: Session, usuario: Usuario | None, accion: str, entidad: str,
              entidad_id: str | None = None, detalle: dict | None = None) -> None:
    """Agrega una entrada al historial de cambios; se confirma junto con el commit del cambio."""
    db.add(Historial(
        usuario_id=usuario.id if usuario else None,
        accion=accion, entidad=entidad, entidad_id=entidad_id, detalle=detalle,
    ))
