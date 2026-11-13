"""Modelo de datos (MySQL; SQLite en la demo local).

Las tablas general_* y usuario_* son compartidas por todas las aplicaciones de la empresa: aquí solo se leen.
Se marcan con info={"compartida": True} y solo se crean en la demo SQLite (con datos de ejemplo).

En código, la sucursal se sigue llamando "unidad" (atributo unidad_id) para no cambiar el contrato de la API;
en la base la columna es sucursal_id y apunta a general_dim_sucursal.
"""
import logging
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CHAR, JSON, Boolean, Column, Date, DateTime, DefaultClause, Float, ForeignKey, Index, Integer, String, Table, Text,
    UniqueConstraint, event, text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, object_session, relationship, synonym

from config import Config
from utils.db import Base
from utils.hora import ahora

COMPARTIDA = {"info": {"compartida": True}}
SUCURSAL = "general_dim_sucursal.id"
USUARIO = "general_dim_usuario.id"


def _sucursal_id(**kwargs):
    """Columna sucursal_id expuesta en código como unidad_id. Va al final de la tabla, con las demás FK."""
    return mapped_column("sucursal_id", ForeignKey(SUCURSAL), index=True, sort_order=100, **kwargs)


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
# Vivero y oficina (general_dim_sucursaltipo) no se certifican: no aparecen en la aplicación
TIPOS_SIN_CERTIFICACION = (4, 5)


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
# Ver el historial completo de cambios; se asigna aparte en el portal (no basta con ADMIN)
PERMISO_HISTORIAL = "CERTIFICACIONES_HISTORIAL"

# Nombre que ve quien asigna permisos en el portal web (usuario_dim_permiso.nombre, máx. 45 caracteres) → código
# que usa la API. Los códigos solos (REGISTROS_EDITAR...) también se aceptan, por compatibilidad.
NOMBRES_PERMISO = {
    # Nombres que usa hoy el portal (12-11-2026): uno por fila, "Módulo - Ver …" / "Módulo - Editar …"
    "Registros - Ver registros de la sucursal": "REGISTROS_VER",
    "Registros - Editar registros de la sucursal": "REGISTROS_EDITAR",
    "NC - Ver no conformidades de la sucursal": "NC_VER",
    "NC - Editar no conformidades de la sucursal": "NC_EDITAR",
    "Laboratorio - Ver análisis de la sucursal": "LABORATORIO_VER",
    "Laboratorio - Editar análisis de la sucursal": "LABORATORIO_EDITAR",
    "Ambiente - Ver consumos de la sucursal": "AMBIENTE_VER",
    "Ambiente - Editar consumos de la sucursal": "AMBIENTE_EDITAR",
    "Auditorías - Ver auditorías de la sucursal": "AUDITORIAS_VER",
    "Documentos - Ver documentos y vencimientos": "DOCUMENTOS_VER",
    "General - Ver todo sin editar (auditores)": PERMISO_VER,
    "General - Ver historial de cambios": PERMISO_HISTORIAL,
    "General - Administrar, aprobar y cerrar todo": PERMISO_ADMIN,
    # Nombres anteriores (12-11-2026), aceptados mientras se renombran en el portal
    "Registros: ver, descargar y su historial": "REGISTROS_VER",
    "Registros: llenar, firmar y enviar a revisión": "REGISTROS_EDITAR",
    "NC: ver hallazgos, plazos y su estado": "NC_VER",
    "NC: plan de acción y cargar evidencias": "NC_EDITAR",
    "Laboratorio: ver análisis y límites MRL": "LABORATORIO_VER",
    "Laboratorio: cargar y reemplazar análisis": "LABORATORIO_EDITAR",
    "Ambiente: ver consumos, huella y reciclaje": "AMBIENTE_VER",
    "Ambiente: registrar consumos": "AMBIENTE_EDITAR",
    "Auditorías: ver programa y respuestas": "AUDITORIAS_VER",
    "Documentos: ver, descargar y vencimientos": "DOCUMENTOS_VER",
    "General: ver todo sin editar (auditores)": PERMISO_VER,
    "General: ver historial de cambios de todos": PERMISO_HISTORIAL,
    "General: administrar, aprobar y cerrar todo": PERMISO_ADMIN,
}


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
        return Config.LOGIN_LOCAL_SIN_APP or any(a.id == Config.APP_ID for a in self.apps)

    @property
    def codigos_permiso(self) -> set[str]:
        if Config.LOGIN_LOCAL_SIN_APP:  # temporal, solo local (ver config.py)
            return {PERMISO_ADMIN, PERMISO_HISTORIAL}
        return {NOMBRES_PERMISO.get(p.nombre.strip(), p.nombre.strip())
                for p in self.permisos if p.app_id == Config.APP_ID and p.id_estado == 1}

    @property
    def rol(self) -> str:
        """certificaciones (ADMIN) | encargado (algún *_EDITAR) | lectura."""
        codigos = self.codigos_permiso
        if PERMISO_ADMIN in codigos:
            return "certificaciones"
        if any(c.endswith("_EDITAR") for c in codigos):
            return "encargado"
        return "lectura"


