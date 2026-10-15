"""Modelo de datos. Portable entre PostgreSQL, MySQL y SQLite (demo)."""
from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from utils.db import Base
from utils.hora import ahora

# ---------- Sitios ----------


class Empresa(Base):
    __tablename__ = "certificaciones_dim_empresa"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ubicaciones: Mapped[list["Ubicacion"]] = relationship(back_populates="empresa")


class Ubicacion(Base):
    __tablename__ = "certificaciones_dim_ubicacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_empresa.id"))
    nombre: Mapped[str] = mapped_column(String(120))
    empresa: Mapped[Empresa] = relationship(back_populates="ubicaciones")
    unidades: Mapped[list["Unidad"]] = relationship(back_populates="ubicacion")


class Unidad(Base):
    """Campo o planta de una ubicación. El nombre se arma: 'Planta Chocalán'."""
    __tablename__ = "certificaciones_dim_unidad"
    __table_args__ = (UniqueConstraint("ubicacion_id", "tipo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ubicacion_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_ubicacion.id"))
    tipo: Mapped[str] = mapped_column(String(10))  # campo | planta
    ubicacion: Mapped[Ubicacion] = relationship(back_populates="unidades")
    areas: Mapped[list["Area"]] = relationship(back_populates="unidad")

    @property
    def nombre(self) -> str:
        return f"{self.tipo.capitalize()} {self.ubicacion.nombre}"

    @property
    def empresa_id(self) -> int:
        return self.ubicacion.empresa_id


class Area(Base):
    """Área de planta o cuartel de campo."""
    __tablename__ = "certificaciones_dim_area"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))
    nombre: Mapped[str] = mapped_column(String(120))
    unidad: Mapped[Unidad] = relationship(back_populates="areas")


class Temporada(Base):
    __tablename__ = "certificaciones_dim_temporada"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(20), unique=True)
    inicio: Mapped[date] = mapped_column(Date)
    fin: Mapped[date] = mapped_column(Date)


# ---------- Usuarios ----------

usuario_unidades = Table(
    "certificaciones_pivot_usuario_unidad", Base.metadata,
    Column("usuario_id", ForeignKey("certificaciones_dim_usuario.id"), primary_key=True),
    Column("unidad_id", ForeignKey("certificaciones_dim_unidad.id"), primary_key=True),
)


class Usuario(Base):
    __tablename__ = "certificaciones_dim_usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    rol: Mapped[str] = mapped_column(String(20))  # certificaciones | encargado | lectura
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    unidades: Mapped[list[Unidad]] = relationship(secondary=usuario_unidades)


# ---------- Protocolos y requisitos ----------


protocolo_unidades = Table(
    "certificaciones_pivot_protocolo_unidad", Base.metadata,
    Column("protocolo_id", ForeignKey("certificaciones_dim_protocolo.id"), primary_key=True),
    Column("unidad_id", ForeignKey("certificaciones_dim_unidad.id"), primary_key=True),
)


class Protocolo(Base):
    __tablename__ = "certificaciones_dim_protocolo"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(10))  # campo | planta | ambos
    versiones: Mapped[list["VersionNorma"]] = relationship(back_populates="protocolo")
    # Si tiene unidades, solo aplica a ellas (p. ej. PrimusGFS en campos con packing)
    unidades: Mapped[list["Unidad"]] = relationship(secondary=protocolo_unidades)

    def aplica_a(self, unidad: "Unidad") -> bool:
        if self.unidades:
            return any(u.id == unidad.id for u in self.unidades)
        return self.ambito in ("ambos", unidad.tipo)


