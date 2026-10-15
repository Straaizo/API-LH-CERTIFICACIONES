"""Demo publicada en Cloud Run: el disco del contenedor parte vacío en cada arranque.

Si SEMILLA_DIR apunta a la carpeta de partida (bucket privado montado como volumen, solo lectura) y aún no hay
base local, copia la base y los archivos a privado/. Los cambios hechos en la demo duran mientras viva el contenedor.
Uso (lo hace el Dockerfile al arrancar): python scripts/cargar_semilla.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config  # noqa: E402

origen = Path(Config.SEMILLA_DIR) if Config.SEMILLA_DIR else None
destino = Config.PRIVADO_DIR
if not origen:
    print("Sin SEMILLA_DIR: se usa la base local tal como esté.")
elif (destino / "demo.db").exists():
    print("La base de la demo ya existe: no se reemplaza.")
elif not (origen / "demo.db").exists():
    sys.exit(f"No se encontró {origen / 'demo.db'}: revisa el bucket montado en SEMILLA_DIR.")
else:
    shutil.copytree(origen, destino, dirs_exist_ok=True)
    print(f"Demo cargada desde {origen}.")
