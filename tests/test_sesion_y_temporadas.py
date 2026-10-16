"""Inicio de sesión (tablas del portal web), permisos por módulo y temporadas por empresa."""
import secrets
from datetime import date

import bcrypt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import Config
from main import app
from utils.auth import unidades_permitidas
from utils.db import Base, get_db
from utils.modelos import (
    App, Empresa, Permiso, Temporada, Unidad, Usuario, usuario_apps, usuario_permisos, usuario_sucursales,
)
from utils.temporadas import en_temporada, listar_temporadas, temporada_para_fecha

CLAVE = secrets.token_urlsafe(16)


@pytest.fixture()
def sesion():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    db.add_all([Empresa(id=1, nombre="LA HORNILLA SPA"), Empresa(id=2, nombre="VIENTO SUR")])
    db.flush()
    db.add_all([Unidad(id=105, nombre="CAMPO CHOCALAN", empresa_id=1, tipo_id=1),
                Unidad(id=201, nombre="ITAHUE", empresa_id=2, tipo_id=1),
                App(id=Config.APP_ID, nombre="CERTIFICACIONES"), App(id=10, nombre="LH INVENTARIO")])
    # LH mayo-abril; VS con otras fechas, para probar que cada sucursal usa las de su empresa
    db.add_all([Temporada(id=1, temporada="25-26", empresa_id=1, inicio=date(2025, 5, 1), fin=date(2026, 4, 30)),
                Temporada(id=2, temporada="26-27", empresa_id=1, inicio=date(2026, 5, 1), fin=date(2027, 4, 30)),
                Temporada(id=3, temporada="25-26", empresa_id=2, inicio=date(2025, 6, 1), fin=date(2026, 5, 31)),
                Temporada(id=4, temporada="26-27", empresa_id=2, inicio=date(2026, 6, 1), fin=date(2027, 5, 31)),
                Temporada(id=5, temporada="23-24", empresa_id=1)])
    db.add_all([Permiso(id="p-admin", nombre="CERTIFICACIONES_ADMIN", app_id=Config.APP_ID, id_estado=1),
                Permiso(id="p-nc", nombre="NC_EDITAR", app_id=Config.APP_ID, id_estado=1),
                Permiso(id="p-otra", nombre="CERTIFICACIONES_ADMIN", app_id=10, id_estado=1)])
    hash_clave = bcrypt.hashpw(CLAVE.encode(), bcrypt.gensalt(rounds=4)).decode()
    for uid, usuario, estado in (("u-admin", "ladmin", 1), ("u-jefe", "jcampo", 1), ("u-sin-app", "otro", 1),
                                 ("u-inactivo", "inactivo", 2)):
        db.add(Usuario(id=uid, usuario=usuario, correo=f"{usuario}@ejemplo.cl", clave=hash_clave, nombre=usuario,
                       id_estado=estado))
    db.flush()
    db.execute(insert(usuario_apps), [{"id": f"a{i}", "id_usuario": u, "id_app": Config.APP_ID}
                                      for i, u in enumerate(("u-admin", "u-jefe", "u-inactivo"))]
               + [{"id": "a9", "id_usuario": "u-sin-app", "id_app": 10}])
    db.execute(insert(usuario_permisos), [{"id": "x1", "id_usuario": "u-admin", "id_permiso": "p-admin"},
                                          {"id": "x2", "id_usuario": "u-jefe", "id_permiso": "p-nc"},
                                          {"id": "x3", "id_usuario": "u-jefe", "id_permiso": "p-otra"}])
    db.execute(insert(usuario_sucursales), [{"id_sucursal": 201, "id_usuario": "u-jefe"}])
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def cliente(sesion, monkeypatch):
    monkeypatch.setattr(Config, "AUTH_MODO", "jwt")
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", secrets.token_hex(32))
    app.dependency_overrides[get_db] = lambda: sesion
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_por_usuario_o_correo_y_refresco(cliente):
    for ident in ("ladmin", "LAdmin@Ejemplo.cl"):
        r = cliente.post("/api/auth/login", json={"usuario": ident, "clave": CLAVE})
        assert r.status_code == 200, r.text
    tokens = r.json()
    yo = cliente.get("/api/yo", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()
    assert yo["id"] == "u-admin" and yo["rol"] == "certificaciones"
    # El refresh no sirve como access, y viceversa
    assert cliente.get("/api/yo", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}).status_code == 401
    assert cliente.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401
    assert cliente.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200


@pytest.mark.parametrize("ident,clave,codigo", [
    ("ladmin", "incorrecta", 401), ("noexiste", CLAVE, 401), ("otro", CLAVE, 403), ("inactivo", CLAVE, 403),
])
def test_login_rechazado(cliente, ident, clave, codigo):
    assert cliente.post("/api/auth/login", json={"usuario": ident, "clave": clave}).status_code == codigo


def test_login_bloquea_tras_intentos_fallidos(cliente, monkeypatch):
    from routers import auth as rauth
    monkeypatch.setattr(rauth, "_fallos", type(rauth._fallos)(rauth._fallos.default_factory))
    for _ in range(rauth.MAX_FALLOS):
        cliente.post("/api/auth/login", json={"usuario": "ladmin", "clave": "mala"})
    assert cliente.post("/api/auth/login", json={"usuario": "ladmin", "clave": CLAVE}).status_code == 429


def test_permisos_solo_de_esta_app_y_sucursales(sesion):
    jefe = sesion.get(Usuario, "u-jefe")
    # El ADMIN de otra app no cuenta: es encargado por NC_EDITAR y ve solo su sucursal
    assert jefe.codigos_permiso == {"NC_EDITAR"} and jefe.rol == "encargado"
    assert unidades_permitidas(jefe) == {201}
    assert unidades_permitidas(sesion.get(Usuario, "u-admin")) is None


def test_temporadas_por_empresa(sesion):
    temporadas = listar_temporadas(sesion)
    assert [(t.id, t.nombre) for t in temporadas] == [(2026, "26-27"), (2025, "25-26")]  # 23-24 sin fechas: fuera
    # 15 de mayo de 2026: LH ya está en 26-27; VS (Itahue) sigue en 25-26
    assert temporada_para_fecha(sesion, date(2026, 5, 15), 1).nombre == "26-27"
    assert temporada_para_fecha(sesion, date(2026, 5, 15), 2).nombre == "25-26"
    from sqlalchemy import literal, select
    t2526 = temporadas[1]
    condicion = en_temporada(t2526, literal(date(2026, 5, 15)), literal(201))
    assert sesion.scalar(select(condicion)) == 1
    condicion = en_temporada(t2526, literal(date(2026, 5, 15)), literal(105))
    assert sesion.scalar(select(condicion)) == 0