class VersionNorma(Base):
    __tablename__ = "certificaciones_dim_versionnorma"
    __table_args__ = (UniqueConstraint("protocolo_id", "nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    protocolo_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_protocolo.id"))
    nombre: Mapped[str] = mapped_column(String(60))
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    # Cuándo y desde qué archivo se cargó (las versiones nunca se sobrescriben: cada actualización es una versión nueva)
    cargada_en: Mapped[datetime | None] = mapped_column(DateTime, default=ahora)
    archivo: Mapped[str | None] = mapped_column(String(250))
    # Cláusulas o secciones de la norma [{codigo, titulo}], para medir la cobertura del programa anual
    secciones: Mapped[list | None] = mapped_column(JSON)
    protocolo: Mapped[Protocolo] = relationship(back_populates="versiones")
    requisitos: Mapped[list["Requisito"]] = relationship(back_populates="version", order_by="Requisito.orden")


class Requisito(Base):
    __tablename__ = "certificaciones_dim_requisito"
    __table_args__ = (UniqueConstraint("version_id", "codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_versionnorma.id"))
    codigo: Mapped[str] = mapped_column(String(40))
    seccion: Mapped[str] = mapped_column(String(40))  # cláusula o sección: "4.1", "FV 20"
    seccion_titulo: Mapped[str | None] = mapped_column(String(300))
    texto: Mapped[str] = mapped_column(Text)
    nivel: Mapped[str | None] = mapped_column(String(30))  # mayor | menor | recomendacion | fundamental
    orden: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[VersionNorma] = relationship(back_populates="requisitos")


certificacion_unidades = Table(
    "certificaciones_pivot_certificacion_unidad", Base.metadata,
    Column("certificacion_id", ForeignKey("certificaciones_fact_certificacion.id"), primary_key=True),
    Column("unidad_id", ForeignKey("certificaciones_dim_unidad.id"), primary_key=True),
)


class Certificacion(Base):
    """Certificado de protocolo obtenido. Puede cubrir varias unidades (multisitio)."""
    __tablename__ = "certificaciones_fact_certificacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    protocolo_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_protocolo.id"))
    empresa_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_empresa.id"))
    temporada_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    entidad_certificadora: Mapped[str | None] = mapped_column(String(120))
    fecha_auditoria: Mapped[date | None] = mapped_column(Date)
    resultado: Mapped[str | None] = mapped_column(String(120))
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_documento.id"))
    # Ficha del certificado subido como documento fijo: una por versión (renovar = versión nueva)
    documento_version_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_fact_documentoversion.id"), unique=True)
    numero: Mapped[str | None] = mapped_column(String(40))  # N° de certificado o LoC
    norma_version: Mapped[str | None] = mapped_column(String(40))  # 6.0-GFS_AUG24, v13_FEB25
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    productos: Mapped[list | None] = mapped_column(JSON)
    protocolo: Mapped[Protocolo] = relationship()
    unidades: Mapped[list[Unidad]] = relationship(secondary=certificacion_unidades)


# ---------- Documentos ----------


class CategoriaDocumento(Base):
    __tablename__ = "certificaciones_dim_categoriadocumento"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(10), default="ambos")  # campo | planta | ambos
    requiere_vencimiento: Mapped[bool] = mapped_column(Boolean, default=False)
    requiere_codigo: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)


documento_protocolos = Table(
    "certificaciones_pivot_documento_protocolo", Base.metadata,
    Column("documento_id", ForeignKey("certificaciones_dim_documento.id"), primary_key=True),
    Column("protocolo_id", ForeignKey("certificaciones_dim_protocolo.id"), primary_key=True),
)

documento_requisitos = Table(
    "certificaciones_pivot_documento_requisito", Base.metadata,
    Column("documento_id", ForeignKey("certificaciones_dim_documento.id"), primary_key=True),
    Column("requisito_id", ForeignKey("certificaciones_dim_requisito.id"), primary_key=True),
)


