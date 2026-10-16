"""Autenticación y permisos.

Usuarios, acceso a la aplicación, permisos y sucursales vienen del portal web (tablas compartidas):
- acceso: usuario_pivot_app_usuario con id_app = Config.APP_ID
- permisos: usuario_dim_permiso de esa app (CERTIFICACIONES_ADMIN, REGISTROS_EDITAR, ..., CERTIFICACIONES_VER)
- sucursales: usuario_pivot_sucursal_usuario (el administrador ve todas)
"""
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from config import Config
from utils.db import get_db
from utils.modelos import PERMISO_ADMIN, Usuario

# Permisos de edición por módulo (además, CERTIFICACIONES_ADMIN puede todo)
REGISTROS = "REGISTROS_EDITAR"
NC = "NC_EDITAR"
LABORATORIO = "LABORATORIO_EDITAR"
AMBIENTE = "AMBIENTE_EDITAR"

_HASH_FICTICIO = bcrypt.hashpw(b"marcador-tiempo-constante", bcrypt.gensalt(rounds=12))


# ---------- Contraseñas y tokens ----------


def verificar_clave(clave: str, guardada: str | None) -> bool:
    """bcrypt, como LH Inventario. Si el usuario no existe igual se calcula un hash (tiempo constante)."""
    if not guardada or not guardada.startswith(("$2a$", "$2b$", "$2y$")):
        bcrypt.checkpw(clave.encode(), _HASH_FICTICIO)
        return False
    try:
        return bcrypt.checkpw(clave.encode(), guardada.encode())
    except ValueError:
        return False


def _token(usuario_id: str, tipo: str, duracion: timedelta) -> str:
    ahora = datetime.now(timezone.utc)
    datos = {"sub": usuario_id, "tipo": tipo, "app": Config.APP_ID, "iat": ahora, "exp": ahora + duracion}
    return jwt.encode(datos, Config.JWT_SECRET_KEY, algorithm="HS256")


def crear_tokens(usuario_id: str) -> dict:
    return {
        "access_token": _token(usuario_id, "access", timedelta(hours=Config.JWT_HORAS_ACCESO)),
        "refresh_token": _token(usuario_id, "refresh", timedelta(days=Config.JWT_DIAS_REFRESCO)),
        "token_type": "bearer",
    }


def leer_token(token: str, tipo: str) -> str:
    """Devuelve el id del usuario si el token es válido y del tipo pedido."""
    try:
        datos = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Sesión inválida o vencida") from exc
    if datos.get("tipo") != tipo or datos.get("app") != Config.APP_ID:
        raise HTTPException(401, "Sesión inválida o vencida")
    return str(datos["sub"])


def cargar_usuario(db: Session, usuario_id: str) -> Usuario | None:
    return db.scalar(select(Usuario).where(Usuario.id == usuario_id).options(
        selectinload(Usuario.unidades), selectinload(Usuario.permisos), selectinload(Usuario.apps)))


def validar_acceso(usuario: Usuario | None) -> Usuario:
    if usuario is None or not usuario.activo:
        raise HTTPException(403, "Usuario inactivo o inexistente")
    if not usuario.tiene_acceso:
        raise HTTPException(403, "No tienes acceso a esta aplicación")
    return usuario


# ---------- Dependencias ----------


def verificar_clave_demo(x_clave_demo: str | None = Header(default=None)) -> None:
    """Demo publicada: exige la clave de acceso en cada petición (comparación en tiempo constante)."""
    if Config.AUTH_MODO != "demo" or not Config.DEMO_CLAVE:
        return
    if not x_clave_demo:
        raise HTTPException(401, "Ingresa la clave de acceso de la demo")
    if not hmac.compare_digest(x_clave_demo.encode(), Config.DEMO_CLAVE.encode()):
        raise HTTPException(401, "Clave de acceso incorrecta")


def usuario_actual(
    authorization: str | None = Header(default=None),
    x_usuario_demo: str | None = Header(default=None),
    x_clave_demo: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Usuario:
    if Config.AUTH_MODO == "demo":
        verificar_clave_demo(x_clave_demo)
        if not x_usuario_demo:
            raise HTTPException(401, "Falta el usuario de demo")
        usuario_id = x_usuario_demo.strip()
    else:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Falta el token")
        usuario_id = leer_token(authorization.split(" ", 1)[1].strip(), "access")
    return validar_acceso(cargar_usuario(db, usuario_id))


def es_certificaciones(usuario: Usuario) -> bool:
    return usuario.rol == "certificaciones"


def tiene_permiso(usuario: Usuario, permiso: str) -> bool:
    codigos = usuario.codigos_permiso
    return PERMISO_ADMIN in codigos or permiso in codigos


def solo_certificaciones(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if not es_certificaciones(usuario):
        raise HTTPException(403, "Solo el equipo de certificaciones puede hacer esto")
    return usuario


def puede_escribir(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol == "lectura":
        raise HTTPException(403, "Usuario de solo lectura")
    return usuario


def requiere_permiso(permiso: str):
    """Dependencia: el usuario puede editar el módulo (permiso del módulo o administrador)."""
    def dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if not tiene_permiso(usuario, permiso):
            raise HTTPException(403, "No tienes permiso para editar en este módulo")
        return usuario
    return dependencia


def unidades_permitidas(usuario: Usuario) -> set[int] | None:
    """Sucursales que ve el usuario. None = todas (administrador)."""
    if es_certificaciones(usuario):
        return None
    return {u.id for u in usuario.unidades}


def verificar_unidad(usuario: Usuario, unidad_id: int | None) -> None:
    permitidas = unidades_permitidas(usuario)
    if permitidas is None:
        return
    if unidad_id is None or unidad_id not in permitidas:
        raise HTTPException(403, "No tienes acceso a esa sucursal")
