import io
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from config import Config
from schemas.documentos import (
    CapacitacionEntrada, DocumentoCambios, DocumentoEntrada, ArchivoSubidoEntrada, VersionEntrada,
)
from utils import almacenamiento
from utils.auth import (
    puede_escribir, solo_certificaciones, unidades_permitidas, usuario_actual, verificar_unidad,
)
from utils.bitacora import registrar
from utils.comunes import dias_para, filtrar_temporada, filtrar_unidades, obtener, unidad_dict
from utils.db import get_db
from utils.analizar_documento import analizar
from utils.modelos import (
    Capacitacion, CategoriaDocumento, Certificacion, Documento, DocumentoVersion, Empresa, Protocolo, Unidad, Usuario,
)
from utils.hora import ahora

router = APIRouter()


# ---------- Reglas de versión ----------

SECCIONES = {"campo": "Campo", "planta": "Planta", "empresarial": "Empresarial (OC)"}


def version_vigente(doc: Documento) -> DocumentoVersion | None:
    """La vigente es la última versión subida (los documentos fijos no se aprueban; las anteriores quedan
    como historial). Se conserva el filtro por estado para versiones antiguas."""
    aprobadas = [v for v in doc.versiones if v.estado == "aprobado"]
    return aprobadas[-1] if aprobadas else None


def _cert_dict(c: Certificacion | None) -> dict | None:
    if c is None:
        return None
    return {
        "protocolo": {"id": c.protocolo.id, "codigo": c.protocolo.codigo, "nombre": c.protocolo.nombre},
        "numero": c.numero, "norma_version": c.norma_version, "entidad_certificadora": c.entidad_certificadora,
        "vigente_desde": c.vigente_desde, "vigente_hasta": c.vigente_hasta, "fecha_auditoria": c.fecha_auditoria,
        "resultado": c.resultado, "productos": c.productos or [],
        "unidades": [unidad_dict(u) for u in sorted(c.unidades, key=lambda u: u.nombre)],
    }


def _version_dict(v: DocumentoVersion) -> dict:
    return {
        "id": v.id, "numero": v.numero, "nombre_archivo": v.nombre_archivo, "tipo_contenido": v.tipo_contenido,
        "version_texto": v.version_texto, "fecha_emision": v.fecha_emision,
        "fecha_vencimiento": v.fecha_vencimiento, "dias_para_vencer": dias_para(v.fecha_vencimiento),
        "estado": v.estado, "observacion": v.observacion, "subido_por": v.subido_por.nombre, "subido_por_id": v.subido_por_id,
        "subido_en": v.subido_en, "revisado_en": v.revisado_en, "certificado": _cert_dict(v.certificacion),
    }


def _doc_dict(doc: Documento, detalle: bool = False) -> dict:
    vigente = version_vigente(doc)
    ultima = doc.versiones[-1] if doc.versiones else None
    datos = {
        "id": doc.id, "titulo": doc.titulo, "codigo": doc.codigo,
        "categoria": {"id": doc.categoria.id, "nombre": doc.categoria.nombre},
        "empresa_id": doc.empresa_id, "seccion": doc.seccion,
        "vigente": _version_dict(vigente) if vigente else None,
        "ultima": _version_dict(ultima) if ultima else None,
        "versiones_total": len(doc.versiones),
    }
    if detalle:
        datos["versiones"] = [_version_dict(v) for v in reversed(doc.versiones)]
    return datos


