"""Protección contra abuso: IP real, límite de peticiones, bloqueo escalonado, listas de IPs, login y tamaño máximo."""
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from utils import proteccion as p


@pytest.fixture(autouse=True)
def limpiar(monkeypatch):
    for d in (p._estado, p._fallos_ip, p._fallos_cuenta, p._pausa, p._subidas):
        d.clear()
    monkeypatch.setattr(p, "IPS_PERMITIDAS", set())
    monkeypatch.setattr(p, "IPS_BLOQUEADAS", set())
    yield
    for d in (p._estado, p._fallos_ip, p._fallos_cuenta, p._pausa, p._subidas):
        d.clear()


def _pedido(xff: str | None) -> Request:
    cabeceras = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": cabeceras, "client": ("10.0.0.9", 1234), "method": "GET", "path": "/"})


def test_ip_real_no_se_puede_falsificar(monkeypatch):
    # El cliente inventa "1.1.1.1"; Google agrega la IP verdadera al final
    assert p.ip_cliente(_pedido("1.1.1.1, 200.1.2.3")) == "200.1.2.3"
    monkeypatch.setattr(p, "PROXIES_CONFIABLES", 1)  # con un balanceador propio delante
    assert p.ip_cliente(_pedido("1.1.1.1, 200.1.2.3, 34.1.1.1")) == "200.1.2.3"
    assert p.ip_cliente(_pedido(None)) == "10.0.0.9"


def test_limite_y_bloqueo_escalonado(monkeypatch):
    monkeypatch.setattr(p, "LIMITE_GENERAL", 3)
    t = 1000.0
    assert all(p.evaluar("9.9.9.9", "/api/x", ahora=t) is None for _ in range(3))
    # Supera el límite: primero solo se le pide esperar
    r = p.evaluar("9.9.9.9", "/api/x", ahora=t)
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"
    p.evaluar("9.9.9.9", "/api/x", ahora=t)
    # Al tercer exceso queda bloqueada 15 min, aunque pase el minuto
    r = p.evaluar("9.9.9.9", "/api/x", ahora=t)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) == p.BLOQUEO_CORTO
    assert p.evaluar("9.9.9.9", "/api/x", ahora=t + 120).status_code == 429
    # Otra IP no se ve afectada
    assert p.evaluar("8.8.8.8", "/api/x", ahora=t) is None
    # Si reincide dentro de 24 h, el bloqueo es de 24 h
    t2 = t + p.BLOQUEO_CORTO + 1
    for _ in range(3):
        p.evaluar("9.9.9.9", "/api/x", ahora=t2)
    for _ in range(3):
        r = p.evaluar("9.9.9.9", "/api/x", ahora=t2)
    assert int(r.headers["Retry-After"]) == p.BLOQUEO_LARGO


def test_limite_mas_estricto_para_lo_pesado(monkeypatch):
    monkeypatch.setattr(p, "LIMITE_PESADO", 2)
    assert p.evaluar("7.7.7.7", "/api/auditorias/1/resumen.pdf", ahora=1.0) is None
    assert p.evaluar("7.7.7.7", "/api/x", pesada=True, ahora=1.0) is None
    assert p.evaluar("7.7.7.7", "/api/x/informe.docx", ahora=1.0).status_code == 429
    assert p.evaluar("7.7.7.7", "/api/catalogos", ahora=1.0) is None  # lo liviano sigue


def test_listas_de_ips(monkeypatch):
    monkeypatch.setattr(p, "IPS_BLOQUEADAS", {"6.6.6.6"})
    monkeypatch.setattr(p, "IPS_PERMITIDAS", {"5.5.5.5"})
    monkeypatch.setattr(p, "LIMITE_GENERAL", 1)
    assert p.evaluar("6.6.6.6", "/api/x").status_code == 403
    assert all(p.evaluar("5.5.5.5", "/api/x") is None for _ in range(10))


def test_login_pausa_por_ip_y_por_cuenta():
    for _ in range(p.MAX_FALLOS_IP):
        p.registrar_fallo_login("4.4.4.4", "otra", ahora=10.0)
    assert p.login_bloqueado("4.4.4.4", "cualquiera", ahora=11.0) > 0
    # Muchas IPs contra la misma cuenta: la cuenta queda en pausa
    for i in range(p.MAX_FALLOS_CUENTA):
        p.registrar_fallo_login(f"3.3.3.{i}", "usuaria@ejemplo.cl", ahora=10.0)
    assert p.login_bloqueado("2.2.2.2", "usuaria@ejemplo.cl", ahora=11.0) > 0
    assert p.login_bloqueado("2.2.2.2", "otra.cuenta", ahora=11.0) == 0


def test_middleware_rechaza_peticion_grande_con_cors(monkeypatch):
    from main import app
    monkeypatch.setattr(p, "MAX_MB_PETICION", 0)
    r = TestClient(app).post("/api/auth/login", json={"usuario": "a", "clave": "b"},
                             headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 413
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_ipv6_se_agrupa_por_red_64():
    # Rotar la dirección dentro de la misma /64 no esquiva el límite
    assert p.ip_cliente(_pedido("2800:150:1:2::1")) == p.ip_cliente(_pedido("2800:150:1:2:ffff::9")) == "2800:150:1:2::/64"
    assert p.ip_cliente(_pedido("::ffff:200.1.2.3")) == "200.1.2.3"


def test_limite_tambien_por_usuario(monkeypatch):
    monkeypatch.setattr(p, "LIMITE_GENERAL", 2)
    t = 1000.0
    # La misma cuenta desde dos IPs distintas comparte su contador de usuario
    assert p.evaluar("usuario:u1", "/api/x", ahora=t) is None
    assert p.evaluar("usuario:u1", "/api/x", ahora=t) is None
    assert p.evaluar("usuario:u1", "/api/x", ahora=t).status_code == 429


def test_cupo_diario_de_subidas(monkeypatch):
    monkeypatch.setattr(p, "CUPO_SUBIDAS_DIA", 2)
    t = 5000.0
    assert p.consumir_cupo_subida("u1", ahora=t) and p.consumir_cupo_subida("u1", ahora=t)
    assert not p.consumir_cupo_subida("u1", ahora=t + 60)
    assert p.consumir_cupo_subida("u2", ahora=t)
    assert p.consumir_cupo_subida("u1", ahora=t + 24 * 3600 + 1)


def test_rechaza_cuerpo_sin_largo_declarado():
    from main import app
    r = TestClient(app).post("/api/auth/login", content=iter([b'{"usuario": "a", "clave": "b"}']),
                             headers={"content-type": "application/json"})
    assert r.status_code == 411


def test_purga_de_contadores_viejos():
    p.evaluar("7.7.7.7", "/api/x", ahora=100.0)
    p._ultima_purga = 0.0
    p.evaluar("6.6.6.6", "/api/x", ahora=100.0 + p.PURGA_CADA + 120)
    assert "7.7.7.7" not in p._estado and "6.6.6.6" in p._estado