# ---------- Estándar de las tablas propias ----------
# Igual que las tablas de la empresa (cosecha_*, general_dim_usuario):
# - id VARCHAR(45) con UUID que genera la API (no autoincremental: no se puede adivinar en una URL)
# - llaves foráneas <tabla a la que apuntan>_id, al final de la tabla; las de usuario dicen su rol (usuario_responsable_id)
# - created_at, created_by, updated_at, updated_by en todas
# En código se mantienen los nombres de atributo anteriores (protocolo_id, creado_por_id...) para no cambiar
# el contrato de la API: solo cambia el nombre de la columna en la base.


def nuevo_id() -> str:
    return str(uuid.uuid4())


def _pk():
    return mapped_column(String(45), primary_key=True, default=nuevo_id)


def _fk(columna: str, destino: str, **kwargs):
    """Llave foránea a una tabla propia (id VARCHAR(45))."""
    return mapped_column(columna, String(45), ForeignKey(destino), sort_order=100, **kwargs)


def _usuario_rol(columna: str, **kwargs):
    """Llave foránea a general_dim_usuario con el rol en el nombre: usuario_responsable_id."""
    return mapped_column(columna, String(45), ForeignKey(USUARIO), sort_order=100, **kwargs)


class Auditable:
    """created_at / created_by / updated_at / updated_by. Se llenan solos al guardar (ver _auditar)."""
    created_at: Mapped[datetime] = mapped_column(DateTime, default=ahora, server_default=text("CURRENT_TIMESTAMP"))
    # Como general_dim_usuario y cosecha_*: CHAR(36) sin llave foránea
    created_by: Mapped[str | None] = mapped_column(CHAR(36))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_by: Mapped[str | None] = mapped_column(CHAR(36))


def _recortar_textos(obj) -> None:
    """VARCHAR estandarizados a 45: un texto más largo (un nombre leído de un PDF) se recorta en vez de que MySQL
    rechace todo el guardado. Las columnas que necesitan más largo ya lo tienen (archivos, títulos)."""
    for prop in obj.__mapper__.column_attrs:
        col = prop.columns[0]
        largo = getattr(col.type, "length", None)
        valor = getattr(obj, prop.key, None)
        if isinstance(col.type, String) and largo and isinstance(valor, str) and len(valor) > largo:
            logging.getLogger(__name__).warning("Texto recortado a %s caracteres en %s.%s", largo, col.table.name, col.name)
            setattr(obj, prop.key, valor[:largo])


@event.listens_for(Session, "before_flush")
def _auditar(session: Session, _contexto, _instancias) -> None:
    """Quién y cuándo: el usuario lo deja usuario_actual en session.info al validar el token."""
    usuario_id = session.info.get("usuario_id")
    momento = ahora()
    for obj in (*session.new, *session.dirty):
        if isinstance(obj, Auditable):
            _recortar_textos(obj)
    for obj in session.new:
        if isinstance(obj, Auditable):
            obj.created_at = obj.created_at or momento
            obj.created_by = obj.created_by or usuario_id
    for obj in session.dirty:
        if isinstance(obj, Auditable) and session.is_modified(obj, include_collections=False):
            obj.updated_at = momento
            obj.updated_by = usuario_id or obj.updated_by


# ---------- Sitios propios de la aplicación ----------


class Area(Auditable, Base):
    """Área de planta o cuartel de campo."""
    __tablename__ = "certificaciones_dim_area"
    id: Mapped[str] = _pk()
    unidad_id: Mapped[int] = _sucursal_id()
    nombre: Mapped[str] = mapped_column(String(45))
    unidad: Mapped[Unidad] = relationship(back_populates="areas")


# ---------- Protocolos y requisitos ----------


sucursal_protocolos = Table(
    "certificaciones_pivot_sucursal_protocolo", Base.metadata,
    Column("created_at", DateTime, default=ahora, server_default=text("CURRENT_TIMESTAMP"), nullable=False),
    Column("created_by", CHAR(36)),
    Column("updated_at", DateTime),
    Column("updated_by", CHAR(36)),
    Column("sucursal_id", ForeignKey(SUCURSAL), primary_key=True),
    Column("protocolo_id", String(45), ForeignKey("certificaciones_dim_protocolo.id"), primary_key=True),
)


class Protocolo(Auditable, Base):
    __tablename__ = "certificaciones_dim_protocolo"
    id: Mapped[str] = _pk()
    codigo: Mapped[str] = mapped_column(String(45), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(45))  # campo | planta | ambos
    versiones: Mapped[list["VersionNorma"]] = relationship(back_populates="protocolo")
    # Sucursales que tienen esta norma (certificaciones_pivot_sucursal_protocolo)
    unidades: Mapped[list[Unidad]] = relationship(secondary=sucursal_protocolos, order_by=Unidad.id)

    def aplica_a(self, unidad: Unidad) -> bool:
        return any(u.id == unidad.id for u in self.unidades)


