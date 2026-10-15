"""Carpeta para el auditor: un ZIP por protocolo, empresa, unidad y temporada."""
import io
import zipfile
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from routers.auditorias import detalle as detalle_auditoria
from routers.documentos import version_vigente
from utils import almacenamiento
from utils.auth import usuario_actual, verificar_unidad
from utils.comunes import obtener
from utils.db import get_db
from utils.modelos import (
    Auditoria, Documento, Empresa, NoConformidad, Protocolo, Temporada, Unidad, Usuario, VersionNorma,
    documento_protocolos,
)
from utils.texto import nombre_archivo_seguro

router = APIRouter()

RESULTADOS = {"si": "Sí", "no": "No", "na": "N/A", None: ""}


def _excel(encabezado: list[str], filas: list[list]) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.append(encabezado)
    for f in filas:
        hoja.append(f)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


@router.get("/carpeta-auditor")
def carpeta_auditor(protocolo_id: int, empresa_id: int, temporada_id: int, unidad_id: int | None = None,
                    usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> StreamingResponse:
    protocolo = obtener(db, Protocolo, protocolo_id)
    empresa = obtener(db, Empresa, empresa_id)
    temporada = obtener(db, Temporada, temporada_id)
    unidad = obtener(db, Unidad, unidad_id) if unidad_id else None
    if unidad:
        verificar_unidad(usuario, unidad.id)
    elif usuario.rol == "encargado":
        raise HTTPException(403, "Indica una de tus sucursales")

    consulta = select(Documento).where(
        Documento.empresa_id == empresa.id,
        # Documentos del protocolo, o sin protocolo asignado (el formulario ya no los pide)
        or_(Documento.id.in_(select(documento_protocolos.c.documento_id)
                             .where(documento_protocolos.c.protocolo_id == protocolo.id)),
            Documento.id.not_in(select(documento_protocolos.c.documento_id))),
        or_(Documento.temporada_id == temporada.id, Documento.temporada_id.is_(None)),
    )
    if unidad:
        consulta = consulta.where(Documento.seccion.in_((unidad.tipo, "empresarial")))

    buffer = io.BytesIO()
    indice: list[list] = []
    faltantes: list[str] = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        usados: set[str] = set()
        for doc in db.scalars(consulta.order_by(Documento.categoria_id, Documento.titulo)):
            vigente = version_vigente(doc)
            if not vigente or not vigente.archivo_key:
                continue
            carpeta = nombre_archivo_seguro(doc.categoria.nombre)
            extension = (vigente.nombre_archivo or "").rsplit(".", 1)[-1] if "." in (vigente.nombre_archivo or "") else "pdf"
            base = nombre_archivo_seguro(f"{doc.codigo + ' - ' if doc.codigo else ''}{doc.titulo} v{vigente.numero}", 100)
            ruta = f"Documentos/{carpeta}/{base}.{extension}"
            n = 2
            while ruta in usados:
                ruta = f"Documentos/{carpeta}/{base}_{n}.{extension}"
                n += 1
            try:
                zf.writestr(ruta, almacenamiento.leer(vigente.archivo_key))
            except Exception:
                faltantes.append(ruta)
                continue
            usados.add(ruta)
            indice.append([doc.categoria.nombre, doc.codigo, doc.titulo, doc.unidad.nombre if doc.unidad else "Empresa",
                           vigente.numero, vigente.fecha_emision, vigente.fecha_vencimiento, ruta])
        zf.writestr("Indice.xlsx", _excel(
            ["Categoría", "Código", "Título", "Unidad", "Versión", "Emisión", "Vencimiento", "Archivo"], indice))

        auditorias = db.scalars(
            select(Auditoria).join(Unidad).where(
                Auditoria.temporada_id == temporada.id, Auditoria.estado != "planificada",
                Auditoria.version_id.in_(select(VersionNorma.id).where(VersionNorma.protocolo_id == protocolo.id)),
                Auditoria.unidad_id == unidad.id if unidad else Auditoria.unidad_id.in_(
                    [u.id for u in db.scalars(select(Unidad)) if u.empresa_id == empresa.id]),
            ).order_by(Auditoria.fecha)).all()
        for a in auditorias:
            datos = detalle_auditoria(a.id, usuario, db)
            filas = [[i["requisito"]["seccion"], i["requisito"]["codigo"], i["requisito"]["nivel"],
                      i["requisito"]["texto"], RESULTADOS[i["resultado"]], i["comentario"]] for i in datos["items"]]
            nombre = nombre_archivo_seguro(f"Checklist {a.fecha.isoformat()} {a.unidad.nombre} {'-'.join(a.secciones or [])}")
            zf.writestr(f"Auditorias internas/{nombre}.xlsx", _excel(
                ["Sección", "Requisito", "Nivel", "Texto", "Resultado", "Comentario"], filas))

        ncs = db.scalars(select(NoConformidad).where(NoConformidad.auditoria_id.in_([a.id for a in auditorias]))
                         .order_by(NoConformidad.fecha_deteccion)).all()
        zf.writestr("No conformidades.xlsx", _excel(
            ["Detectada", "Unidad", "Requisito", "Descripción", "Tipo", "Clasificación", "Responsable", "Plazo",
             "Estado", "Reincidente", "Levantamientos"],
            [[nc.fecha_deteccion, nc.unidad.nombre, nc.requisito.codigo, nc.descripcion, nc.tipo, nc.clasificacion,
              nc.responsable.nombre if nc.responsable else None, nc.plazo, nc.estado,
              "Sí" if nc.reincidente_de_id else "No", " | ".join(x.descripcion for x in nc.acciones)] for nc in ncs]))
        if faltantes:
            zf.writestr("LEEME_archivos_faltantes.txt", "\n".join(faltantes))

    nombre_zip = nombre_archivo_seguro(
        f"Carpeta {protocolo.codigo} {empresa.codigo} {unidad.nombre if unidad else 'todas'} {temporada.nombre} "
        f"{date.today().isoformat()}")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{nombre_zip}.zip"'})
