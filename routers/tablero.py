from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from routers.auditorias import listar as listar_auditorias
from routers.auditorias import programa
from routers.documentos import calcular_vencimientos
from routers.laboratorio import listar as listar_analisis
from routers.no_conformidades import listar as listar_nc
from routers.registros import _atraso
from utils.auth import solo_certificaciones, usuario_actual
from utils.comunes import filtrar_unidades, temporada_actual
from utils.db import get_db
from utils.modelos import (
    Bitacora, Certificacion, Empresa, Protocolo, Registro,
    Temporada, Usuario,
)

router = APIRouter()


def _semaforo(cert: Certificacion | None, auditorias: list[dict], ncs: list[dict]) -> tuple[str, str]:
    """(color, motivo). Gris = sin información: nunca se presenta como cumplido."""
    hoy = date.today()
    if cert is None and not auditorias:
        return "gris", "Sin información cargada"
    if cert and cert.vigente_hasta and cert.vigente_hasta < hoy:
        return "rojo", "Certificado vencido"
    abiertas = [n for n in ncs if n["estado"] != "cerrada"]
    if any(n["vencida"] for n in abiertas):
        return "rojo", "NC con plazo vencido"
    cumplimientos = [a["resumen"]["cumplimiento"] for a in auditorias if a["resumen"]["cumplimiento"] is not None]
    ultimo = cumplimientos[0] if cumplimientos else None
    if ultimo is not None and ultimo < 80:
        return "rojo", f"Cumplimiento última auditoría {ultimo} %"
    if cert is None:
        return "amarillo", "Sin certificado vigente cargado"
    if cert.vigente_hasta and (cert.vigente_hasta - hoy).days <= 60:
        return "amarillo", f"Certificado vence en {(cert.vigente_hasta - hoy).days} días"
    if abiertas:
        return "amarillo", f"{len(abiertas)} NC abiertas"
    if ultimo is not None and ultimo < 95:
        return "amarillo", f"Cumplimiento última auditoría {ultimo} %"
    return "verde", "Al día"


