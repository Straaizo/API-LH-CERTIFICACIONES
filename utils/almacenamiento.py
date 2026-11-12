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

# Subir: 15 min (una foto de 10 MB con mala señal en terreno puede tardar). Bajar: 5 min, porque una URL de descarga se puede
# reusar mientras está vigente y cada descarga es tráfico de salida que se cobra
MINUTOS_VALIDEZ = 15
MINUTOS_DESCARGA = 5
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


_credenciales = None


def _firma_iam() -> dict:
    """En Cloud Run no hay archivo de llave: la URL se firma con la cuenta de servicio vía IAM (signBlob).

    Requiere que la cuenta de servicio de Cloud Run tenga roles/iam.serviceAccountTokenCreator sobre sí misma.
    En local, con una llave de cuenta de servicio, no hace falta y se firma con ella.
    """
    global _credenciales
    import google.auth
    from google.auth.transport.requests import Request

    if _credenciales is None:
        _credenciales, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if getattr(_credenciales, "signer", None):
        return {}
    # El token dura ~1 h: se renueva solo cuando venció, no en cada URL
    if not _credenciales.valid:
        _credenciales.refresh(Request())
    return {"service_account_email": _credenciales.service_account_email, "access_token": _credenciales.token}


def _url_local(metodo: str, clave: str) -> str:
    expira = int(time.time()) + MINUTOS_VALIDEZ * 60
    firma = _firma_local(metodo, clave, expira)
    return f"{Config.URL_PUBLICA_API}/api/archivos-locales/{quote(clave)}?expira={expira}&firma={firma}"


def url_subida(clave: str, tipo_contenido: str, max_bytes: int) -> tuple[str, dict[str, str]]:
    """URL firmada para subir y las cabeceras que el navegador debe enviar con ella.

    En Cloud Storage el tamaño máximo va firmado (x-goog-content-length-range): Google rechaza un archivo más
    grande aunque alguien use la URL fuera de la aplicación. El bucket debe permitir esa cabecera en su CORS.
    """
    if Config.ALMACENAMIENTO == "gcs":
        cabeceras = {"x-goog-content-length-range": f"0,{max_bytes}"}
        url = _bucket().blob(clave).generate_signed_url(
            version="v4", expiration=timedelta(minutes=MINUTOS_VALIDEZ), method="PUT", content_type=tipo_contenido,
            headers=cabeceras, **_firma_iam())
        return url, cabeceras
    return _url_local("PUT", clave), {}


def url_descarga(clave: str, nombre: str | None = None) -> str:
    if Config.ALMACENAMIENTO == "gcs":
        disposicion = f'attachment; filename="{nombre_archivo_seguro(nombre)}"' if nombre else None
        return _bucket().blob(clave).generate_signed_url(
            version="v4", expiration=timedelta(minutes=MINUTOS_DESCARGA), method="GET",
            response_disposition=disposicion, **_firma_iam())
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
