"""Auditorías externas: informes de la certificadora que certificaciones sube como documento de consulta.

La aplicación lee el PDF y arma el resumen (norma, sucursales, puntajes, preguntas y hallazgos); no se llena
ningún campo ni se generan no conformidades. Solo lo ve el equipo de certificaciones.
"""
import re
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from utils import almacenamiento
from utils.proteccion import MAX_MB_ARCHIVO
from utils.auth import solo_certificaciones, solo_ve_todo
from utils.historial import registrar
from utils.duplicados import error_duplicado, existente
from utils.comunes import TemporadaLogica, obtener, temporada_al_guardar, temporada_seleccionada, unidad_dict
from utils.db import get_db
from utils.exportar_auditoria_externa import resumen_docx, resumen_pdf
from utils.hora import ahora
from utils.importar_asoex import normalizar
from utils.leer_auditoria_externa import TIPOS, leer_auditoria_externa
from utils.modelos import AuditoriaExterna, AuditoriaExternaVersion, Empresa, Protocolo, Unidad, Usuario
from utils.temporadas import temporada_para_fecha
from utils.texto import nombre_archivo_seguro

router = APIRouter(prefix="/auditorias-externas")

MAX_ARCHIVO = MAX_MB_ARCHIVO * 1024 * 1024
PREFIJO = re.compile(r"^(fundo|campo|packing|planta|huerto|empaque)\s+", re.IGNORECASE)


def _sucursales(sitios: list[str], unidades: list[Unidad], protocolo: Protocolo | None) -> list[int]:
    """'Fundo Maiten Gigante' → MAITEN GIGANTE; 'Packing Maiten Gigante' → PACKING MG (prefiere el tipo y la norma)."""
    from routers.documentos import es_del_sitio

    elegidas: list[int] = []
    for sitio in sitios:
        es_packing = bool(re.match(r"(packing|planta|empaque)", sitio, re.IGNORECASE))
        lugar = PREFIJO.sub("", sitio).strip()
        candidatas = [u for u in unidades if es_del_sitio(u, lugar.title())
                      or normalizar(u.etiqueta) == normalizar(sitio) or normalizar(u.nombre) == normalizar(lugar)]
        if not candidatas:
            continue
        del_tipo = [u for u in candidatas if (u.tipo == "planta") == es_packing] or candidatas
        elegida = next((u for u in del_tipo if protocolo and protocolo.aplica_a(u)), del_tipo[0])
        if elegida.id not in elegidas:
            elegidas.append(elegida.id)
    return elegidas


def _resumen(lectura) -> dict:
    datos = asdict(lectura)
    for clave in ("fecha_inicio", "fecha_fin", "certificado_desde", "certificado_hasta"):
        datos[clave] = datos[clave].isoformat() if datos[clave] else None
    return datos


def _titulo(protocolo: Protocolo | None, unidades: list[Unidad], db: Session, fecha, empresa_id) -> str:
    partes = [protocolo.nombre if protocolo else "Auditoría externa"]
    if unidades:
        nombres = [u.etiqueta for u in unidades]
        partes.append(", ".join(nombres[:-1]) + " y " + nombres[-1] if len(nombres) > 1 else nombres[0])
    if fecha and (t := temporada_para_fecha(db, fecha, empresa_id)):
        partes.append(t.nombre)
    return " · ".join(partes)


def _dict(a: AuditoriaExterna, unidades: dict[int, Unidad], empresas: dict[int, Empresa], detalle: bool = False) -> dict:
    ultima = a.versiones[-1] if a.versiones else None
    resumen = ultima.resumen if ultima else {}
    datos = {
        "id": a.id, "titulo": a.titulo, "tipo_informe": a.tipo_informe, "tipo_nombre": TIPOS.get(a.tipo_informe, a.tipo_informe),
        "protocolo": {"id": a.protocolo.id, "codigo": a.protocolo.codigo, "nombre": a.protocolo.nombre} if a.protocolo else None,
        "empresa": empresas[a.empresa_id].codigo if a.empresa_id in empresas else None,
        "numero": a.numero, "entidad": a.entidad, "auditor": a.auditor, "fecha": a.fecha,
        "sucursales": [unidad_dict(unidades[i]) for i in a.sucursales_auditadas if i in unidades],
        "versiones_total": len(a.versiones),
        "version": {"id": ultima.id, "numero": ultima.numero, "nombre_archivo": ultima.nombre_archivo,
                    "subido_en": ultima.subido_en} if ultima else None,
        "puntajes": resumen.get("puntajes", []), "preguntas": resumen.get("preguntas", {}),
        "hallazgos_total": len(resumen.get("hallazgos", [])),
    }
    if detalle:
        datos["resumen"] = resumen
        datos["versiones"] = [{"id": v.id, "numero": v.numero, "nombre_archivo": v.nombre_archivo, "subido_en": v.subido_en,
                               "subido_por": v.subido_por.nombre if v.subido_por else None} for v in reversed(a.versiones)]
    return datos


