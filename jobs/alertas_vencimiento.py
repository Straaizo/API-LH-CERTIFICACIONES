"""Job diario de avisos de vencimiento (Cloud Scheduler + Cloud Run job).

Avisa a 60, 30 y 7 días (DIAS_ALERTA) al responsable y a certificaciones.
El servicio de correo está pendiente de definir: por ahora solo imprime los avisos.

Uso, desde API-CERTIFICACIONES/:  python -m jobs.alertas_vencimiento
"""
from sqlalchemy import select

from config import Config
from routers.documentos import calcular_vencimientos
from utils.db import SessionLocal
from utils.modelos import Usuario


def enviar_correo(destinatarios: list[str], asunto: str, cuerpo: str) -> None:
    # TODO conectar el servicio de correo cuando se defina (pendiente con el cliente)
    print(f"[correo] Para: {', '.join(destinatarios)} | {asunto}\n{cuerpo}\n")


def main() -> None:
    try:
        with SessionLocal() as db:
            items = [i for i in calcular_vencimientos(db, None) if i["dias"] in Config.DIAS_ALERTA]
            certificaciones = [u.email for u in db.scalars(
                select(Usuario).where(Usuario.rol == "certificaciones", Usuario.activo))]
            responsables = {u.nombre: u.email for u in db.scalars(select(Usuario).where(Usuario.activo))}
        for item in items:
            destinatarios = set(certificaciones)
            if item["responsable"] in responsables:
                destinatarios.add(responsables[item["responsable"]])
            enviar_correo(
                sorted(destinatarios),
                f"Vence en {item['dias']} días: {item['titulo']}",
                f"{item['detalle']} · {item['unidad']}\nVence el {item['vence']:%d-%m-%Y}.",
            )
        print(f"Avisos generados: {len(items)}")
    except Exception as exc:
        print(f"Error en el job de alertas: {exc}")
        raise


if __name__ == "__main__":
    main()