class Documento(Base):
    __tablename__ = "certificaciones_dim_documento"
    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_categoriadocumento.id"))
    empresa_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_empresa.id"))
    # Documentos fijos: sección campo | planta | empresarial (códigos OC). No van por sucursal.
    seccion: Mapped[str] = mapped_column(String(12), default="empresarial")
    unidad_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))  # null = nivel empresa
    temporada_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    titulo: Mapped[str] = mapped_column(String(250))
    codigo: Mapped[str | None] = mapped_column(String(40), index=True)  # P OC CE 29, DPL 23
    responsable: Mapped[str | None] = mapped_column(String(120))
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    categoria: Mapped[CategoriaDocumento] = relationship()
    unidad: Mapped[Unidad | None] = relationship()
    protocolos: Mapped[list[Protocolo]] = relationship(secondary=documento_protocolos)
    requisitos: Mapped[list[Requisito]] = relationship(secondary=documento_requisitos)
    versiones: Mapped[list["DocumentoVersion"]] = relationship(
        back_populates="documento", order_by="DocumentoVersion.numero")


class DocumentoVersion(Base):
    """Versión de un documento. Una versión aprobada nunca se modifica ni se borra."""
    __tablename__ = "certificaciones_fact_documentoversion"
    __table_args__ = (UniqueConstraint("documento_id", "numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_documento.id"))
    numero: Mapped[int] = mapped_column(Integer)
    archivo_key: Mapped[str | None] = mapped_column(String(400))
    nombre_archivo: Mapped[str | None] = mapped_column(String(250))
    tipo_contenido: Mapped[str | None] = mapped_column(String(100))
    version_texto: Mapped[str | None] = mapped_column(String(20))  # versión del procedimiento: "03"
    fecha_emision: Mapped[date | None] = mapped_column(Date)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | aprobado | rechazado
    observacion: Mapped[str | None] = mapped_column(Text)
    subido_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    revisado_por_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime)
    documento: Mapped[Documento] = relationship(back_populates="versiones")
    subido_por: Mapped[Usuario] = relationship(foreign_keys=[subido_por_id])
    certificacion: Mapped[Certificacion | None] = relationship(foreign_keys="Certificacion.documento_version_id")


class Capacitacion(Base):
    __tablename__ = "certificaciones_fact_capacitacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))
    temporada_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    tema: Mapped[str] = mapped_column(String(250))
    fecha: Mapped[date] = mapped_column(Date)
    relator: Mapped[str | None] = mapped_column(String(120))
    asistentes: Mapped[list | None] = mapped_column(JSON)  # nombres o RUT (tabla de trabajadores por confirmar)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_documento.id"))
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    unidad: Mapped[Unidad] = relationship()


# ---------- Registros (documentos no fijos, llenados en la aplicación) ----------


class PlantillaRegistro(Base):
    """Plantilla que define certificaciones; desde ella se generan registros para llenar.

    campos: [{id, etiqueta, tipo, obligatorio, columnas?: [{id, etiqueta, tipo}]}]
    tipos: texto | numero | fecha | si_no | tabla | foto | archivo | firma
    """
    __tablename__ = "certificaciones_dim_plantillaregistro"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str | None] = mapped_column(String(40), unique=True)  # R-OC-CE-01: el mismo del documento
    version: Mapped[str] = mapped_column(String(10), default="01")
    # Base del documento: encargado, frecuencia, orientacion, creado_por, aprobado_por, fecha_revision,
    # direccion, notas, logo_clave
    formato: Mapped[dict] = mapped_column(JSON, default=dict)
    # Word original del formulario: la descarga escribe los datos sobre él
    word_clave: Mapped[str | None] = mapped_column(String(400))
    nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str | None] = mapped_column(Text)
    ambito: Mapped[str] = mapped_column(String(10), default="campo")  # campo | planta | ambos
    campos: Mapped[list] = mapped_column(JSON, default=list)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Registro(Base):
    """Registro generado desde una plantilla. Guarda una copia de los campos: editar la plantilla no lo altera."""
    __tablename__ = "certificaciones_fact_registro"
    id: Mapped[int] = mapped_column(primary_key=True)
    plantilla_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_plantillaregistro.id"))
    unidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))
    temporada_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    titulo: Mapped[str] = mapped_column(String(250))
    # Copia de la plantilla al crear el registro
    codigo: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[str | None] = mapped_column(String(10))
    formato: Mapped[dict] = mapped_column(JSON, default=dict)
    word_clave: Mapped[str | None] = mapped_column(String(400))
    campos: Mapped[list] = mapped_column(JSON, default=list)
    valores: Mapped[dict] = mapped_column(JSON, default=dict)
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    # Última vez que alguien del campo (no certificaciones) guardó o envió: "fecha de revisión"
    revision_campo_en: Mapped[datetime | None] = mapped_column(DateTime)
    # borrador | en_revision | aprobado | rechazado
    estado: Mapped[str] = mapped_column(String(20), default="borrador")
    observacion: Mapped[str | None] = mapped_column(Text)
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime)
    actualizado_por_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime)
    aprobado_por_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime)
    plantilla: Mapped[PlantillaRegistro] = relationship()
    unidad: Mapped[Unidad] = relationship()
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id])
    aprobado_por: Mapped[Usuario | None] = relationship(foreign_keys=[aprobado_por_id])
    actualizado_por: Mapped[Usuario | None] = relationship(foreign_keys=[actualizado_por_id])


