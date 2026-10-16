"""Crea la base de DEMO local (SQLite en privado/demo.db) desde cero.

- Copia de ejemplo de las tablas compartidas (general_* y usuario_*): empresas, sucursales y temporadas con los
  ids de lahornilla_base_normalizada; usuarios ficticios con acceso a la app y sus permisos y sucursales.
- Catálogos según docs/requerimientos.md (protocolos y sus sucursales, categorías, análisis, medio ambiente).
- Importa las planillas reales de ../referencias si existen (quedan solo en privado/, fuera de git).
- Agrega datos FICTICIOS de ejemplo (documentos, análisis, ambiente) con fechas relativas a hoy.

Uso, desde API-CERTIFICACIONES/:  python -m scripts.crear_demo   (o python scripts/crear_demo.py)
"""
import random
import shutil
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from usar_venv import asegurar_venv  # noqa: E402

asegurar_venv()

from config import Config  # noqa: E402

if Config.DB_MOTOR != "sqlite":
    sys.exit("Este script solo crea la base de demo SQLite. No se ejecuta contra Cloud SQL.")

from sqlalchemy import insert, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from utils import almacenamiento  # noqa: E402
from utils.db import Base, SessionLocal, engine  # noqa: E402
from utils.modelos import (  # noqa: E402
    AccionCorrectiva, Analisis, App, Area, Auditoria, Bitacora, Capacitacion, CategoriaDocumento, Certificacion,
    ConceptoAmbiental, Documento, DocumentoVersion, Empresa, Especie, FactorEmision, FuenteAgua, LimiteParametro,
    NoConformidad, Permiso, PlantillaRegistro, Protocolo, Registro, RegistroAmbiental, Requisito, Respuesta,
    ResultadoAnalisis, SucursalTipo, Temporada, TipoAnalisis, Unidad, Usuario, VersionNorma, usuario_apps,
    usuario_permisos, usuario_sucursales,
)
from routers.documentos import es_del_sitio, lugares_conocidos  # noqa: E402
from utils.temporadas import TemporadaLogica, temporada_anterior, temporada_para_fecha  # noqa: E402
from utils.leer_certificado import leer_certificado  # noqa: E402
from utils.no_conformidades import recalcular_reincidencias, sincronizar_nc  # noqa: E402
from utils.servicio_importacion import importar_brcgs, importar_checklist  # noqa: E402
from utils.hora import ahora

HOY = date.today()
random.seed(42)

# Tablas compartidas: ids y nombres de lahornilla_base_normalizada (15 de octubre de 2026), sin direcciones
EMPRESAS = [(1, "LA HORNILLA SPA"), (2, "VIENTO SUR")]
TIPOS_SUCURSAL = [(1, "CAMPO"), (2, "PACKING"), (3, "OTRO"), (4, "VIVERO"), (5, "OFICINA")]
# id, nombre, empresa, tipo. Itahue es de Viento Sur
SUCURSALES = [
    (101, "OFICINA CENTRAL", 1, 5),
    (102, "SAN MANUEL", 1, 1), (103, "SANTA VICTORIA", 1, 1), (104, "CULLIPEUMO", 1, 1), (105, "CAMPO CHOCALAN", 1, 1),
    (106, "SANTA INES", 1, 1), (107, "MAITEN GIGANTE", 1, 1), (108, "HOSPITAL", 1, 1),
    (113, "PACKING PAINE", 1, 2), (114, "PACKING MG", 1, 2), (116, "PACKING SI", 1, 2), (117, "PACKING HO", 1, 2),
    (118, "PLANTA CHOCALAN", 1, 2), (199, "FUNDO QA", 1, 1),
    (201, "ITAHUE", 2, 1),
]
# Claves que usa este script para referirse a cada sucursal
CLAVES_SUCURSAL = {
    "Campo San Manuel": 102, "Campo Santa Victoria": 103, "Campo Cullipeumo": 104, "Campo Chocalán": 105,
    "Campo Santa Inés": 106, "Campo Maitén Gigante": 107, "Campo Hospital": 108, "Packing Paine": 113,
    "Packing MG": 114, "Planta Chocalán": 118, "Campo Itahue": 201,
}
PERMISOS = ["CERTIFICACIONES_ADMIN", "REGISTROS_EDITAR", "NC_EDITAR", "LABORATORIO_EDITAR", "AMBIENTE_EDITAR",
            "CERTIFICACIONES_VER"]
AREAS_PLANTA_CHOCALAN = ["Packing Unitec", "Packing cerezas", "Packing carozos", "Frío 1", "Frío 2", "Cámara 5",
                         "Zona sucia Unitec", "Patio", "Casino", "Baños", "Laboratorios", "Zona de desechos",
                         "Maestranza"]
