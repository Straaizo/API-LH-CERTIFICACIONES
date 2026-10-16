from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from utils import almacenamiento
from utils.auth import NC, es_certificaciones, requiere_permiso, solo_certificaciones, usuario_actual, verificar_unidad
from utils.bitacora import registrar
from utils.comunes import filtrar_temporada, filtrar_unidades, obtener, unidad_dict
from utils.db import get_db
from utils.modelos import AccionCorrectiva, Auditoria, NoConformidad, Usuario, VersionNorma
from utils.hora import ahora

router = APIRouter(prefix="/no-conformidades")

TIPOS = ("infraestructura", "documental", "operacional")
PORQUES = 5
CLASIFICACIONES = ("menor", "mayor", "critica")


class PlanAccion(BaseModel):
    """Lo completa el jefe de área: 5 porqués, acción correctiva y acción preventiva."""
    causa_raiz: list[str] = Field(default=[], max_length=PORQUES)
    accion_correctiva: str | None = None
    accion_preventiva: str | None = None
    enviar: bool = False


class NcCambios(BaseModel):
    descripcion: str | None = None
    tipo: str | None = None
    clasificacion: str | None = None
    responsable_id: str | None = None
    plazo: date | None = None
    area_id: int | None = None
    estado: str | None = None


class AccionEntrada(BaseModel):
    """Levantamiento: la evidencia (foto o documento) que sube el jefe de área."""
    archivo_key: str
    nombre_archivo: str
    descripcion: str = "Evidencia"


def _cadena(nc: NoConformidad) -> list[dict]:
    """NC anteriores del mismo requisito y unidad (reincidencias)."""
    cadena, actual = [], nc.reincidente_de
    while actual is not None and len(cadena) < 10:
        cadena.append({"id": actual.id, "fecha": actual.fecha_deteccion, "estado": actual.estado,
                       "descripcion": actual.descripcion})
        actual = actual.reincidente_de
    return cadena


def _titulo(a: Auditoria) -> str:
    return a.titulo or f"Auditoría interna {a.version.protocolo.nombre} · {a.unidad.etiqueta} · {a.fecha:%m-%Y}"


def _nc_dict(nc: NoConformidad, detalle: bool = False) -> dict:
    hoy = date.today()
    fin = nc.cerrada_en.date() if nc.cerrada_en else hoy
    datos = {
        "id": nc.id, "descripcion": nc.descripcion, "tipo": nc.tipo, "clasificacion": nc.clasificacion,
        "estado": nc.estado, "plazo": nc.plazo, "fecha_deteccion": nc.fecha_deteccion,
        "dias_abierta": (fin - nc.fecha_deteccion).days,
        "vencida": bool(nc.plazo and nc.plazo < hoy and nc.estado != "cerrada"),
        "requisito": {"id": nc.requisito.id, "codigo": nc.requisito.codigo, "nivel": nc.requisito.nivel},
        "protocolo": {"id": nc.auditoria.version.protocolo.id, "codigo": nc.auditoria.version.protocolo.codigo},
        "auditoria": {"id": nc.auditoria.id, "fecha": nc.auditoria.fecha, "titulo": _titulo(nc.auditoria),
                      "emitida_en": nc.auditoria.emitida_en},
        "clausula": nc.requisito.seccion, "clausula_titulo": nc.requisito.seccion_titulo,
        "dias_para_plazo": (nc.plazo - hoy).days if nc.plazo and nc.estado != "cerrada" else None,
        "plan": {"causa_raiz": nc.causa_raiz or [], "accion_correctiva": nc.accion_correctiva,
                 "accion_preventiva": nc.accion_preventiva,
                 "por": nc.plan_por.nombre if nc.plan_por else None, "en": nc.plan_en,
                 "enviado_en": nc.plan_enviado_en},
        "unidad": unidad_dict(nc.unidad), "area": {"id": nc.area.id, "nombre": nc.area.nombre} if nc.area else None,
        "responsable": {"id": nc.responsable.id, "nombre": nc.responsable.nombre} if nc.responsable else None,
        # Reincidencia: certificaciones revisó y no quedó conforme (la devolvió)
        "reincidente": (nc.reincidencias or 0) > 0, "reincidencias": nc.reincidencias or 0,
        "ultima_revision": (nc.revisiones or [None])[-1],
        # Hallazgo repetido: el mismo requisito ya había fallado en una auditoría anterior
        "repetida": nc.reincidente_de_id is not None,
        "repetida_de": {"id": nc.reincidente_de.id, "fecha": nc.reincidente_de.fecha_deteccion}
        if nc.reincidente_de else None,
        "acciones": len(nc.acciones), "cerrada_en": nc.cerrada_en,
    }
    if detalle:
        datos["requisito"]["texto"] = nc.requisito.texto.split("\n\nCriterio")[0]
        datos["historial_repeticiones"] = _cadena(nc)
        datos["revisiones"] = nc.revisiones or []
        datos["acciones"] = [
            {"id": a.id, "descripcion": a.descripcion, "nombre_archivo": a.nombre_archivo,
             "tiene_evidencia": bool(a.archivo_key), "creada_por": a.creada_por.nombre, "creada_en": a.creada_en}
            for a in nc.acciones
        ]
    return datos