# ---------- Laboratorio ----------

fuente_agua_unidades = Table(
    "certificaciones_pivot_fuenteagua_unidad", Base.metadata,
    Column("fuente_agua_id", ForeignKey("certificaciones_dim_fuenteagua.id"), primary_key=True),
    Column("unidad_id", ForeignKey("certificaciones_dim_unidad.id"), primary_key=True),
)


class FuenteAgua(Base):
    """Fuente de agua. Puede abastecer a varias unidades (p. ej. campo y planta Chocalán)."""
    __tablename__ = "certificaciones_dim_fuenteagua"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ubicacion_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_ubicacion.id"))
    unidades: Mapped[list[Unidad]] = relationship(secondary=fuente_agua_unidades)


unidad_especies = Table(
    "certificaciones_pivot_unidad_especie", Base.metadata,
    Column("unidad_id", ForeignKey("certificaciones_dim_unidad.id"), primary_key=True),
    Column("especie_id", ForeignKey("certificaciones_dim_especie.id"), primary_key=True),
)


class Especie(Base):
    """Especie frutal (cerezo, ciruelo…). Cada campo tiene las suyas."""
    __tablename__ = "certificaciones_dim_especie"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    unidades: Mapped[list[Unidad]] = relationship(secondary=unidad_especies)


class TipoAnalisis(Base):
    __tablename__ = "certificaciones_dim_tipoanalisis"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(10))  # campo | planta
    usa_fuente_agua: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fruta, hoja y suelo se asocian a una especie del campo
    usa_especie: Mapped[bool] = mapped_column(Boolean, default=False)


class LimiteParametro(Base):
    """Límite de referencia vigente. Al registrar un resultado se copia al resultado."""
    __tablename__ = "certificaciones_dim_limiteparametro"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_analisis_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_tipoanalisis.id"))
    parametro: Mapped[str] = mapped_column(String(120))
    unidad_medida: Mapped[str | None] = mapped_column(String(30))
    minimo: Mapped[float | None] = mapped_column(Float)
    maximo: Mapped[float | None] = mapped_column(Float)
    norma: Mapped[str | None] = mapped_column(String(120))


class Analisis(Base):
    __tablename__ = "certificaciones_fact_analisis"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_analisis_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_tipoanalisis.id"))
    unidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))
    temporada_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    fuente_agua_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_fuenteagua.id"))
    especie_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_especie.id"))
    punto: Mapped[str | None] = mapped_column(String(120))  # punto, cuartel o superficie
    fecha_muestreo: Mapped[date] = mapped_column(Date)
    laboratorio: Mapped[str | None] = mapped_column(String(120))
    archivo_key: Mapped[str | None] = mapped_column(String(400))
    nombre_archivo: Mapped[str | None] = mapped_column(String(250))
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    tipo: Mapped[TipoAnalisis] = relationship()
    unidad: Mapped[Unidad] = relationship()
    fuente_agua: Mapped[FuenteAgua | None] = relationship()
    especie: Mapped[Especie | None] = relationship()
    resultados: Mapped[list["ResultadoAnalisis"]] = relationship(back_populates="analisis", cascade="all, delete-orphan")


