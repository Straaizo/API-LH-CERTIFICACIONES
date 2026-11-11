"""Inicio de sesión con usuario o correo + clave (AUTH_MODO=jwt), igual que LH Inventario."""
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from config import Config
from utils.auth import cargar_usuario, crear_tokens, leer_token, validar_acceso, verificar_clave
from utils.db import get_db
from utils.modelos import Usuario
from utils.proteccion import ip_cliente, login_bloqueado, registrar_exito_login, registrar_fallo_login

router = APIRouter(prefix="/auth")
logger = logging.getLogger("seguridad")

# Toda respuesta del login tarda lo mismo (piso + azar), acierte o no, exista o no el usuario, esté o no en pausa:
# medir el tiempo de respuesta no revela nada. El piso debe quedar sobre lo que tarda bcrypt (~0,3 s con costo 12).
PISO_LOGIN = 1.0
AZAR_LOGIN = 0.2


def _esperar_piso(inicio: float) -> None:
    transcurrido = time.perf_counter() - inicio
    if transcurrido > PISO_LOGIN:
        logger.warning("[SEGURIDAD] El login tardó %.2f s, más que el piso de %.2f s: subir PISO_LOGIN", transcurrido, PISO_LOGIN)
    time.sleep(max(0.0, PISO_LOGIN - transcurrido) + secrets.randbelow(max(1, int(AZAR_LOGIN * 1000))) / 1000)

class LoginEntrada(BaseModel):
    usuario: str = Field(min_length=1, max_length=200)  # usuario (inicial y apellido) o correo
    clave: str = Field(min_length=1, max_length=200)


class RefrescoEntrada(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2000)


def _modo_jwt() -> None:
    if Config.AUTH_MODO != "jwt":
        raise HTTPException(404, "El inicio de sesión con clave no está activo en este entorno")


@router.post("/login")
def login(datos: LoginEntrada, request: Request, db: Session = Depends(get_db)) -> dict:
    _modo_jwt()
    inicio = time.perf_counter()
    try:
        return _login(datos, request, db)
    finally:
        _esperar_piso(inicio)


def _login(datos: LoginEntrada, request: Request, db: Session) -> dict:
    ip = ip_cliente(request)
    ident = datos.usuario.strip().lower()
    # Pausa por IP (5 fallos en 15 min) y por cuenta (10 fallos desde cualquier IP): frena el robo de claves
    if espera := login_bloqueado(ip, ident):
        raise HTTPException(429, "Demasiados intentos fallidos. Intenta de nuevo en unos minutos.",
                            headers={"Retry-After": str(espera)})
    encontrado = db.scalar(select(Usuario).where(or_(
        func.lower(func.trim(Usuario.correo)) == ident, func.lower(func.trim(Usuario.usuario)) == ident)).limit(1))
    if not verificar_clave(datos.clave, encontrado.clave if encontrado else None):
        registrar_fallo_login(ip, ident)
        raise HTTPException(401, "Usuario o clave incorrectos")
    registrar_exito_login(ip, ident)
    usuario = validar_acceso(cargar_usuario(db, encontrado.id))
    return crear_tokens(usuario.id)


@router.post("/refresh")
def refrescar(datos: RefrescoEntrada, db: Session = Depends(get_db)) -> dict:
    _modo_jwt()
    usuario = validar_acceso(cargar_usuario(db, leer_token(datos.refresh_token, "refresh")))
    return crear_tokens(usuario.id)
