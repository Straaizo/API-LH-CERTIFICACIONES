"""Clave de acceso de la demo publicada."""
import pytest
from fastapi import HTTPException

from config import Config
from utils.auth import verificar_clave_demo


def test_sin_clave_configurada_no_se_exige(monkeypatch):
    monkeypatch.setattr(Config, "DEMO_CLAVE", "")
    verificar_clave_demo(None)


def test_con_clave_configurada(monkeypatch):
    monkeypatch.setattr(Config, "AUTH_MODO", "demo")
    monkeypatch.setattr(Config, "DEMO_CLAVE", "clave-de-prueba")
    for enviada, mensaje in ((None, "Ingresa la clave"), ("otra", "incorrecta")):
        with pytest.raises(HTTPException) as e:
            verificar_clave_demo(enviada)
        assert e.value.status_code == 401 and mensaje in e.value.detail
    verificar_clave_demo("clave-de-prueba")
