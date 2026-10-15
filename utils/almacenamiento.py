"""Archivos: el navegador sube y descarga directo con URLs firmadas.

- gcs: Cloud Storage (URL firmada v4).
- local: emulación en disco (privado/archivos) para la demo, con firma HMAC y vencimiento.
"""
import hashlib
import hmac
import time
import uuid
from urllib.parse import quote
from datetime import timedelta
from pathlib import Path

from config import Config
from utils.texto import nombre_archivo_seguro

MINUTOS_VALIDEZ = 15
DIR_LOCAL: Path = Config.PRIVADO_DIR / "archivos"


def nueva_clave(prefijo: str, nombre_archivo: str) -> str:
    return f"{prefijo}/{uuid.uuid4().hex}/{nombre_archivo_seguro(nombre_archivo)}"


def _firma_local(metodo: str, clave: str, expira: int) -> str:
    mensaje = f"{metodo}:{clave}:{expira}".encode()
    return hmac.new(Config.CLAVE_FIRMA_LOCAL.encode(), mensaje, hashlib.sha256).hexdigest()


def verificar_firma_local(metodo: str, clave: str, expira: int, firma: str) -> bool:
    if expira < time.time():
        return False
    return hmac.compare_digest(_firma_local(metodo, clave, expira), firma)


def _bucket():
    from google.cloud import storage
    return storage.Client(project=Config.GCP_PROJECT_ID or None).bucket(Config.BUCKET_DOCUMENTOS)


def _url_local(metodo: str, clave: str) -> str:
    expira = int(time.time()) + MINUTOS_VALIDEZ * 60
    firma = _firma_local(metodo, clave, expira)
    return f"{Config.URL_PUBLICA_API}/api/archivos-locales/{quote(clave)}?expira={expira}&firma={firma}"


def url_subida(clave: str, tipo_contenido: str) -> str:
    if Config.ALMACENAMIENTO == "gcs":
        return _bucket().blob(clave).generate_signed_url(
            version="v4", expiration=timedelta(minutes=MINUTOS_VALIDEZ), method="PUT", content_type=tipo_contenido)
    return _url_local("PUT", clave)


def url_descarga(clave: str, nombre: str | None = None) -> str:
    if Config.ALMACENAMIENTO == "gcs":
        disposicion = f'attachment; filename="{nombre_archivo_seguro(nombre)}"' if nombre else None
        return _bucket().blob(clave).generate_signed_url(
            version="v4", expiration=timedelta(minutes=MINUTOS_VALIDEZ), method="GET",
            response_disposition=disposicion)
    return _url_local("GET", clave)


def existe(clave: str) -> bool:
    if Config.ALMACENAMIENTO == "gcs":
        return _bucket().blob(clave).exists()
    return (DIR_LOCAL / clave).is_file()


def leer(clave: str) -> bytes:
    """Lectura del lado servidor (solo para armar el ZIP del auditor)."""
    if Config.ALMACENAMIENTO == "gcs":
        return _bucket().blob(clave).download_as_bytes()
    return (DIR_LOCAL / clave).read_bytes()


def escribir_local(clave: str, contenido: bytes) -> None:
    ruta = (DIR_LOCAL / clave).resolve()
    if DIR_LOCAL.resolve() not in ruta.parents:
        raise ValueError("Ruta inválida")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)


def escribir(clave: str, contenido: bytes, tipo_contenido: str = "application/octet-stream") -> None:
    """Escritura del lado servidor (logos de plantillas importadas)."""
    if Config.ALMACENAMIENTO == "gcs":
        _bucket().blob(clave).upload_from_string(contenido, content_type=tipo_contenido)
    else:
        escribir_local(clave, contenido)
