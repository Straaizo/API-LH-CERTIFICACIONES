"""Modelo de datos (MySQL; SQLite en la demo local).

Las tablas general_* y usuario_* son compartidas por todas las aplicaciones de la empresa: aquí solo se leen.
Se marcan con info={"compartida": True} y solo se crean en la demo SQLite (con datos de ejemplo).

En código, la sucursal se sigue llamando "unidad" (atributo unidad_id) para no cambiar el contrato de la API;
en la base la columna es sucursal_id y apunta a general_dim_sucursal.
"""
from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from config import Config
from utils.db import Base
from utils.hora import ahora

COMPARTIDA = {"info": {"compartida": True}}
SUCURSAL = "general_dim_sucursal.id"
USUARIO = "general_dim_usuario.id"


def _sucursal_id(**kwargs):
    """Columna sucursal_id expuesta en código como unidad_id."""
    return mapped_column("sucursal_id", ForeignKey(SUCURSAL), index=True, **kwargs)


def _usuario_fk(**kwargs):
    return mapped_column(String(45), ForeignKey(USUARIO), **kwargs)


def _temporada_de(objeto, fecha: date | None, unidad: "Unidad | None") -> int | None:
    from utils.temporadas import id_temporada

    db = object_session(objeto)
    if db is None or fecha is None or unidad is None:
        return None
    return id_temporada(db, fecha, unidad.empresa_id)


# ---------- Compartidas de la empresa (lahornilla_base_normalizada) ----------


class Empresa(Base):
    __tablename__ = "general_dim_empresa"
    __table_args__ = COMPARTIDA
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(45))
    rut: Mapped[int | None] = mapped_column(Integer)
    codigo_verificador: Mapped[int | None] = mapped_column(Integer)
    fecha_suscripcion: Mapped[date | None] = mapped_column(Date)
    sucursales: Mapped[list["Unidad"]] = relationship(back_populates="empresa", order_by="Unidad.id")

    @property
    def codigo(self) -> str:
        return {1: "LH", 2: "VS"}.get(self.id, self.nombre[:2].upper())


class SucursalTipo(Base):
    __tablename__ = "general_dim_sucursaltipo"
    __table_args__ = COMPARTIDA
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(45))  # CAMPO | PACKING | OTRO | VIVERO | OFICINA


TIPO_CAMPO, TIPO_PACKING = 1, 2


class Unidad(Base):
    """Sucursal de la empresa (campo, packing, oficina...). La empresa y el tipo vienen de la tabla general."""
    __tablename__ = "general_dim_sucursal"
    __table_args__ = COMPARTIDA
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(45))
    ubicacion: Mapped[str | None] = mapped_column(String(60))
    empresa_id: Mapped[int] = mapped_column("id_empresa", ForeignKey("general_dim_empresa.id"))
    tipo_id: Mapped[int | None] = mapped_column("id_sucursaltipo", ForeignKey("general_dim_sucursaltipo.id"))
    empresa: Mapped[Empresa] = relationship(back_populates="sucursales")
    tipo_sucursal: Mapped[SucursalTipo | None] = relationship()
    areas: Mapped[list["Area"]] = relationship(back_populates="unidad")

    @property
    def tipo(self) -> str:
        """Ámbito de las normas y plantillas: campo | planta (packing) | otro."""
        return {TIPO_CAMPO: "campo", TIPO_PACKING: "planta"}.get(self.tipo_id, "otro")

    @property
    def tipo_nombre(self) -> str:
        return self.tipo_sucursal.nombre.capitalize() if self.tipo_sucursal else "Otro"

    @property
    def etiqueta(self) -> str:
        """Nombre para mostrar: 'CAMPO CHOCALAN' -> 'Campo Chocalan', 'PACKING MG' -> 'Packing MG'."""
        return " ".join(p if len(p) <= 2 else p.capitalize() for p in self.nombre.split())