@router.get("/dashboard")
def dashboard(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
              protocolo_id: int | None = None, usuario: Usuario = Depends(usuario_actual),
              db: Session = Depends(get_db)) -> dict:
    temporada = db.get(Temporada, temporada_id) if temporada_id else temporada_actual(db)
    t_id = temporada.id if temporada else None
    auditorias = listar_auditorias(empresa_id=empresa_id, unidad_id=unidad_id, temporada_id=t_id,
                                   protocolo_id=protocolo_id, usuario=usuario, db=db)
    ncs = listar_nc(empresa_id=empresa_id, unidad_id=unidad_id, temporada_id=None, protocolo_id=protocolo_id,
                    estado=None, solo_reincidentes=False, solo_repetidas=False, responsable_id=None,
                    usuario=usuario, db=db)
    analisis = listar_analisis(empresa_id=empresa_id, unidad_id=unidad_id, temporada_id=t_id, tipo_analisis_id=None,
                               solo_fuera_de_norma=False, usuario=usuario, db=db)
    vencimientos = calcular_vencimientos(db, usuario, empresa_id, unidad_id, protocolo_id)

    empresas = db.scalars(select(Empresa).where(Empresa.id == empresa_id) if empresa_id else select(Empresa)).all()
    protocolos = db.scalars(select(Protocolo).where(Protocolo.id == protocolo_id) if protocolo_id
                            else select(Protocolo).order_by(Protocolo.ambito, Protocolo.id)).all()
    semaforo = []
    for e in empresas:
        for p in protocolos:
            certs = db.scalars(select(Certificacion).where(Certificacion.empresa_id == e.id,
                                                           Certificacion.protocolo_id == p.id)
                               .order_by(Certificacion.vigente_hasta.desc())).all()
            if unidad_id:
                certs = [c for c in certs if unidad_id in {u.id for u in c.unidades}]
            unidades_e = [u for x in e.ubicaciones for u in x.unidades if not unidad_id or u.id == unidad_id]
            if not any(p.aplica_a(u) for u in unidades_e):
                continue
            aud = [a for a in auditorias if a["protocolo"]["id"] == p.id and a["unidad"]["empresa_id"] == e.id
                   and a["estado"] != "planificada"]
            nc_p = [n for n in ncs if n["protocolo"]["id"] == p.id and n["unidad"]["empresa_id"] == e.id]
            color, motivo = _semaforo(certs[0] if certs else None, aud, nc_p)
            semaforo.append({
                "empresa": e.codigo, "empresa_id": e.id, "protocolo": p.nombre, "protocolo_id": p.id,
                "ambito": p.ambito, "color": color, "motivo": motivo,
                "vigente_hasta": certs[0].vigente_hasta if certs else None,
                "cumplimiento": next((a["resumen"]["cumplimiento"] for a in aud
                                      if a["resumen"]["cumplimiento"] is not None), None),
                "nc_abiertas": sum(1 for n in nc_p if n["estado"] != "cerrada"),
            })

    abiertas = [n for n in ncs if n["estado"] != "cerrada"]

    def agrupar(clave) -> list[dict]:
        conteo: dict[str, int] = {}
        for n in abiertas:
            k = clave(n)
            conteo[k] = conteo.get(k, 0) + 1
        return [{"nombre": k, "cantidad": v} for k, v in sorted(conteo.items(), key=lambda x: -x[1])]

    registros = db.scalars(filtrar_unidades(select(Registro), Registro.unidad_id, usuario, empresa_id, unidad_id)).all()

    return {
        "temporada": {"id": t_id, "nombre": temporada.nombre if temporada else None},
        "kpis": {
            "registros_por_revisar": sum(1 for r in registros if r.estado == "en_revision"),
            "registros_atrasados": sum(1 for r in registros if _atraso(r)["atrasado"]),
            "vencidos": sum(1 for v in vencimientos if v["grupo"] == "vencido"),
            "vencen_30": sum(1 for v in vencimientos if 0 <= v["dias"] <= 30),
            "nc_abiertas": len(abiertas),
            "nc_reincidentes": sum(1 for n in abiertas if n["reincidente"]),
            "nc_vencidas": sum(1 for n in abiertas if n["vencida"]),
            "analisis_fuera_norma": sum(1 for a in analisis if a["fuera_de_norma"]),
            "analisis_total": len(analisis),
        },
        "semaforo": semaforo,
        "nc_por_responsable": agrupar(lambda n: n["responsable"]["nombre"] if n["responsable"] else "Sin asignar"),
        "nc_por_antiguedad": agrupar(lambda n: "0-30 días" if n["dias_abierta"] <= 30
                                     else "31-90 días" if n["dias_abierta"] <= 90 else "Más de 90 días"),
        "nc_reincidentes": [n for n in abiertas if n["reincidente"]][:10],
        "nc_repetidas": [n for n in abiertas if n["repetida"]][:10],
        "proximos_vencimientos": [v for v in vencimientos if v["dias"] <= 60][:10],
        "analisis_fuera_norma": [a for a in analisis if a["fuera_de_norma"]][:10],
        "cobertura": programa(t_id, empresa_id, unidad_id, protocolo_id, usuario, db)["filas"] if t_id else [],
    }


@router.get("/bitacora")
def bitacora(entidad: str | None = None, entidad_id: int | None = None, limite: int = 200,
             _: Usuario = Depends(solo_certificaciones), db: Session = Depends(get_db)) -> list[dict]:
    consulta = select(Bitacora).order_by(Bitacora.fecha_hora.desc(), Bitacora.id.desc()).limit(min(limite, 1000))
    if entidad:
        consulta = consulta.where(Bitacora.entidad == entidad)
    if entidad_id:
        consulta = consulta.where(Bitacora.entidad_id == entidad_id)
    return [{"id": b.id, "fecha_hora": b.fecha_hora, "usuario": b.usuario.nombre if b.usuario else "Sistema",
             "accion": b.accion, "entidad": b.entidad, "entidad_id": b.entidad_id, "detalle": b.detalle}
            for b in db.scalars(consulta)]