class VersionNorma(Auditable, Base):
    __tablename__ = "certificaciones_dim_versionnorma"
    __table_args__ = (UniqueConstraint("protocolo_id", "nombre", name="uq_versionnorma_protocolo_nombre"),)
    id: Mapped[str] = _pk()
    protocolo_id: Mapped[str] = _fk("protocolo_id", "certificaciones_dim_protocolo.id")
    nombre: Mapped[str] = mapped_column(String(60))
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    # Las versiones nunca se sobrescriben: cada actualización es una versión nueva (cargada = created_at)
    cargada_en = synonym("created_at")
    archivo: Mapped[str | None] = mapped_column(String(250))
    # Cláusulas o secciones de la norma [{codigo, titulo}], para medir la cobertura del programa anual
    secciones: Mapped[list | None] = mapped_column(JSON)
    protocolo: Mapped[Protocolo] = relationship(back_populates="versiones")
    requisitos: Mapped[list["Requisito"]] = relationship(back_populates="version", order_by="Requisito.orden")


class Requisito(Auditable, Base):
    __tablename__ = "certificaciones_dim_requisito"
    __table_args__ = (UniqueConstraint("versionnorma_id", "codigo", name="uq_requisito_version_codigo"),)
    id: Mapped[str] = _pk()
    version_id: Mapped[str] = _fk("versionnorma_id", "certificaciones_dim_versionnorma.id")
    codigo: Mapped[str] = mapped_column(String(45))
    seccion: Mapped[str] = mapped_column(String(45))  # cláusula o sección: "4.1", "FV 20"
    seccion_titulo: Mapped[str | None] = mapped_column(String(250))
    texto: Mapped[str] = mapped_column(Text)
    nivel: Mapped[str | None] = mapped_column(String(45))  # mayor | menor | recomendacion | fundamental
    orden: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[VersionNorma] = relationship(back_populates="requisitos")


class Certificacion(Auditable, Base):
    """Certificado de protocolo obtenido. Sin sucursal = cubre toda la empresa (multisitio)."""
    __tablename__ = "certificaciones_fact_certificacion"
    id: Mapped[str] = _pk()
    protocolo_id: Mapped[str] = _fk("protocolo_id", "certificaciones_dim_protocolo.id")
    empresa_id: Mapped[int] = mapped_column("empresa_id", ForeignKey("general_dim_empresa.id"), sort_order=100)
    entidad_certificadora: Mapped[str | None] = mapped_column(String(120))
    fecha_auditoria: Mapped[date | None] = mapped_column(Date)
    resultado: Mapped[str | None] = mapped_column(String(120))
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    # Ficha del certificado subido como documento fijo: una por versión (renovar = versión nueva)
    documento_version_id: Mapped[str | None] = _fk(
        "documentoversion_id", "certificaciones_fact_documentoversion.id", unique=True)
    numero: Mapped[str | None] = mapped_column(String(45))  # N° de certificado o LoC
    norma_version: Mapped[str | None] = mapped_column(String(45))  # 6.0-GFS_AUG24, v13_FEB25
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    productos: Mapped[list | None] = mapped_column(JSON)
    unidad_id: Mapped[int | None] = mapped_column("sucursal_id", ForeignKey(SUCURSAL), sort_order=100)
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


class CategoriaDocumento(Auditable, Base):
    __tablename__ = "certificaciones_dim_categoriadocumento"
    id: Mapped[str] = _pk()
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(45), default="ambos")  # campo | planta | ambos
    requiere_vencimiento: Mapped[bool] = mapped_column(Boolean, default=False)
    requiere_codigo: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class Documento(Auditable, Base):
    __tablename__ = "certificaciones_dim_documento"
    id: Mapped[str] = _pk()
    categoria_id: Mapped[str] = _fk("categoriadocumento_id", "certificaciones_dim_categoriadocumento.id")
    empresa_id: Mapped[int] = mapped_column("empresa_id", ForeignKey("general_dim_empresa.id"), sort_order=100)
    # Documentos fijos: sección campo | planta | empresarial (códigos OC). No van por sucursal.
    seccion: Mapped[str] = mapped_column(String(45), default="empresarial")
    titulo: Mapped[str] = mapped_column(String(250))
    codigo: Mapped[str | None] = mapped_column(String(45), index=True)  # P OC CE 29, DPL 23
    creado_por_id = synonym("created_by")
    creado_en = synonym("created_at")
    categoria: Mapped[CategoriaDocumento] = relationship()
    versiones: Mapped[list["DocumentoVersion"]] = relationship(
        back_populates="documento", order_by="DocumentoVersion.numero")