class Temporada(Base):
    """Temporada por empresa (mayo a abril). En la API se agrupan por nombre: ver utils/temporadas.py."""
    __tablename__ = "general_dim_temporada"
    __table_args__ = COMPARTIDA
    id: Mapped[int] = mapped_column(primary_key=True)
    temporada: Mapped[str] = mapped_column(String(45))  # 24-25
    empresa_id: Mapped[int] = mapped_column("id_empresa", ForeignKey("general_dim_empresa.id"))
    inicio: Mapped[date | None] = mapped_column("fechainicio_produccion", Date)
    fin: Mapped[date | None] = mapped_column("fechatermino_produccion", Date)
    fechainicio_riego: Mapped[date | None] = mapped_column(Date)
    fechatermino_riego: Mapped[date | None] = mapped_column(Date)
    fechainicio_fito: Mapped[date | None] = mapped_column(Date)
    fechatermino_fito: Mapped[date | None] = mapped_column(Date)


class App(Base):
    __tablename__ = "general_dim_app"
    __table_args__ = COMPARTIDA
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(45))
    descripcion: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column("URL", String(100))


class Permiso(Base):
    __tablename__ = "usuario_dim_permiso"
    __table_args__ = COMPARTIDA
    id: Mapped[str] = mapped_column(String(45), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(45))  # CERTIFICACIONES_ADMIN, REGISTROS_EDITAR...
    app_id: Mapped[int] = mapped_column("id_app", ForeignKey("general_dim_app.id"))
    id_estado: Mapped[int] = mapped_column(Integer, default=1)


usuario_apps = Table(
    "usuario_pivot_app_usuario", Base.metadata,
    Column("id", String(45), primary_key=True),
    Column("id_usuario", ForeignKey(USUARIO)),
    Column("id_app", ForeignKey("general_dim_app.id")),
    **COMPARTIDA,
)

usuario_permisos = Table(
    "usuario_pivot_permiso_usuario", Base.metadata,
    Column("id", String(25), primary_key=True),
    Column("id_usuario", ForeignKey(USUARIO)),
    Column("id_permiso", ForeignKey("usuario_dim_permiso.id")),
    **COMPARTIDA,
)

usuario_sucursales = Table(
    "usuario_pivot_sucursal_usuario", Base.metadata,
    Column("id_sucursal", ForeignKey(SUCURSAL), primary_key=True),
    Column("id_usuario", ForeignKey(USUARIO), primary_key=True),
    **COMPARTIDA,
)

PERMISO_ADMIN = "CERTIFICACIONES_ADMIN"
PERMISO_VER = "CERTIFICACIONES_VER"


class Usuario(Base):
    """Usuario del portal web. Acceso, permisos y sucursales se administran allá, no en esta aplicación."""
    __tablename__ = "general_dim_usuario"
    __table_args__ = COMPARTIDA
    id: Mapped[str] = mapped_column(String(45), primary_key=True)
    usuario: Mapped[str] = mapped_column(String(60))
    correo: Mapped[str | None] = mapped_column(String(200))
    clave: Mapped[str] = mapped_column(String(255))
    nombre: Mapped[str | None] = mapped_column(String(150))
    id_estado: Mapped[int] = mapped_column(Integer, default=1)
    apps: Mapped[list[App]] = relationship(secondary=usuario_apps, viewonly=True)
    permisos: Mapped[list[Permiso]] = relationship(secondary=usuario_permisos, viewonly=True)
    unidades: Mapped[list[Unidad]] = relationship(secondary=usuario_sucursales, viewonly=True, order_by=Unidad.id)

    @property
    def email(self) -> str:
        return self.correo or ""

    @property
    def activo(self) -> bool:
        return self.id_estado == 1

    @property
    def tiene_acceso(self) -> bool:
        return any(a.id == Config.APP_ID for a in self.apps)

    @property
    def codigos_permiso(self) -> set[str]:
        return {p.nombre for p in self.permisos if p.app_id == Config.APP_ID and p.id_estado == 1}

    @property
    def rol(self) -> str:
        """certificaciones (ADMIN) | encargado (algún *_EDITAR) | lectura."""
        codigos = self.codigos_permiso
        if PERMISO_ADMIN in codigos:
            return "certificaciones"
        if any(c.endswith("_EDITAR") for c in codigos):
            return "encargado"
        return "lectura"


# ---------- Sitios propios de la aplicación ----------


class Area(Base):
    """Área de planta o cuartel de campo."""
    __tablename__ = "certificaciones_dim_area"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_id: Mapped[int] = _sucursal_id()
    nombre: Mapped[str] = mapped_column(String(120))
    unidad: Mapped[Unidad] = relationship(back_populates="areas")


