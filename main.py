"""
main.py — Entry point de la API FastAPI (estructura de API-BASE-LH).

Para levantar el servidor:
    python run_dev.py          ← script con apertura automática del navegador
    python main.py             ← uvicorn directo

Documentación interactiva disponible en:
    http://localhost:8080/docs        ← Swagger UI personalizado
    http://localhost:8080/redoc       ← ReDoc
    http://localhost:8080/openapi.json ← Schema JSON crudo
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from config import Config
from routers import (
    ambiente, archivos, auditorias, auditorias_externas, auth, carpeta, catalogos, documentos, laboratorio, no_conformidades, registros, tablero,
)
from utils.db import SessionLocal
from utils.docs_html import get_docs_html
from utils.proteccion import middleware_proteccion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VERSION = "0.1.0"
if Config.LOGIN_LOCAL_SIN_APP:
    logger.warning("LOGIN_LOCAL_SIN_APP=1: todo usuario activo entra como ADMIN sin revisar acceso a la app. Solo local.")
EN_PRODUCCION = Config.ENTORNO == "produccion"
# La demo publicada (con clave) tampoco muestra la documentación de la API
SIN_DOCS = EN_PRODUCCION or bool(Config.DEMO_CLAVE)


# ── Aplicación FastAPI ────────────────────────────────────────────────────────

app = FastAPI(
    title="API Certificaciones LH y VS",
    version=VERSION,
    description=" ",   # espacio intencional — el panel se inyecta via JS
    docs_url=None,     # se reemplaza con endpoint custom /docs
    redoc_url=None if SIN_DOCS else "/redoc",
    openapi_url=None if SIN_DOCS else "/openapi.json",
    openapi_tags=[
        {"name": "⚙️ Sistema",          "description": "Estado y monitoreo de la API"},
        {"name": "🗄️ Base de Datos",    "description": "Verificación de conexión"},
        {"name": "🔐 Sesión",            "description": "Inicio de sesión con usuario o correo + clave (JWT)"},
        {"name": "📍 Catálogos",         "description": "Sucursales, temporadas, protocolos, usuarios"},
        {"name": "📎 Archivos",          "description": "URLs firmadas para subir y bajar archivos"},
        {"name": "📄 Documentos fijos",  "description": "Documentos subidos: versiones, revisión, capacitaciones y vencimientos"},
        {"name": "📝 Registros",         "description": "Plantillas de certificaciones, llenado por encargados, aprobación y descarga Word/PDF"},
        {"name": "🧪 Laboratorio",       "description": "Análisis y comparación con límites"},
        {"name": "✅ Auditorías",        "description": "Checklist, programa anual e importación de planillas"},
        {"name": "📑 Auditorías externas", "description": "Informes de la certificadora: resumen leído del PDF, versiones y descarga"},
        {"name": "⚠️ No conformidades",  "description": "Levantamientos, cierre y reincidencias"},
        {"name": "🌿 Medio ambiente",    "description": "Huella de carbono y reciclaje"},
        {"name": "📊 Tablero y bitácora", "description": "Resumen de inicio y registro de cambios"},
        {"name": "🗂️ Carpeta auditor",   "description": "ZIP con evidencias por protocolo, empresa, sucursal y temporada"},
    ],
)

# ── Archivos estáticos (logo, etc.) ──────────────────────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# ── Middleware de seguridad ───────────────────────────────────────────────────
# Orden: el último que se registra es el más externo. CORS va último para que también los 429/413 lleguen
# al navegador con sus cabeceras (si no, el navegador muestra un error de red en vez del mensaje).

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["X-XSS-Protection"]        = "1; mode=block"
    response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]      = "geolocation=(), microphone=(), camera=(), payment=()"
    response.headers["Server"]                  = "LH-API"
    if EN_PRODUCCION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response


# Límite de peticiones por IP, listas de IPs y tamaño máximo (utils/proteccion.py)
app.middleware("http")(middleware_proteccion)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Solo orígenes permitidos (ORIGENES_PERMITIDOS en .env / Secret Manager)
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.ORIGENES_PERMITIDOS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Usuario-Demo", "X-Clave-Demo"],
    expose_headers=["Content-Type", "Content-Disposition", "Retry-After"],
    max_age=3600,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Error no manejado en {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Error interno del servidor"})


# ── Routers ───────────────────────────────────────────────────────────────────
# Para registrar un nuevo módulo, añadir una línea a esta lista

ROUTERS = [
    (auth,             "🔐 Sesión"),
    (catalogos,        "📍 Catálogos"),
    (archivos,         "📎 Archivos"),
    (documentos,       "📄 Documentos fijos"),
    (registros,        "📝 Registros"),
    (laboratorio,      "🧪 Laboratorio"),
    (auditorias,       "✅ Auditorías"),
    (auditorias_externas, "📑 Auditorías externas"),
    (no_conformidades, "⚠️ No conformidades"),
    (ambiente,         "🌿 Medio ambiente"),
    (tablero,          "📊 Tablero y bitácora"),
    (carpeta,          "🗂️ Carpeta auditor"),
]
for modulo, tag in ROUTERS:
    app.include_router(modulo.router, prefix="/api", tags=[tag])


# ── Endpoints de sistema (ocultos en Swagger, visibles en el panel de estado) ─

@app.get("/api/", tags=["⚙️ Sistema"], summary="Estado de la API")
def index():
    # En producción no se informa cómo está configurada (menos pistas para un atacante)
    if EN_PRODUCCION:
        return {"message": "API Certificaciones activa"}
    return {"message": "API Certificaciones activa", "version": VERSION, "entorno": Config.ENTORNO,
            "auth": Config.AUTH_MODO, "almacenamiento": Config.ALMACENAMIENTO}


@app.get("/api/db/ping", tags=["🗄️ Base de Datos"], summary="Verificar conexión")
def ping_db():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "message": "Conexión exitosa" if EN_PRODUCCION else f"Conexión exitosa ({Config.DB_MOTOR})"}
    except Exception as exc:
        logger.error(f"Ping BD falló: {exc}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Sin conexión"})


# ── Documentación personalizada ───────────────────────────────────────────────

if not SIN_DOCS:
    @app.get("/docs", include_in_schema=False)
    def custom_docs():
        return HTMLResponse(content=get_docs_html())


# ── Inicio directo ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=Config.DEV_PORT, reload=True)
