"""Genera el DDL del esquema para el motor elegido, para revisarlo antes de aplicarlo en Cloud SQL.

Uso, desde API-CERTIFICACIONES/:  python -m scripts.generar_sql postgresql > migrations/001_esquema_inicial.sql
                                   python -m scripts.generar_sql mysql
No se conecta a ninguna base.
"""
import sys

from sqlalchemy import create_mock_engine
from sqlalchemy.schema import CreateIndex, CreateTable

from utils.db import Base
import utils.modelos  # noqa: F401  registra las tablas

DIALECTOS = {"postgresql": "postgresql://", "mysql": "mysql+pymysql://"}


def main() -> None:
    motor = sys.argv[1] if len(sys.argv) > 1 else ""
    if motor not in DIALECTOS:
        sys.exit("Indica el motor: postgresql | mysql")
    engine = create_mock_engine(DIALECTOS[motor], lambda *a, **k: None)
    print(f"-- Esquema inicial Certificaciones ({motor}). Generado desde utils/modelos.py\n")
    for tabla in Base.metadata.sorted_tables:
        print(str(CreateTable(tabla).compile(dialect=engine.dialect)).strip() + ";\n")
        for indice in tabla.indexes:
            print(str(CreateIndex(indice).compile(dialect=engine.dialect)).strip() + ";\n")


if __name__ == "__main__":
    main()