# ---------- Protocolos y requisitos ----------


sucursal_protocolos = Table(
    "certificaciones_pivot_sucursal_protocolo", Base.metadata,
    Column("sucursal_id", ForeignKey(SUCURSAL), primary_key=True),
    Column("protocolo_id", ForeignKey("certificaciones_dim_protocolo.id"), primary_key=True),
)


class Protocolo(Base):
    __tablename__ = "certificaciones_dim_protocolo"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(10))  # campo | planta | ambos
    versiones: Mapped[list["VersionNorma"]] = relationship(back_populates="protocolo")
    # Sucursales que tienen esta norma (certificaciones_pivot_sucursal_protocolo)
    unidades: Mapped[list[Unidad]] = relationship(secondary=sucursal_protocolos, order_by=Unidad.id)

    def aplica_a(self, unidad: Unidad) -> bool:
        return any(u.id == unidad.id for u in self.unidades)


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


class Certificacion(Base):
    """Certificado de protocolo obtenido. Sin sucursal = cubre toda la empresa (multisitio)."""
    __tablename__ = "certificaciones_fact_certificacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    protocolo_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_protocolo.id"))
    empresa_id: Mapped[int] = mapped_column(ForeignKey("general_dim_empresa.id"))
    entidad_certificadora: Mapped[str | None] = mapped_column(String(120))
    fecha_auditoria: Mapped[date | None] = mapped_column(Date)
    resultado: Mapped[str | None] = mapped_column(String(120))
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    # Ficha del certificado subido como documento fijo: una por versión (renovar = versión nueva)
    documento_version_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_fact_documentoversion.id"), unique=True)
    numero: Mapped[str | None] = mapped_column(String(40))  # N° de certificado o LoC
    norma_version: Mapped[str | None] = mapped_column(String(40))  # 6.0-GFS_AUG24, v13_FEB25
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    productos: Mapped[list | None] = mapped_column(JSON)
    unidad_id: Mapped[int | None] = mapped_column("sucursal_id", ForeignKey(SUCURSAL))
    protocolo: Mapped[Protocolo] = relationship()
    empresa: Mapped[Empresa] = relationship()
    unidad: Mapped[Unidad | None] = relationship()

    @property
    def unidades(self) -> list[Unidad]:
        """Sucursales cubiertas: la indicada o, si no hay, las de la empresa que tienen la norma."""
        if self.unidad is not None:
            return [self.unidad]
        return [u for u in self.empresa.sucursales if self.protocolo.aplica_a(u)]


# ---------- Documentos ----------


class CategoriaDocumento(Base):
    __tablename__ = "certificaciones_dim_categoriadocumento"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(10), default="ambos")  # campo | planta | ambos
    requiere_vencimiento: Mapped[bool] = mapped_column(Boolean, default=False)
    requiere_codigo: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class Documento(Base):
    __tablename__ = "certificaciones_dim_documento"
    id: Mapped[int] = mapped_column(primary_key=True)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_categoriadocumento.id"))
    empresa_id: Mapped[int] = mapped_column(ForeignKey("general_dim_empresa.id"))
    # Documentos fijos: sección campo | planta | empresarial (códigos OC). No van por sucursal.
    seccion: Mapped[str] = mapped_column(String(12), default="empresarial")
    titulo: Mapped[str] = mapped_column(String(250))
    codigo: Mapped[str | None] = mapped_column(String(40), index=True)  # P OC CE 29, DPL 23
    creado_por_id: Mapped[str] = _usuario_fk()
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    categoria: Mapped[CategoriaDocumento] = relationship()
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
    subido_por_id: Mapped[str] = _usuario_fk()
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    revisado_por_id: Mapped[str | None] = _usuario_fk(nullable=True)
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime)
    documento: Mapped[Documento] = relationship(back_populates="versiones")
    subido_por: Mapped[Usuario] = relationship(foreign_keys=[subido_por_id])
    certificacion: Mapped[Certificacion | None] = relationship(foreign_keys="Certificacion.documento_version_id")


