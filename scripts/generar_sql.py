"""Genera el DDL de Certificaciones (MySQL) para revisarlo antes de aplicarlo en Cloud SQL.

Solo las tablas propias (certificaciones_*) y sus vistas: las tablas general_* y usuario_* ya existen en la base
y no se crean ni se modifican. No se conecta a ninguna base.
"""
import sys
from pathlib import Path

from sqlalchemy import create_mock_engine
from sqlalchemy.schema import CreateIndex, CreateTable

from utils.modelos import tablas_propias

VISTAS = Path(__file__).resolve().parents[1] / "migrations" / "vistas_mysql.sql"


def main() -> None:
    engine = create_mock_engine("mysql+pymysql://", lambda *a, **k: None)
    salida = ["-- Esquema Certificaciones (MySQL). Generado desde utils/modelos.py",
              "-- Requiere las tablas compartidas general_empresa/sucursal/temporada/usuario ya existentes.\n"]
    for tabla in tablas_propias():
        salida.append(str(CreateTable(tabla).compile(dialect=engine.dialect)).strip() + ";\n")
        for indice in tabla.indexes:
            salida.append(str(CreateIndex(indice).compile(dialect=engine.dialect)).strip() + ";\n")
    salida.append(VISTAS.read_text(encoding="utf-8"))
    sys.stdout.write("\n".join(salida))


if __name__ == "__main__":
    main()
