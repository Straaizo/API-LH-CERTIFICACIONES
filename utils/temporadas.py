"""Temporadas desde general_dim_temporada (una fila por empresa, mayo a abril).

La API agrupa por nombre ('25-26'): el id que ve el frontend es el año de inicio (2025).
Una fecha pertenece a la temporada según el rango de la empresa de su sucursal.
Solo se usan las temporadas con fechas desde 2024 (las anteriores no las tienen).
"""
from dataclasses import dataclass, field
from datetime import date

from fastapi import HTTPException
from sqlalchemy import ColumnElement, and_, false, or_, select
from sqlalchemy.orm import Session

from utils.modelos import Temporada, Unidad

DESDE = date(2024, 1, 1)


@dataclass
class TemporadaLogica:
    id: int  # año de inicio
    nombre: str  # 25-26
    rangos: dict[int, tuple[date, date]] = field(default_factory=dict)  # empresa_id -> (inicio, fin)

    @property
    def inicio(self) -> date:
        return min(i for i, _ in self.rangos.values())

    @property
    def fin(self) -> date:
        return max(f for _, f in self.rangos.values())

    def rango(self, empresa_id: int | None = None) -> tuple[date, date]:
        return self.rangos.get(empresa_id) or (self.inicio, self.fin)

    def contiene(self, fecha: date, empresa_id: int | None = None) -> bool:
        inicio, fin = self.rango(empresa_id)
        return inicio <= fecha <= fin


def listar_temporadas(db: Session) -> list[TemporadaLogica]:
    """De la más reciente a la más antigua. Se calcula una vez por sesión."""
    if "temporadas" not in db.info:
        filas = db.scalars(select(Temporada).where(Temporada.inicio >= DESDE, Temporada.fin.is_not(None)))
        por_nombre: dict[str, TemporadaLogica] = {}
        for f in filas:
            t = por_nombre.setdefault(f.temporada, TemporadaLogica(id=f.inicio.year, nombre=f.temporada))
            t.id = min(t.id, f.inicio.year)
            t.rangos[f.empresa_id] = (f.inicio, f.fin)
        db.info["temporadas"] = sorted(por_nombre.values(), key=lambda t: t.id, reverse=True)
    return db.info["temporadas"]


def buscar_temporada(db: Session, temporada_id: int | None) -> TemporadaLogica | None:
    return next((t for t in listar_temporadas(db) if t.id == temporada_id), None)


def obtener_temporada(db: Session, temporada_id: int) -> TemporadaLogica:
    t = buscar_temporada(db, temporada_id)
    if t is None:
        raise HTTPException(404, f"Temporada {temporada_id} no existe")
    return t


def temporada_para_fecha(db: Session, fecha: date, empresa_id: int | None = None) -> TemporadaLogica | None:
    return next((t for t in listar_temporadas(db) if t.contiene(fecha, empresa_id)), None)


def temporada_actual(db: Session) -> TemporadaLogica | None:
    return temporada_para_fecha(db, date.today())


def temporada_anterior(db: Session, t: TemporadaLogica) -> TemporadaLogica | None:
    return next((x for x in listar_temporadas(db) if x.id < t.id), None)


def id_temporada(db: Session, fecha: date, empresa_id: int | None) -> int | None:
    t = temporada_para_fecha(db, fecha, empresa_id)
    return t.id if t else None


def en_temporada(t: TemporadaLogica | None, columna_fecha, columna_unidad) -> ColumnElement[bool]:
    """Condición SQL: la fecha cae en la temporada según la empresa de la sucursal."""
    if t is None:
        return false()
    return or_(*(
        and_(columna_unidad.in_(select(Unidad.id).where(Unidad.empresa_id == empresa_id)),
             columna_fecha.between(inicio, fin))
        for empresa_id, (inicio, fin) in t.rangos.items()
    ))


def temporada_dict(t: TemporadaLogica | None) -> dict | None:
    if t is None:
        return None
    return {"id": t.id, "nombre": t.nombre, "inicio": t.inicio, "fin": t.fin}