class Capacitacion(Base):
    __tablename__ = "certificaciones_fact_capacitacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_id: Mapped[int] = _sucursal_id()
    tema: Mapped[str] = mapped_column(String(250))
    fecha: Mapped[date] = mapped_column(Date)
    relator: Mapped[str | None] = mapped_column(String(120))
    asistentes: Mapped[list | None] = mapped_column(JSON)  # nombres o RUT (tabla de trabajadores por confirmar)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    documento_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_documento.id"))
    creado_por_id: Mapped[str] = _usuario_fk()
    unidad: Mapped[Unidad] = relationship()

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.fecha, self.unidad)


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
    creada_por_id: Mapped[str] = _usuario_fk()
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Registro(Base):
    """Registro generado desde una plantilla. Guarda una copia de los campos: editar la plantilla no lo altera."""
    __tablename__ = "certificaciones_fact_registro"
    id: Mapped[int] = mapped_column(primary_key=True)
    plantilla_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_plantillaregistro.id"))
    unidad_id: Mapped[int] = _sucursal_id()
    titulo: Mapped[str] = mapped_column(String(250))
    # Copia de la plantilla al crear el registro
    codigo: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[str | None] = mapped_column(String(10))
    formato: Mapped[dict] = mapped_column(JSON, default=dict)
    word_clave: Mapped[str | None] = mapped_column(String(400))
    campos: Mapped[list] = mapped_column(JSON, default=list)
    valores: Mapped[dict] = mapped_column(JSON, default=dict)
    responsable_id: Mapped[str | None] = _usuario_fk(nullable=True)
    # Última vez que alguien del campo (no certificaciones) guardó o envió: "fecha de revisión"
    revision_campo_en: Mapped[datetime | None] = mapped_column(DateTime)
    # borrador | en_revision | aprobado | rechazado
    estado: Mapped[str] = mapped_column(String(20), default="borrador")
    observacion: Mapped[str | None] = mapped_column(Text)
    creado_por_id: Mapped[str] = _usuario_fk()
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime)
    actualizado_por_id: Mapped[str | None] = _usuario_fk(nullable=True)
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime)
    aprobado_por_id: Mapped[str | None] = _usuario_fk(nullable=True)
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime)
    plantilla: Mapped[PlantillaRegistro] = relationship()
    unidad: Mapped[Unidad] = relationship()
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id])
    aprobado_por: Mapped[Usuario | None] = relationship(foreign_keys=[aprobado_por_id])
    actualizado_por: Mapped[Usuario | None] = relationship(foreign_keys=[actualizado_por_id])

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.creado_en.date() if self.creado_en else None, self.unidad)


# ---------- Laboratorio ----------


class FuenteAgua(Base):
    """Fuente de agua de una sucursal."""
    __tablename__ = "certificaciones_dim_fuenteagua"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    unidad_id: Mapped[int] = _sucursal_id()
    unidad: Mapped[Unidad] = relationship()

    @property
    def unidades(self) -> list[Unidad]:
        return [self.unidad]


class Especie(Base):
    """Especie frutal (cerezo, ciruelo…)."""
    __tablename__ = "certificaciones_dim_especie"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)


