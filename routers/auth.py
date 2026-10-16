"""Inicio de sesión con usuario o correo + clave (AUTH_MODO=jwt), igual que LH Inventario."""
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from config import Config
from utils.auth import cargar_usuario, crear_tokens, leer_token, validar_acceso, verificar_clave
from utils.db import get_db
from utils.modelos import Usuario

router = APIRouter(prefix="/auth")

MAX_FALLOS = 5
VENTANA_SEG = 15 * 60
_fallos: dict[str, deque] = defaultdict(deque)


class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=200)  # usuario (inicial y apellido) o correo
    clave: str = Field(min_length=1, max_length=200)


class RefrescoEntrada(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2000)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _bloqueado(ip: str) -> bool:
    fallos = _fallos[ip]
    while fallos and fallos[0] < time.monotonic() - VENTANA_SEG:
        fallos.popleft()
    return len(fallos) >= MAX_FALLOS


def _modo_jwt() -> None:
    if Config.AUTH_MODO != "jwt":
        raise HTTPException(404, "El inicio de sesión con clave no está activo en este entorno")


@router.post("/login")
def login(datos: LoginEntrada, request: Request, db: Session = Depends(get_db)) -> dict:
    _modo_jwt()
    ip = _ip(request)
    if _bloqueado(ip):
        raise HTTPException(429, "Demasiados intentos fallidos. Intenta de nuevo en unos minutos.")
    ident = datos.usuario.strip().lower()
    encontrado = db.scalar(select(Usuario).where(or_(
        func.lower(func.trim(Usuario.correo)) == ident, func.lower(func.trim(Usuario.usuario)) == ident)).limit(1))
    if not verificar_clave(datos.clave, encontrado.clave if encontrado else None):
        _fallos[ip].append(time.monotonic())
        raise HTTPException(401, "Usuario o clave incorrectos")
    _fallos.pop(ip, None)
    usuario = validar_acceso(cargar_usuario(db, encontrado.id))
    return crear_tokens(usuario.id)


@router.post("/refresh")
def refrescar(datos: RefrescoEntrada, db: Session = Depends(get_db)) -> dict:
    _modo_jwt()
    usuario = validar_acceso(cargar_usuario(db, leer_token(datos.refresh_token, "refresh")))
    return crear_tokens(usuario.id)
