"""Importación de planillas a la base. Sin confirmar, solo devuelve la vista previa."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from utils.bitacora import registrar
from utils.comunes import temporada_para_fecha
from utils.importadores import HojaImportada, ItemImportado, PuntoControl, leer_brcgs, orden_codigo
from utils.importar_checklist import leer_checklist
from utils.modelos import Auditoria, Protocolo, Requisito, Respuesta, Unidad, Usuario, VersionNorma
from utils.no_conformidades import sincronizar_nc
from utils.texto import normalizar

VERSION_BRCGS = "v9"


def _version(db: Session, codigo_protocolo: str, nombre: str) -> VersionNorma:
    protocolo = db.scalar(select(Protocolo).where(Protocolo.codigo == codigo_protocolo))
    if protocolo is None:
        raise ValueError(f"No existe el protocolo {codigo_protocolo}")
    version = db.scalar(select(VersionNorma).where(VersionNorma.protocolo_id == protocolo.id,
                                                   VersionNorma.nombre == nombre))
    if version is None:
        version = VersionNorma(protocolo_id=protocolo.id, nombre=nombre, vigente=True)
        db.add(version)
        db.flush()
    return version


def _detectar_unidad(db: Session, lugar: str) -> Unidad | None:
    buscado = normalizar(lugar)
    for unidad in db.scalars(select(Unidad)):
        if normalizar(unidad.nombre) == buscado:
            return unidad
    return None


def _deduplicar(items: list[ItemImportado]) -> list[ItemImportado]:
    """Si un requisito aparece repetido, se usa la primera fila con respuesta."""
    elegidos: dict[str, ItemImportado] = {}
    for item in items:
        actual = elegidos.get(item.codigo)
        if actual is None or (actual.resultado is None and item.resultado is not None):
            elegidos[item.codigo] = item
    return list(elegidos.values())


def importar_brcgs(db: Session, contenido: bytes, nombre_archivo: str, usuario: Usuario | None,
                   confirmar: bool, unidad_id: int | None = None) -> dict:
    hojas = leer_brcgs(contenido)
    salida = []
    for hoja in hojas:
        unidad = db.get(Unidad, unidad_id) if unidad_id else _detectar_unidad(db, hoja.lugar)
        temporada = temporada_para_fecha(db, hoja.fecha) if hoja.fecha else None
        origen = f"{nombre_archivo} / {hoja.hoja}"
        duplicada = db.scalar(select(Auditoria.id).where(Auditoria.archivo_origen == origen)) is not None
        resumen = hoja.resumen() | {
            "unidad": {"id": unidad.id, "nombre": unidad.nombre} if unidad else None,
            "temporada": temporada.nombre if temporada else None, "ya_importada": duplicada,
        }
        errores = []
        if not unidad:
            errores.append(f"No se reconoce la unidad '{hoja.lugar}'; indícala manualmente")
        if not temporada:
            errores.append("La fecha no cae en ninguna temporada registrada")
        if duplicada:
            errores.append("Esta hoja ya fue importada")
        resumen["errores"] = errores
        if confirmar and not errores:
            resumen["auditoria_id"] = _guardar_brcgs(db, hoja, unidad, temporada.id, origen, usuario)
        salida.append(resumen)
    if confirmar:
        db.commit()
    return {"archivo": nombre_archivo, "confirmado": confirmar, "hojas": salida}


def _guardar_brcgs(db: Session, hoja: HojaImportada, unidad: Unidad, temporada_id: int, origen: str,
                   usuario: Usuario | None) -> int:
    version = _version(db, "BRCGS", VERSION_BRCGS)
    existentes = {r.codigo: r for r in db.scalars(select(Requisito).where(Requisito.version_id == version.id))}
    advertencias_items = [f"{i.codigo}: {a}" for i in hoja.items for a in i.advertencias]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]
    # Las auditorías de planillas anteriores se consideran con informe ya emitido
    auditoria = Auditoria(
        version_id=version.id, unidad_id=unidad.id, temporada_id=temporada_id, fecha=hoja.fecha, fecha_fin=hoja.fecha,
        titulo=f"Auditoría interna BRCGS cláusula {', '.join(hoja.secciones)} · {meses[hoja.fecha.month - 1]} {hoja.fecha.year}",
        auditor=hoja.auditor.title(), secciones=hoja.secciones, estado="cerrada", origen="importada",
        archivo_origen=origen, advertencias=hoja.advertencias + advertencias_items,
        emitida_en=datetime.combine(hoja.fecha, datetime.min.time()),
    )
    db.add(auditoria)
    db.flush()
    for item in _deduplicar(hoja.items):
        requisito = existentes.get(item.codigo)
        if requisito is None:
            requisito = Requisito(
                version_id=version.id, codigo=item.codigo, seccion=item.seccion, seccion_titulo=item.seccion_titulo,
                texto=item.texto, nivel="fundamental" if item.fundamental else None, orden=orden_codigo(item.codigo),
            )
            db.add(requisito)
            db.flush()
            existentes[item.codigo] = requisito
        respuesta = Respuesta(
            auditoria_id=auditoria.id, requisito_id=requisito.id, resultado=item.resultado,
            comentario=item.comentario or None, advertencia="; ".join(item.advertencias) or None,
        )
        db.add(respuesta)
        db.flush()
        sincronizar_nc(db, auditoria, respuesta)
    registrar(db, usuario, "importar", "auditoria", auditoria.id, {"archivo": origen, "items": len(hoja.items)})
    return auditoria.id


def _comparar(anterior: VersionNorma, puntos: list[PuntoControl]) -> dict:
    """Diferencias contra la versión anterior del mismo protocolo: qué puntos se agregan, quitan o cambian."""
    previos = {r.codigo: r.texto for r in anterior.requisitos}
    nuevos = {p.codigo: p.texto for p in puntos}
    agregados = [c for c in nuevos if c not in previos]
    quitados = [c for c in previos if c not in nuevos]
    cambiados = [c for c in nuevos if c in previos and normalizar(nuevos[c]) != normalizar(previos[c])]
    return {"version": anterior.nombre, "agregados": agregados, "quitados": quitados, "cambiados": cambiados}


def importar_checklist(db: Session, contenido: bytes, nombre_archivo: str, usuario: Usuario | None,
                       confirmar: bool, protocolo_codigo: str | None = None) -> dict:
    """Checklist de cualquier norma conocida. Si la versión ya existe (p. ej. otro módulo de PrimusGFS),
    se agregan solo los puntos que falten; si es una versión nueva, las anteriores dejan de estar vigentes."""
    leido = leer_checklist(contenido, nombre_archivo)
    codigo = protocolo_codigo or leido.protocolo_sugerido
    protocolo = db.scalar(select(Protocolo).where(Protocolo.codigo == codigo)) if codigo else None
    niveles: dict[str, int] = {}
    secciones: dict[str, str] = {}
    for p in leido.puntos:
        niveles[p.nivel] = niveles.get(p.nivel, 0) + 1
        secciones.setdefault(p.seccion, p.seccion_titulo)
    resumen = {"archivo": nombre_archivo, "formato": leido.formato, "protocolo_sugerido": leido.protocolo_sugerido,
               "protocolo": codigo, "protocolo_nombre": protocolo.nombre if protocolo else None,
               "version": leido.version, "puntos": len(leido.puntos), "niveles": niveles,
               "secciones": [{"codigo": c, "titulo": t} for c, t in secciones.items()],
               "muestra": [{"codigo": p.codigo, "seccion": p.seccion, "texto": p.texto[:240], "nivel": p.nivel}
                           for p in leido.puntos[:6]],
               "advertencias": leido.advertencias, "version_existente": None, "comparacion": None,
               "confirmado": confirmar, "nuevos": 0}
    if protocolo:
        versiones = sorted(protocolo.versiones, key=lambda v: v.id)
        existente = next((v for v in versiones if v.nombre == leido.version), None)
        if existente:
            ya = {r.codigo for r in existente.requisitos}
            resumen["version_existente"] = {"requisitos": len(ya),
                                            "faltantes": sum(1 for p in leido.puntos if p.codigo not in ya)}
        elif versiones:
            resumen["comparacion"] = _comparar(versiones[-1], leido.puntos)
    if not confirmar:
        return resumen
    if not protocolo:
        raise ValueError("Elige a qué protocolo corresponde el checklist")
    es_nueva = resumen["version_existente"] is None
    version = _version(db, protocolo.codigo, leido.version)
    if es_nueva:
        version.archivo = nombre_archivo
        for otra in protocolo.versiones:
            if otra.id != version.id:
                otra.vigente = False
    previas = {s["codigo"]: s for s in version.secciones or []}
    for c, t in secciones.items():
        previas.setdefault(c, {"codigo": c, "titulo": t})
    version.secciones = sorted(previas.values(), key=lambda s: orden_codigo(s["codigo"]))
    existentes = set(db.scalars(select(Requisito.codigo).where(Requisito.version_id == version.id)))
    for p in leido.puntos:
        if p.codigo in existentes:
            continue
        db.add(Requisito(version_id=version.id, codigo=p.codigo, seccion=p.seccion,
                         seccion_titulo=p.seccion_titulo, texto=p.texto, nivel=p.nivel, orden=p.orden))
        resumen["nuevos"] += 1
    registrar(db, usuario, "importar", "norma", version.id,
              {"archivo": nombre_archivo, "protocolo": protocolo.codigo, "version": version.nombre,
               "nuevos": resumen["nuevos"]})
    db.commit()
    resumen["version_id"] = version.id
    return resumen
