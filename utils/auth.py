"""Autenticación y permisos.

Usuarios, acceso a la aplicación, permisos y sucursales vienen del portal web (tablas compartidas):
- acceso: usuario_pivot_app_usuario con id_app = Config.APP_ID
- permisos: usuario_dim_permiso de esa app (CERTIFICACIONES_ADMIN, REGISTROS_EDITAR, ..., CERTIFICACIONES_VER,
  CERTIFICACIONES_HISTORIAL)
- sucursales: usuario_pivot_sucursal_usuario (todos, incluido el administrador, ven solo las suyas)
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
from utils.modelos import PERMISO_ADMIN, PERMISO_HISTORIAL, PERMISO_VER, Usuario

# Permisos por acción (CERTIFICACIONES_ADMIN puede todo). Contrato completo en docs/requerimientos.md (Permisos).
REGISTROS = "REGISTROS_EDITAR"            # llenar y enviar registros
REGISTROS_REVISAR = "REGISTROS_REVISAR"   # crear y asignar registros, corregir, aprobar o rechazar
PLANTILLAS = "PLANTILLAS_EDITAR"          # crear, importar desde Word y editar plantillas
DOCUMENTOS = "DOCUMENTOS_EDITAR"          # subir documentos fijos y versiones nuevas
NC = "NC_EDITAR"                          # plan de acción y evidencia
NC_REVISAR = "NC_REVISAR"                 # devolver, cerrar y reasignar no conformidades
LABORATORIO = "LABORATORIO_EDITAR"        # análisis y residuos (MRL)
LABORATORIO_ASOEX = "LABORATORIO_ASOEX"   # actualizar ASOEX y la carta de destino
AMBIENTE = "AMBIENTE_EDITAR"              # consumos de combustible
AMBIENTE_TODOS = "AMBIENTE_TODOS"        # ver y registrar todos los conceptos (electricidad, fertilizantes…)
AMBIENTE_RECICLAJE = "AMBIENTE_RECICLAJE" # registrar reciclaje
AUDITORIAS = "AUDITORIAS_EDITAR"          # planificar, responder y emitir auditorías internas
AUDITORIAS_IMPORTAR = "AUDITORIAS_IMPORTAR"  # importar auditorías internas hechas en Excel (BRCGS)
AUDITORIAS_EXTERNAS = "AUDITORIAS_EXTERNAS_EDITAR"  # subir informes externos
IMPORTAR = "IMPORTAR_PLANILLAS"           # Normas: cargar checklist oficiales y sus versiones

# Módulos que se ven: con cualquiera de sus permisos. CERTIFICACIONES_ADMIN ve todos; CERTIFICACIONES_VER (auditores,
# solo lectura) ve todos menos Importar, que es una acción.
PERMISOS_MODULO: dict[str, set[str]] = {
    "REGISTROS": {"REGISTROS_VER", REGISTROS, REGISTROS_REVISAR},
    "DOCUMENTOS": {"DOCUMENTOS_VER", DOCUMENTOS},
    "PLANTILLAS": {"PLANTILLAS_VER", PLANTILLAS},
    "VENCIMIENTOS": {"VENCIMIENTOS_VER"},
    "LABORATORIO": {"LABORATORIO_VER", LABORATORIO, LABORATORIO_ASOEX},
    "AUDITORIAS": {"AUDITORIAS_VER", AUDITORIAS, AUDITORIAS_IMPORTAR},
    "AUDITORIAS_EXTERNAS": {"AUDITORIAS_EXTERNAS_VER", AUDITORIAS_EXTERNAS},
    "NC": {"NC_VER", NC, NC_REVISAR},
    "AMBIENTE": {"AMBIENTE_VER", AMBIENTE, AMBIENTE_TODOS, AMBIENTE_RECICLAJE},
    "IMPORTAR": {IMPORTAR},
}
MODULOS = tuple(PERMISOS_MODULO)
SOLO_ADMIN_O_PERMISO = {"IMPORTAR"}  # CERTIFICACIONES_VER no los ve

_HASH_FICTICIO = bcrypt.hashpw(b"marcador-tiempo-constante", bcrypt.gensalt(rounds=12))


# ---------- Contraseñas y tokens ----------


def verificar_clave(clave: str, guardada: str | None) -> bool:
    """bcrypt, como LH Inventario. Si el usuario no existe igual se calcula un hash (tiempo constante).

    bcrypt solo usa los primeros 72 bytes: se recortan siempre igual, para que una clave larga no falle distinto
    (ni más rápido) según exista o no el usuario.
    """
    entrada = clave.encode()[:72]
    if not guardada or not guardada.startswith(("$2a$", "$2b$", "$2y$")):
        bcrypt.checkpw(entrada, _HASH_FICTICIO)
        return False
    try:
        return bcrypt.checkpw(entrada, guardada.encode())
    except ValueError:
        bcrypt.checkpw(entrada, _HASH_FICTICIO)
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
    usuario = validar_acceso(cargar_usuario(db, usuario_id))
    # created_by / updated_by de lo que se guarde en esta petición (ver modelos._auditar)
    db.info["usuario_id"] = usuario.id
    return usuario


def es_certificaciones(usuario: Usuario) -> bool:
    return usuario.rol == "certificaciones"


def tiene_permiso(usuario: Usuario, permiso: str) -> bool:
    codigos = usuario.codigos_permiso
    return PERMISO_ADMIN in codigos or permiso in codigos


def puede_ver(usuario: Usuario, modulo: str) -> bool:
    codigos = usuario.codigos_permiso
    if PERMISO_ADMIN in codigos or (PERMISO_VER in codigos and modulo not in SOLO_ADMIN_O_PERMISO):
        return True
    return bool(codigos & PERMISOS_MODULO.get(modulo, set()))


def ve_todo(usuario: Usuario) -> bool:
    return bool(usuario.codigos_permiso & {PERMISO_ADMIN, PERMISO_VER})


def modulos_visibles(usuario: Usuario) -> list[str]:
    return [m for m in MODULOS if puede_ver(usuario, m)]


def requiere_ver(*modulos: str):
    """Dependencia: el usuario puede ver todos los módulos indicados (algún permiso del módulo, o ve todo)."""
    def dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if not all(puede_ver(usuario, m) for m in modulos):
            raise HTTPException(403, "No tienes permiso para ver este módulo")
        return usuario
    return dependencia


def solo_certificaciones(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if not es_certificaciones(usuario):
        raise HTTPException(403, "Solo el equipo de certificaciones puede hacer esto")
    return usuario


def solo_ve_todo(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if not ve_todo(usuario):
        raise HTTPException(403, "Solo para quien ve todo Certificaciones")
    return usuario


def solo_historial(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if PERMISO_HISTORIAL not in usuario.codigos_permiso:
        raise HTTPException(403, "No tienes permiso para ver el historial de cambios")
    return usuario


def puede_escribir(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol == "lectura":
        raise HTTPException(403, "Usuario de solo lectura")
    return usuario


def requiere_permiso(*permisos: str):
    """Dependencia: el usuario tiene alguno de los permisos de acción indicados (o es administrador)."""
    def dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if not any(tiene_permiso(usuario, p) for p in permisos):
            raise HTTPException(403, "No tienes permiso para hacer esto")
        return usuario
    return dependencia


def requiere_ver_alguno(*modulos: str):
    """Dependencia: el usuario puede ver al menos uno de los módulos indicados."""
    def dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if not any(puede_ver(usuario, m) for m in modulos):
            raise HTTPException(403, "No tienes permiso para ver este módulo")
        return usuario
    return dependencia


def unidades_permitidas(usuario: Usuario) -> set[int] | None:
    """Sucursales que ve el usuario: solo las habilitadas en el portal web, también para el administrador."""
    return {u.id for u in usuario.unidades}


def unidad_para_descarga(usuario: Usuario, unidad_id: int | None) -> int:
    """Toda descarga corresponde a una sucursal: la indicada, o la única que tiene el usuario."""
    if unidad_id is not None:
        verificar_unidad(usuario, unidad_id)
        return unidad_id
    permitidas = unidades_permitidas(usuario)
    if len(permitidas) == 1:
        return next(iter(permitidas))
    raise HTTPException(400, "Elige a qué sucursal corresponde la descarga" if permitidas
                        else "No tienes sucursales habilitadas en el portal web")


def verificar_unidad(usuario: Usuario, unidad_id: int | None) -> None:
    permitidas = unidades_permitidas(usuario)
    if permitidas is None:
        return
    if unidad_id is None or unidad_id not in permitidas:
        raise HTTPException(403, "No tienes acceso a esa sucursal")
