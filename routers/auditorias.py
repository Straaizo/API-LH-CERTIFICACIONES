from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from utils.auth import NC, solo_certificaciones, tiene_permiso, usuario_actual, verificar_unidad
from utils.bitacora import registrar
from utils.comunes import (
    filtrar_temporada, filtrar_unidades, obtener, obtener_temporada, temporada_dict, temporada_para_fecha, unidad_dict,
)
from utils.db import get_db
from utils.exportar_auditoria import exportar_auditoria
from utils.modelos import (
    Area, Auditoria, NoConformidad, Requisito, Respuesta, Unidad, Usuario, VersionNorma, usuario_sucursales,
)
from utils.no_conformidades import sincronizar_nc
from utils.servicio_importacion import importar_brcgs, importar_checklist
from utils.texto import nombre_archivo_seguro
from utils.hora import ahora

router = APIRouter()

MAX_PLANILLA = 15 * 1024 * 1024
# Plazo para responder las no conformidades desde que se emite el informe
PLAZO_NC_DIAS = 28


class AuditoriaEntrada(BaseModel):
    version_id: int
    unidad_id: int
    titulo: str | None = Field(default=None, max_length=250)
    fecha_inicio: date
    fecha_fin: date | None = None
    auditor: str | None = None


class AuditoriaCambios(BaseModel):
    titulo: str | None = Field(default=None, max_length=250)
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    auditor: str | None = None
    estado: str | None = None


class RespuestaEntrada(BaseModel):
    resultado: str | None  # si | no | na | None (sin responder)
    comentario: str | None = None
    area_id: int | None = None


def seccion_principal(requisito: Requisito) -> str:
    """'4.1.3' → '4' ; 'FV 30.02' → 'FV 30.02' (GLOBALG.A.P. usa la sección completa)."""
    return requisito.seccion if requisito.seccion.startswith("FV") else requisito.codigo.split(".")[0]


def en_alcance(requisito: Requisito, secciones: list[str]) -> bool:
    return not secciones or seccion_principal(requisito) in secciones


def resumen_respuestas(respuestas: list[Respuesta]) -> dict:
    conteo = {"si": 0, "no": 0, "na": 0, "sin": 0}
    por_nivel: dict[str, dict[str, int]] = {}
    for r in respuestas:
        conteo[r.resultado or "sin"] += 1
        nivel = r.requisito.nivel
        if nivel and r.resultado in ("si", "no"):
            por_nivel.setdefault(nivel, {"si": 0, "no": 0})[r.resultado] += 1
    evaluados = conteo["si"] + conteo["no"]
    datos = conteo | {"cumplimiento": round(conteo["si"] / evaluados * 100, 1) if evaluados else None}
    niveles = {n: round(v["si"] / (v["si"] + v["no"]) * 100, 1) for n, v in por_nivel.items()}
    datos["por_nivel"] = niveles
    if "mayor" in niveles or "menor" in niveles:
        # Regla GLOBALG.A.P.: 100 % de mayores y 95 % de menores
        datos["aprueba"] = niveles.get("mayor", 100) >= 100 and niveles.get("menor", 100) >= 95
    return datos


def titulo_auditoria(a: Auditoria) -> str:
    return a.titulo or f"Auditoría interna {a.version.protocolo.nombre} · {a.unidad.etiqueta} · {a.fecha:%m-%Y}"


def _auditoria_dict(a: Auditoria, ncs: int = 0) -> dict:
    return {
        "id": a.id, "titulo": titulo_auditoria(a), "fecha": a.fecha, "fecha_inicio": a.fecha,
        "fecha_fin": a.fecha_fin, "emitida_en": a.emitida_en,
        "auditor": a.auditor, "estado": a.estado, "origen": a.origen,
        "secciones": a.secciones or [], "temporada_id": a.temporada_id, "archivo_origen": a.archivo_origen,
        "advertencias": a.advertencias or [],
        "protocolo": {"id": a.version.protocolo.id, "codigo": a.version.protocolo.codigo,
                      "nombre": a.version.protocolo.nombre},
        "version": {"id": a.version.id, "nombre": a.version.nombre},
        "unidad": unidad_dict(a.unidad), "resumen": resumen_respuestas(a.respuestas), "no_conformidades": ncs,
    }