class DocumentoVersion(Auditable, Base):
    """Versión de un documento. Una versión aprobada nunca se modifica ni se borra."""
    __tablename__ = "certificaciones_fact_documentoversion"
    __table_args__ = (UniqueConstraint("documento_id", "numero", name="uq_documentoversion_documento_numero"),)
    id: Mapped[str] = _pk()
    documento_id: Mapped[str] = _fk("documento_id", "certificaciones_dim_documento.id")
    numero: Mapped[int] = mapped_column(Integer)
    archivo_key: Mapped[str | None] = mapped_column(String(200))
    nombre_archivo: Mapped[str | None] = mapped_column(String(250))
    tipo_contenido: Mapped[str | None] = mapped_column(String(100))
    version_texto: Mapped[str | None] = mapped_column(String(45))  # versión del procedimiento: "03"
    fecha_emision: Mapped[date | None] = mapped_column(Date)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(45), default="pendiente")  # pendiente | aprobado | rechazado
    observacion: Mapped[str | None] = mapped_column(Text)
    subido_por_id = synonym("created_by")
    subido_en = synonym("created_at")
    revisado_por_id: Mapped[str | None] = _usuario_rol("usuario_revisor_id", nullable=True)
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime)
    documento: Mapped[Documento] = relationship(back_populates="versiones")
    subido_por: Mapped[Usuario] = relationship(primaryjoin="foreign(DocumentoVersion.created_by) == Usuario.id")
    certificacion: Mapped[Certificacion | None] = relationship(foreign_keys="Certificacion.documento_version_id")


class Capacitacion(Auditable, Base):
    __tablename__ = "certificaciones_fact_capacitacion"
    id: Mapped[str] = _pk()
    unidad_id: Mapped[int] = _sucursal_id()
    tema: Mapped[str] = mapped_column(String(120))
    fecha: Mapped[date] = mapped_column(Date)
    relator: Mapped[str | None] = mapped_column(String(120))
    asistentes: Mapped[list | None] = mapped_column(JSON)  # nombres o RUT (tabla de trabajadores por confirmar)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    documento_id: Mapped[str | None] = _fk("documento_id", "certificaciones_dim_documento.id")
    creado_por_id = synonym("created_by")
    unidad: Mapped[Unidad] = relationship()

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.fecha, self.unidad)


# ---------- Registros (documentos no fijos, llenados en la aplicación) ----------


class PlantillaRegistro(Auditable, Base):
    """Plantilla que define certificaciones; desde ella se generan registros para llenar.

    campos: [{id, etiqueta, tipo, obligatorio, columnas?: [{id, etiqueta, tipo}]}]
    tipos: texto | numero | fecha | si_no | tabla | foto | archivo | firma
    """
    __tablename__ = "certificaciones_dim_plantillaregistro"
    id: Mapped[str] = _pk()
    codigo: Mapped[str | None] = mapped_column(String(45), unique=True)  # R-OC-CE-01: el mismo del documento
    version: Mapped[str] = mapped_column(String(45), default="01")
    # Base del documento: encargado, frecuencia, orientacion, creado_por, aprobado_por, fecha_revision,
    # direccion, notas, logo_clave
    formato: Mapped[dict] = mapped_column(JSON, default=dict)
    # Word original del formulario: la descarga escribe los datos sobre él
    word_clave: Mapped[str | None] = mapped_column(String(200))
    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None] = mapped_column(Text)
    ambito: Mapped[str] = mapped_column(String(45), default="campo")  # campo | planta | ambos
    campos: Mapped[list] = mapped_column(JSON, default=list)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_por_id = synonym("created_by")
    creada_en = synonym("created_at")


class Registro(Auditable, Base):
    """Registro generado desde una plantilla. Guarda una copia de los campos: editar la plantilla no lo altera."""
    __tablename__ = "certificaciones_fact_registro"
    id: Mapped[str] = _pk()
    plantilla_id: Mapped[str] = _fk("plantillaregistro_id", "certificaciones_dim_plantillaregistro.id")
    unidad_id: Mapped[int] = _sucursal_id()
    titulo: Mapped[str] = mapped_column(String(250))
    # Copia de la plantilla al crear el registro
    codigo: Mapped[str | None] = mapped_column(String(45))
    version: Mapped[str | None] = mapped_column(String(45))
    formato: Mapped[dict] = mapped_column(JSON, default=dict)
    word_clave: Mapped[str | None] = mapped_column(String(200))
    campos: Mapped[list] = mapped_column(JSON, default=list)
    valores: Mapped[dict] = mapped_column(JSON, default=dict)
    responsable_id: Mapped[str | None] = _usuario_rol("usuario_responsable_id", nullable=True)
    # Última vez que alguien del campo (no certificaciones) guardó o envió: "fecha de revisión"
    revision_campo_en: Mapped[datetime | None] = mapped_column("revision_campo", DateTime)
    # borrador | en_revision | aprobado | rechazado
    estado: Mapped[str] = mapped_column(String(45), default="borrador")
    observacion: Mapped[str | None] = mapped_column(Text)
    creado_por_id = synonym("created_by")
    creado_en = synonym("created_at")
    actualizado_en = synonym("updated_at")
    actualizado_por_id = synonym("updated_by")
    enviado_en: Mapped[datetime | None] = mapped_column("enviado", DateTime)
    aprobado_por_id: Mapped[str | None] = _usuario_rol("usuario_aprobador_id", nullable=True)
    aprobado_en: Mapped[datetime | None] = mapped_column("aprobado", DateTime)
    plantilla: Mapped[PlantillaRegistro] = relationship()
    unidad: Mapped[Unidad] = relationship()
    responsable: Mapped[Usuario | None] = relationship(foreign_keys=[responsable_id])
    aprobado_por: Mapped[Usuario | None] = relationship(foreign_keys=[aprobado_por_id])
    actualizado_por: Mapped[Usuario | None] = relationship(primaryjoin="foreign(Registro.updated_by) == Usuario.id")

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.creado_en.date() if self.creado_en else None, self.unidad)