class TipoAnalisis(Base):
    __tablename__ = "certificaciones_dim_tipoanalisis"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(10))  # campo | planta
    usa_fuente_agua: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fruta, hoja y suelo se asocian a una especie
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
    unidad_id: Mapped[int] = _sucursal_id()
    fuente_agua_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_fuenteagua.id"))
    especie_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_especie.id"))
    punto: Mapped[str | None] = mapped_column(String(120))  # punto, cuartel o superficie
    fecha_muestreo: Mapped[date] = mapped_column(Date)
    laboratorio: Mapped[str | None] = mapped_column(String(120))
    archivo_key: Mapped[str | None] = mapped_column(String(400))
    nombre_archivo: Mapped[str | None] = mapped_column(String(250))
    creado_por_id: Mapped[str] = _usuario_fk()
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    tipo: Mapped[TipoAnalisis] = relationship()
    unidad: Mapped[Unidad] = relationship()
    fuente_agua: Mapped[FuenteAgua | None] = relationship()
    especie: Mapped[Especie | None] = relationship()
    resultados: Mapped[list["ResultadoAnalisis"]] = relationship(back_populates="analisis", cascade="all, delete-orphan")

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.fecha_muestreo, self.unidad)


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
    unidad_id: Mapped[int] = _sucursal_id()
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
    emitida_por_id: Mapped[str | None] = _usuario_fk(nullable=True)
    version: Mapped[VersionNorma] = relationship()
    unidad: Mapped[Unidad] = relationship()
    respuestas: Mapped[list["Respuesta"]] = relationship(back_populates="auditoria", cascade="all, delete-orphan")

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.fecha, self.unidad)


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
    unidad_id: Mapped[int] = _sucursal_id()
    area_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_dim_area.id"))
    descripcion: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(String(20))  # infraestructura | documental | operacional
    clasificacion: Mapped[str | None] = mapped_column(String(10))  # menor | mayor | critica
    responsable_id: Mapped[str | None] = _usuario_fk(nullable=True)
    plazo: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="abierta")  # abierta | en_proceso | cerrada
    reincidente_de_id: Mapped[int | None] = mapped_column(ForeignKey("certificaciones_fact_noconformidad.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    fecha_deteccion: Mapped[date] = mapped_column(Date)
    cerrada_por_id: Mapped[str | None] = _usuario_fk(nullable=True)
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Plan de acción que completa el jefe de área
    causa_raiz: Mapped[list | None] = mapped_column(JSON)  # 5 porqués
    accion_correctiva: Mapped[str | None] = mapped_column(Text)  # qué se hace de inmediato
    accion_preventiva: Mapped[str | None] = mapped_column(Text)  # qué se hará para que no vuelva a ocurrir
    plan_por_id: Mapped[str | None] = _usuario_fk(nullable=True)
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
    creada_por_id: Mapped[str] = _usuario_fk()
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    no_conformidad: Mapped[NoConformidad] = relationship(back_populates="acciones")
    creada_por: Mapped[Usuario] = relationship()


# ---------- Medio ambiente ----------


class ConceptoAmbiental(Base):
    """Qué se mide: combustibles, electricidad, fertilizantes y materiales reciclados."""
    __tablename__ = "certificaciones_dim_conceptoambiental"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)  # combustible_diesel, electricidad, carton...
    nombre: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[str] = mapped_column(String(20))  # combustible | electricidad | fertilizante | reciclaje
    unidad_medida: Mapped[str] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class FactorEmision(Base):
    """Factor por nombre de temporada: el mismo para LH y VS (general_dim_temporada tiene un id por empresa)."""
    __tablename__ = "certificaciones_dim_factoremision"
    id: Mapped[int] = mapped_column(primary_key=True)
    temporada: Mapped[str] = mapped_column(String(10))  # 24-25
    concepto_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_conceptoambiental.id"))
    factor_kgco2e: Mapped[float] = mapped_column(Float)
    fuente: Mapped[str | None] = mapped_column(String(250))
    concepto: Mapped[ConceptoAmbiental] = relationship()


class RegistroAmbiental(Base):
    """Consumo o reciclaje de una sucursal en una fecha, en la unidad del concepto (L, kWh, kg)."""
    __tablename__ = "certificaciones_fact_registroambiental"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_id: Mapped[int] = _sucursal_id()
    concepto_id: Mapped[int] = mapped_column(ForeignKey("certificaciones_dim_conceptoambiental.id"))
    fecha: Mapped[date] = mapped_column(Date, index=True)
    cantidad: Mapped[float] = mapped_column(Float)
    creado_por_id: Mapped[str] = _usuario_fk()
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    unidad: Mapped[Unidad] = relationship()
    concepto: Mapped[ConceptoAmbiental] = relationship()

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.fecha, self.unidad)


# ---------- Bitácora ----------


class Bitacora(Base):
    __tablename__ = "certificaciones_fact_bitacora"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[str | None] = _usuario_fk(nullable=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)
    accion: Mapped[str] = mapped_column(String(40))
    entidad: Mapped[str] = mapped_column(String(40))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    detalle: Mapped[dict | None] = mapped_column(JSON)
    usuario: Mapped[Usuario | None] = relationship()


def tablas_propias() -> list[Table]:
    """Tablas de la aplicación (las que crea su migración); excluye las compartidas de la empresa."""
    return [t for t in Base.metadata.sorted_tables if not t.info.get("compartida")]