@router.get("/auditorias")
def listar(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
           protocolo_id: int | None = None, usuario: Usuario = Depends(usuario_actual),
           db: Session = Depends(get_db)) -> list[dict]:
    consulta = filtrar_unidades(
        select(Auditoria).options(selectinload(Auditoria.respuestas).selectinload(Respuesta.requisito)),
        Auditoria.unidad_id, usuario, empresa_id, unidad_id)
    consulta = filtrar_temporada(db, consulta, temporada_id, Auditoria.fecha, Auditoria.unidad_id)
    if protocolo_id:
        consulta = consulta.where(Auditoria.version_id.in_(
            select(VersionNorma.id).where(VersionNorma.protocolo_id == protocolo_id)))
    auditorias = db.scalars(consulta.order_by(Auditoria.fecha.desc())).all()
    conteo = {}
    for nc in db.scalars(select(NoConformidad).where(NoConformidad.auditoria_id.in_([a.id for a in auditorias]))):
        conteo[nc.auditoria_id] = conteo.get(nc.auditoria_id, 0) + 1
    return [_auditoria_dict(a, conteo.get(a.id, 0)) for a in auditorias]


@router.post("/auditorias", status_code=201)
def planificar(datos: AuditoriaEntrada, usuario: Usuario = Depends(solo_certificaciones),
               db: Session = Depends(get_db)) -> dict:
    version = obtener(db, VersionNorma, datos.version_id)
    unidad = obtener(db, Unidad, datos.unidad_id)
    if not version.protocolo.aplica_a(unidad):
        raise HTTPException(400, f"{version.protocolo.nombre} no aplica a {unidad.etiqueta}")
    if datos.fecha_fin and datos.fecha_fin < datos.fecha_inicio:
        raise HTTPException(400, "La fecha de fin no puede ser anterior a la de inicio")
    if not temporada_para_fecha(db, datos.fecha_inicio, unidad.empresa_id):
        raise HTTPException(400, "La fecha no cae en ninguna temporada registrada")
    # Sin cláusulas: la auditoría incluye todas las de la versión de la norma
    auditoria = Auditoria(version_id=version.id, unidad_id=unidad.id, titulo=(datos.titulo or "").strip() or None,
                          fecha=datos.fecha_inicio, fecha_fin=datos.fecha_fin, auditor=datos.auditor, secciones=[],
                          estado="planificada", origen="app")
    db.add(auditoria)
    db.flush()
    registrar(db, usuario, "planificar", "auditoria", auditoria.id, datos.model_dump(mode="json"))
    db.commit()
    db.refresh(auditoria)
    return _auditoria_dict(auditoria)


