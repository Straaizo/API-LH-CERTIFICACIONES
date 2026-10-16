from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class CertificadoEntrada(BaseModel):
    """Ficha de un certificado de protocolo (categoría Certificados). El vencimiento es el de la versión."""
    protocolo_id: int
    numero: str | None = Field(default=None, max_length=40)
    norma_version: str | None = Field(default=None, max_length=40)
    entidad_certificadora: str | None = Field(default=None, max_length=120)
    vigente_desde: date | None = None
    fecha_auditoria: date | None = None
    resultado: str | None = Field(default=None, max_length=120)  # puntaje o grado
    unidad_ids: list[int] = []
    productos: list[str] = []


class VersionEntrada(BaseModel):
    archivo_key: str
    nombre_archivo: str
    tipo_contenido: str | None = None
    version_texto: str | None = Field(default=None, max_length=20)
    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None
    certificado: CertificadoEntrada | None = None


class ArchivoSubidoEntrada(BaseModel):
    archivo_key: str
    nombre_archivo: str


class DocumentoEntrada(BaseModel):
    categoria_id: int
    empresa_id: int
    seccion: Literal["campo", "planta", "empresarial"]
    titulo: str = Field(min_length=2, max_length=250)
    codigo: str | None = Field(default=None, max_length=40)
    version: VersionEntrada


class DocumentoCambios(BaseModel):
    titulo: str | None = Field(default=None, min_length=2, max_length=250)
    codigo: str | None = Field(default=None, max_length=40)


class CapacitacionEntrada(BaseModel):
    unidad_id: int
    tema: str = Field(min_length=2, max_length=250)
    fecha: date
    relator: str | None = None
    asistentes: list[str] = []
    vigente_hasta: date | None = None
    documento_id: int | None = None