# ---------- Laboratorio ----------


class FuenteAgua(Auditable, Base):
    """Fuente de agua de una sucursal."""
    __tablename__ = "certificaciones_dim_fuenteagua"
    id: Mapped[str] = _pk()
    nombre: Mapped[str] = mapped_column(String(120))
    unidad_id: Mapped[int] = _sucursal_id()
    unidad: Mapped[Unidad] = relationship()

    @property
    def unidades(self) -> list[Unidad]:
        return [self.unidad]


class Especie(Auditable, Base):
    """Especie frutal (cerezo, ciruelo…)."""
    __tablename__ = "certificaciones_dim_especie"
    id: Mapped[str] = _pk()
    nombre: Mapped[str] = mapped_column(String(45), unique=True)


class TipoAnalisis(Auditable, Base):
    __tablename__ = "certificaciones_dim_tipoanalisis"
    id: Mapped[str] = _pk()
    nombre: Mapped[str] = mapped_column(String(120))
    ambito: Mapped[str] = mapped_column(String(45))  # campo | planta
    usa_fuente_agua: Mapped[bool] = mapped_column(Boolean, default=False)
    # Fruta, hoja y suelo se asocian a una especie
    usa_especie: Mapped[bool] = mapped_column(Boolean, default=False)


class LimiteParametro(Auditable, Base):
    """Límite de referencia vigente. Al registrar un resultado se copia al resultado."""
    __tablename__ = "certificaciones_dim_limiteparametro"
    id: Mapped[str] = _pk()
    tipo_analisis_id: Mapped[str] = _fk("tipoanalisis_id", "certificaciones_dim_tipoanalisis.id")
    parametro: Mapped[str] = mapped_column(String(120))
    unidad_medida: Mapped[str | None] = mapped_column(String(45))
    minimo: Mapped[float | None] = mapped_column(Float)
    maximo: Mapped[float | None] = mapped_column(Float)
    norma: Mapped[str | None] = mapped_column(String(120))


class Analisis(Auditable, Base):
    __tablename__ = "certificaciones_fact_analisis"
    id: Mapped[str] = _pk()
    tipo_analisis_id: Mapped[str] = _fk("tipoanalisis_id", "certificaciones_dim_tipoanalisis.id")
    unidad_id: Mapped[int] = _sucursal_id()
    fuente_agua_id: Mapped[str | None] = _fk("fuenteagua_id", "certificaciones_dim_fuenteagua.id")
    especie_id: Mapped[str | None] = _fk("especie_id", "certificaciones_dim_especie.id")
    punto: Mapped[str | None] = mapped_column(String(120))  # punto, cuartel o superficie
    fecha_muestreo: Mapped[date] = mapped_column(Date)
    laboratorio: Mapped[str | None] = mapped_column(String(120))
    archivo_key: Mapped[str | None] = mapped_column(String(200))
    nombre_archivo: Mapped[str | None] = mapped_column(String(250))
    creado_por_id = synonym("created_by")
    creado_en = synonym("created_at")
    tipo: Mapped[TipoAnalisis] = relationship()
    unidad: Mapped[Unidad] = relationship()
    fuente_agua: Mapped[FuenteAgua | None] = relationship()
    especie: Mapped[Especie | None] = relationship()
    resultados: Mapped[list["ResultadoAnalisis"]] = relationship(back_populates="analisis", cascade="all, delete-orphan")

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.fecha_muestreo, self.unidad)


class ResultadoAnalisis(Auditable, Base):
    __tablename__ = "certificaciones_fact_analisisresultado"
    id: Mapped[str] = _pk()
    analisis_id: Mapped[str] = _fk("analisis_id", "certificaciones_fact_analisis.id")
    parametro: Mapped[str] = mapped_column(String(120))
    valor: Mapped[float | None] = mapped_column(Float)
    valor_texto: Mapped[str | None] = mapped_column(String(60))  # "< LD", "Ausencia"
    unidad_medida: Mapped[str | None] = mapped_column(String(45))
    limite_min: Mapped[float | None] = mapped_column(Float)
    limite_max: Mapped[float | None] = mapped_column(Float)
    cumple: Mapped[bool | None] = mapped_column(Boolean)
    analisis: Mapped[Analisis] = relationship(back_populates="resultados")