@router.get("")
def listar(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
           protocolo_id: int | None = None, estado: str | None = None, solo_reincidentes: bool = False,
           solo_repetidas: bool = False,
           responsable_id: str | None = None, usuario: Usuario = Depends(usuario_actual),
           db: Session = Depends(get_db)) -> list[dict]:
    consulta = filtrar_unidades(
        select(NoConformidad).join(Auditoria).options(selectinload(NoConformidad.acciones)),
        NoConformidad.unidad_id, usuario, empresa_id, unidad_id)
    if not es_certificaciones(usuario):
        # El jefe de campo o área ve las no conformidades cuando se emite el informe de la auditoría
        consulta = consulta.where(Auditoria.emitida_en.is_not(None))
    consulta = filtrar_temporada(db, consulta, temporada_id, NoConformidad.fecha_deteccion, NoConformidad.unidad_id)
    if protocolo_id:
        consulta = consulta.where(Auditoria.version_id.in_(
            select(VersionNorma.id).where(VersionNorma.protocolo_id == protocolo_id)))
    if estado == "pendientes":
        consulta = consulta.where(NoConformidad.estado != "cerrada")
    elif estado:
        consulta = consulta.where(NoConformidad.estado == estado)
    if solo_reincidentes:
        consulta = consulta.where(NoConformidad.reincidencias > 0)
    if solo_repetidas:
        consulta = consulta.where(NoConformidad.reincidente_de_id.is_not(None))
    if responsable_id:
        consulta = consulta.where(NoConformidad.responsable_id == responsable_id)
    return [_nc_dict(nc) for nc in db.scalars(consulta.order_by(NoConformidad.fecha_deteccion.desc(), NoConformidad.id))]


