"""Protección contra abuso: límite de peticiones por IP, bloqueo escalonado, listas de IPs y tamaño máximo.

Objetivo: que nadie pueda martillar la API (costos de Cloud Run y Cloud SQL) ni probar claves a la fuerza.

- IP real: en Cloud Run la conexión llega desde el balanceador de Google; la IP del cliente es la que Google agrega
  al final de X-Forwarded-For. Los valores anteriores los puede inventar el cliente, así que no se usan.
  PROXIES_CONFIABLES = cuántas IPs agregadas por infraestructura propia hay después de la del cliente
  (0 con la URL de Cloud Run; 1 si se pone un balanceador de carga delante).
- Límite general por IP (ventana deslizante de 60 s) y uno más estricto para lo caro (subidas, PDF, ZIP, lecturas).
  IPv6 se agrupa por /64: un mismo equipo puede cambiar de dirección dentro de su red sin pedir permiso a nadie.
- El mismo límite corre también por usuario (token válido): una cuenta robada no lo esquiva cambiando de IP.
- Cupo diario de subidas por usuario (CUPO_SUBIDAS_DIA): nadie llena el bucket a punta de URLs firmadas.
- Quien supera el límite varias veces queda bloqueado 15 min; si reincide en 24 h, 24 h.
- IPS_PERMITIDAS (nunca se limitan, p. ej. la oficina) e IPS_BLOQUEADAS (siempre 403), separadas por coma.
- Peticiones con cuerpo más grande que MAX_MB_PETICION se rechazan antes de leerlas (413); sin largo declarado
  (cuerpo "chunked") no se aceptan (411), porque así no se podría medir antes de leerlo.

Los contadores viven en memoria de cada instancia: frenan el abuso desde una IP; el tope de instancias de
Cloud Run (--max-instances) y una alerta de presupuesto en GCP completan la protección de costos.
"""
import ipaddress
import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse

from config import Config

logger = logging.getLogger("seguridad")


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


def _lista(nombre: str) -> set[str]:
    return {v.strip() for v in os.getenv(nombre, "").split(",") if v.strip()}


PROXIES_CONFIABLES = _entero("PROXIES_CONFIABLES", 0)
LIMITE_GENERAL = _entero("LIMITE_PETICIONES_MINUTO", 240)   # por IP; la app abre varias consultas por pantalla
LIMITE_PESADO = _entero("LIMITE_PESADAS_MINUTO", 30)         # subidas, PDF, Word, ZIP y lectura de informes
MAX_MB_PETICION = _entero("MAX_MB_PETICION", 32)            # Cloud Run tampoco acepta más de 32 MB
CUPO_SUBIDAS_DIA = _entero("CUPO_SUBIDAS_DIA", 300)          # URLs de subida por usuario en 24 h
EXCESOS_PARA_BLOQUEO = 3                                    # veces que supera el límite antes de bloquear
BLOQUEO_CORTO = 15 * 60
BLOQUEO_LARGO = 24 * 3600
IPS_PERMITIDAS = _lista("IPS_PERMITIDAS")
IPS_BLOQUEADAS = _lista("IPS_BLOQUEADAS")

# Rutas caras: leen informes, generan documentos o comprimen evidencias (además, toda subida de archivo)
PESADAS = ("/leer", "/analizar", ".pdf", ".docx", "/excel", "/carpeta", "/exportar", "/url-subida")
PURGA_CADA = 300                                            # segundos entre limpiezas de contadores viejos


def ip_cliente(request: Request) -> str:
    """IP del cliente: la que agregó la infraestructura de Google a X-Forwarded-For (no la que pueda enviar el cliente)."""
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        saltos = [p.strip() for p in reenviada.split(",") if p.strip()]
        if saltos:
            return _agrupar(saltos[max(0, len(saltos) - 1 - PROXIES_CONFIABLES)])
    return _agrupar(request.client.host) if request.client else "desconocida"