class Asoex(Auditable, Base):
    """Carga de la Agenda de pesticidas de ASOEX (límites máximos de residuos por país). La más reciente es la vigente."""
    __tablename__ = "certificaciones_dim_asoex"
    id: Mapped[str] = _pk()
    nombre_archivo: Mapped[str] = mapped_column(String(250))
    archivo_key: Mapped[str | None] = mapped_column(String(200))
    fecha: Mapped[date | None] = mapped_column(Date)  # fecha de la planilla (LMR ASOEX 28-09-2026)
    # Por fruta: {fruta: {"paises": [...], "sustancias": n, "proximos_cambios": [...]}}
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)
    cargado_por_id = synonym("created_by")
    cargado_en = synonym("created_at")
    limites: Mapped[list["AsoexLimite"]] = relationship(back_populates="asoex", cascade="all, delete-orphan")


class CartaDestino(Auditable, Base):
    """Carta de mercados de destino de GESEX: a qué países se exporta cada especie en una temporada, por empresa.

    Con ella se preseleccionan los países al comparar un informe de residuos con ASOEX.
    """
    __tablename__ = "certificaciones_dim_cartadestino"
    id: Mapped[str] = _pk()
    empresa_id: Mapped[int | None] = mapped_column("empresa_id", ForeignKey("general_dim_empresa.id"), sort_order=100)
    temporada: Mapped[str | None] = mapped_column(String(45))  # 25-26 (por nombre, como los factores de emisión)
    destinatario: Mapped[str | None] = mapped_column(String(200))  # "0723 Agricola Viento Sur SPA"
    fecha: Mapped[date | None] = mapped_column(Date)
    # {"CEREZAS": ["USA", "UE", "UK", ...]}: especie y países con los nombres de ASOEX
    destinos: Mapped[dict] = mapped_column(JSON, default=dict)
    nombre_archivo: Mapped[str] = mapped_column(String(250))
    archivo_key: Mapped[str | None] = mapped_column(String(200))
    cargado_por_id = synonym("created_by")
    cargado_en = synonym("created_at")
    empresa: Mapped["Empresa | None"] = relationship()


class AsoexLimite(Auditable, Base):
    """Límite máximo de residuo de una sustancia en una fruta para un país (ppm), o condición ST/EX."""
    __tablename__ = "certificaciones_dim_asoexlimite"
    id: Mapped[str] = _pk()
    asoex_id: Mapped[str] = _fk("asoex_id", "certificaciones_dim_asoex.id", index=True)
    fruta: Mapped[str] = mapped_column(String(60))  # CEREZAS, CIRUELAS / LOBESIA BOTRANA
    sustancia: Mapped[str] = mapped_column(String(120))
    tipo_producto: Mapped[str | None] = mapped_column(String(45))  # INSECTICIDA, FUNGICIDA...
    pais: Mapped[str] = mapped_column(String(45))
    ppm: Mapped[float | None] = mapped_column(Float)
    condicion: Mapped[str | None] = mapped_column(String(45))  # ST = sin tolerancia | EX = exento
    carencia_dias: Mapped[int | None] = mapped_column(Integer)
    asoex: Mapped[Asoex] = relationship(back_populates="limites")


# ---------- Auditorías ----------


class Auditoria(Auditable, Base):
    __tablename__ = "certificaciones_fact_auditoria"
    id: Mapped[str] = _pk()
    version_id: Mapped[str] = _fk("versionnorma_id", "certificaciones_dim_versionnorma.id")
    unidad_id: Mapped[int] = _sucursal_id()
    titulo: Mapped[str | None] = mapped_column(String(120))
    fecha: Mapped[date] = mapped_column(Date)  # fecha de inicio
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    auditor: Mapped[str | None] = mapped_column(String(120))
    # Vacío = todas las cláusulas de la versión de la norma (lo normal); las importadas traen las de su planilla
    secciones: Mapped[list] = mapped_column(JSON, default=list)
    estado: Mapped[str] = mapped_column(String(45), default="planificada")  # planificada | en_curso | cerrada
    origen: Mapped[str] = mapped_column(String(45), default="app")  # app | importada
    archivo_origen: Mapped[str | None] = mapped_column(String(250))
    advertencias: Mapped[list | None] = mapped_column(JSON)
    # Al emitir el informe, las no conformidades pasan a los responsables con su plazo
    emitida_en: Mapped[datetime | None] = mapped_column(DateTime)
    emitida_por_id: Mapped[str | None] = _usuario_rol("usuario_emisor_id", nullable=True)
    version: Mapped[VersionNorma] = relationship()
    unidad: Mapped[Unidad] = relationship()
    respuestas: Mapped[list["Respuesta"]] = relationship(back_populates="auditoria", cascade="all, delete-orphan")

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.fecha, self.unidad)


class Respuesta(Auditable, Base):
    __tablename__ = "certificaciones_fact_respuesta"
    __table_args__ = (UniqueConstraint("auditoria_id", "requisito_id", name="uq_respuesta_auditoria_requisito"),)
    id: Mapped[str] = _pk()
    auditoria_id: Mapped[str] = _fk("auditoria_id", "certificaciones_fact_auditoria.id")
    requisito_id: Mapped[str] = _fk("requisito_id", "certificaciones_dim_requisito.id")
    resultado: Mapped[str | None] = mapped_column(String(45))  # si | no | na
    comentario: Mapped[str | None] = mapped_column(Text)
    area_id: Mapped[str | None] = _fk("area_id", "certificaciones_dim_area.id")
    advertencia: Mapped[str | None] = mapped_column(Text)  # detectada al importar, para revisión
    auditoria: Mapped[Auditoria] = relationship(back_populates="respuestas")
    requisito: Mapped[Requisito] = relationship()
    area: Mapped[Area | None] = relationship()


