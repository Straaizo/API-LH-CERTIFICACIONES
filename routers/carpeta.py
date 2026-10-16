"""Carpeta para el auditor: un ZIP por protocolo, empresa, sucursal y temporada."""
import io
import zipfile
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from routers.auditorias import detalle as detalle_auditoria
from routers.documentos import version_vigente
from utils import almacenamiento
from utils.auth import usuario_actual, verificar_unidad
from utils.comunes import en_temporada, obtener, obtener_temporada
from utils.db import get_db
from utils.modelos import (
    Auditoria, Certificacion, Documento, DocumentoVersion, Empresa, NoConformidad, Protocolo, Unidad, Usuario,
    VersionNorma,
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
    temporada = obtener_temporada(db, temporada_id)
    unidad = obtener(db, Unidad, unidad_id) if unidad_id else None
    if unidad:
        verificar_unidad(usuario, unidad.id)
    elif usuario.rol == "encargado":
        raise HTTPException(403, "Indica una de tus sucursales")

    consulta = select(Documento).where(
        Documento.empresa_id == empresa.id,
        # Todos los documentos fijos de la empresa, salvo los certificados de otras normas
        Documento.id.not_in(select(DocumentoVersion.documento_id).join(
            Certificacion, Certificacion.documento_version_id == DocumentoVersion.id).where(
            Certificacion.protocolo_id != protocolo.id)),
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
            indice.append([doc.categoria.nombre, doc.codigo, doc.titulo, doc.seccion.capitalize(),
                           vigente.numero, vigente.fecha_emision, vigente.fecha_vencimiento, ruta])
        zf.writestr("Indice.xlsx", _excel(
            ["Categoría", "Código", "Título", "Sección", "Versión", "Emisión", "Vencimiento", "Archivo"], indice))

        auditorias = db.scalars(
            select(Auditoria).where(
                en_temporada(temporada, Auditoria.fecha, Auditoria.unidad_id), Auditoria.estado != "planificada",
                Auditoria.version_id.in_(select(VersionNorma.id).where(VersionNorma.protocolo_id == protocolo.id)),
                Auditoria.unidad_id == unidad.id if unidad else Auditoria.unidad_id.in_(
                    select(Unidad.id).where(Unidad.empresa_id == empresa.id)),
            ).order_by(Auditoria.fecha)).all()
        for a in auditorias:
            datos = detalle_auditoria(a.id, usuario, db)
            filas = [[i["requisito"]["seccion"], i["requisito"]["codigo"], i["requisito"]["nivel"],
                      i["requisito"]["texto"], RESULTADOS[i["resultado"]], i["comentario"]] for i in datos["items"]]
            nombre = nombre_archivo_seguro(f"Checklist {a.fecha.isoformat()} {a.unidad.etiqueta} {'-'.join(a.secciones or [])}")
            zf.writestr(f"Auditorias internas/{nombre}.xlsx", _excel(
                ["Sección", "Requisito", "Nivel", "Texto", "Resultado", "Comentario"], filas))

        ncs = db.scalars(select(NoConformidad).where(NoConformidad.auditoria_id.in_([a.id for a in auditorias]))
                         .order_by(NoConformidad.fecha_deteccion)).all()
        zf.writestr("No conformidades.xlsx", _excel(
            ["Detectada", "Sucursal", "Requisito", "Descripción", "Tipo", "Clasificación", "Responsable", "Plazo",
             "Estado", "Reincidente", "Levantamientos"],
            [[nc.fecha_deteccion, nc.unidad.etiqueta, nc.requisito.codigo, nc.descripcion, nc.tipo, nc.clasificacion,
              nc.responsable.nombre if nc.responsable else None, nc.plazo, nc.estado,
              "Sí" if nc.reincidente_de_id else "No", " | ".join(x.descripcion for x in nc.acciones)] for nc in ncs]))
        if faltantes:
            zf.writestr("LEEME_archivos_faltantes.txt", "\n".join(faltantes))

    nombre_zip = nombre_archivo_seguro(
        f"Carpeta {protocolo.codigo} {empresa.codigo} {unidad.etiqueta if unidad else 'todas'} {temporada.nombre} "
        f"{date.today().isoformat()}")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{nombre_zip}.zip"'})
