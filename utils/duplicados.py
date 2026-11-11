"""Aviso de archivo repetido: la API responde 409 y la aplicación pregunta si reemplazar (o subir igual).

detail = {"codigo": "duplicado", "mensaje": ..., "existentes": [{"nombre", "detalle"}], "accion": "Reemplazar"}
La aplicación repite la petición con reemplazar=true si la persona confirma.
"""
from datetime import date, datetime

from fastapi import HTTPException


def _fecha(valor: date | datetime | None) -> str:
    return valor.strftime("%d-%m-%Y") if valor else "sin fecha"


def existente(nombre: str, cuando: date | datetime | None = None, por: str | None = None, extra: str | None = None) -> dict:
    partes = [f"cargado el {_fecha(cuando)}" if cuando else None, f"por {por}" if por else None, extra]
    return {"nombre": nombre, "detalle": " · ".join(p for p in partes if p)}


def error_duplicado(mensaje: str, existentes: list[dict], accion: str = "Reemplazar") -> HTTPException:
    return HTTPException(409, {"codigo": "duplicado", "mensaje": mensaje, "existentes": existentes, "accion": accion})