def _consulta_documentos(db: Session, usuario: Usuario, empresa_id, unidad_id, protocolo_id, categoria_id,
                         seccion=None):
    """Los documentos fijos no van por temporada: siempre se muestra la versión vigente."""
    consulta = select(Documento).options(
        selectinload(Documento.versiones).selectinload(DocumentoVersion.subido_por), selectinload(Documento.categoria),
        selectinload(Documento.versiones).selectinload(DocumentoVersion.certificacion).selectinload(Certificacion.unidad),
    )
    if unidades_permitidas(usuario) is not None:
        # Encargados: los documentos fijos de las empresas de sus sucursales (solo lectura)
        consulta = consulta.where(Documento.empresa_id.in_({u.empresa_id for u in usuario.unidades} or {-1}))
    if empresa_id:
        consulta = consulta.where(Documento.empresa_id == empresa_id)
    if unidad_id:
        # Con una sucursal elegida: los de su tipo (campo o planta) y los empresariales de su empresa
        unidad = obtener(db, Unidad, unidad_id)
        consulta = consulta.where(Documento.empresa_id == unidad.empresa_id,
                                  Documento.seccion.in_((unidad.tipo, "empresarial")))
    if seccion:
        consulta = consulta.where(Documento.seccion == seccion)
    if protocolo_id:
        # Solo los certificados tienen norma (por su ficha)
        consulta = consulta.where(Documento.id.in_(select(DocumentoVersion.documento_id).join(
            Certificacion, Certificacion.documento_version_id == DocumentoVersion.id).where(
            Certificacion.protocolo_id == protocolo_id)))
    if categoria_id:
        consulta = consulta.where(Documento.categoria_id == categoria_id)
    return consulta.order_by(Documento.titulo)