class ResultadoAnalisis(Base):
    __tablename__ = "certificaciones_fact_analisisresultado"
    id: Mapped[int] = mapped_column(primary_key=True)
    analisis_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_fact_analisis.id"))
    parametro: Mapped[str] = mapped_column(String(120))
    valor: Mapped[float | None] = mapped_column(Float)
    valor_texto: Mapped[str | None] = mapped_column(String(60))  # "< LD", "Ausencia"
    unidad_medida: Mapped[str | None] = mapped_column(String(30))
    limite_min: Mapped[float | None] = mapped_column(Float)
    limite_max: Mapped[float | None] = mapped_column(Float)
    cumple: Mapped[bool | None] = mapped_column(Boolean)
    analisis: Mapped[Analisis] = relationship(back_populates="resultados")


# ---------- Auditorías ----------


class Auditoria(Base):
    __tablename__ = "certificaciones_fact_auditoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_versionnorma.id"))
    unidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))
    temporada_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    titulo: Mapped[str | None] = mapped_column(String(250))
    fecha: Mapped[date] = mapped_column(Date)  # fecha de inicio
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    auditor: Mapped[str | None] = mapped_column(String(120))
    # Vacío = todas las cláusulas de la versión de la norma (lo normal); las importadas traen las de su planilla
    secciones: Mapped[list] = mapped_column(JSON, default=list)
    estado: Mapped[str] = mapped_column(String(20), default="planificada")  # planificada | en_curso | cerrada
    origen: Mapped[str] = mapped_column(String(20), default="app")  # app | importada
    archivo_origen: Mapped[str | None] = mapped_column(String(250))
    advertencias: Mapped[list | None] = mapped_column(JSON)
    # Al emitir el informe, las no conformidades pasan a los responsables con su plazo
    emitida_en: Mapped[datetime | None] = mapped_column(DateTime)
    emitida_por_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    version: Mapped[VersionNorma] = relationship()
    unidad: Mapped[Unidad] = relationship()
    respuestas: Mapped[list["Respuesta"]] = relationship(back_populates="auditoria", cascade="all, delete-orphan")


class Respuesta(Base):
    __tablename__ = "certificaciones_fact_respuesta"
    __table_args__ = (UniqueConstraint("auditoria_id", "requisito_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_fact_auditoria.id"))
    requisito_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_requisito.id"))
    resultado: Mapped[str | None] = mapped_column(String(5))  # si | no | na
    comentario: Mapped[str | None] = mapped_column(Text)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_area.id"))
    advertencia: Mapped[str | None] = mapped_column(Text)  # detectada al importar, para revisión
    auditoria: Mapped[Auditoria] = relationship(back_populates="respuestas")
    requisito: Mapped[Requisito] = relationship()
    area: Mapped[Area | None] = relationship()