# Según el cliente (8 de octubre de 2026). Planta: BRC, SMETA, Tesco TMPS, Walmart.
# Campo: SMETA, Tesco TMPS, Walmart, GROW, GRASP, GLOBALG.A.P., LEAF, SPRING, Tesco Nurture.
# FSMA PSR vuelve el 14 de octubre de 2026: LH y VS tienen su carta de conformidad vigente.
PROTOCOLOS = [
    ("BRCGS", "BRCGS", "planta"),
    ("SMETA", "SMETA", "ambos"), ("TESCO_TMPS", "Tesco TMPS", "ambos"), ("WALMART", "Walmart", "ambos"),
    ("GLOBALGAP", "GLOBALG.A.P. (IFA v6 GFS)", "campo"), ("GRASP", "GRASP", "campo"), ("GROW", "GROW", "campo"),
    ("LEAF", "LEAF", "campo"), ("SPRING", "SPRING", "campo"), ("TESCO_NURTURE", "Tesco Nurture", "campo"),
    ("PRIMUSGFS", "PrimusGFS", "planta"), ("FSMA_PSR", "FSMA PSR", "campo"),
]
# Normas de cada sucursal (certificaciones_pivot_sucursal_protocolo). Propuesta del 15 de octubre de 2026;
# SMETA, Tesco TMPS, Walmart y GROW quedan sin sucursales hasta confirmarlo con Loreto
CAMPOS_NORMAS = [102, 103, 104, 105, 106, 107, 108, 201]
NORMAS_POR_SUCURSAL = {
    "GLOBALGAP": CAMPOS_NORMAS, "GRASP": CAMPOS_NORMAS, "SPRING": CAMPOS_NORMAS, "TESCO_NURTURE": CAMPOS_NORMAS,
    "LEAF": CAMPOS_NORMAS, "FSMA_PSR": CAMPOS_NORMAS,
    "PRIMUSGFS": [113, 114],  # packing Santa Victoria (Paine) y Maitén Gigante
    "BRCGS": [118],
}
SECCIONES_BRCGS_V9 = [
    ("1", "Compromiso del equipo directivo"), ("2", "Plan de inocuidad alimentaria: HACCP"),
    ("3", "Sistema de gestión de calidad e inocuidad alimentaria"), ("4", "Normas relativas al establecimiento"),
    ("5", "Control de productos"), ("6", "Control de procesos"), ("7", "Personal"),
    ("8", "Zonas de producción de alto riesgo y cuidados elevados"), ("9", "Requisitos para productos comercializados"),
]
CATEGORIAS = [
    # Documentos fijos (9 de octubre de 2026): los sube certificaciones, sin aprobación ni sucursal.
    # nombre, ámbito, requiere vencimiento, requiere código
    ("Procedimientos", "ambos", False, False),
    ("Análisis de riesgos", "ambos", False, False),
    ("Planes de gestión", "ambos", False, False),
    ("Instructivos", "ambos", False, False),
    # Los certificados son los únicos documentos fijos con vencimiento: alimentan el panel de Vencimientos
    ("Certificados", "ambos", True, False),
]
# Límites de DEMO: no son oficiales (pendiente con el cliente)
# Solo análisis de campo. nombre: (usa fuente de agua, usa especie, límites de DEMO no oficiales)
TIPOS_ANALISIS = {
    "Agua fisicoquímica": (True, False, [("pH", "pH", 6.5, 8.5), ("Conductividad", "µS/cm", None, 750),
                                         ("Nitratos", "mg/L", None, 50)]),
    "Agua microbiológica": (True, False, [("Coliformes fecales", "NMP/100 mL", None, 1000),
                                          ("E. coli", "NMP/100 mL", None, 1000)]),
    "Suelo": (False, True, [("pH", "pH", 5.5, 8.0), ("Materia orgánica", "%", 2, None)]),
    "Hoja": (False, True, [("Nitrógeno", "%", 2.0, 3.2), ("Potasio", "%", 1.0, 2.0)]),
    "Fruta": (False, True, [("Calcio", "mg/100 g", 4, None)]),
    "MRL": (False, False, [("Clorpirifos", "mg/kg", None, 0.01), ("Captan", "mg/kg", None, 3.0)]),
}
ESPECIES = ["Cerezo", "Ciruelo", "Duraznero", "Nectarino"]
# Conceptos de medio ambiente: código, nombre, categoría, unidad, kg CO2e por unidad (valor referencial de demo)
CONCEPTOS_AMBIENTALES = [
    ("combustible_diesel", "Diésel", "combustible", "L", 2.68),
    ("combustible_gasolina", "Bencina", "combustible", "L", 2.31),
    ("combustible_gas", "Gas", "combustible", "kg", 2.94),
    ("electricidad", "Electricidad", "electricidad", "kWh", 0.29),
    ("fertilizante_n", "Fertilizante nitrogenado", "fertilizante", "kg", 5.88),
    ("fertilizante_no_n", "Fertilizante no nitrogenado", "fertilizante", "kg", 0.6),
    ("plastico_film", "Plástico film", "reciclaje", "kg", None),
    ("envases_agroquimicos", "Envases de agroquímicos (triple lavado)", "reciclaje", "kg", None),
    ("carton", "Cartón", "reciclaje", "kg", None),
    ("bins_plasticos", "Bins plásticos", "reciclaje", "kg", None),
]


def pdf_ficticio(titulo: str) -> bytes:
    """PDF mínimo de una página con un título, para que la demo tenga archivos descargables."""
    texto = titulo.encode("latin-1", "replace").decode("latin-1").replace("(", "[").replace(")", "]")
    contenido = f"BT /F1 18 Tf 60 760 Td ({texto}) Tj 0 -30 Td /F1 11 Tf (Documento ficticio de demostracion) Tj ET"
    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(contenido.encode('latin-1'))} >>\nstream\n{contenido}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    salida += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return salida


def archivo_demo(prefijo: str, titulo: str) -> tuple[str, str]:
    nombre = f"{titulo}.pdf"
    clave = almacenamiento.nueva_clave(prefijo, nombre)
    almacenamiento.escribir_local(clave, pdf_ficticio(titulo))
    return clave, nombre


def temporada_de(db: Session, fecha: date) -> TemporadaLogica:
    return temporada_para_fecha(db, fecha, 1)


