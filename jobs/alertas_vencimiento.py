"""Job diario de avisos de vencimiento (Cloud Scheduler + Cloud Run job).

Avisa a 60, 30 y 7 días (DIAS_ALERTA) a los administradores de certificaciones (permiso CERTIFICACIONES_ADMIN).
El servicio de correo está pendiente de definir: por ahora solo imprime los avisos.

Uso, desde API-CERTIFICACIONES/:  python -m jobs.alertas_vencimiento
"""
from config import Config
from routers.catalogos import _usuarios_app
from routers.documentos import calcular_vencimientos
from utils.db import SessionLocal


def enviar_correo(destinatarios: list[str], asunto: str, cuerpo: str) -> None:
    # TODO conectar el servicio de correo cuando se defina (pendiente con el cliente)
    print(f"[correo] Para: {', '.join(destinatarios)} | {asunto}\n{cuerpo}\n")


def main() -> None:
    try:
        with SessionLocal() as db:
            items = [i for i in calcular_vencimientos(db, None) if i["dias"] in Config.DIAS_ALERTA]
            certificaciones = sorted(u.email for u in _usuarios_app(db) if u.rol == "certificaciones" and u.email)
        for item in items:
            enviar_correo(
                certificaciones,
                f"Vence en {item['dias']} días: {item['titulo']}",
                f"{item['detalle']} · {item['unidad']}\nVence el {item['vence']:%d-%m-%Y}.",
            )
        print(f"Avisos generados: {len(items)}")
    except Exception as exc:
        print(f"Error en el job de alertas: {exc}")
        raise


if __name__ == "__main__":
    main()
