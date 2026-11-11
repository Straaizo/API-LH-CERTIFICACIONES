from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import Config

_url = Config.url_base_datos()
engine = create_engine(
    _url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {},
)

if _url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _activar_fk(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _fk_columna_tabla(restriccion, tabla) -> str:
    """fk_<columna sin _id>_<tabla sin prefijo>: fk_protocolo_versionnorma. El nombre de una FK no se repite en la base."""
    corta = tabla.name.removeprefix("certificaciones_")
    for prefijo in ("dim_", "fact_", "pivot_"):
        corta = corta.removeprefix(prefijo)
    return f"{restriccion.elements[0].parent.name.removesuffix('_id')}_{corta}"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",  # el de SQLAlchemy por defecto
        "fk_columna_tabla": _fk_columna_tabla, "fk": "fk_%(fk_columna_tabla)s",
    })


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