@router.patch("/auditorias/{auditoria_id}")
def modificar(auditoria_id: int, datos: AuditoriaCambios, usuario: Usuario = Depends(solo_certificaciones),
              db: Session = Depends(get_db)) -> dict:
    auditoria = obtener(db, Auditoria, auditoria_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "estado" in cambios and cambios["estado"] not in ("planificada", "en_curso", "cerrada"):
        raise HTTPException(400, "Estado inválido")
    if auditoria.emitida_en and set(cambios) - {"titulo"}:
        raise HTTPException(400, "El informe ya fue emitido")
    if "fecha_inicio" in cambios:
        if not temporada_para_fecha(db, cambios["fecha_inicio"], auditoria.unidad.empresa_id):
            raise HTTPException(400, "La fecha no cae en ninguna temporada registrada")
        auditoria.fecha = cambios.pop("fecha_inicio")
    for campo, valor in cambios.items():
        setattr(auditoria, campo, valor)
    if auditoria.fecha_fin and auditoria.fecha_fin < auditoria.fecha:
        raise HTTPException(400, "La fecha de fin no puede ser anterior a la de inicio")
    registrar(db, usuario, "modificar", "auditoria", auditoria.id, datos.model_dump(mode="json", exclude_unset=True))
    db.commit()
    db.refresh(auditoria)
    return _auditoria_dict(auditoria)


def _historial(db: Session, auditoria: Auditoria) -> dict[int, list[dict]]:
    """Resultados de auditorías anteriores de la misma norma y unidad, por requisito (más reciente primero)."""
    anteriores = db.scalars(
        select(Auditoria).where(Auditoria.version_id == auditoria.version_id, Auditoria.unidad_id == auditoria.unidad_id,
                                Auditoria.fecha < auditoria.fecha, Auditoria.id != auditoria.id)
        .order_by(Auditoria.fecha.desc())
    ).all()
    historial: dict[int, list[dict]] = {}
    for a in anteriores:
        for r in a.respuestas:
            if r.resultado:
                historial.setdefault(r.requisito_id, []).append(
                    {"auditoria_id": a.id, "fecha": a.fecha, "resultado": r.resultado, "comentario": r.comentario})
    return historial


@router.get("/auditorias/{auditoria_id}")
def detalle(auditoria_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    auditoria = obtener(db, Auditoria, auditoria_id)
    verificar_unidad(usuario, auditoria.unidad_id)
    respuestas = {r.requisito_id: r for r in auditoria.respuestas}
    ncs = {nc.requisito_id: nc for nc in db.scalars(select(NoConformidad).where(NoConformidad.auditoria_id == auditoria.id))}
    historial = _historial(db, auditoria)
    requisitos = [r for r in auditoria.version.requisitos if en_alcance(r, auditoria.secciones or [])]
    items = []
    for req in requisitos:
        resp = respuestas.get(req.id)
        nc = ncs.get(req.id)
        items.append({
            "requisito": {"id": req.id, "codigo": req.codigo, "texto": req.texto, "nivel": req.nivel,
                          "seccion": req.seccion, "seccion_titulo": req.seccion_titulo},
            "resultado": resp.resultado if resp else None, "comentario": resp.comentario if resp else None,
            "area_id": resp.area_id if resp else None, "advertencia": resp.advertencia if resp else None,
            "no_conformidad": {"id": nc.id, "estado": nc.estado, "repetida": nc.reincidente_de_id is not None,
                               "reincidencias": nc.reincidencias or 0}
            if nc else None,
            "historial": historial.get(req.id, [])[:3],
        })
    return _auditoria_dict(auditoria, len(ncs)) | {
        "items": items,
        "clausulas": avance_clausulas(auditoria, requisitos),
        "areas": [{"id": a.id, "nombre": a.nombre} for a in db.scalars(select(Area).where(Area.unidad_id == auditoria.unidad_id))],
    }


def titulos_secciones(auditoria: Auditoria) -> dict[str, str]:
    titulos = {s["codigo"]: s.get("titulo", "") for s in (auditoria.version.secciones or [])}
    for r in auditoria.version.requisitos:
        titulos.setdefault(seccion_principal(r), r.seccion_titulo if r.seccion.startswith("FV") else "")
    return titulos


def avance_clausulas(auditoria: Auditoria, requisitos: list[Requisito]) -> list[dict]:
    """Por cláusula: cuántos requisitos tiene y cuántos ya se respondieron (para trabajar una por día)."""
    respuestas = {r.requisito_id: r.resultado for r in auditoria.respuestas}
    titulos = titulos_secciones(auditoria)
    salida: dict[str, dict] = {}
    for r in requisitos:
        c = salida.setdefault(seccion_principal(r), {"codigo": seccion_principal(r),
                                                     "titulo": titulos.get(seccion_principal(r), ""),
                                                     "total": 0, "respondidos": 0, "no": 0})
        c["total"] += 1
        if respuestas.get(r.id):
            c["respondidos"] += 1
        if respuestas.get(r.id) == "no":
            c["no"] += 1
    return list(salida.values())


def _encargado_de(db: Session, unidad_id: int) -> Usuario | None:
    """Jefe de la sucursal: usuario activo con esa sucursal y permiso para responder no conformidades."""
    candidatos = db.scalars(select(Usuario).where(Usuario.id_estado == 1, Usuario.id.in_(
        select(usuario_sucursales.c.id_usuario).where(usuario_sucursales.c.id_sucursal == unidad_id))))
    return next((u for u in candidatos if u.rol == "encargado" and tiene_permiso(u, NC)), None)


@router.post("/auditorias/{auditoria_id}/emitir")
def emitir(auditoria_id: int, usuario: Usuario = Depends(solo_certificaciones), db: Session = Depends(get_db)) -> dict:
    """Emite el informe: cierra la auditoría y entrega cada no conformidad al jefe del campo o área,
    con plazo de 28 días para el análisis de causa raíz y las acciones correctiva y preventiva."""
    auditoria = obtener(db, Auditoria, auditoria_id)
    if auditoria.emitida_en:
        raise HTTPException(400, "El informe ya fue emitido")
    momento = ahora()
    encargado = _encargado_de(db, auditoria.unidad_id)
    ncs = list(db.scalars(select(NoConformidad).where(NoConformidad.auditoria_id == auditoria.id)))
    for nc in ncs:
        nc.plazo = nc.plazo or (momento.date() + timedelta(days=PLAZO_NC_DIAS))
        if nc.responsable_id is None and encargado:
            nc.responsable_id = encargado.id
    auditoria.estado, auditoria.emitida_en, auditoria.emitida_por_id = "cerrada", momento, usuario.id
    registrar(db, usuario, "emitir", "auditoria", auditoria.id,
              {"no_conformidades": len(ncs), "responsable": encargado.nombre if encargado else None})
    db.commit()
    db.refresh(auditoria)
    return _auditoria_dict(auditoria, len(ncs)) | {"responsable": encargado.nombre if encargado else None,
                                                   "plazo_dias": PLAZO_NC_DIAS}


@router.get("/auditorias/{auditoria_id}/exportar")
def exportar(auditoria_id: int, clausulas: str | None = None, usuario: Usuario = Depends(usuario_actual),
             db: Session = Depends(get_db)) -> Response:
    """Excel con el formato de las planillas: todas las cláusulas o las indicadas ("5,6")."""
    auditoria = obtener(db, Auditoria, auditoria_id)
    verificar_unidad(usuario, auditoria.unidad_id)
    elegidas = [c.strip() for c in (clausulas or "").split(",") if c.strip()]
    requisitos = [r for r in auditoria.version.requisitos if en_alcance(r, auditoria.secciones or [])]
    titulos = titulos_secciones(auditoria)
    grupos: dict[str, list[Requisito]] = {}
    for r in requisitos:
        if not elegidas or seccion_principal(r) in elegidas:
            grupos.setdefault(seccion_principal(r), []).append(r)
    ncs = [nc for nc in db.scalars(select(NoConformidad).where(NoConformidad.auditoria_id == auditoria.id))
           if not elegidas or seccion_principal(nc.requisito) in elegidas]
    try:
        contenido = exportar_auditoria(auditoria, [(c, titulos.get(c, ""), reqs) for c, reqs in grupos.items()], ncs)
    except Exception as exc:
        raise HTTPException(500, f"No se pudo generar el archivo: {exc}") from exc
    sufijo = f"clausulas {'-'.join(elegidas)}" if elegidas else "completa"
    nombre = nombre_archivo_seguro(f"{titulo_auditoria(auditoria)} {sufijo}")
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.xlsx"'})


@router.put("/auditorias/{auditoria_id}/respuestas/{requisito_id}")
def responder(auditoria_id: int, requisito_id: int, datos: RespuestaEntrada,
              usuario: Usuario = Depends(solo_certificaciones), db: Session = Depends(get_db)) -> dict:
    auditoria = obtener(db, Auditoria, auditoria_id)
    if auditoria.estado == "cerrada":
        raise HTTPException(400, "La auditoría está cerrada")
    if datos.resultado not in (None, "si", "no", "na"):
        raise HTTPException(400, "Resultado inválido")
    if datos.resultado == "no" and not (datos.comentario or "").strip():
        raise HTTPException(400, "Un 'No' requiere comentario (será la descripción de la no conformidad)")
    requisito = obtener(db, Requisito, requisito_id)
    if requisito.version_id != auditoria.version_id:
        raise HTTPException(400, "El requisito no pertenece a la norma de la auditoría")
    respuesta = db.scalar(select(Respuesta).where(Respuesta.auditoria_id == auditoria.id,
                                                  Respuesta.requisito_id == requisito_id))
    if respuesta is None:
        respuesta = Respuesta(auditoria_id=auditoria.id, requisito_id=requisito_id)
        db.add(respuesta)
    respuesta.resultado, respuesta.comentario, respuesta.area_id = datos.resultado, datos.comentario, datos.area_id
    if auditoria.estado == "planificada":
        auditoria.estado = "en_curso"
    db.flush()
    nc = sincronizar_nc(db, auditoria, respuesta)
    registrar(db, usuario, "responder", "auditoria", auditoria.id,
              {"requisito": requisito.codigo, "resultado": datos.resultado})
    db.commit()
    db.refresh(auditoria)
    return {
        "resultado": respuesta.resultado,
        "no_conformidad": {"id": nc.id, "estado": nc.estado, "repetida": nc.reincidente_de_id is not None,
                               "reincidencias": nc.reincidencias or 0}
        if nc else None,
        "resumen": resumen_respuestas(auditoria.respuestas),
    }


# ---------- Programa anual ----------

@router.get("/programa")
def programa(temporada_id: int, empresa_id: int | None = None, unidad_id: int | None = None,
             protocolo_id: int | None = None, usuario: Usuario = Depends(usuario_actual),
             db: Session = Depends(get_db)) -> dict:
    temporada = obtener_temporada(db, temporada_id)
    auditorias = listar(empresa_id, unidad_id, temporada_id, protocolo_id, usuario, db)
    grupos: dict[tuple[int, int], dict] = {}
    for a in auditorias:
        clave = (a["version"]["id"], a["unidad"]["id"])
        grupos.setdefault(clave, {"protocolo": a["protocolo"], "version": a["version"], "unidad": a["unidad"],
                                  "auditorias": []})["auditorias"].append(a)
    filas = []
    for (version_id, _), grupo in grupos.items():
        version = db.get(VersionNorma, version_id)
        secciones = version.secciones or [
            {"codigo": c, "titulo": ""} for c in sorted({seccion_principal(r) for r in version.requisitos})]
        cobertura = []
        totales: dict[str, int] = {}
        for r in version.requisitos:
            totales[seccion_principal(r)] = totales.get(seccion_principal(r), 0) + 1
        respondidos: dict[str, int] = {}
        planificadas: set[str] = set()
        for a in grupo["auditorias"]:
            alcance = a["secciones"] or [s["codigo"] for s in secciones]
            if a["estado"] == "planificada":
                planificadas.update(alcance)
                continue
            modelo = db.get(Auditoria, a["id"])
            por_seccion: dict[str, int] = {}
            for resp in modelo.respuestas:
                if resp.resultado:
                    clave = seccion_principal(resp.requisito)
                    por_seccion[clave] = por_seccion.get(clave, 0) + 1
            for clave, n in por_seccion.items():
                respondidos[clave] = max(respondidos.get(clave, 0), n)
            planificadas.update(alcance)
        for s in secciones:
            total, hechos = totales.get(s["codigo"], 0), respondidos.get(s["codigo"], 0)
            if total and hechos >= total:
                estado = "cubierta"
            elif hechos:
                estado = "en_curso"
            elif s["codigo"] in planificadas:
                estado = "planificada"
            else:
                estado = "pendiente"
            cobertura.append(s | {"estado": estado, "total": total, "respondidos": hechos})
        cubiertas = sum(1 for c in cobertura if c["estado"] == "cubierta")
        filas.append(grupo | {"cobertura": cobertura,
                              "porcentaje": round(cubiertas / len(cobertura) * 100) if cobertura else None})
    return {"temporada": temporada_dict(temporada), "filas": filas}


# ---------- Importación de planillas ----------

async def _leer_planilla(archivo: UploadFile) -> bytes:
    if not (archivo.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Se espera una planilla .xlsx")
    contenido = await archivo.read()
    if len(contenido) > MAX_PLANILLA:
        raise HTTPException(413, "Planilla demasiado grande")
    return contenido


@router.post("/importaciones/brcgs")
async def importar_auditoria_brcgs(archivo: UploadFile = File(...), confirmar: bool = Form(False),
                                   unidad_id: int | None = Form(None), usuario: Usuario = Depends(solo_certificaciones),
                                   db: Session = Depends(get_db)) -> dict:
    """Sin confirmar: vista previa con lo detectado y los errores de la planilla. Confirmado: guarda."""
    contenido = await _leer_planilla(archivo)
    try:
        return importar_brcgs(db, contenido, archivo.filename, usuario, confirmar, unidad_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/importaciones/checklist")
async def importar_checklist_norma(archivo: UploadFile = File(...), confirmar: bool = Form(False),
                                   protocolo: str | None = Form(None), usuario: Usuario = Depends(solo_certificaciones),
                                   db: Session = Depends(get_db)) -> dict:
    """Checklist de una norma (GLOBALG.A.P. y add-on, GRASP, PrimusGFS). Sin confirmar: vista previa."""
    contenido = await _leer_planilla(archivo)
    try:
        return importar_checklist(db, contenido, archivo.filename, usuario, confirmar, protocolo or None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
