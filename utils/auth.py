import hmac

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from config import Config
from utils.db import get_db
from utils.modelos import Usuario

_firebase_listo = False


def _verificar_token_firebase(token: str) -> str:
    """Devuelve el email del token de Firebase Authentication."""
    global _firebase_listo
    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not _firebase_listo:
        firebase_admin.initialize_app(options={"projectId": Config.GCP_PROJECT_ID} if Config.GCP_PROJECT_ID else None)
        _firebase_listo = True
    try:
        datos = fb_auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(401, "Token inválido o vencido") from exc
    email = datos.get("email")
    if not email:
        raise HTTPException(401, "El token no trae email")
    return email.lower()


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
    consulta = select(Usuario).options(selectinload(Usuario.unidades))
    if Config.AUTH_MODO == "demo":
        verificar_clave_demo(x_clave_demo)
        if not x_usuario_demo or not x_usuario_demo.isdigit():
            raise HTTPException(401, "Falta el usuario de demo")
        usuario = db.scalar(consulta.where(Usuario.id == int(x_usuario_demo)))
    else:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Falta el token")
        email = _verificar_token_firebase(authorization.split(" ", 1)[1])
        usuario = db.scalar(consulta.where(Usuario.email == email))
    if not usuario or not usuario.activo:
        raise HTTPException(403, "Usuario sin acceso a la aplicación")
    return usuario


def es_certificaciones(usuario: Usuario) -> bool:
    return usuario.rol == "certificaciones"


def solo_certificaciones(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if not es_certificaciones(usuario):
        raise HTTPException(403, "Solo el equipo de certificaciones puede hacer esto")
    return usuario


def puede_escribir(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol == "lectura":
        raise HTTPException(403, "Usuario de solo lectura")
    return usuario


def unidades_permitidas(usuario: Usuario) -> set[int] | None:
    """None = todas las unidades."""
    if usuario.rol in ("certificaciones", "lectura"):
        return None
    return {u.id for u in usuario.unidades}


def verificar_unidad(usuario: Usuario, unidad_id: int | None) -> None:
    permitidas = unidades_permitidas(usuario)
    if permitidas is None:
        return
    if unidad_id is None or unidad_id not in permitidas:
        raise HTTPException(403, "No tienes acceso a esa sucursal")
