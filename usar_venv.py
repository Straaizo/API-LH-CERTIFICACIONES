"""Si el script se ejecuta con el Python global, se relanza con el del venv del proyecto.

Así `python run_dev.py` funciona aunque no se haya activado el venv.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def asegurar_venv() -> None:
    python_venv = ROOT / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if sys.prefix != sys.base_prefix:
        return
    if not python_venv.exists():
        print("ERROR: no existe el entorno virtual. Créalo desde API-CERTIFICACIONES/ con:")
        print("  python -m venv venv")
        print("  venv\\Scripts\\activate")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    try:
        resultado = subprocess.run([str(python_venv), *sys.argv], cwd=os.getcwd())
        sys.exit(resultado.returncode)
    except KeyboardInterrupt:
        sys.exit(0)