def _agrupar(ip: str) -> str:
    """IPv6 se cuenta por su red /64 (cada hogar o celular recibe una /64 completa y puede rotar dentro)."""
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if direccion.version == 6:
        if direccion.ipv4_mapped:
            return str(direccion.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(direccion)


def usuario_de_peticion(request: Request) -> str | None:
    """Id del usuario si la petición trae un token válido (firma verificada). Sin token o inválido: None."""
    if Config.AUTH_MODO == "demo":
        demo = request.headers.get("x-usuario-demo", "").strip()
        return demo[:64] or None
    cabecera = request.headers.get("authorization", "")
    if not cabecera.lower().startswith("bearer "):
        return None
    try:
        datos = jwt.decode(cabecera.split(" ", 1)[1].strip(), Config.JWT_SECRET_KEY, algorithms=["HS256"],
                           options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None
    return str(datos["sub"])


@dataclass
class _EstadoIP:
    general: deque = field(default_factory=deque)
    pesadas: deque = field(default_factory=deque)
    excesos: deque = field(default_factory=deque)       # cuándo superó el límite
    bloqueos: deque = field(default_factory=deque)      # cuándo fue bloqueada (para escalar)
    bloqueada_hasta: float = 0.0


_estado: dict[str, _EstadoIP] = defaultdict(_EstadoIP)
_candado = threading.Lock()
_ultima_purga = 0.0


def _purgar(ahora: float) -> None:
    """Borra contadores sin actividad: con miles de IPs distintas la memoria de la instancia no crece sin fin."""
    global _ultima_purga
    if ahora - _ultima_purga < PURGA_CADA:
        return
    _ultima_purga = ahora
    for clave in [c for c, e in _estado.items() if e.bloqueada_hasta <= ahora and (not e.general or e.general[-1] < ahora - 60)
                  and (not e.bloqueos or e.bloqueos[-1] < ahora - BLOQUEO_LARGO)]:
        del _estado[clave]
    for colas in (_fallos_ip, _fallos_cuenta, _subidas):
        for clave in [c for c, cola in colas.items() if not cola or cola[-1] < ahora - BLOQUEO_LARGO]:
            del colas[clave]
    for clave in [c for c, hasta in _pausa.items() if hasta <= ahora]:
        del _pausa[clave]


def _recortar(cola: deque, desde: float) -> None:
    while cola and cola[0] < desde:
        cola.popleft()


def _respuesta(estado: int, mensaje: str, segundos: int | None = None) -> JSONResponse:
    respuesta = JSONResponse(status_code=estado, content={"detail": mensaje})
    if segundos:
        respuesta.headers["Retry-After"] = str(segundos)
    return respuesta


def evaluar(ip: str, ruta: str, pesada: bool = False, ahora: float | None = None) -> JSONResponse | None:
    """None si la petición puede seguir; si no, la respuesta 403/429 que corresponde."""
    if ip in IPS_PERMITIDAS:
        return None
    if ip in IPS_BLOQUEADAS:
        return _respuesta(403, "Acceso no permitido")
    ahora = ahora or time.monotonic()
    pesada = pesada or any(p in ruta for p in PESADAS)
    with _candado:
        _purgar(ahora)
        e = _estado[ip]
        if e.bloqueada_hasta > ahora:
            return _respuesta(429, "Demasiadas peticiones. Intenta más tarde.", int(e.bloqueada_hasta - ahora) + 1)
        _recortar(e.general, ahora - 60)
        _recortar(e.pesadas, ahora - 60)
        excede = len(e.general) >= LIMITE_GENERAL or (pesada and len(e.pesadas) >= LIMITE_PESADO)
        if not excede:
            e.general.append(ahora)
            if pesada:
                e.pesadas.append(ahora)
            return None
        _recortar(e.excesos, ahora - 600)
        e.excesos.append(ahora)
        if len(e.excesos) < EXCESOS_PARA_BLOQUEO:
            logger.warning("[SEGURIDAD] Límite de peticiones superado ip=%s ruta=%s", ip, ruta)
            return _respuesta(429, "Demasiadas peticiones. Espera un momento.", 60)
        _recortar(e.bloqueos, ahora - BLOQUEO_LARGO)
        duracion = BLOQUEO_LARGO if e.bloqueos else BLOQUEO_CORTO
        e.bloqueos.append(ahora)
        e.bloqueada_hasta = ahora + duracion
        e.excesos.clear()
        logger.warning("[SEGURIDAD] IP bloqueada %s min ip=%s ruta=%s", duracion // 60, ip, ruta)
        return _respuesta(429, "Demasiadas peticiones. Intenta más tarde.", duracion)


async def middleware_proteccion(request: Request, call_next):
    """Middleware de FastAPI: tamaño máximo, listas de IPs y límite de peticiones (solo rutas /api/)."""
    if request.method == "OPTIONS" or not request.url.path.startswith("/api/"):
        return await call_next(request)
    largo = request.headers.get("content-length")
    if largo and largo.isdigit() and int(largo) > MAX_MB_PETICION * 1024 * 1024:
        return _respuesta(413, f"El archivo supera el máximo de {MAX_MB_PETICION} MB")
    if "chunked" in request.headers.get("transfer-encoding", "").lower():
        return _respuesta(411, "Falta el largo de la petición")
    subida = "multipart/form-data" in request.headers.get("content-type", "")
    ip = ip_cliente(request)
    bloqueo = evaluar(ip, request.url.path, subida)
    # Mismo límite por usuario (las IPs permitidas, como la oficina, tampoco se limitan por usuario)
    if bloqueo is None and ip not in IPS_PERMITIDAS and (usuario := usuario_de_peticion(request)):
        bloqueo = evaluar(f"usuario:{usuario}", request.url.path, subida)
    if bloqueo is not None:
        return bloqueo
    return await call_next(request)


# ---------- Cupo diario de subidas por usuario ----------

_subidas: dict[str, deque] = defaultdict(deque)


def consumir_cupo_subida(usuario_id: str, ahora: float | None = None) -> bool:
    """True si el usuario aún puede pedir una URL de subida hoy (ventana de 24 h); la descuenta del cupo."""
    ahora = ahora or time.monotonic()
    with _candado:
        cola = _subidas[usuario_id]
        _recortar(cola, ahora - 24 * 3600)
        if len(cola) >= CUPO_SUBIDAS_DIA:
            logger.warning("[SEGURIDAD] Cupo diario de subidas agotado usuario=%s", usuario_id)
            return False
        cola.append(ahora)
        return True


# ---------- Inicio de sesión: intentos fallidos por IP y por cuenta ----------

MAX_FALLOS_IP = 5            # desde una IP en 15 min → esa IP no puede intentar por 30 min
MAX_FALLOS_CUENTA = 10       # contra una cuenta desde cualquier IP en 15 min → la cuenta queda en pausa 15 min
VENTANA_FALLOS = 15 * 60
PAUSA_IP = 30 * 60
PAUSA_CUENTA = 15 * 60

_fallos_ip: dict[str, deque] = defaultdict(deque)
_fallos_cuenta: dict[str, deque] = defaultdict(deque)
_pausa: dict[str, float] = {}


def login_bloqueado(ip: str, cuenta: str, ahora: float | None = None) -> int:
    """Segundos que faltan si la IP o la cuenta están en pausa; 0 si puede intentar."""
    if ip in IPS_PERMITIDAS:
        return 0
    ahora = ahora or time.monotonic()
    with _candado:
        restante = max(_pausa.get(f"ip:{ip}", 0), _pausa.get(f"cuenta:{cuenta}", 0)) - ahora
    return int(restante) + 1 if restante > 0 else 0


def registrar_fallo_login(ip: str, cuenta: str, ahora: float | None = None) -> None:
    ahora = ahora or time.monotonic()
    with _candado:
        for clave, cola, maximo, pausa in ((f"ip:{ip}", _fallos_ip[ip], MAX_FALLOS_IP, PAUSA_IP),
                                           (f"cuenta:{cuenta}", _fallos_cuenta[cuenta], MAX_FALLOS_CUENTA, PAUSA_CUENTA)):
            _recortar(cola, ahora - VENTANA_FALLOS)
            cola.append(ahora)
            if len(cola) >= maximo:
                _pausa[clave] = ahora + pausa
                cola.clear()
                logger.warning("[SEGURIDAD] Inicio de sesión en pausa %s (%s min)", clave, pausa // 60)


def registrar_exito_login(ip: str, cuenta: str) -> None:
    with _candado:
        _fallos_ip.pop(ip, None)
        _fallos_cuenta.pop(cuenta, None)