def _catalogos(db: Session) -> tuple[dict[int, Unidad], dict[int, Empresa]]:
    return ({u.id: u for u in db.scalars(select(Unidad))}, {e.id: e for e in db.scalars(select(Empresa))})


@router.get("")
def listar(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
           protocolo_id: str | None = None, _: Usuario = Depends(solo_ve_todo),
           db: Session = Depends(get_db)) -> list[dict]:
    from utils.temporadas import buscar_temporada

    unidades, empresas = _catalogos(db)
    temporada = buscar_temporada(db, temporada_id) if temporada_id else None
    salida = []
    for a in db.scalars(select(AuditoriaExterna).options(selectinload(AuditoriaExterna.versiones),
                                                         selectinload(AuditoriaExterna.protocolo))):
        if empresa_id and a.empresa_id != empresa_id:
            continue
        if unidad_id and unidad_id not in a.sucursales_auditadas:
            continue
        if protocolo_id and a.protocolo_id != protocolo_id:
            continue
        if temporada and (not a.fecha or not temporada.contiene(a.fecha, a.empresa_id)):
            continue
        salida.append(_dict(a, unidades, empresas))
    return sorted(salida, key=lambda x: (str(x["fecha"] or ""), x["id"]), reverse=True)


async def _leer_archivo(archivo: UploadFile) -> tuple[bytes, str]:
    nombre = archivo.filename or "informe.pdf"
    if not nombre.lower().endswith(".pdf"):
        raise HTTPException(400, f"{nombre}: se espera el informe en PDF")
    contenido = await archivo.read()
    if len(contenido) > MAX_ARCHIVO:
        raise HTTPException(413, f"{nombre}: archivo demasiado grande")
    return contenido, nombre


def _nueva_version(db: Session, auditoria: AuditoriaExterna, contenido: bytes, nombre: str, lectura, usuario: Usuario):
    clave = almacenamiento.nueva_clave("auditorias_externas", nombre)
    almacenamiento.escribir(clave, contenido, "application/pdf")
    numero = (auditoria.versiones[-1].numero + 1) if auditoria.versiones else 1
    version = AuditoriaExternaVersion(numero=numero, archivo_key=clave, nombre_archivo=nombre, resumen=_resumen(lectura),
                                      subido_por_id=usuario.id)
    auditoria.versiones.append(version)
    return version


def _version_igual(db: Session, lectura) -> AuditoriaExternaVersion | None:
    """Versión ya subida del mismo informe (ID de la certificadora, tipo y norma) con el mismo contenido leído."""
    if not lectura.numero:
        return None
    protocolo = db.scalar(select(Protocolo).where(Protocolo.codigo == lectura.protocolo)) if lectura.protocolo else None
    auditoria = db.scalar(select(AuditoriaExterna).where(
        AuditoriaExterna.numero == lectura.numero, AuditoriaExterna.tipo_informe == lectura.tipo_informe,
        AuditoriaExterna.protocolo_id == (protocolo.id if protocolo else None)))
    resumen = _resumen(lectura)
    return next((v for v in auditoria.versiones if v.resumen == resumen), None) if auditoria else None


