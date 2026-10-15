import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _lista(valor: str) -> list[str]:
    return [v.strip() for v in valor.split(",") if v.strip()]


class Config:
    DEBUG = os.getenv("DEBUG", "True") == "True"
    # desarrollo | produccion
    ENTORNO = os.getenv("ENTORNO", "desarrollo")
    DEV_PORT = int(os.getenv("DEV_PORT", 8080))

    # ── CORS ──────────────────────────────────────────────────────────────────
    ORIGENES_PERMITIDOS = _lista(os.getenv("ORIGENES_PERMITIDOS", "http://localhost:5173"))

    # ── Conexión a base de datos ──────────────────────────────────────────────
    # sqlite = demo local en privado/demo.db | mysql | postgresql (motor por confirmar)
    DB_MOTOR = os.getenv("DB_MOTOR", "sqlite")
    # DATABASE_URL (formato SQLAlchemy) se usa en Cloud Run. Si no está, se arma con DB_*.
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    # Cuando corre en Cloud Run (K_SERVICE definido) el proxy escucha en localhost.
    if os.getenv("K_SERVICE"):
        DB_HOST = "localhost"
    else:
        DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = os.getenv("DB_PORT", "")
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "certificaciones")

    # ── Autenticación ─────────────────────────────────────────────────────────
    # demo: usuario elegido en pantalla (solo desarrollo) | firebase: token de Firebase Authentication
    AUTH_MODO = os.getenv("AUTH_MODO", "demo")
    # Demo publicada (Cloud Run): sin esta clave no se entra. Vacía = demo local sin clave.
    DEMO_CLAVE = os.getenv("DEMO_CLAVE", "").strip()
    # Demo publicada: carpeta (bucket montado) con la base y los archivos de partida
    SEMILLA_DIR = os.getenv("SEMILLA_DIR", "")

    # ── Archivos ──────────────────────────────────────────────────────────────
    # local: disco en privado/archivos | gcs: Cloud Storage con URLs firmadas
    ALMACENAMIENTO = os.getenv("ALMACENAMIENTO", "local")
    BUCKET_DOCUMENTOS = os.getenv("BUCKET_DOCUMENTOS", "")
    GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
    URL_PUBLICA_API = os.getenv("URL_PUBLICA_API", f"http://localhost:{DEV_PORT}")
    CLAVE_FIRMA_LOCAL = (os.getenv("CLAVE_FIRMA_LOCAL") or "solo-desarrollo-local").strip()

    PRIVADO_DIR = BASE_DIR / "privado"
    REFERENCIAS_DIR = BASE_DIR.parent / "referencias"

    # Días de aviso antes de un vencimiento
    DIAS_ALERTA = [int(d) for d in _lista(os.getenv("DIAS_ALERTA", "60,30,7"))]

    @classmethod
    def url_base_datos(cls) -> str:
        if cls.DATABASE_URL:
            return cls.DATABASE_URL
        if cls.DB_MOTOR == "sqlite":
            cls.PRIVADO_DIR.mkdir(exist_ok=True)
            return f"sqlite:///{(cls.PRIVADO_DIR / 'demo.db').as_posix()}"
        driver = {"postgresql": "postgresql+psycopg", "mysql": "mysql+pymysql"}[cls.DB_MOTOR]
        puerto = f":{cls.DB_PORT}" if cls.DB_PORT else ""
        return f"{driver}://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}{puerto}/{cls.DB_NAME}"


if Config.ENTORNO == "produccion" and (
    Config.AUTH_MODO == "demo" or Config.DB_MOTOR == "sqlite" or Config.ALMACENAMIENTO == "local"
):
    raise RuntimeError("En produccion no se permite AUTH_MODO=demo, DB_MOTOR=sqlite ni ALMACENAMIENTO=local")
