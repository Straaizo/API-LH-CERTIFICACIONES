"""
run_dev.py — Script de desarrollo para levantar la API y abrir Swagger UI (igual que API-BASE-LH).

Uso:
    python run_dev.py

Qué hace:
  1. Verifica que el archivo .env existe (si no, lo crea desde .env.example)
  2. Muestra la configuración activa (base de datos, autenticación, archivos)
  3. Levanta uvicorn con recarga automática (hot reload)
  4. Abre el navegador en http://localhost:8080/docs (Swagger UI)
"""

import os
import shutil
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent

from usar_venv import asegurar_venv  # noqa: E402

asegurar_venv()

# La consola de Windows (cp1252) no imprime los caracteres del banner ni las tildes
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# ── 1. Verificar / crear .env ─────────────────────────────────────────────────
env_file    = ROOT / ".env"
env_example = next((p for p in (ROOT / ".env.example", ROOT / "env.ejemplo") if p.exists()), ROOT / ".env.example")

if not env_file.exists():
    if env_example.exists():
        shutil.copy(env_example, env_file)
        print("=" * 60)
        print(f"  AVISO: Se creó el archivo .env desde {env_example.name}")
        print("  Edita .env con tus credenciales reales si no usas la demo.")
        print("=" * 60)
        print()
    else:
        print("ADVERTENCIA: No se encontró .env ni .env.example")

# ── 2. Cargar y mostrar configuración ─────────────────────────────────────────
from dotenv import load_dotenv  # noqa: E402

load_dotenv(env_file)

HOST   = "127.0.0.1"
PORT   = int(os.getenv("DEV_PORT", 8080))
RELOAD = True
URL    = f"http://{HOST}:{PORT}"

db_motor = os.getenv("DB_MOTOR", "sqlite")
db_url   = os.getenv("DATABASE_URL", "")
if db_url:
    modo_bd = "Cloud SQL (DATABASE_URL)"
elif db_motor == "sqlite":
    modo_bd = "Demo local (privado/demo.db)"
else:
    modo_bd = f"{db_motor} vía proxy ({os.getenv('DB_HOST', '127.0.0.1')})"
db_name  = "demo.db" if db_motor == "sqlite" and not db_url else os.getenv("DB_NAME", "(no definida)")
auth     = os.getenv("AUTH_MODO", "demo")
archivos = os.getenv("ALMACENAMIENTO", "local")

# ── 3 & 4. Levantar uvicorn y abrir navegador ────────────────────────────────
try:
    import uvicorn
except ImportError:
    print("ERROR: uvicorn no está instalado. Ejecuta: pip install -r requirements.txt")
    sys.exit(1)

# IMPORTANTE: el guard if __name__ == "__main__" es obligatorio en Windows
# cuando reload=True usa multiprocessing (spawn).
if __name__ == "__main__":
    # La variable de entorno la hereda el proceso hijo del reloader: evita banner y navegador duplicados
    if not os.environ.get("_RUN_DEV_STARTED"):
        os.environ["_RUN_DEV_STARTED"] = "1"

        if db_motor == "sqlite" and not db_url and not (ROOT / "privado" / "demo.db").exists():
            print("AVISO: no existe la base demo. Créala con:  python -m scripts.crear_demo")
            print()

        print()
        print("╔══════════════════════════════════════════════════════════╗")
        print("║        API Certificaciones VS y LH — FASTAPI             ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print(f"║ Servidor:   {URL:<45}║")
        print(f"║ Swagger UI: {URL + '/docs':<45}║")
        print(f"║ ReDoc:      {URL + '/redoc':<45}║")
        print("╠══════════════════════════════════════════════════════════╣")
        print(f"║ BD Modo:   {modo_bd:<45} ║")
        print(f"║ BD Nombre: {db_name:<45} ║")
        print(f"║ Auth:      {auth:<45} ║")
        print(f"║ Archivos:  {archivos:<45} ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print()

        def abrir_navegador():
            time.sleep(2)
            webbrowser.open(f"{URL}/docs")
            print(f"  → Navegador abierto en {URL}/docs")

        threading.Thread(target=abrir_navegador, daemon=True).start()

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        reload_dirs=[str(ROOT)],
        log_level="info",
    )