def _reemplazar_version(db: Session, version: AuditoriaExternaVersion, contenido: bytes, nombre: str, usuario: Usuario) -> dict:
    """Reemplaza el archivo y el resumen de una versión ya subida (mismo número de versión)."""
    lectura = leer_auditoria_externa(contenido, nombre)
    clave = almacenamiento.nueva_clave("auditorias_externas", nombre)
    almacenamiento.escribir(clave, contenido, "application/pdf")
    version.archivo_key, version.resumen, version.subido_por_id, version.subido_en = clave, _resumen(lectura), usuario.id, ahora()
    db.flush()
    auditoria = version.auditoria
    registrar(db, usuario, "reemplazar", "auditoria_externa", auditoria.id, {"archivo": nombre, "version": version.numero})
    return {"id": auditoria.id, "titulo": auditoria.titulo, "archivo": nombre, "nueva": False, "version": version.numero,
            "tipo_nombre": TIPOS.get(auditoria.tipo_informe), "advertencias": lectura.advertencias, "reemplazada": True}


def registrar_informe(db: Session, contenido: bytes, nombre: str, usuario: Usuario,
                      temporada: TemporadaLogica | None = None) -> dict:
    """Lee el PDF y lo guarda: auditoría nueva o, si ya existe (mismo ID de la certificadora, tipo y norma), versión nueva."""
    lectura = leer_auditoria_externa(contenido, nombre)
    protocolo = db.scalar(select(Protocolo).where(Protocolo.codigo == lectura.protocolo)) if lectura.protocolo else None
    unidades = list(db.scalars(select(Unidad)))
    sucursales_auditadas = _sucursales(lectura.sitios, unidades, protocolo)
    empresa = db.scalar(select(Empresa).where(Empresa.id == {"LH": 1, "VS": 2}.get(lectura.empresa or "", 0)))
    existente = db.scalar(select(AuditoriaExterna).where(
        AuditoriaExterna.numero == lectura.numero, AuditoriaExterna.tipo_informe == lectura.tipo_informe,
        AuditoriaExterna.protocolo_id == (protocolo.id if protocolo else None))) if lectura.numero else None
    if existente:
        auditoria, nueva = existente, False
    else:
        auditoria = AuditoriaExterna(
            protocolo_id=protocolo.id if protocolo else None, empresa_id=empresa.id if empresa else None,
            tipo_informe=lectura.tipo_informe, numero=lectura.numero, entidad=lectura.entidad,
            auditor=lectura.auditor, fecha=lectura.fecha_inicio, sucursales_auditadas=sucursales_auditadas,
            titulo=_titulo(protocolo, [u for u in unidades if u.id in sucursales_auditadas], db, lectura.fecha_inicio,
                           empresa.id if empresa else None),
            creado_por_id=usuario.id,
            temporada=temporada_al_guardar(db, temporada, lectura.fecha_inicio, empresa.id if empresa else None)
            if temporada else None,
        )
        db.add(auditoria)
        nueva = True
    version = _nueva_version(db, auditoria, contenido, nombre, lectura, usuario)
    db.flush()
    registrar(db, usuario, "subir", "auditoria_externa", auditoria.id,
              {"archivo": nombre, "version": version.numero, "titulo": auditoria.titulo})
    return {"id": auditoria.id, "titulo": auditoria.titulo, "archivo": nombre, "nueva": nueva, "version": version.numero,
            "tipo_nombre": TIPOS.get(auditoria.tipo_informe), "advertencias": lectura.advertencias}


