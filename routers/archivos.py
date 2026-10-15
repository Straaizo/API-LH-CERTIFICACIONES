from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config import Config
from utils import almacenamiento
from utils.auth import puede_escribir
from utils.modelos import Usuario

router = APIRouter()

PREFIJOS = {"documentos", "analisis", "evidencias", "registros"}
TIPOS_PERMITIDOS = ("application/pdf", "image/", "application/vnd.openxmlformats", "application/vnd.ms-excel",
                    "application/msword")
MAX_BYTES = 30 * 1024 * 1024


class SolicitudSubida(BaseModel):
    prefijo: str
    nombre_archivo: str = Field(min_length=1, max_length=250)
    tipo_contenido: str


@router.post("/archivos/url-subida")
def url_subida(datos: SolicitudSubida, _: Usuario = Depends(puede_escribir)) -> dict:
    """Paso 1 de la carga: entrega una URL firmada; el navegador sube con PUT directo al almacenamiento."""
    if datos.prefijo not in PREFIJOS:
        raise HTTPException(400, "Prefijo no permitido")
    if not datos.tipo_contenido.startswith(TIPOS_PERMITIDOS):
        raise HTTPException(400, "Tipo de archivo no permitido (PDF, imagen, Excel o Word)")
    clave = almacenamiento.nueva_clave(datos.prefijo, datos.nombre_archivo)
    return {"clave": clave, "url": almacenamiento.url_subida(clave, datos.tipo_contenido)}


# ---- Emulación local de URLs firmadas (solo ALMACENAMIENTO=local) ----

def _validar_local(metodo: str, clave: str, expira: int, firma: str) -> None:
    if Config.ALMACENAMIENTO != "local":
        raise HTTPException(404)
    if not almacenamiento.verificar_firma_local(metodo, clave, expira, firma):
        raise HTTPException(403, "URL vencida o inválida")


@router.put("/archivos-locales/{clave:path}", include_in_schema=False)
async def subir_local(clave: str, expira: int, firma: str, request: Request) -> dict:
    _validar_local("PUT", clave, expira, firma)
    contenido = await request.body()
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "Archivo demasiado grande")
    almacenamiento.escribir_local(clave, contenido)
    return {"ok": True}


@router.get("/archivos-locales/{clave:path}", include_in_schema=False)
def bajar_local(clave: str, expira: int, firma: str) -> FileResponse:
    _validar_local("GET", clave, expira, firma)
    ruta = (almacenamiento.DIR_LOCAL / clave).resolve()
    if almacenamiento.DIR_LOCAL.resolve() not in ruta.parents or not ruta.is_file():
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(ruta, filename=ruta.name)