@router.get("/documentos")
def listar(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
           protocolo_id: int | None = None, categoria_id: int | None = None, seccion: str | None = None,
           q: str | None = None, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> list[dict]:
    # Los documentos fijos no tienen protocolo: el filtro de protocolo no aplica
    docs = db.scalars(_consulta_documentos(db, usuario, empresa_id, unidad_id, None, categoria_id, seccion)).all()
    resultado = [_doc_dict(d) for d in docs]
    if q:
        ql = q.lower()
        resultado = [d for d in resultado if ql in d["titulo"].lower() or ql in (d["codigo"] or "").lower()]
    return resultado


@router.get("/documentos/codigos")
def codigos(usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict[str, int]:
    """Mapa código → id, para convertir en enlaces los códigos citados en observaciones (P OC CE 29, DPL 23)."""
    docs = db.scalars(_consulta_documentos(db, usuario, None, None, None, None).where(Documento.codigo.is_not(None)))
    return {d.codigo: d.id for d in docs}


@router.get("/documentos/exportar")
def exportar(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
             protocolo_id: int | None = None, usuario: Usuario = Depends(usuario_actual),
             db: Session = Depends(get_db)) -> StreamingResponse:
    docs = db.scalars(_consulta_documentos(db, usuario, empresa_id, unidad_id, None, None)).all()
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Documentos fijos"
    hoja.append(["Sección", "Categoría", "Código", "Título", "Versión", "Fecha de emisión", "Subido por",
                 "Subido el", "Versiones en historial"])
    for d in docs:
        vigente = version_vigente(d)
        hoja.append([SECCIONES.get(d.seccion, d.seccion), d.categoria.nombre, d.codigo, d.titulo,
                     (vigente.version_texto or vigente.numero) if vigente else None,
                     vigente.fecha_emision if vigente else None, vigente.subido_por.nombre if vigente else None,
                     vigente.subido_en.replace(microsecond=0) if vigente else None, len(d.versiones)])
    salida = io.BytesIO()
    libro.save(salida)
    salida.seek(0)
    return StreamingResponse(
        salida, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="documentos.xlsx"'})


@router.get("/documentos/{documento_id}")
def detalle(documento_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    doc = obtener(db, Documento, documento_id)
    _verificar_lectura(usuario, doc)
    return _doc_dict(doc, detalle=True)


def _verificar_lectura(usuario: Usuario, doc: Documento) -> None:
    if unidades_permitidas(usuario) is not None and doc.empresa_id not in {u.empresa_id for u in usuario.unidades}:
        raise HTTPException(403, "No tienes acceso a ese documento")


def _validar_version(categoria: CategoriaDocumento, datos: VersionEntrada) -> None:
    if categoria.requiere_vencimiento and not datos.fecha_vencimiento:
        raise HTTPException(400, f"La categoría '{categoria.nombre}' exige fecha de vencimiento")
    if datos.certificado and not categoria.requiere_vencimiento:
        raise HTTPException(400, "Solo los certificados llevan ficha de certificado")
    c = datos.certificado
    if c and c.vigente_desde and datos.fecha_vencimiento and c.vigente_desde > datos.fecha_vencimiento:
        raise HTTPException(400, "La vigencia empieza después del vencimiento")
    if Config.ALMACENAMIENTO == "local" and not almacenamiento.existe(datos.archivo_key):
        raise HTTPException(400, "El archivo no se subió correctamente")


def _bitacora_cert(datos: VersionEntrada) -> dict:
    c = datos.certificado
    return {"certificado": c.numero, "vence": str(datos.fecha_vencimiento)} if c else {}


def _nueva_version(db: Session, doc: Documento, datos: VersionEntrada, usuario: Usuario) -> DocumentoVersion:
    """Los documentos fijos no se aprueban: cada archivo subido queda guardado y pasa a ser la versión vigente."""
    version = DocumentoVersion(
        documento_id=doc.id, numero=(doc.versiones[-1].numero + 1) if doc.versiones else 1,
        archivo_key=datos.archivo_key, nombre_archivo=datos.nombre_archivo, tipo_contenido=datos.tipo_contenido,
        version_texto=datos.version_texto, fecha_emision=datos.fecha_emision,
        fecha_vencimiento=datos.fecha_vencimiento, subido_por_id=usuario.id,
        estado="aprobado", revisado_por_id=usuario.id, revisado_en=ahora(),
    )
    db.add(version)
    db.flush()
    if c := datos.certificado:
        unidades = list(db.scalars(select(Unidad).where(
            Unidad.id.in_(c.unidad_ids), Unidad.empresa_id == doc.empresa_id)))
        if len(unidades) != len(set(c.unidad_ids)):
            raise HTTPException(400, "Las sucursales cubiertas deben ser de la empresa del certificado")
        # Una sucursal (PrimusGFS: el packing) o, si son varias o ninguna, toda la empresa (multisitio)
        db.add(Certificacion(
            protocolo_id=obtener(db, Protocolo, c.protocolo_id).id, empresa_id=doc.empresa_id,
            documento_version_id=version.id, numero=c.numero, norma_version=c.norma_version,
            entidad_certificadora=c.entidad_certificadora, vigente_desde=c.vigente_desde,
            vigente_hasta=datos.fecha_vencimiento, fecha_auditoria=c.fecha_auditoria, resultado=c.resultado,
            productos=c.productos, unidad_id=unidades[0].id if len(unidades) == 1 else None,
        ))
        db.flush()
    return version


# Packing nombrado por su comuna: PACKING PAINE es el packing de Santa Victoria
ALIAS_LUGAR = {"PAINE": "Santa Victoria"}


def lugar_sucursal(u: Unidad) -> str:
    """Nombre del lugar sin el tipo, para buscarlo en los certificados: 'CAMPO CHOCALAN' -> 'Chocalan'."""
    nombre = re.sub(r"^(CAMPO|PACKING|PLANTA|FUNDO)\s+", "", u.nombre.strip(), flags=re.IGNORECASE)
    return ALIAS_LUGAR.get(nombre.upper(), nombre.title())


def lugares_conocidos(sucursales: list[Unidad]) -> list[str]:
    """Nombres de lugar que se buscan en el texto (las siglas, como MG, no)."""
    return sorted({lugar_sucursal(u) for u in sucursales if len(lugar_sucursal(u)) > 3})


def es_del_sitio(u: Unidad, sitio: str) -> bool:
    """La sucursal está en el sitio nombrado. Siglas por iniciales: PACKING MG = Maitén Gigante."""
    lugar = lugar_sucursal(u)
    if len(lugar) <= 3:
        return lugar.upper() == "".join(p[0] for p in sitio.split()).upper()
    return lugar == sitio


DESCRIPCION_CATEGORIA = {"Procedimientos": "un procedimiento", "Análisis de riesgos": "un análisis de riesgos",
                         "Planes de gestión": "un plan de gestión", "Instructivos": "un instructivo"}


def _sin_espacios(texto: str | None) -> str:
    return re.sub(r"\s+", "", (texto or "").upper())


def _parecido(db: Session, a, empresa: Empresa | None, protocolo: Protocolo | None,
              unidad_ids: list[int]) -> dict | None:
    """Documento ya cargado al que se parece el archivo: mismo certificado (norma, empresa y sucursales)
    o mismo código. Sirve para proponer subirlo como versión nueva en vez de duplicarlo."""
    docs = db.scalars(select(Documento).options(
        selectinload(Documento.versiones).selectinload(DocumentoVersion.certificacion).selectinload(Certificacion.unidad),
        selectinload(Documento.categoria))).all()
    for d in docs:
        if empresa and d.empresa_id != empresa.id:
            continue
        if protocolo:
            vigente = version_vigente(d)
            ficha = vigente.certificacion if vigente else None
            if not ficha or ficha.protocolo_id != protocolo.id:
                continue
            cubiertas = {u.id for u in ficha.unidades}
            if cubiertas and unidad_ids and not cubiertas & set(unidad_ids):
                continue
            motivo = "misma norma y empresa" + (", mismas sucursales" if cubiertas & set(unidad_ids) else "")
        elif a.codigo and _sin_espacios(d.codigo) == _sin_espacios(a.codigo):
            motivo = f"mismo código {d.codigo}"
        else:
            continue
        return {"id": d.id, "titulo": d.titulo, "codigo": d.codigo, "motivo": motivo,
                "requiere_vencimiento": d.categoria.requiere_vencimiento}
    return None


@router.post("/documentos/analizar")
def analizar_subido(datos: ArchivoSubidoEntrada, _: Usuario = Depends(solo_certificaciones),
                    db: Session = Depends(get_db)) -> dict:
    """Interpreta el archivo ya subido: qué documento parece ser, a cuál ya cargado se parece y con qué datos
    se puede rellenar el formulario. No guarda nada: la aplicación le pregunta a certificaciones antes."""
    if not almacenamiento.existe(datos.archivo_key):
        raise HTTPException(400, "El archivo no se subió correctamente")
    try:
        contenido = almacenamiento.leer(datos.archivo_key)
    except Exception as exc:
        raise HTTPException(400, "No se pudo leer el archivo") from exc
    sucursales = list(db.scalars(select(Unidad)))
    a = analizar(contenido, datos.nombre_archivo, lugares_conocidos(sucursales))
    empresa = db.scalar(select(Empresa).where(Empresa.codigo == a.empresa)) if a.empresa else None
    categorias = {c.nombre: c for c in db.scalars(select(CategoriaDocumento))}
    r = a.certificado
    protocolo = db.scalar(select(Protocolo).where(Protocolo.codigo == r.protocolo)) if r and r.protocolo else None

    propuesta, descripcion, unidad_ids = None, None, []
    if r and protocolo:
        # Sitio → sucursal de la empresa del certificado; si hay varias con ese nombre, la que tiene la norma
        for sitio in r.sitios:
            candidatas = [u for u in sucursales if es_del_sitio(u, sitio)
                          and (empresa is None or u.empresa_id == empresa.id)]
            elegida = next((u for u in candidatas if protocolo.aplica_a(u)), candidatas[0] if candidatas else None)
            if elegida:
                unidad_ids.append(elegida.id)
        categoria = next((c for c in categorias.values() if c.requiere_vencimiento), None)
        titulo = f"Certificado {protocolo.nombre}" + (f" {empresa.codigo}" if empresa else "")
        titulo += f" · {r.operacion}" if r.operacion else ""
        descripcion = f"el certificado {protocolo.nombre}" + (f" de {empresa.nombre}" if empresa else "") + \
            (f" ({r.operacion})" if r.operacion else "")
        propuesta = {
            "categoria_id": categoria.id if categoria else None, "empresa_id": empresa.id if empresa else None,
            "seccion": protocolo.ambito if protocolo.ambito in ("campo", "planta") else None,
            "titulo": titulo, "codigo": None, "fecha_emision": r.fecha_decision, "fecha_vencimiento": r.vigente_hasta,
            "certificado": {
                "protocolo_id": protocolo.id, "protocolo": protocolo.nombre, "numero": r.numero,
                "norma_version": r.norma_version, "entidad_certificadora": r.entidad, "vigente_desde": r.vigente_desde,
                "fecha_auditoria": r.fecha_auditoria, "resultado": r.puntaje, "unidad_ids": unidad_ids,
                "productos": r.productos,
            },
        }
    elif a.categoria or a.codigo:
        categoria = categorias.get(a.categoria) if a.categoria else None
        descripcion = DESCRIPCION_CATEGORIA.get(a.categoria or "", "un documento") + \
            (f" con código {a.codigo}" if a.codigo else "") + (f" de {empresa.nombre}" if empresa else "")
        propuesta = {
            "categoria_id": categoria.id if categoria else None, "empresa_id": empresa.id if empresa else None,
            "seccion": "empresarial" if a.codigo and " OC " in f" {a.codigo} " else None,
            "titulo": a.titulo, "codigo": a.codigo, "fecha_emision": None, "fecha_vencimiento": None,
            "certificado": None,
        }
    return {
        "texto_leido": a.texto_leido, "descripcion": descripcion, "propuesta": propuesta,
        "parecido": _parecido(db, a, empresa, protocolo, unidad_ids) if propuesta else None,
    }


@router.post("/documentos", status_code=201)
def crear(datos: DocumentoEntrada, usuario: Usuario = Depends(solo_certificaciones),
          db: Session = Depends(get_db)) -> dict:
    """Los documentos fijos los sube certificaciones; no van por sucursal sino por sección."""
    categoria = obtener(db, CategoriaDocumento, datos.categoria_id)
    if categoria.requiere_codigo and not datos.codigo:
        raise HTTPException(400, f"La categoría '{categoria.nombre}' exige código")
    _validar_version(categoria, datos.version)
    obtener(db, Empresa, datos.empresa_id)
    doc = Documento(
        categoria_id=categoria.id, empresa_id=datos.empresa_id, seccion=datos.seccion, titulo=datos.titulo.strip(),
        codigo=datos.codigo.strip().upper() if datos.codigo else None, creado_por_id=usuario.id,
    )
    db.add(doc)
    db.flush()
    version = _nueva_version(db, doc, datos.version, usuario)
    registrar(db, usuario, "crear", "documento", doc.id, {"titulo": doc.titulo, "version": version.numero,
                                                          "seccion": doc.seccion, **_bitacora_cert(datos.version)})
    db.commit()
    db.refresh(doc)
    return _doc_dict(doc, detalle=True)


@router.post("/documentos/{documento_id}/versiones", status_code=201)
def agregar_version(documento_id: int, datos: VersionEntrada, usuario: Usuario = Depends(solo_certificaciones),
                    db: Session = Depends(get_db)) -> dict:
    doc = obtener(db, Documento, documento_id)
    _validar_version(doc.categoria, datos)
    version = _nueva_version(db, doc, datos, usuario)
    registrar(db, usuario, "nueva_version", "documento", doc.id, {"version": version.numero, **_bitacora_cert(datos)})
    db.commit()
    db.refresh(doc)
    return _doc_dict(doc, detalle=True)


@router.patch("/documentos/{documento_id}")
def modificar(documento_id: int, datos: DocumentoCambios, usuario: Usuario = Depends(solo_certificaciones),
              db: Session = Depends(get_db)) -> dict:
    doc = obtener(db, Documento, documento_id)
    cambios = datos.model_dump(exclude_unset=True)
    for campo in ("titulo", "codigo"):
        if campo in cambios:
            setattr(doc, campo, cambios[campo])
    registrar(db, usuario, "modificar", "documento", doc.id, cambios)
    db.commit()
    db.refresh(doc)
    return _doc_dict(doc, detalle=True)


@router.get("/documentos/versiones/{version_id}/descarga")
def descargar(version_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    version = obtener(db, DocumentoVersion, version_id)
    _verificar_lectura(usuario, version.documento)
    if not version.archivo_key:
        raise HTTPException(404, "La versión no tiene archivo")
    return {"url": almacenamiento.url_descarga(version.archivo_key, version.nombre_archivo)}


# ---------- Capacitaciones ----------

@router.get("/capacitaciones")
def listar_capacitaciones(empresa_id: int | None = None, unidad_id: int | None = None,
                          temporada_id: int | None = None, usuario: Usuario = Depends(usuario_actual),
                          db: Session = Depends(get_db)) -> list[dict]:
    consulta = filtrar_unidades(select(Capacitacion), Capacitacion.unidad_id, usuario, empresa_id, unidad_id)
    consulta = filtrar_temporada(db, consulta, temporada_id, Capacitacion.fecha, Capacitacion.unidad_id)
    return [
        {"id": c.id, "tema": c.tema, "fecha": c.fecha, "relator": c.relator, "asistentes": c.asistentes or [],
         "vigente_hasta": c.vigente_hasta, "dias_para_vencer": dias_para(c.vigente_hasta),
         "unidad": unidad_dict(c.unidad), "documento_id": c.documento_id}
        for c in db.scalars(consulta.order_by(Capacitacion.fecha.desc()))
    ]


@router.post("/capacitaciones", status_code=201)
def crear_capacitacion(datos: CapacitacionEntrada, usuario: Usuario = Depends(puede_escribir),
                       db: Session = Depends(get_db)) -> dict:
    verificar_unidad(usuario, datos.unidad_id)
    cap = Capacitacion(**datos.model_dump(), creado_por_id=usuario.id)
    db.add(cap)
    db.flush()
    registrar(db, usuario, "crear", "capacitacion", cap.id, {"tema": cap.tema})
    db.commit()
    return {"id": cap.id}


# ---------- Vencimientos ----------

def calcular_vencimientos(db: Session, usuario: Usuario | None, empresa_id: int | None = None,
                          unidad_id: int | None = None, protocolo_id: int | None = None) -> list[dict]:
    """Vencimientos = certificados subidos como documentos fijos (categoría con fecha de vencimiento).
    Cuenta la fecha de la versión vigente; las capacitaciones ya no forman parte de este panel."""
    consulta = select(Documento).options(
        selectinload(Documento.versiones).selectinload(DocumentoVersion.certificacion), selectinload(Documento.categoria))
    if usuario is not None:
        consulta = _consulta_documentos(db, usuario, empresa_id, unidad_id, protocolo_id, None)
    consulta = consulta.where(Documento.categoria_id.in_(
        select(CategoriaDocumento.id).where(CategoriaDocumento.requiere_vencimiento.is_(True))))
    empresas = {e.id: e.codigo for e in db.scalars(select(Empresa))}
    items: list[dict] = []
    hoy = date.today()
    for doc in db.scalars(consulta):
        vigente = version_vigente(doc)
        if not vigente or not vigente.fecha_vencimiento:
            continue
        # Con una sucursal elegida, un certificado con ficha solo cuenta si la cubre
        ficha = vigente.certificacion
        if unidad_id and ficha and ficha.unidades and unidad_id not in {u.id for u in ficha.unidades}:
            continue
        dias = (vigente.fecha_vencimiento - hoy).days
        items.append({
            "tipo": "certificado", "id": doc.id, "titulo": doc.titulo, "codigo": doc.codigo,
            "detalle": doc.categoria.nombre, "seccion": doc.seccion, "unidad": SECCIONES.get(doc.seccion, doc.seccion),
            "empresa_id": doc.empresa_id, "empresa": empresas.get(doc.empresa_id),
            "version": vigente.version_texto or str(vigente.numero), "emision": vigente.fecha_emision,
            "vence": vigente.fecha_vencimiento, "dias": dias, "certificado": _cert_dict(vigente.certificacion),
            "grupo": "vencido" if dias < 0 else next((f"{d}" for d in sorted(Config.DIAS_ALERTA) if dias <= d), "vigente"),
        })
    return sorted(items, key=lambda i: i["vence"])


@router.get("/vencimientos")
def vencimientos(empresa_id: int | None = None, unidad_id: int | None = None, protocolo_id: int | None = None,
                 usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    items = calcular_vencimientos(db, usuario, empresa_id, unidad_id, protocolo_id)
    grupos = ["vencido"] + [str(d) for d in sorted(Config.DIAS_ALERTA)] + ["vigente"]
    return {"grupos": grupos, "items": items}