class AuditoriaExterna(Auditable, Base):
    """Informe de una auditoría externa (certificadora), consultado solo por certificaciones.

    Va aparte de las auditorías internas: no genera no conformidades. Los datos se leen del PDF.
    """
    __tablename__ = "certificaciones_fact_auditoriaexterna"
    id: Mapped[str] = _pk()
    protocolo_id: Mapped[str | None] = _fk("protocolo_id", "certificaciones_dim_protocolo.id")
    empresa_id: Mapped[int | None] = mapped_column("empresa_id", ForeignKey("general_dim_empresa.id"), sort_order=100)
    # final | no_conformidades | acciones_correctivas
    tipo_informe: Mapped[str] = mapped_column(String(45), default="final")
    numero: Mapped[str | None] = mapped_column(String(45), index=True)  # ID de auditoría de la certificadora
    titulo: Mapped[str] = mapped_column(String(250))
    entidad: Mapped[str | None] = mapped_column(String(120))
    auditor: Mapped[str | None] = mapped_column(String(120))
    fecha: Mapped[date | None] = mapped_column(Date)
    # Lista de ids de general_dim_sucursal detectadas del PDF (JSON, no llave foránea)
    sucursales_auditadas: Mapped[list] = mapped_column(JSON, default=list)
    creado_por_id = synonym("created_by")
    creado_en = synonym("created_at")
    protocolo: Mapped[Protocolo | None] = relationship()
    versiones: Mapped[list["AuditoriaExternaVersion"]] = relationship(
        back_populates="auditoria", order_by="AuditoriaExternaVersion.numero", cascade="all, delete-orphan")


class AuditoriaExternaVersion(Auditable, Base):
    """Archivo del informe externo. Una versión nueva no borra las anteriores."""
    __tablename__ = "certificaciones_fact_auditoriaexternaversion"
    __table_args__ = (UniqueConstraint("auditoriaexterna_id", "numero", name="uq_auditoriaexternaversion_numero"),)
    id: Mapped[str] = _pk()
    auditoria_externa_id: Mapped[str] = _fk("auditoriaexterna_id", "certificaciones_fact_auditoriaexterna.id")
    numero: Mapped[int] = mapped_column(Integer)
    archivo_key: Mapped[str] = mapped_column(String(200))
    nombre_archivo: Mapped[str] = mapped_column(String(250))
    # Resumen leído del PDF: puntajes, conteo de preguntas, secciones, hallazgos, sitios, productos
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)
    subido_por_id = synonym("created_by")
    subido_en = synonym("created_at")
    auditoria: Mapped[AuditoriaExterna] = relationship(back_populates="versiones")
    subido_por: Mapped[Usuario] = relationship(primaryjoin="foreign(AuditoriaExternaVersion.created_by) == Usuario.id")


class NoConformidad(Auditable, Base):
    __tablename__ = "certificaciones_fact_noconformidad"
    id: Mapped[str] = _pk()
    auditoria_id: Mapped[str] = _fk("auditoria_id", "certificaciones_fact_auditoria.id")
    respuesta_id: Mapped[str | None] = _fk("respuesta_id", "certificaciones_fact_respuesta.id")
    requisito_id: Mapped[str] = _fk("requisito_id", "certificaciones_dim_requisito.id")
    unidad_id: Mapped[int] = _sucursal_id()
    area_id: Mapped[str | None] = _fk("area_id", "certificaciones_dim_area.id")
    descripcion: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str | None] = mapped_column(String(45))  # infraestructura | documental | operacional
    clasificacion: Mapped[str | None] = mapped_column(String(45))  # menor | mayor | critica
    responsable_id: Mapped[str | None] = _usuario_rol("usuario_responsable_id", nullable=True)
    plazo: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(45), default="abierta")  # abierta | en_proceso | cerrada
    reincidente_de_id: Mapped[str | None] = _fk("noconformidad_original_id", "certificaciones_fact_noconformidad.id")
    creada_en = synonym("created_at")
    fecha_deteccion: Mapped[date] = mapped_column(Date)
    cerrada_por_id: Mapped[str | None] = _usuario_rol("usuario_cierre_id", nullable=True)
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Plan de acción que completa el jefe de área
    causa_raiz: Mapped[list | None] = mapped_column(JSON)  # 5 porqués
    accion_correctiva: Mapped[str | None] = mapped_column(Text)  # qué se hace de inmediato
    accion_preventiva: Mapped[str | None] = mapped_column(Text)  # qué se hará para que no vuelva a ocurrir
    plan_por_id: Mapped[str | None] = _usuario_rol("usuario_plan_id", nullable=True)
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
        back_populates="no_conformidad", order_by="AccionCorrectiva.created_at")