@router.post("", status_code=201)
async def subir(archivos: list[UploadFile] = File(...), reemplazar: bool = Form(False),
                usuario: Usuario = Depends(solo_certificaciones), db: Session = Depends(get_db),
                temporada: TemporadaLogica = Depends(temporada_seleccionada)) -> list[dict]:
    """Sube uno o varios informes; cada uno se lee y se guarda solo, sin campos que llenar.
    Si un PDF ya está subido (mismo nombre), avisa; con reemplazar=true reemplaza esa versión."""
    leidos = []
    for archivo in archivos:
        contenido, nombre = await _leer_archivo(archivo)
        leidos.append((nombre, contenido))
    repetidas = {v.nombre_archivo: v for v in db.scalars(select(AuditoriaExternaVersion).where(
        AuditoriaExternaVersion.nombre_archivo.in_([n for n, _ in leidos])))}
    lecturas = {nombre: leer_auditoria_externa(contenido, nombre) for nombre, contenido in leidos}
    for nombre, _ in leidos:
        if nombre not in repetidas and (igual := _version_igual(db, lecturas[nombre])):
            repetidas[nombre] = igual
    # Todo se valida antes de escribir archivos: un error a mitad del lote no deja PDF huérfanos en el bucket
    for nombre, _ in leidos:
        lectura = lecturas[nombre]
        if not lectura.texto_leido:
            raise HTTPException(400, f"No se pudo leer el texto de «{nombre}»: parece escaneado o dañado. "
                                     "Sube el PDF original que entregó la certificadora.")
        if nombre not in repetidas:
            empresa_id = {"LH": 1, "VS": 2}.get(lectura.empresa or "")
            temporada_al_guardar(db, temporada, lectura.fecha_inicio, empresa_id)
    if repetidas and not reemplazar:
        raise error_duplicado(
            "Estos informes ya están subidos." if len(repetidas) > 1 else "Este informe ya está subido.",
            [existente(v.nombre_archivo, v.subido_en, v.subido_por.nombre if v.subido_por else None,
                       f"{v.auditoria.titulo} · versión {v.numero}") for v in repetidas.values()])
    resultados = []
    for nombre, contenido in leidos:
        if nombre in repetidas:
            resultados.append(_reemplazar_version(db, repetidas[nombre], contenido, nombre, usuario))
        else:
            resultados.append(registrar_informe(db, contenido, nombre, usuario, temporada))
    db.commit()
    return resultados


@router.get("/{auditoria_id}")
def detalle(auditoria_id: str, _: Usuario = Depends(solo_ve_todo), db: Session = Depends(get_db)) -> dict:
    unidades, empresas = _catalogos(db)
    return _dict(obtener(db, AuditoriaExterna, auditoria_id), unidades, empresas, detalle=True)


@router.post("/{auditoria_id}/versiones", status_code=201)
async def nueva_version(auditoria_id: str, archivo: UploadFile = File(...), reemplazar: bool = Form(False),
                        usuario: Usuario = Depends(solo_certificaciones), db: Session = Depends(get_db)) -> dict:
    auditoria = obtener(db, AuditoriaExterna, auditoria_id)
    contenido, nombre = await _leer_archivo(archivo)
    lectura = leer_auditoria_externa(contenido, nombre)
    repetida = next((v for v in auditoria.versiones if v.nombre_archivo == nombre or v.resumen == _resumen(lectura)), None)
    if repetida and not reemplazar:
        raise error_duplicado(f"Este informe ya está subido como versión {repetida.numero}.",
                              [existente(nombre, repetida.subido_en, repetida.subido_por.nombre if repetida.subido_por else None)])
    if repetida:
        _reemplazar_version(db, repetida, contenido, nombre, usuario)
    else:
        version = _nueva_version(db, auditoria, contenido, nombre, lectura, usuario)
        db.flush()
        registrar(db, usuario, "nueva_version", "auditoria_externa", auditoria.id, {"archivo": nombre, "version": version.numero})
    db.commit()
    unidades, empresas = _catalogos(db)
    return _dict(auditoria, unidades, empresas, detalle=True)


@router.get("/versiones/{version_id}/descarga")
def descargar(version_id: str, _: Usuario = Depends(solo_ve_todo), db: Session = Depends(get_db)) -> dict:
    version = obtener(db, AuditoriaExternaVersion, version_id)
    return {"url": almacenamiento.url_descarga(version.archivo_key, version.nombre_archivo)}


@router.get("/{auditoria_id}/resumen.{formato}")
def resumen(auditoria_id: str, formato: str, _: Usuario = Depends(solo_ve_todo),
            db: Session = Depends(get_db)) -> Response:
    """Resumen del informe en PDF o Word."""
    if formato not in ("pdf", "docx"):
        raise HTTPException(404, "Formato no disponible")
    unidades, empresas = _catalogos(db)
    datos = _dict(obtener(db, AuditoriaExterna, auditoria_id), unidades, empresas, detalle=True)
    nombre = nombre_archivo_seguro(f"Resumen {datos['titulo']} {datos['tipo_nombre']}", 120)
    if formato == "pdf":
        return Response(resumen_pdf(datos), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}.pdf"'})
    return Response(resumen_docx(datos),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.docx"'})