class NoConformidad(Base):
    __tablename__ = "certificaciones_fact_noconformidad"
    id: Mapped[int] = mapped_column(primary_key=True)
    auditoria_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_fact_auditoria.id"))
    respuesta_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_fact_respuesta.id"))
    requisito_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_requisito.id"))
    unidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_area.id"))
    descripcion: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(String(20))  # infraestructura | documental | operacional
    clasificacion: Mapped[str | None] = mapped_column(String(10))  # menor | mayor | critica
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    plazo: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="abierta")  # abierta | en_proceso | cerrada
    reincidente_de_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_fact_noconformidad.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    fecha_deteccion: Mapped[date] = mapped_column(Date)
    cerrada_por_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Plan de acción que completa el jefe de área
    causa_raiz: Mapped[list | None] = mapped_column(JSON)  # 5 porqués
    accion_correctiva: Mapped[str | None] = mapped_column(Text)  # qué se hace de inmediato
    accion_preventiva: Mapped[str | None] = mapped_column(Text)  # qué se hará para que no vuelva a ocurrir
    plan_por_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    plan_en: Mapped[datetime | None] = mapped_column(DateTime)
    plan_enviado_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Revisión de certificaciones: [{fecha, por, resultado: cumple|no_cumple, observacion}]
    revisiones: Mapped[list | None] = mapped_column(JSON)
    # Reincidencia: veces que certificaciones no quedó conforme y la devolvió al jefe de área
    reincidencias: Mapped[int] = mapped_column(Integer, default=0)
    auditoria: Mapped[Auditoria] = relationship()
    requisito: Mapped[Requisito] = relationship()
    unidad: Mapped[Unidad] = relationship()
    area: Mapped[Area | None] = relationship()
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id])
    plan_por: Mapped[Usuario | None] = relationship(foreign_keys=[plan_por_id])
    reincidente_de: Mapped["NoConformidad | None"] = relationship(remote_side=[id])
    acciones: Mapped[list["AccionCorrectiva"]] = relationship(
        back_populates="no_conformidad", order_by="AccionCorrectiva.creada_en")


class AccionCorrectiva(Base):
    """Levantamiento: acción correctiva con evidencia (foto o PDF)."""
    __tablename__ = "certificaciones_fact_accioncorrectiva"
    id: Mapped[int] = mapped_column(primary_key=True)
    no_conformidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_fact_noconformidad.id"))
    descripcion: Mapped[str] = mapped_column(Text)
    archivo_key: Mapped[str | None] = mapped_column(String(400))
    nombre_archivo: Mapped[str | None] = mapped_column(String(250))
    creada_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    no_conformidad: Mapped[NoConformidad] = relationship(back_populates="acciones")
    creada_por: Mapped[Usuario] = relationship()


# ---------- Medio ambiente ----------


class FactorEmision(Base):
    __tablename__ = "certificaciones_dim_factoremision"
    __table_args__ = (UniqueConstraint("temporada_id", "concepto"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    temporada_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    concepto: Mapped[str] = mapped_column(String(40))  # combustible_diesel | electricidad | fertilizante_n | ...
    unidad_medida: Mapped[str] = mapped_column(String(20))
    factor_kgco2e: Mapped[float] = mapped_column(Float)
    fuente: Mapped[str | None] = mapped_column(String(250))


class RegistroConsumo(Base):
    __tablename__ = "certificaciones_fact_registroconsumo"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))
    temporada_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    fecha: Mapped[date] = mapped_column(Date)
    concepto: Mapped[str] = mapped_column(String(40))
    cantidad: Mapped[float] = mapped_column(Float)
    unidad_medida: Mapped[str] = mapped_column(String(20))
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    unidad: Mapped[Unidad] = relationship()


class MaterialReciclaje(Base):
    __tablename__ = "certificaciones_dim_materialreciclaje"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)


class RegistroReciclaje(Base):
    __tablename__ = "certificaciones_fact_registroreciclaje"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_unidad.id"))
    temporada_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_temporada.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_materialreciclaje.id"))
    fecha: Mapped[date] = mapped_column(Date)
    kilos: Mapped[float] = mapped_column(Float)
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    unidad: Mapped[Unidad] = relationship()
    material: Mapped[MaterialReciclaje] = relationship()


# ---------- Bitácora ----------


class Bitacora(Base):
    __tablename__ = "certificaciones_fact_bitacora"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_usuario.id"))
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)
    accion: Mapped[str] = mapped_column(String(40))
    entidad: Mapped[str] = mapped_column(String(40))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    detalle: Mapped[dict | None] = mapped_column(JSON)
    usuario: Mapped[Usuario | None] = relationship()