class AccionCorrectiva(Auditable, Base):
    """Levantamiento: acción correctiva con evidencia (foto o PDF)."""
    __tablename__ = "certificaciones_fact_accioncorrectiva"
    id: Mapped[str] = _pk()
    no_conformidad_id: Mapped[str] = _fk("noconformidad_id", "certificaciones_fact_noconformidad.id")
    descripcion: Mapped[str] = mapped_column(Text)
    archivo_key: Mapped[str | None] = mapped_column(String(200))
    nombre_archivo: Mapped[str | None] = mapped_column(String(250))
    creada_por_id = synonym("created_by")
    creada_en = synonym("created_at")
    no_conformidad: Mapped[NoConformidad] = relationship(back_populates="acciones")
    creada_por: Mapped[Usuario] = relationship(primaryjoin="foreign(AccionCorrectiva.created_by) == Usuario.id")


# ---------- Medio ambiente ----------


class ConceptoAmbiental(Auditable, Base):
    """Qué se mide: combustibles, electricidad, fertilizantes y materiales reciclados."""
    __tablename__ = "certificaciones_dim_conceptoambiental"
    id: Mapped[str] = _pk()
    codigo: Mapped[str] = mapped_column(String(45), unique=True)  # combustible_diesel, electricidad, carton...
    nombre: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[str] = mapped_column(String(45))  # combustible | electricidad | fertilizante | reciclaje
    unidad_medida: Mapped[str] = mapped_column(String(45))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class FactorEmision(Auditable, Base):
    """Factor por nombre de temporada: el mismo para LH y VS (general_dim_temporada tiene un id por empresa)."""
    __tablename__ = "certificaciones_dim_factoremision"
    id: Mapped[str] = _pk()
    temporada: Mapped[str] = mapped_column(String(45))  # 24-25
    concepto_id: Mapped[str] = _fk("conceptoambiental_id", "certificaciones_dim_conceptoambiental.id")
    factor_kgco2e: Mapped[float] = mapped_column("factor", Float)  # kg CO2e por unidad del concepto
    fuente: Mapped[str | None] = mapped_column(String(250))
    concepto: Mapped[ConceptoAmbiental] = relationship()


class RegistroAmbiental(Auditable, Base):
    """Consumo o reciclaje de una sucursal en una fecha, en la unidad del concepto (L, kWh, kg)."""
    __tablename__ = "certificaciones_fact_registroambiental"
    id: Mapped[str] = _pk()
    unidad_id: Mapped[int] = _sucursal_id()
    concepto_id: Mapped[str] = _fk("conceptoambiental_id", "certificaciones_dim_conceptoambiental.id")
    fecha: Mapped[date] = mapped_column(Date, index=True)
    cantidad: Mapped[float] = mapped_column(Float)
    creado_por_id = synonym("created_by")
    creado_en = synonym("created_at")
    unidad: Mapped[Unidad] = relationship()
    concepto: Mapped[ConceptoAmbiental] = relationship()

    @property
    def temporada_id(self) -> int | None:
        return _temporada_de(self, self.fecha, self.unidad)


# ---------- Historial de cambios ----------


class Historial(Auditable, Base):
    """Quién (created_by) hizo qué y cuándo (created_at). Solo se agrega: nunca se edita ni se borra."""
    __tablename__ = "certificaciones_fact_historial"
    __table_args__ = (Index("ix_historial_created_at", "created_at"),)
    id: Mapped[str] = _pk()
    usuario_id = synonym("created_by")
    fecha_hora = synonym("created_at")
    accion: Mapped[str] = mapped_column(String(45))
    entidad: Mapped[str] = mapped_column(String(45))
    # Id del dato afectado (registro, documento, NC...): sin llave foránea, apunta a una tabla distinta según entidad
    entidad_id: Mapped[str | None] = mapped_column("referencia", String(45))
    detalle: Mapped[dict | None] = mapped_column(JSON)
    usuario: Mapped[Usuario | None] = relationship(primaryjoin="foreign(Historial.created_by) == Usuario.id")


def tablas_propias() -> list[Table]:
    """Tablas de la aplicación (las que crea su migración); excluye las compartidas de la empresa."""
    return [t for t in Base.metadata.sorted_tables if not t.info.get("compartida")]


def _defaults_en_la_base() -> None:
    """Los valores por defecto simples también quedan en MySQL (como id_estado DEFAULT '1' en las tablas de la empresa):
    así un INSERT hecho a mano en Workbench no falla por una columna NOT NULL sin valor. Los JSON los pone la API."""
    for tabla in tablas_propias():
        for col in tabla.columns:
            d = col.default
            if col.server_default is not None or d is None or not d.is_scalar or isinstance(col.type, JSON):
                continue
            v = d.arg
            literal = str(int(v)) if isinstance(v, bool) else str(v) if isinstance(v, int) else "'" + v.replace("'", "''") + "'"
            DefaultClause(text(literal))._set_parent_with_dispatch(col)


_defaults_en_la_base()