@router.get("/{nc_id}")
def detalle(nc_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    nc = obtener(db, NoConformidad, nc_id)
    verificar_unidad(usuario, nc.unidad_id)
    if not es_certificaciones(usuario) and not nc.auditoria.emitida_en:
        raise HTTPException(404, "El informe de esta auditoría aún no se emite")
    return _nc_dict(nc, detalle=True)


@router.put("/{nc_id}/plan")
def guardar_plan(nc_id: int, datos: PlanAccion, usuario: Usuario = Depends(requiere_permiso(NC)),
                 db: Session = Depends(get_db)) -> dict:
    """El jefe de área registra el análisis de causa raíz y las acciones. Puede guardar y seguir después;
    al enviar quedan para revisión de certificaciones."""
    nc = obtener(db, NoConformidad, nc_id)
    verificar_unidad(usuario, nc.unidad_id)
    if not es_certificaciones(usuario) and not nc.auditoria.emitida_en:
        raise HTTPException(400, "El informe de esta auditoría aún no se emite")
    if nc.estado == "cerrada":
        raise HTTPException(400, "La no conformidad ya está cerrada")
    porques = [p.strip() for p in datos.causa_raiz][:PORQUES]
    if datos.enviar:
        faltan = []
        # Los 5 porqués son obligatorios: los exige el cliente y van en el documento final
        vacios = [str(i + 1) for i in range(PORQUES) if i >= len(porques) or not porques[i]]
        if vacios:
            faltan.append(f"porqué {', '.join(vacios)} del análisis de causa raíz")
        if not (datos.accion_correctiva or "").strip():
            faltan.append("acción correctiva")
        if not (datos.accion_preventiva or "").strip():
            faltan.append("acción preventiva")
        if faltan:
            raise HTTPException(400, f"Falta completar: {', '.join(faltan)}")
    nc.causa_raiz = porques
    nc.accion_correctiva = (datos.accion_correctiva or "").strip() or None
    nc.accion_preventiva = (datos.accion_preventiva or "").strip() or None
    nc.plan_por_id, nc.plan_en = usuario.id, ahora()
    if datos.enviar:
        nc.plan_enviado_en = ahora()
        if nc.estado == "abierta":
            nc.estado = "en_proceso"
    registrar(db, usuario, "enviar_plan" if datos.enviar else "guardar_plan", "no_conformidad", nc.id,
              {"porques": len([p for p in porques if p])})
    db.commit()
    db.refresh(nc)
    return _nc_dict(nc, detalle=True)


@router.patch("/{nc_id}")
def modificar(nc_id: int, datos: NcCambios, usuario: Usuario = Depends(solo_certificaciones),
              db: Session = Depends(get_db)) -> dict:
    nc = obtener(db, NoConformidad, nc_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios.get("tipo") not in (None, *TIPOS):
        raise HTTPException(400, "Tipo inválido")
    if cambios.get("clasificacion") not in (None, *CLASIFICACIONES):
        raise HTTPException(400, "Clasificación inválida")
    if "estado" in cambios:
        if cambios["estado"] == "cerrada":
            raise HTTPException(400, "Para cerrar usa la acción 'cerrar' (exige evidencia)")
        if nc.estado == "cerrada" or cambios["estado"] not in ("abierta", "en_proceso"):
            raise HTTPException(400, "Cambio de estado no permitido")
    for campo, valor in cambios.items():
        setattr(nc, campo, valor)
    registrar(db, usuario, "modificar", "no_conformidad", nc.id, datos.model_dump(mode="json", exclude_unset=True))
    db.commit()
    db.refresh(nc)
    return _nc_dict(nc, detalle=True)


@router.post("/{nc_id}/acciones", status_code=201)
def agregar_accion(nc_id: int, datos: AccionEntrada, usuario: Usuario = Depends(requiere_permiso(NC)),
                   db: Session = Depends(get_db)) -> dict:
    nc = obtener(db, NoConformidad, nc_id)
    verificar_unidad(usuario, nc.unidad_id)
    if nc.estado == "cerrada":
        raise HTTPException(400, "La no conformidad ya está cerrada")
    if datos.archivo_key and not almacenamiento.existe(datos.archivo_key):
        raise HTTPException(400, "La evidencia no se subió correctamente")
    db.add(AccionCorrectiva(no_conformidad_id=nc.id, creada_por_id=usuario.id, **datos.model_dump()))
    nc.estado = "en_proceso"
    registrar(db, usuario, "levantamiento", "no_conformidad", nc.id,
              {"descripcion": datos.descripcion, "evidencia": datos.nombre_archivo})
    db.commit()
    db.refresh(nc)
    return _nc_dict(nc, detalle=True)


class Revision(BaseModel):
    cumple: bool
    observacion: str | None = None


def _revision(nc: NoConformidad, usuario: Usuario, cumple: bool, observacion: str | None) -> None:
    nc.revisiones = (nc.revisiones or []) + [{
        "fecha": ahora().isoformat(timespec="minutes"), "por": usuario.nombre,
        "resultado": "cumple" if cumple else "no_cumple", "observacion": observacion}]


@router.post("/{nc_id}/revision")
def revisar(nc_id: int, datos: Revision, usuario: Usuario = Depends(solo_certificaciones),
            db: Session = Depends(get_db)) -> dict:
    """Certificaciones revisa el plan y la evidencia del jefe de área.
    Cumple: se cierra (exige evidencia). No cumple: vuelve al jefe de área y cuenta como reincidencia."""
    nc = obtener(db, NoConformidad, nc_id)
    if nc.estado == "cerrada":
        raise HTTPException(400, "Ya está cerrada")
    if not nc.plan_enviado_en:
        raise HTTPException(400, "El jefe de área aún no envía su plan")
    observacion = (datos.observacion or "").strip() or None
    if datos.cumple:
        if not any(a.archivo_key for a in nc.acciones):
            raise HTTPException(400, "Solo se cierra con evidencia: falta que el jefe de área suba una foto o documento")
        _revision(nc, usuario, True, observacion)
        nc.estado, nc.cerrada_por_id, nc.cerrada_en = "cerrada", usuario.id, ahora()
        registrar(db, usuario, "cerrar", "no_conformidad", nc.id, {"observacion": observacion})
    else:
        if not observacion:
            raise HTTPException(400, "Indica por qué no cumple: el jefe de área lo verá para corregir")
        _revision(nc, usuario, False, observacion)
        nc.reincidencias = (nc.reincidencias or 0) + 1
        nc.plan_enviado_en = None
        nc.estado = "en_proceso"
        registrar(db, usuario, "devolver", "no_conformidad", nc.id,
                  {"observacion": observacion, "reincidencias": nc.reincidencias})
    db.commit()
    db.refresh(nc)
    return _nc_dict(nc, detalle=True)


@router.post("/{nc_id}/cerrar")
def cerrar(nc_id: int, usuario: Usuario = Depends(solo_certificaciones), db: Session = Depends(get_db)) -> dict:
    nc = obtener(db, NoConformidad, nc_id)
    if nc.estado == "cerrada":
        raise HTTPException(400, "Ya está cerrada")
    if not any(a.archivo_key for a in nc.acciones):
        raise HTTPException(400, "Solo se cierra con evidencia: falta un levantamiento con foto o PDF")
    _revision(nc, usuario, True, None)
    nc.estado, nc.cerrada_por_id, nc.cerrada_en = "cerrada", usuario.id, ahora()
    registrar(db, usuario, "cerrar", "no_conformidad", nc.id)
    db.commit()
    db.refresh(nc)
    return _nc_dict(nc, detalle=True)


@router.get("/acciones/{accion_id}/evidencia")
def evidencia(accion_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    accion = obtener(db, AccionCorrectiva, accion_id)
    verificar_unidad(usuario, accion.no_conformidad.unidad_id)
    if not accion.archivo_key:
        raise HTTPException(404, "Sin evidencia")
    return {"url": almacenamiento.url_descarga(accion.archivo_key, accion.nombre_archivo)}

