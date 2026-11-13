"""Temporadas desde general_dim_temporada (una fila por empresa, mayo a abril).

La API agrupa por nombre ('25-26'): el id que ve el frontend es el año de inicio (2025).
Una fecha pertenece a la temporada según el rango de la empresa de su sucursal.
Solo se usan las temporadas con fechas desde 2024 (las anteriores no las tienen) y, de ellas, la que está en curso
y la anterior (decisión del 13-11-2026): lo de la anterior sirve para comparar. Cada mayo avanza sola.
"""
from dataclasses import dataclass, field
from datetime import date

from fastapi import HTTPException
from sqlalchemy import ColumnElement, and_, false, or_, select
from sqlalchemy.orm import Session

from utils.modelos import Temporada, Unidad

DESDE = date(2024, 1, 1)
TEMPORADAS_VISIBLES = 2  # la en curso y la anterior


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


def listar_temporadas(db: Session, hoy: date | None = None) -> list[TemporadaLogica]:
    """La en curso y la anterior, de la más reciente a la más antigua. Se calcula una vez por sesión."""
    if "temporadas" not in db.info:
        hoy = hoy or date.today()
        filas = db.scalars(select(Temporada).where(Temporada.inicio >= DESDE, Temporada.fin.is_not(None)))
        por_nombre: dict[str, TemporadaLogica] = {}
        for f in filas:
            t = por_nombre.setdefault(f.temporada, TemporadaLogica(id=f.inicio.year, nombre=f.temporada))
            t.id = min(t.id, f.inicio.year)
            t.rangos[f.empresa_id] = (f.inicio, f.fin)
        # Las que ya empezaron (no las futuras ya cargadas en la tabla), de la más reciente: en curso y anterior
        iniciadas = [t for t in por_nombre.values() if t.inicio <= hoy]
        db.info["temporadas"] = sorted(iniciadas, key=lambda t: t.id, reverse=True)[:TEMPORADAS_VISIBLES]
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


def temporada_elegida(db: Session, valor: str | None) -> TemporadaLogica:
    """La temporada seleccionada arriba en la app (cabecera X-Temporada, su id: año de inicio); sin ella, la actual."""
    t = buscar_temporada(db, int(valor)) if valor and valor.strip().isdigit() else None
    t = t or temporada_actual(db) or next(iter(listar_temporadas(db)), None)
    if t is None:
        raise HTTPException(400, "No hay temporadas disponibles")
    return t


def temporada_al_guardar(db: Session, elegida: TemporadaLogica, fecha: date | None, empresa_id: int | None) -> str:
    """Nombre de temporada a guardar. Si el dato tiene fecha, debe ser de la temporada elegida; si no, no se guarda."""
    if fecha:
        de_la_fecha = temporada_para_fecha(db, fecha, empresa_id)
        if de_la_fecha is None:
            habilitadas = " y ".join(t.nombre for t in listar_temporadas(db))
            raise HTTPException(400, f"La fecha {fecha:%d-%m-%Y} no pertenece a las temporadas habilitadas ({habilitadas}).")
        if de_la_fecha.id != elegida.id:
            raise HTTPException(400, f"La fecha {fecha:%d-%m-%Y} es de la temporada {de_la_fecha.nombre}. "
                                     f"Cambia la temporada arriba a {de_la_fecha.nombre} y vuelve a subirlo.")
    return elegida.nombre


def en_temporada_guardada(t: TemporadaLogica | None, columna_temporada, columna_fecha, columna_unidad) -> ColumnElement[bool]:
    """Por la temporada guardada; lo cargado antes de existir la columna (vacía) se ubica por su fecha."""
    if t is None:
        return false()
    return or_(columna_temporada == t.nombre,
               and_(columna_temporada.is_(None), en_temporada(t, columna_fecha, columna_unidad)))


def temporada_dict(t: TemporadaLogica | None) -> dict | None:
    if t is None:
        return None
    return {"id": t.id, "nombre": t.nombre, "inicio": t.inicio, "fin": t.fin}