def _id_corto(*partes: str) -> str:
    """Id determinista (las tablas del portal usan UUID): así el usuario elegido en la demo sobrevive a regenerarla."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "certificaciones-demo/" + "/".join(partes)))


def crear_generales(db: Session) -> dict[str, Unidad]:
    """Copia de ejemplo de las tablas compartidas (en GCP ya existen y no se tocan)."""
    db.add_all([Empresa(id=i, nombre=n) for i, n in EMPRESAS])
    db.add_all([SucursalTipo(id=i, nombre=n) for i, n in TIPOS_SUCURSAL])
    db.flush()
    db.add_all([Unidad(id=i, nombre=n, empresa_id=e, tipo_id=t) for i, n, e, t in SUCURSALES])
    # Temporadas por empresa, mayo a abril; las anteriores a 24-25 no tienen fechas (como en la tabla real)
    n = 1
    for empresa_id, _ in EMPRESAS:
        for anio in range(2022, HOY.year + 1):
            con_fechas = anio >= 2024
            db.add(Temporada(id=n, temporada=f"{anio % 100:02d}-{(anio + 1) % 100:02d}", empresa_id=empresa_id,
                             inicio=date(anio, 5, 1) if con_fechas else None,
                             fin=date(anio + 1, 4, 30) if con_fechas else None))
            n += 1
    db.add(App(id=Config.APP_ID, nombre="CERTIFICACIONES", descripcion="Certificaciones VS y LH"))
    db.flush()
    for codigo in PERMISOS:
        db.add(Permiso(id=_id_corto("permiso", codigo), nombre=codigo, app_id=Config.APP_ID, id_estado=1))
    db.flush()
    return {clave: db.get(Unidad, i) for clave, i in CLAVES_SUCURSAL.items()}


def crear_usuario(db: Session, clave: str, nombre: str, permisos: list[str], sucursales: list[Unidad]) -> Usuario:
    """Usuario ficticio con acceso a la app. La clave no es un hash bcrypt: no se puede iniciar sesión con él."""
    usuario = Usuario(id=_id_corto("usuario", clave), usuario=f"demo.{clave}", correo=f"{clave}@demo.local",
                      clave="!sin-clave", nombre=nombre, id_estado=1)
    db.add(usuario)
    db.flush()
    db.execute(insert(usuario_apps).values(id=_id_corto("app", clave), id_usuario=usuario.id, id_app=Config.APP_ID))
    for codigo in permisos:
        db.execute(insert(usuario_permisos).values(id=_id_corto("pu", clave, codigo)[:25], id_usuario=usuario.id,
                                                   id_permiso=_id_corto("permiso", codigo)))
    for s in sucursales:
        db.execute(insert(usuario_sucursales).values(id_sucursal=s.id, id_usuario=usuario.id))
    return usuario


def crear_catalogos(db: Session) -> dict:
    u = crear_generales(db)
    lh, vs = db.get(Empresa, 1), db.get(Empresa, 2)

    for area in AREAS_PLANTA_CHOCALAN:
        db.add(Area(unidad_id=u["Planta Chocalán"].id, nombre=area))
    for unidad in ("Campo Chocalán", "Campo Itahue", "Campo Maitén Gigante"):
        for n in range(1, 5):
            db.add(Area(unidad_id=u[unidad].id, nombre=f"Cuartel {n} (ficticio)"))

    for codigo, nombre, ambito in PROTOCOLOS:
        db.add(Protocolo(codigo=codigo, nombre=nombre, ambito=ambito,
                         unidades=[db.get(Unidad, i) for i in NORMAS_POR_SUCURSAL.get(codigo, [])]))
    db.flush()
    brc = db.scalar(select(Protocolo).where(Protocolo.codigo == "BRCGS"))
    db.add(VersionNorma(protocolo_id=brc.id, nombre="v9", secciones=[{"codigo": c, "titulo": t}
                                                                     for c, t in SECCIONES_BRCGS_V9]))

    for i, (nombre, ambito, venc, cod) in enumerate(CATEGORIAS):
        db.add(CategoriaDocumento(nombre=nombre, ambito=ambito, requiere_vencimiento=venc, requiere_codigo=cod,
                                  orden=i))
    db.add_all([Especie(nombre=nombre) for nombre in ESPECIES])
    for nombre, (usa_fuente, usa_especie, limites) in TIPOS_ANALISIS.items():
        tipo = TipoAnalisis(nombre=nombre, ambito="campo", usa_fuente_agua=usa_fuente, usa_especie=usa_especie)
        db.add(tipo)
        db.flush()
        for parametro, um, minimo, maximo in limites:
            db.add(LimiteParametro(tipo_analisis_id=tipo.id, parametro=parametro, unidad_medida=um,
                                   minimo=minimo, maximo=maximo, norma="Valor de demo (por confirmar)"))

    db.add_all([FuenteAgua(nombre="Pozo 1 Chocalán (ficticio)", unidad_id=u["Campo Chocalán"].id),
                FuenteAgua(nombre="Canal Itahue (ficticio)", unidad_id=u["Campo Itahue"].id)])
    for codigo, nombre, categoria, um, _ in CONCEPTOS_AMBIENTALES:
        db.add(ConceptoAmbiental(codigo=codigo, nombre=nombre, categoria=categoria, unidad_medida=um, activo=True))
    db.flush()
    conceptos = {c.codigo: c for c in db.scalars(select(ConceptoAmbiental))}
    # El factor es el mismo para LH y VS: uno por nombre de temporada
    for nombre in sorted({t.temporada for t in db.scalars(select(Temporada).where(Temporada.inicio.is_not(None)))}):
        for codigo, _, _, _, factor in CONCEPTOS_AMBIENTALES:
            if factor is not None:
                db.add(FactorEmision(temporada=nombre, concepto_id=conceptos[codigo].id, factor_kgco2e=factor,
                                     fuente="Valor referencial de demo (fuente oficial por confirmar)"))

    con_normas = sorted({i for ids in NORMAS_POR_SUCURSAL.values() for i in ids})
    usuarios = {
        "cert": crear_usuario(db, "certificaciones", "Equipo Certificaciones", ["CERTIFICACIONES_ADMIN"], []),
        "planta": crear_usuario(db, "planta", "Jefe de área · Planta Chocalán", ["REGISTROS_EDITAR", "NC_EDITAR"],
                                [u["Planta Chocalán"]]),
        "campo": crear_usuario(db, "campo", "Jefe de campo · Chocalán e Itahue",
                               ["REGISTROS_EDITAR", "NC_EDITAR", "LABORATORIO_EDITAR", "AMBIENTE_EDITAR"],
                               [u["Campo Chocalán"], u["Campo Itahue"]]),
        "vs": crear_usuario(db, "vs", "Supervisor · VS Itahue", ["REGISTROS_EDITAR", "AMBIENTE_EDITAR"],
                            [u["Campo Itahue"]]),
        "auditor": crear_usuario(db, "auditor", "Auditor externo (solo lectura)", ["CERTIFICACIONES_VER"],
                                 [db.get(Unidad, i) for i in con_normas]),
    }
    db.commit()
    return {"unidades": u, "usuarios": usuarios, "lh": lh, "vs": vs}


def importar_referencias(db: Session, cert: Usuario) -> None:
    if not Config.REFERENCIAS_DIR.is_dir():
        print("  (sin carpeta referencias/: se omiten las planillas reales)")
        return
    for ruta in sorted(Config.REFERENCIAS_DIR.glob("checklist/*/*.xlsx")):
        try:
            r = importar_checklist(db, ruta.read_bytes(), ruta.name, cert, confirmar=True)
        except ValueError as exc:
            print(f"  (se omite {ruta.parent.name}/{ruta.name}: {exc})")
            continue
        print(f"  {r['protocolo']} {r['version']}: {r['puntos']} puntos ({r['nuevos']} nuevos), "
              f"{len(r['secciones'])} secciones, {len(r['advertencias'])} advertencias")
    for ruta in sorted(Config.REFERENCIAS_DIR.glob("AI*.xlsx")):
        r = importar_brcgs(db, ruta.read_bytes(), ruta.name, cert, confirmar=True)
        for h in r["hojas"]:
            print(f"  BRCGS {ruta.name} / {h['hoja']}: {h['fecha']} {h['si']} sí, {h['no']} no, "
                  f"{len(h['advertencias'])} advertencias {h['errores'] or ''}")


def datos_ficticios(db: Session, ctx: dict) -> None:
    u, us, lh, vs = ctx["unidades"], ctx["usuarios"], ctx["lh"], ctx["vs"]
    cert = us["cert"]
    cat = {c.nombre: c for c in db.scalars(select(CategoriaDocumento))}
    prot = {p.codigo: p for p in db.scalars(select(Protocolo))}

    def doc(categoria, empresa, seccion, titulo, codigo=None, versiones_previas=0, vence=None):
        d = Documento(categoria_id=cat[categoria].id, empresa_id=empresa.id, seccion=seccion, titulo=titulo,
                      codigo=codigo, creado_por_id=cert.id)
        db.add(d)
        db.flush()
        for n in range(1, versiones_previas + 2):
            clave, nombre = archivo_demo("documentos", f"{codigo + ' ' if codigo else ''}{titulo} v{n}")
            subido = ahora() - timedelta(days=400 - n * 120)
            db.add(DocumentoVersion(
                documento_id=d.id, numero=n, archivo_key=clave, nombre_archivo=nombre, tipo_contenido="application/pdf",
                version_texto=f"{n:02d}", fecha_emision=subido.date(), estado="aprobado", subido_por_id=cert.id,
                fecha_vencimiento=(vence if n == versiones_previas + 1 else subido.date() + timedelta(days=365))
                if vence else None,
                subido_en=subido, revisado_por_id=cert.id, revisado_en=subido,
            ))
        return d

    pc = u["Planta Chocalán"]
    # Empresariales (códigos OC)
    doc("Procedimientos", lh, "empresarial", "Procedimiento de control de plagas", codigo="P OC CE 29", versiones_previas=2)
    doc("Procedimientos", lh, "empresarial", "Aprobación de proveedores", codigo="P OC CE 26")
    doc("Procedimientos", lh, "empresarial", "Contaminación cruzada", codigo="P OC CE 20", versiones_previas=1)
    doc("Procedimientos", lh, "empresarial", "Control de documentos y registros", codigo="P OC CE 01")
    doc("Planes de gestión", lh, "empresarial", "Plan de gestión de crisis", codigo="P OC CE 33")
    # Planta
    doc("Análisis de riesgos", lh, "planta", "Evaluación de riesgos de materias primas", codigo="DPL 23",
        versiones_previas=1)
    doc("Análisis de riesgos", lh, "planta", "Análisis de riesgos de cuerpos extraños")
    doc("Instructivos", lh, "planta", "Instructivo de limpieza de líneas de proceso")
    doc("Planes de gestión", lh, "planta", "Plan de control de alérgenos")
    # Campo
    doc("Análisis de riesgos", lh, "campo", "Evaluación de riesgos del sitio y del agua", versiones_previas=1)
    doc("Planes de gestión", lh, "campo", "Plan de gestión de residuos y envases")
    doc("Instructivos", lh, "campo", "Instructivo de calibración de pulverizadoras")
    doc("Instructivos", vs, "campo", "Instructivo de higiene en cosecha")
    doc("Procedimientos", vs, "empresarial", "Procedimiento de trazabilidad", codigo="P OC VS 05")
    # Certificados (con vencimiento): los reales de referencias/certificados; sin ellos, ficticios
    if not certificados_reales(db, ctx, cat["Certificados"]):
        certificados_ficticios(db, ctx, doc, prot)

    for tema, unidad, dias_fecha, dias_vence, relator in (
        ("Food defense", pc, -20, 345, "Equipo Certificaciones"),
        ("Primeros auxilios", u["Campo Itahue"], -340, 25, "Mutual (ficticio)"),
        ("Manejo de productos fitosanitarios", u["Campo Chocalán"], -200, 165, "Asesor externo (ficticio)"),
        ("Higiene y buenas prácticas de manufactura", pc, -360, 5, "Equipo Certificaciones"),
    ):
        db.add(Capacitacion(unidad_id=unidad.id, tema=tema, fecha=HOY + timedelta(days=dias_fecha), relator=relator,
                            asistentes=["Trabajador A", "Trabajador B", "Trabajador C"],
                            vigente_hasta=HOY + timedelta(days=dias_vence), creado_por_id=cert.id))

    # Laboratorio
    tipos = {t.nombre: t for t in db.scalars(select(TipoAnalisis))}
    limites = {}
    for lp in db.scalars(select(LimiteParametro)):
        limites.setdefault(lp.tipo_analisis_id, []).append(lp)
    pozo, canal = db.scalars(select(FuenteAgua).order_by(FuenteAgua.id)).all()

    especies = {e.nombre: e for e in db.scalars(select(Especie))}

    def analisis(tipo, unidad, dias, fuera=(), fuente=None, punto=None, por=cert, especie=None):
        t = tipos[tipo]
        clave, nombre = archivo_demo("analisis", f"Informe {tipo} {unidad.nombre} {HOY + timedelta(days=dias)}")
        a = Analisis(tipo_analisis_id=t.id, unidad_id=unidad.id, fuente_agua_id=fuente.id if fuente else None,
                     especie_id=especies[especie].id if especie else None,
                     punto=punto, fecha_muestreo=HOY + timedelta(days=dias), laboratorio="Laboratorio (ficticio)",
                     archivo_key=clave,
                     nombre_archivo=nombre, creado_por_id=por.id)
        for lp in limites[t.id]:
            if lp.parametro in fuera:
                valor = (lp.maximo or 0) * 2.4 + 1 if lp.maximo is not None else (lp.minimo or 0) * 0.5
            else:
                bajo, alto = lp.minimo or 0, lp.maximo if lp.maximo is not None else (lp.minimo or 1) * 2
                valor = round(random.uniform(bajo, alto * 0.8 if alto else 0), 2)
            cumple = (lp.minimo is None or valor >= lp.minimo) and (lp.maximo is None or valor <= lp.maximo)
            a.resultados.append(ResultadoAnalisis(parametro=lp.parametro, valor=round(valor, 2),
                                                  unidad_medida=lp.unidad_medida, limite_min=lp.minimo,
                                                  limite_max=lp.maximo, cumple=cumple))
        db.add(a)

    analisis("Agua microbiológica", u["Campo Itahue"], -12, fuera=("E. coli",), fuente=canal, punto="Bocatoma",
             por=us["campo"])
    analisis("Agua fisicoquímica", u["Campo Itahue"], -12, fuente=canal, punto="Bocatoma")
    analisis("Agua microbiológica", u["Campo Chocalán"], -50, fuente=pozo, punto="Pozo 1")
    analisis("Suelo", u["Campo Chocalán"], -90, punto="Cuartel 2 (ficticio)", especie="Cerezo")
    analisis("Hoja", u["Campo Maitén Gigante"], -60, punto="Cuartel 1 (ficticio)", especie="Duraznero")
    analisis("Hoja", u["Campo Itahue"], -45, fuera=("Nitrógeno",), punto="Cuartel 3 (ficticio)", especie="Nectarino")
    analisis("Fruta", u["Campo Chocalán"], -25, punto="Cuartel 1 (ficticio)", especie="Ciruelo")
    analisis("MRL", u["Campo Chocalán"], -200, punto="Lote cerezas")

    # Medio ambiente: temporada anterior completa y la actual hasta el mes pasado (datos FICTICIOS).
    # Estacionalidad agrícola (temporada mayo-abril) y una tendencia mixta para que la comparación muestre algo:
    # diésel y fertilizante N bajan, electricidad y gas suben, reciclaje sube.
    conceptos = {c.codigo: c for c in db.scalars(select(ConceptoAmbiental))}
    materiales = [c for c in conceptos.values() if c.categoria == "reciclaje"]
    base_consumo = {"combustible_diesel": 1800, "combustible_gasolina": 350, "combustible_gas": 120,
                    "electricidad": 26000, "fertilizante_n": 900, "fertilizante_no_n": 600}
    # Multiplicador por mes calendario (1 = enero): cosecha nov-mar, frío en verano, calefacción en invierno, abonos sep-dic
    estacional = {
        "combustible_diesel": [1.5, 1.4, 1.2, 0.8, 0.6, 0.5, 0.5, 0.6, 0.9, 1.1, 1.3, 1.5],
        "combustible_gasolina": [1.2, 1.2, 1.1, 0.9, 0.8, 0.8, 0.8, 0.8, 0.9, 1.0, 1.1, 1.2],
        "combustible_gas": [0.4, 0.4, 0.6, 1.0, 1.5, 1.9, 2.0, 1.8, 1.3, 0.9, 0.6, 0.5],
        "electricidad": [1.6, 1.6, 1.3, 0.8, 0.6, 0.6, 0.6, 0.7, 0.8, 1.0, 1.3, 1.5],
        "fertilizante_n": [0.3, 0.2, 0.3, 0.4, 0.3, 0.2, 0.3, 0.8, 1.9, 2.2, 1.8, 1.0],
        "fertilizante_no_n": [0.5, 0.4, 0.6, 0.9, 0.8, 0.5, 0.4, 0.7, 1.4, 1.6, 1.3, 0.9],
    }
    tendencia_actual = {"combustible_diesel": 0.90, "combustible_gasolina": 0.96, "combustible_gas": 1.06,
                        "electricidad": 1.09, "fertilizante_n": 0.85, "fertilizante_no_n": 0.97}
    t_hoy = temporada_de(db, HOY)
    t_prev = temporada_anterior(db, t_hoy)
    meses_demo: list[tuple[TemporadaLogica, date]] = []
    for t, hasta in ((t_prev, t_prev.fin), (t_hoy, date(HOY.year, HOY.month, 1) - timedelta(days=1))):
        mes = t.inicio
        while mes <= hasta:
            meses_demo.append((t, mes))
            mes = date(mes.year + (mes.month == 12), mes.month % 12 + 1, 1)
    escala_unidad = ((u["Campo Chocalán"], 1.0), (u["Planta Chocalán"], 1.6), (u["Campo Itahue"], 0.7))
    for unidad, escala in escala_unidad:
        for t, mes in meses_demo:
            es_actual = t.id == t_hoy.id
            fecha = date(mes.year, mes.month, 15)
            for concepto, base in base_consumo.items():
                if unidad.tipo == "planta" and concepto.startswith("fertilizante"):
                    continue
                factor = estacional[concepto][mes.month - 1] * (tendencia_actual[concepto] if es_actual else 1.0)
                db.add(RegistroAmbiental(unidad_id=unidad.id, concepto_id=conceptos[concepto].id, fecha=fecha,
                                         cantidad=round(base * escala * factor * random.uniform(0.92, 1.08)),
                                         creado_por_id=cert.id))
            for material in materiales:
                db.add(RegistroAmbiental(unidad_id=unidad.id, concepto_id=material.id, fecha=fecha,
                                         cantidad=round(random.uniform(60, 220) * escala * (1.18 if es_actual else 1.0)),
                                         creado_por_id=cert.id))
    db.commit()


def certificados_ficticios(db: Session, ctx: dict, doc, prot: dict) -> None:
    """Sin referencias/certificados: 7 certificados inventados con fechas relativas a hoy."""
    u, lh, vs = ctx["unidades"], ctx["lh"], ctx["vs"]
    pc = u["Planta Chocalán"]
    doc("Certificados", lh, "planta", "Certificado BRCGS Planta Chocalán", vence=HOY + timedelta(days=48), versiones_previas=1)
    doc("Certificados", lh, "campo", "Certificado GLOBALG.A.P. multisitio LH", vence=HOY + timedelta(days=210))
    doc("Certificados", lh, "planta", "Certificado PrimusGFS Packing Maitén Gigante", vence=HOY - timedelta(days=12))
    doc("Certificados", lh, "planta", "Certificado de calibración de balanzas", vence=HOY + timedelta(days=5))
    doc("Certificados", lh, "planta", "Resolución sanitaria Planta Chocalán", vence=HOY + timedelta(days=25))
    doc("Certificados", lh, "campo", "Certificado de análisis de agua de riego", vence=HOY + timedelta(days=55))
    doc("Certificados", vs, "campo", "Certificado GLOBALG.A.P. VS", vence=HOY + timedelta(days=120))
    db.flush()

    db.add(Certificacion(protocolo_id=prot["BRCGS"].id, empresa_id=lh.id, entidad_certificadora="Certificadora (ficticia)",
                         fecha_auditoria=HOY - timedelta(days=317), resultado="Grado AA", vigente_hasta=HOY + timedelta(days=48),
                         unidad_id=pc.id))
    db.add(Certificacion(protocolo_id=prot["GLOBALGAP"].id, empresa_id=lh.id, entidad_certificadora="Certificadora (ficticia)",
                         fecha_auditoria=HOY - timedelta(days=150), resultado="Aprobado", vigente_hasta=HOY + timedelta(days=210)))
    db.add(Certificacion(protocolo_id=prot["PRIMUSGFS"].id, empresa_id=lh.id, entidad_certificadora="Certificadora (ficticia)",
                         fecha_auditoria=HOY - timedelta(days=377), resultado="96 %", vigente_hasta=HOY - timedelta(days=12),
                         unidad_id=u["Packing MG"].id))
    db.add(Certificacion(protocolo_id=prot["GLOBALGAP"].id, empresa_id=vs.id, entidad_certificadora="Certificadora (ficticia)",
                         fecha_auditoria=HOY - timedelta(days=200), resultado="Aprobado", vigente_hasta=HOY + timedelta(days=120)))


def certificados_reales(db: Session, ctx: dict, categoria: CategoriaDocumento) -> bool:
    """Carga los certificados reales de referencias/certificados (quedan solo en privado/, fuera de git)."""
    carpeta = Config.REFERENCIAS_DIR / "certificados"
    rutas = sorted(carpeta.glob("*.pdf")) if carpeta.is_dir() else []
    if not rutas:
        return False
    cert = ctx["usuarios"]["cert"]
    empresas = {e.codigo: e for e in db.scalars(select(Empresa))}
    protocolos = {p.codigo: p for p in db.scalars(select(Protocolo))}
    sucursales = list(db.scalars(select(Unidad)))
    for ruta in rutas:
        contenido = ruta.read_bytes()
        r = leer_certificado(contenido, ruta.name, lugares_conocidos(sucursales))
        if not (r.protocolo in protocolos and r.empresa in empresas and r.vigente_hasta):
            print(f"  (se omite {ruta.name}: faltan {r.no_encontrados})")
            continue
        empresa, protocolo = empresas[r.empresa], protocolos[r.protocolo]
        unidades = []
        for sitio in r.sitios:
            candidatas = [x for x in sucursales if es_del_sitio(x, sitio) and x.empresa_id == empresa.id]
            elegida = next((x for x in candidatas if protocolo.aplica_a(x)), candidatas[0] if candidatas else None)
            if elegida:
                unidades.append(elegida)
        titulo = f"Certificado {protocolo.nombre} {empresa.codigo}" + (f" · {r.operacion}" if r.operacion else "")
        seccion = protocolo.ambito if protocolo.ambito in ("campo", "planta") else "campo"
        d = Documento(categoria_id=categoria.id, empresa_id=empresa.id, seccion=seccion, titulo=titulo,
                      creado_por_id=cert.id)
        db.add(d)
        db.flush()
        clave = almacenamiento.nueva_clave("documentos", ruta.name)
        almacenamiento.escribir_local(clave, contenido)
        subido = ahora() - timedelta(days=30)
        v = DocumentoVersion(
            documento_id=d.id, numero=1, archivo_key=clave, nombre_archivo=ruta.name, tipo_contenido="application/pdf",
            fecha_emision=date.fromisoformat(r.fecha_decision) if r.fecha_decision else None,
            fecha_vencimiento=date.fromisoformat(r.vigente_hasta), estado="aprobado", subido_por_id=cert.id,
            subido_en=subido, revisado_por_id=cert.id, revisado_en=subido)
        db.add(v)
        db.flush()
        desde = date.fromisoformat(r.vigente_desde) if r.vigente_desde else None
        db.add(Certificacion(
            protocolo_id=protocolo.id, empresa_id=empresa.id, documento_version_id=v.id,
            numero=r.numero, norma_version=r.norma_version, entidad_certificadora=r.entidad, vigente_desde=desde,
            vigente_hasta=v.fecha_vencimiento, resultado=r.puntaje, productos=r.productos,
            unidad_id=unidades[0].id if len(unidades) == 1 else None,
            fecha_auditoria=date.fromisoformat(r.fecha_auditoria) if r.fecha_auditoria else None))
        print(f"  {titulo}: N° {r.numero}, vence {r.vigente_hasta}, sucursales {[x.nombre for x in unidades]}")
    return True


def demo_auditorias(db: Session, ctx: dict) -> None:
    """Completa el ciclo con las NC importadas y planifica el programa de la temporada actual."""
    u, us = ctx["unidades"], ctx["usuarios"]
    pc = u["Planta Chocalán"]
    t_actual = temporada_de(db, HOY)
    brc = db.scalar(select(VersionNorma).join(Protocolo).where(Protocolo.codigo == "BRCGS"))
    areas = {a.nombre: a for a in db.scalars(select(Area).where(Area.unidad_id == pc.id))}

    # Clasificación y responsables de ejemplo para las NC importadas
    pistas = [("palomas", "Laboratorios"), ("zona sucia", "Zona sucia Unitec"), ("moho", "Frío 2"),
              ("casino", "Casino"), ("cerezas", "Packing cerezas"), ("carozos", "Packing carozos"),
              ("patio", "Patio"), ("unitec", "Packing Unitec"), ("baños", "Baños"), ("frio", "Frío 1")]
    for nc in db.scalars(select(NoConformidad).where(NoConformidad.unidad_id == pc.id)):
        texto = (nc.descripcion or "").lower()
        area = next((areas[a] for clave, a in pistas if clave in texto), None)
        nc.area_id = area.id if area else None
        nc.tipo = "documental" if nc.requisito.codigo.startswith("9") else "infraestructura"
        nc.clasificacion = "mayor" if nc.requisito.nivel == "fundamental" or nc.reincidente_de_id else "menor"
        nc.responsable_id = us["planta"].id
        nc.plazo = nc.fecha_deteccion + timedelta(days=28)

    # Plan de acción del jefe de área: uno enviado y otro a medio llenar
    for codigo, enviado in (("4.1.3", True), ("4.4.4", False)):
        nc = db.scalar(select(NoConformidad).join(Requisito).join(Auditoria)
                       .where(Requisito.codigo == codigo, Auditoria.fecha >= HOY - timedelta(days=60)))
        if nc is None:
            continue
        nc.causa_raiz = (["Hay aves dentro de la zona de laboratorios.", "Hay aberturas sin malla en el techo.",
                          "La malla se dañó en el último temporal.", "No hay inspección periódica de techos.",
                          "El plan de mantención no incluye techos ni mallas."] if enviado
                         else ["Hay moho en el cielo de las cámaras.", "Se acumula humedad cerca de los ventiladores."])
        nc.accion_correctiva = "Limpieza y sanitización de la zona; reparación de la malla (texto ficticio)." if enviado else None
        nc.accion_preventiva = ("Incluir techos y mallas en la inspección mensual del plan de mantención "
                                "(texto ficticio).") if enviado else None
        nc.plan_por_id, nc.plan_en = us["planta"].id, ahora() - timedelta(days=2)
        if enviado:
            # Loreto revisó y no quedó conforme: se la devolvió al jefe de área (1 reincidencia)
            nc.estado = "en_proceso"
            nc.reincidencias = 1
            nc.revisiones = [{"fecha": (ahora() - timedelta(hours=20)).isoformat(timespec="minutes"),
                              "por": us["cert"].nombre, "resultado": "no_cumple",
                              "observacion": "La acción preventiva no indica responsable ni fecha, y falta la "
                                             "foto de la malla reparada (texto ficticio)."}]

    # Una NC de marzo cerrada con evidencia, otra en proceso
    marzo = db.scalars(select(NoConformidad).join(Requisito).where(Requisito.codigo.in_(["4.4.6", "9.6.2"]))).all()
    for nc in marzo:
        clave, nombre = archivo_demo("evidencias", f"Evidencia levantamiento {nc.requisito.codigo}")
        db.add(AccionCorrectiva(no_conformidad_id=nc.id, creada_por_id=us["planta"].id, archivo_key=clave,
                                nombre_archivo=nombre,
                                descripcion="Acción correctiva ejecutada (texto ficticio de demostración)."))
        nc.estado = "cerrada" if nc.requisito.codigo == "4.4.6" else "en_proceso"
        if nc.estado == "cerrada":
            nc.cerrada_por_id, nc.cerrada_en = us["cert"].id, ahora() - timedelta(days=100)

    # Programa anual: una auditoría BRCGS planificada con todas sus cláusulas
    inicio = HOY + timedelta(days=20)
    db.add(Auditoria(version_id=brc.id, unidad_id=pc.id, fecha=inicio,
                     fecha_fin=inicio + timedelta(days=4), titulo=f"Auditoría interna BRCGS {t_actual.nombre} · Planta Chocalán",
                     auditor="Equipo Certificaciones", secciones=[], estado="planificada", origen="app"))

    # Auditoría GLOBALG.A.P. en curso en Campo Itahue, con algunas respuestas
    gg = db.scalar(select(VersionNorma).join(Protocolo).where(Protocolo.codigo == "GLOBALGAP"))
    if gg:
        # Todas las cláusulas; se trabaja una por día (ya van FV 01, 02, 03 y 20)
        aud = Auditoria(version_id=gg.id, unidad_id=u["Campo Itahue"].id,
                        fecha=HOY - timedelta(days=3), fecha_fin=HOY + timedelta(days=4),
                        titulo=f"Auditoría interna GLOBALG.A.P. {t_actual.nombre} · Campo Itahue",
                        auditor="Equipo Certificaciones", secciones=[], estado="en_curso", origen="app")
        db.add(aud)
        db.flush()
        reqs = [r for r in gg.requisitos if r.seccion in ("FV 01", "FV 02", "FV 03", "FV 20")]
        for n, req in enumerate(reqs):
            resultado = "no" if n in (3, 11) else ("na" if n % 9 == 8 else "si")
            resp = Respuesta(auditoria_id=aud.id, requisito_id=req.id, resultado=resultado,
                             comentario="Hallazgo de ejemplo (ficticio)" if resultado == "no" else None)
            db.add(resp)
            db.flush()
            sincronizar_nc(db, aud, resp)
        inicio = HOY + timedelta(days=45)
        db.add(Auditoria(version_id=gg.id, unidad_id=u["Campo Chocalán"].id,
                         fecha=inicio, fecha_fin=inicio + timedelta(days=5),
                         titulo=f"Auditoría interna GLOBALG.A.P. {t_actual.nombre} · Campo Chocalán",
                         auditor="Equipo Certificaciones", secciones=[], estado="planificada", origen="app"))
    db.commit()

    for nc in db.scalars(select(NoConformidad)):
        recalcular_reincidencias(db, nc.requisito_id, nc.unidad_id)
    db.commit()


def firma_ficticia() -> tuple[str, str]:
    """PNG con un trazo, para simular una firma hecha en pantalla."""
    import io
    import math

    from PIL import Image, ImageDraw
    imagen = Image.new("RGB", (360, 120), "white")
    trazo = ImageDraw.Draw(imagen)
    puntos = [(20 + x, 60 + 28 * math.sin(x / 18) * math.cos(x / 47)) for x in range(0, 320, 3)]
    trazo.line(puntos, fill=(20, 40, 90), width=3)
    salida = io.BytesIO()
    imagen.save(salida, "PNG")
    clave = almacenamiento.nueva_clave("registros", "firma.png")
    almacenamiento.escribir_local(clave, salida.getvalue())
    return clave, "firma.png"


def _valor_ejemplo(tipo: str, n: int, fecha_base: date):
    if tipo == "fecha":
        return (fecha_base + timedelta(days=n * 3)).isoformat()
    if tipo == "numero":
        return 10 + n * 5
    if tipo == "si_no":
        return n % 4 != 3
    return f"Ejemplo {n + 1}"


def _llenar_ejemplo(campos: list[dict], firma: dict, completo: bool = True) -> dict:
    """Valores ficticios coherentes con cada tipo de campo, para mostrar registros llenos en la demo."""
    valores: dict = {}
    base = HOY.replace(day=1) - timedelta(days=30)
    for c in campos:
        if c["tipo"] == "tabla":
            filas = 4 if completo else 1
            valores[c["id"]] = [
                {col["id"]: ("Trabajador de ejemplo" if "responsable" in col["etiqueta"].lower()
                             else _valor_ejemplo(col["tipo"], n, base)) for col in c["columnas"]}
                for n in range(filas)]
        elif c["tipo"] == "checklist":
            items = c["items"] if completo else c["items"][:3]
            valores[c["id"]] = {it["id"]: {"r": "no" if k % 6 == 5 else "si",
                                           "obs": "Se corrige en la semana" if k % 6 == 5 else ""}
                                for k, it in enumerate(items)}
        elif c["tipo"] == "firma":
            if completo:
                valores[c["id"]] = firma
        elif c["tipo"] in ("foto", "archivo"):
            continue
        elif c["tipo"] == "fecha":
            valores[c["id"]] = HOY.isoformat()
        elif completo or c is campos[0]:
            valores[c["id"]] = _valor_ejemplo(c["tipo"], 0, base)
    return valores


def datos_registros(db: Session, ctx: dict) -> None:
    """Plantillas desde los Word de referencias/registros (R-OC-CE-XX) y registros de ejemplo."""
    from routers.registros import crear_plantilla_desde_word

    u, us = ctx["unidades"], ctx["usuarios"]
    cert = us["cert"]
    carpeta = Config.REFERENCIAS_DIR / "registros"
    archivos = sorted(carpeta.rglob("*.docx")) if carpeta.is_dir() else []
    for ruta in archivos:
        ambito = "planta" if "planta" in [x.lower() for x in ruta.relative_to(carpeta).parts[:-1]] else "campo"
        r = crear_plantilla_desde_word(db, ruta.read_bytes(), ruta.name, cert, ambito)
        if r["advertencias"]:
            print(f"  {r['codigo']}: {len(r['advertencias'])} advertencias")
    db.flush()
    plantillas = {pl.codigo: pl for pl in db.scalars(select(PlantillaRegistro))}
    print(f"  Plantillas de registro importadas: {len(plantillas)}")

    # R-OC-CE-10: el Word es una frase con espacios en blanco ("CON FECHA __ DE __ DEL __ ... EL CUARTEL __");
    # una liberación por documento: fecha, cuartel y especie completan la frase, más las dos firmas
    if "R-OC-CE-10" in plantillas:
        pl = plantillas["R-OC-CE-10"]
        frase = [("fecha", "Fecha de liberación", "fecha", True), ("cuartel", "Cuartel", "texto", True),
                 ("especie", "Especie / variedad", "texto", False)]
        pl.campos = [{"id": cid, "etiqueta": etiqueta, "tipo": tipo, "obligatorio": obligatorio,
                      "origen": {"tabla": 0, "fila": 0, "frase": cid}}
                     for cid, etiqueta, tipo, obligatorio in frase] + pl.campos

    if not plantillas:
        print("  (sin referencias/registros: se crea una plantilla de ejemplo)")
        pl = PlantillaRegistro(codigo="R-EJ-01", version="01", nombre="Registro de ejemplo", ambito="campo",
                               creada_por_id=cert.id, formato={"encargado": "Encargado de campo",
                                                               "frecuencia": "Mensual"},
                               campos=[{"id": "registros", "etiqueta": "Registros", "tipo": "tabla",
                                        "obligatorio": True, "columnas": [
                                            {"id": "fecha", "etiqueta": "Fecha", "tipo": "fecha"},
                                            {"id": "detalle", "etiqueta": "Detalle", "tipo": "texto"},
                                            {"id": "responsable", "etiqueta": "Responsable", "tipo": "texto"}]}])
        db.add(pl)
        db.flush()
        plantillas = {pl.codigo: pl}

    clave_firma, nombre_firma = firma_ficticia()
    firma = {"clave": clave_firma, "nombre": nombre_firma}
    mes = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"]
    mes_anterior = mes[(HOY.month - 2) % 12]
    mes_actual = mes[HOY.month - 1]

    def registro(codigo, unidad, periodo, responsable, estado, completo=True, dias_revision=0, observacion=None):
        """dias_revision: hace cuántos días alguien del campo guardó por última vez (15 o más = atrasado)."""
        pl = plantillas.get(codigo) or next(iter(plantillas.values()))
        from routers.registros import valores_iniciales
        valores = _llenar_ejemplo(pl.campos, firma, completo) | valores_iniciales(pl.campos, responsable)
        momento = ahora()
        # Filas firmadas por quien las ingresó (como lo hace la API al guardar)
        for c in pl.campos:
            if c["tipo"] == "tabla":
                for k, fila in enumerate(valores.get(c["id"], [])):
                    fila["_por"] = responsable.nombre if k % 3 else "Trabajador de apoyo (ficticio)"
                    fila["_en"] = (momento - timedelta(days=12 - k * 3)).isoformat(timespec="minutes")
        r = Registro(
            plantilla_id=pl.id, unidad_id=unidad.id,
            titulo=f"{pl.codigo} {pl.nombre} · {periodo}", codigo=pl.codigo, version=pl.version,
            formato=pl.formato, word_clave=pl.word_clave, campos=pl.campos, valores=valores,
            responsable_id=responsable.id, estado=estado, observacion=observacion, creado_por_id=cert.id,
            creado_en=momento - timedelta(days=max(10, dias_revision + 4)),
            revision_campo_en=momento - timedelta(days=dias_revision, hours=5),
            actualizado_en=momento - timedelta(days=dias_revision, hours=5) if valores else None,
            actualizado_por_id=responsable.id if valores else None,
            enviado_en=momento - timedelta(hours=3) if estado in ("en_revision", "aprobado") else None,
            aprobado_por_id=cert.id if estado == "aprobado" else None,
            aprobado_en=momento - timedelta(hours=1) if estado == "aprobado" else None)
        db.add(r)
        db.flush()
        # Historial: quién creó, guardó, envió y revisó
        eventos = [(cert, "crear", {"titulo": r.titulo}, max(10, dias_revision + 4) * 24)]
        if valores:
            eventos += [(responsable, "guardar", {"cambios": ["Registros: 2 fila(s) nueva(s)"], "avance": 40},
                         (dias_revision + 2) * 24),
                        (responsable, "guardar", {"cambios": ["Registros: 2 fila(s) nueva(s)", "Responsable"],
                                                  "avance": 100 if completo else 60}, dias_revision * 24 + 5)]
        if estado in ("en_revision", "aprobado", "rechazado"):
            eventos.append((responsable, "enviar", {}, 3))
        if estado == "aprobado":
            eventos.append((cert, "aprobar", {"observacion": None}, 1))
        if estado == "rechazado":
            eventos.append((cert, "rechazar", {"observacion": observacion}, 1))
        for autor, accion, detalle, horas in eventos:
            db.add(Bitacora(usuario_id=autor.id, accion=accion, entidad="registro", entidad_id=r.id,
                            detalle=detalle, fecha_hora=momento - timedelta(hours=horas)))

    cc, ci = u["Campo Chocalán"], u["Campo Itahue"]
    registro("R-OC-CE-12", cc, mes_anterior, us["campo"], "aprobado")
    registro("R-OC-CE-08", cc, mes_anterior, us["campo"], "aprobado")
    registro("R-OC-CE-03", ci, mes_anterior, us["campo"], "en_revision")
    registro("R-OC-CE-04", ci, "cuartel 2", us["campo"], "rechazado",
             observacion="Falta la observación del ítem marcado 'No' y la firma del jefe de campo.")
    registro("R-OC-CE-17", cc, mes_actual, us["campo"], "borrador", completo=False, dias_revision=2)
    registro("R-OC-CE-06", ci, "faena de poda", us["campo"], "borrador", completo=False, dias_revision=18)
    registro("R-OC-CE-21", cc, str(HOY.year), us["campo"], "borrador", completo=False, dias_revision=16)
    db.commit()


def main() -> None:
    print(f"Base demo: {Config.url_base_datos()}")
    # Se parte de un archivo nuevo: drop_all falla si la base trae un esquema anterior
    engine.dispose()
    Path(engine.url.database).unlink(missing_ok=True)
    # En la demo se crean también las tablas compartidas (en GCP ya existen)
    Base.metadata.create_all(engine)
    if almacenamiento.DIR_LOCAL.exists():
        shutil.rmtree(almacenamiento.DIR_LOCAL)
    with SessionLocal() as db:
        ctx = crear_catalogos(db)
        print("Catálogos creados. Importando referencias...")
        importar_referencias(db, ctx["usuarios"]["cert"])
        datos_ficticios(db, ctx)
        datos_registros(db, ctx)
        demo_auditorias(db, ctx)
        reinc = db.scalars(select(NoConformidad).where(NoConformidad.reincidente_de_id.is_not(None))).all()
        print("Reincidentes:", sorted({nc.requisito.codigo for nc in reinc}))
    print("Listo.")


if __name__ == "__main__":
    main()
