"""Registros: documentos no fijos que certificaciones define como plantilla y los encargados llenan en la app."""
import re
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from utils import almacenamiento
from utils.auth import es_certificaciones, puede_escribir, solo_certificaciones, usuario_actual, verificar_unidad
from utils.bitacora import registrar
from utils.comunes import filtrar_unidades, obtener, temporada_para_fecha, unidad_dict
from utils.db import get_db
from utils.exportar_registro import a_pdf, a_word
from utils.importar_plantilla_word import leer_plantilla_word
from utils.rellenar_word import rellenar_word
from utils.modelos import Bitacora, PlantillaRegistro, Registro, Unidad, Usuario
from utils.texto import nombre_archivo_seguro
from utils.hora import ahora

router = APIRouter(prefix="/registros")

TIPOS_SIMPLES = ("texto", "numero", "fecha", "si_no")
TIPOS_ARCHIVO = ("foto", "archivo", "firma")
TIPOS = (*TIPOS_SIMPLES, "tabla", "checklist", *TIPOS_ARCHIVO)
OPCIONES_CHECKLIST = ("si", "no", "na")
MAX_WORD = 10 * 1024 * 1024
ESTADOS_EDITABLES = ("borrador", "rechazado")
# Un registro en llenado sin revisión del campo por este número de días o más queda "atrasado"
DIAS_ATRASO = 15
# Certificaciones supervisa y puede corregir también mientras está en revisión
ESTADOS_EDITABLES_CERT = ("borrador", "rechazado", "en_revision")


# ---------- Esquemas ----------

class Columna(BaseModel):
    id: str | None = None
    etiqueta: str = Field(min_length=1, max_length=120)
    tipo: str = "texto"


class ItemChecklist(BaseModel):
    id: str | None = None
    texto: str = Field(min_length=1, max_length=500)
    seccion: str = ""


class CampoPlantilla(BaseModel):
    id: str | None = None
    etiqueta: str = Field(min_length=1, max_length=200)
    tipo: str
    obligatorio: bool = True
    columnas: list[Columna] = []
    filas_sugeridas: int | None = None
    items: list[ItemChecklist] = []
    opciones: list[str] = ["si", "no"]
    con_observacion: bool = True
    # Celda del Word original donde va el valor (lo define el importador)
    origen: dict | None = None


class PlantillaEntrada(BaseModel):
    codigo: str | None = Field(default=None, max_length=40)
    version: str = Field(default="01", max_length=10)
    nombre: str = Field(min_length=2, max_length=200)
    descripcion: str | None = None
    ambito: str = "campo"
    # encargado, frecuencia, orientacion (vertical|horizontal), creado_por, aprobado_por, fecha_revision,
    # direccion, notas (lista)
    formato: dict = {}
    campos: list[CampoPlantilla] = Field(min_length=1)
    activa: bool = True


class RegistroEntrada(BaseModel):
    plantilla_id: int
    unidad_id: int
    titulo: str = Field(min_length=2, max_length=250)
    responsable_id: int | None = None


class Revision(BaseModel):
    aprobar: bool
    observacion: str | None = None


# ---------- Reglas ----------

def _id_desde(etiqueta: str, usados: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", etiqueta.lower()).strip("_")[:30] or "campo"
    candidato, n = base, 2
    while candidato in usados:
        candidato, n = f"{base}_{n}", n + 1
    usados.add(candidato)
    return candidato


def _normalizar_campos(campos: list[CampoPlantilla]) -> list[dict]:
    usados: set[str] = set()
    salida = []
    for c in campos:
        if c.tipo not in TIPOS:
            raise HTTPException(400, f"Tipo de campo inválido: {c.tipo}")
        campo = {"id": c.id if c.id and c.id not in usados else _id_desde(c.etiqueta, usados),
                 "etiqueta": c.etiqueta.strip(), "tipo": c.tipo, "obligatorio": c.obligatorio}
        usados.add(campo["id"])
        if c.origen:
            campo["origen"] = c.origen
        if c.tipo == "tabla":
            if not c.columnas:
                raise HTTPException(400, f"La tabla '{c.etiqueta}' necesita al menos una columna")
            usados_col: set[str] = set()
            columnas = []
            for col in c.columnas:
                if col.tipo not in TIPOS_SIMPLES:
                    raise HTTPException(400, f"Tipo de columna inválido: {col.tipo}")
                cid = col.id if col.id and col.id not in usados_col else _id_desde(col.etiqueta, usados_col)
                usados_col.add(cid)
                columnas.append({"id": cid, "etiqueta": col.etiqueta.strip(), "tipo": col.tipo})
            campo["columnas"] = columnas
            if c.filas_sugeridas:
                campo["filas_sugeridas"] = max(1, min(c.filas_sugeridas, 60))
        if c.tipo == "checklist":
            if not c.items:
                raise HTTPException(400, f"El checklist '{c.etiqueta}' necesita al menos un ítem")
            opciones = [o for o in OPCIONES_CHECKLIST if o in c.opciones] or ["si", "no"]
            usados_item: set[str] = set()
            items = []
            for n, it in enumerate(c.items, start=1):
                iid = it.id if it.id and it.id not in usados_item else f"i{n}"
                while iid in usados_item:
                    iid += "_"
                usados_item.add(iid)
                items.append({"id": iid, "texto": it.texto.strip(), "seccion": it.seccion.strip()})
            campo.update({"items": items, "opciones": opciones, "con_observacion": c.con_observacion})
        salida.append(campo)
    return salida


def _completo(campo: dict, valor) -> bool:
    if campo["tipo"] == "tabla":
        return isinstance(valor, list) and any(any(v not in (None, "") for v in f.values()) for f in valor)
    if campo["tipo"] in TIPOS_ARCHIVO:
        return isinstance(valor, dict) and bool(valor.get("clave"))
    if campo["tipo"] == "si_no":
        return isinstance(valor, bool)
    if campo["tipo"] == "checklist":
        respuestas = valor if isinstance(valor, dict) else {}
        return all((respuestas.get(it["id"]) or {}).get("r") for it in campo.get("items", []))
    return valor not in (None, "")


def avance(registro: Registro) -> dict:
    exigidos = [c for c in registro.campos if c.get("obligatorio")] or registro.campos
    listos = sum(1 for c in exigidos if _completo(c, registro.valores.get(c["id"])))
    return {"completos": listos, "total": len(exigidos),
            "porcentaje": round(listos / len(exigidos) * 100) if exigidos else 100}


def _plantilla_dict(p: PlantillaRegistro) -> dict:
    return {"id": p.id, "codigo": p.codigo, "version": p.version, "nombre": p.nombre, "descripcion": p.descripcion,
            "ambito": p.ambito, "formato": p.formato or {}, "campos": p.campos, "activa": p.activa,
            "tiene_word_original": bool(p.word_clave),
            "creada_en": p.creada_en}


def _codigo_libre(db: Session, codigo: str | None, plantilla_id: int | None = None) -> str | None:
    codigo = codigo.strip().upper() if codigo and codigo.strip() else None
    if codigo:
        otra = db.scalar(select(PlantillaRegistro).where(PlantillaRegistro.codigo == codigo))
        if otra and otra.id != plantilla_id:
            raise HTTPException(400, f"Ya existe una plantilla con el código {codigo}")
    return codigo


def guardar_logo(db_codigo: str | None, contenido: bytes, extension: str) -> str:
    clave = almacenamiento.nueva_clave("plantillas", f"logo_{db_codigo or 'plantilla'}.{extension}")
    almacenamiento.escribir(clave, contenido, f"image/{extension.replace('jpg', 'jpeg')}")
    return clave


def _atraso(r: Registro) -> dict:
    """Días desde la última revisión del campo (o desde que se creó) y si está atrasado."""
    desde = r.revision_campo_en or r.creado_en
    dias = (ahora() - desde).days if desde else 0
    return {"dias_sin_revision": dias, "atrasado": r.estado in ESTADOS_EDITABLES and dias >= DIAS_ATRASO}


def _registro_dict(r: Registro, detalle: bool = False) -> dict:
    datos = {
        "id": r.id, "titulo": r.titulo, "estado": r.estado, "observacion": r.observacion,
        "codigo": r.codigo, "version": r.version,
        "plantilla": {"id": r.plantilla.id, "nombre": r.plantilla.nombre},
        "unidad": unidad_dict(r.unidad), "temporada_id": r.temporada_id,
        "responsable": {"id": r.responsable.id, "nombre": r.responsable.nombre} if r.responsable else None,
        "fecha_revision": r.revision_campo_en, **_atraso(r), "creado_en": r.creado_en, "actualizado_en": r.actualizado_en,
        "enviado_en": r.enviado_en, "aprobado_en": r.aprobado_en,
        "aprobado_por": r.aprobado_por.nombre if r.aprobado_por else None,
        "actualizado_por": r.actualizado_por.nombre if r.actualizado_por else None,
        "tiene_word_original": bool(r.word_clave),
        "avance": avance(r),
    }
    if detalle:
        datos["campos"] = r.campos
        datos["valores"] = r.valores
        datos["formato"] = {k: v for k, v in (r.formato or {}).items() if k != "logo_clave"}
        datos["tiene_logo"] = bool((r.formato or {}).get("logo_clave"))
    return datos


def valores_iniciales(campos: list[dict], responsable: Usuario | None) -> dict:
    """El campo "Responsable" del formulario parte con el nombre de la persona asignada."""
    if not responsable:
        return {}
    return {c["id"]: responsable.nombre for c in campos
            if c["tipo"] == "texto" and c["etiqueta"].strip().lower().rstrip(":.") == "responsable"}


def _puede_llenar(usuario: Usuario, registro: Registro) -> None:
    if es_certificaciones(usuario):
        return
    verificar_unidad(usuario, registro.unidad_id)


def _sin_meta(fila: dict) -> dict:
    return {k: v for k, v in fila.items() if not k.startswith("_")}


def _resumen_cambios(campos: list[dict], antes: dict, despues: dict, autor: str, ahora: str) -> list[str]:
    """Describe qué cambió y marca cada fila de tabla nueva o modificada con su autor (_por, _en)."""
    cambios = []
    for c in campos:
        a, d = antes.get(c["id"]), despues.get(c["id"])
        if c["tipo"] == "tabla":
            filas_a = a if isinstance(a, list) else []
            filas_d = d if isinstance(d, list) else []
            nuevas = modificadas = 0
            for k, fila in enumerate(filas_d):
                previa = filas_a[k] if k < len(filas_a) else None
                if previa is None:
                    nuevas += 1
                    fila["_por"], fila["_en"] = autor, ahora
                elif _sin_meta(previa) != _sin_meta(fila):
                    modificadas += 1
                    fila["_por"], fila["_en"] = autor, ahora
                else:
                    fila["_por"], fila["_en"] = previa.get("_por"), previa.get("_en")
            eliminadas = max(0, len(filas_a) - len(filas_d))
            partes = [f"{n} {t}" for n, t in ((nuevas, "fila(s) nueva(s)"), (modificadas, "fila(s) modificada(s)"),
                                               (eliminadas, "fila(s) eliminada(s)")) if n]
            if partes:
                cambios.append(f"{c['etiqueta']}: {', '.join(partes)}")
        elif c["tipo"] == "checklist":
            a, d = a or {}, d or {}
            distintos = [k for k in set(a) | set(d) if a.get(k) != d.get(k)]
            if distintos:
                cambios.append(f"{c['etiqueta']}: {len(distintos)} ítem(s) respondido(s) o modificado(s)")
        elif (a or None) != (d or None):
            cambios.append(c["etiqueta"])
    return cambios


# ---------- Plantillas (solo certificaciones) ----------

@router.get("/plantillas")
def listar_plantillas(solo_activas: bool = False, _: Usuario = Depends(usuario_actual),
                      db: Session = Depends(get_db)) -> list[dict]:
    consulta = select(PlantillaRegistro).order_by(PlantillaRegistro.codigo, PlantillaRegistro.nombre)
    if solo_activas:
        consulta = consulta.where(PlantillaRegistro.activa)
    return [_plantilla_dict(p) for p in db.scalars(consulta)]


@router.post("/plantillas", status_code=201)
def crear_plantilla(datos: PlantillaEntrada, usuario: Usuario = Depends(solo_certificaciones),
                    db: Session = Depends(get_db)) -> dict:
    plantilla = PlantillaRegistro(codigo=_codigo_libre(db, datos.codigo), version=datos.version.strip() or "01",
                                  nombre=datos.nombre.strip(), descripcion=datos.descripcion, ambito=datos.ambito,
                                  formato={k: v for k, v in datos.formato.items() if k != "logo_clave"},
                                  campos=_normalizar_campos(datos.campos), activa=datos.activa,
                                  creada_por_id=usuario.id)
    db.add(plantilla)
    db.flush()
    registrar(db, usuario, "crear", "plantilla_registro", plantilla.id, {"nombre": plantilla.nombre})
    db.commit()
    return _plantilla_dict(plantilla)


@router.put("/plantillas/{plantilla_id}")
def modificar_plantilla(plantilla_id: int, datos: PlantillaEntrada, usuario: Usuario = Depends(solo_certificaciones),
                        db: Session = Depends(get_db)) -> dict:
    """Los registros ya generados conservan su copia de los campos."""
    plantilla = obtener(db, PlantillaRegistro, plantilla_id)
    plantilla.codigo = _codigo_libre(db, datos.codigo, plantilla.id)
    plantilla.version = datos.version.strip() or plantilla.version
    plantilla.nombre, plantilla.descripcion = datos.nombre.strip(), datos.descripcion
    plantilla.ambito, plantilla.activa = datos.ambito, datos.activa
    logo = (plantilla.formato or {}).get("logo_clave")
    plantilla.formato = {k: v for k, v in datos.formato.items() if k != "logo_clave"} | ({"logo_clave": logo} if logo else {})
    anteriores = {c["id"]: c for c in plantilla.campos or []}
    campos = _normalizar_campos(datos.campos)
    for campo in campos:
        # El constructor no envía la ubicación en el Word: se conserva la del campo con el mismo id
        if "origen" not in campo and anteriores.get(campo["id"], {}).get("origen"):
            campo["origen"] = anteriores[campo["id"]]["origen"]
    plantilla.campos = campos
    registrar(db, usuario, "modificar", "plantilla_registro", plantilla.id, {"nombre": plantilla.nombre})
    db.commit()
    return _plantilla_dict(plantilla)


@router.post("/plantillas/importar-word")
async def importar_word(archivo: UploadFile = File(...), confirmar: bool = Form(False), ambito: str = Form("campo"),
                        reemplazar: bool = Form(False), usuario: Usuario = Depends(solo_certificaciones),
                        db: Session = Depends(get_db)) -> dict:
    """Lee un formulario Word y propone la plantilla. Sin confirmar, solo devuelve la vista previa."""
    if not (archivo.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "Se espera un archivo Word .docx")
    contenido = await archivo.read()
    if len(contenido) > MAX_WORD:
        raise HTTPException(413, "Archivo demasiado grande")
    try:
        resultado = crear_plantilla_desde_word(db, contenido, archivo.filename, usuario, ambito, confirmar, reemplazar)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if confirmar:
        db.commit()
    return resultado


def crear_plantilla_desde_word(db: Session, contenido: bytes, nombre_archivo: str, usuario: Usuario | None,
                               ambito: str = "campo", confirmar: bool = True, reemplazar: bool = False) -> dict:
    """Usado por el endpoint y por la carga inicial de la demo."""
    try:
        detectada = leer_plantilla_word(contenido, nombre_archivo)
    except Exception as exc:
        raise ValueError(f"No se pudo leer el Word: {exc}") from exc
    existente = db.scalar(select(PlantillaRegistro).where(PlantillaRegistro.codigo == detectada.codigo)) \
        if detectada.codigo else None
    vista = {"codigo": detectada.codigo, "version": detectada.version, "nombre": detectada.nombre,
             "formato": detectada.formato, "campos": detectada.campos, "advertencias": detectada.advertencias,
             "tiene_logo": bool(detectada.logo), "ya_existe": existente is not None, "confirmado": False}
    if not confirmar:
        return vista
    if existente and not reemplazar:
        raise ValueError(f"Ya existe la plantilla {detectada.codigo}. Marca 'reemplazar' para actualizarla")
    formato = dict(detectada.formato)
    if detectada.logo:
        formato["logo_clave"] = guardar_logo(detectada.codigo, detectada.logo, detectada.logo_extension)
    word_clave = almacenamiento.nueva_clave("plantillas", f"{detectada.codigo or 'plantilla'}.docx")
    almacenamiento.escribir(word_clave, contenido,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    plantilla = existente or PlantillaRegistro(creada_por_id=usuario.id if usuario else None)
    plantilla.codigo, plantilla.version, plantilla.nombre = detectada.codigo or None, detectada.version, detectada.nombre
    plantilla.ambito, plantilla.formato, plantilla.campos, plantilla.activa = ambito, formato, detectada.campos, True
    plantilla.word_clave = word_clave
    plantilla.descripcion = plantilla.descripcion or f"Importada desde {nombre_archivo}"
    if existente is None:
        db.add(plantilla)
    db.flush()
    registrar(db, usuario, "importar", "plantilla_registro", plantilla.id,
              {"codigo": plantilla.codigo, "archivo": nombre_archivo})
    return vista | {"confirmado": True, "plantilla": _plantilla_dict(plantilla)}


@router.get("/plantillas/{plantilla_id}/logo")
def logo_plantilla(plantilla_id: int, _: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    clave = (obtener(db, PlantillaRegistro, plantilla_id).formato or {}).get("logo_clave")
    if not clave:
        raise HTTPException(404, "La plantilla no tiene logo")
    return {"url": almacenamiento.url_descarga(clave)}


# ---------- Registros ----------

@router.get("")
def listar(empresa_id: int | None = None, unidad_id: int | None = None, temporada_id: int | None = None,
           estado: str | None = None, plantilla_id: int | None = None, usuario: Usuario = Depends(usuario_actual),
           db: Session = Depends(get_db)) -> list[dict]:
    consulta = filtrar_unidades(select(Registro), Registro.unidad_id, usuario, empresa_id, unidad_id)
    if temporada_id:
        consulta = consulta.where(Registro.temporada_id == temporada_id)
    if estado:
        consulta = consulta.where(Registro.estado == estado)
    if plantilla_id:
        consulta = consulta.where(Registro.plantilla_id == plantilla_id)
    return [_registro_dict(r) for r in db.scalars(consulta.order_by(Registro.creado_en.desc(), Registro.id.desc()))]


@router.post("", status_code=201)
def crear(datos: RegistroEntrada, usuario: Usuario = Depends(solo_certificaciones),
          db: Session = Depends(get_db)) -> dict:
    plantilla = obtener(db, PlantillaRegistro, datos.plantilla_id)
    if not plantilla.activa:
        raise HTTPException(400, "La plantilla está desactivada")
    unidad = obtener(db, Unidad, datos.unidad_id)
    if plantilla.ambito != "ambos" and unidad.tipo != plantilla.ambito:
        raise HTTPException(400, f"La plantilla es de {plantilla.ambito} y la sucursal es {unidad.tipo}")
    responsable = obtener(db, Usuario, datos.responsable_id) if datos.responsable_id else None
    temporada = temporada_para_fecha(db, date.today())
    registro = Registro(plantilla_id=plantilla.id, unidad_id=unidad.id, temporada_id=temporada.id if temporada else None,
                        titulo=datos.titulo.strip(), codigo=plantilla.codigo, version=plantilla.version,
                        formato=plantilla.formato or {}, word_clave=plantilla.word_clave, campos=plantilla.campos,
                        valores=valores_iniciales(plantilla.campos, responsable),
                        responsable_id=datos.responsable_id,
                        creado_por_id=usuario.id)
    db.add(registro)
    db.flush()
    registrar(db, usuario, "crear", "registro", registro.id, {"titulo": registro.titulo, "plantilla": plantilla.nombre})
    db.commit()
    db.refresh(registro)
    return _registro_dict(registro, detalle=True)


def _evento_dict(b: Bitacora, registros: dict[int, Registro] | None = None) -> dict:
    datos = {"id": b.id, "fecha_hora": b.fecha_hora, "usuario": b.usuario.nombre if b.usuario else "Sistema",
             "accion": b.accion, "detalle": b.detalle or {}, "registro_id": b.entidad_id}
    if registros is not None and b.entidad_id in registros:
        r = registros[b.entidad_id]
        datos["registro"] = {"id": r.id, "titulo": r.titulo, "codigo": r.codigo, "unidad": r.unidad.nombre,
                             "estado": r.estado}
    return datos


@router.get("/actividad")
def actividad(limite: int = 30, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> list[dict]:
    """Últimos cambios en registros: quién guardó, envió o revisó y cuándo."""
    visibles = {r.id: r for r in db.scalars(filtrar_unidades(select(Registro), Registro.unidad_id, usuario))}
    eventos = db.scalars(select(Bitacora).where(Bitacora.entidad == "registro", Bitacora.entidad_id.in_(visibles))
                         .order_by(Bitacora.fecha_hora.desc(), Bitacora.id.desc()).limit(min(limite, 200)))
    return [_evento_dict(b, visibles) for b in eventos]


@router.get("/{registro_id}/historial")
def historial(registro_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> list[dict]:
    registro = obtener(db, Registro, registro_id)
    verificar_unidad(usuario, registro.unidad_id)
    eventos = db.scalars(select(Bitacora).where(Bitacora.entidad == "registro", Bitacora.entidad_id == registro.id)
                         .order_by(Bitacora.fecha_hora.desc(), Bitacora.id.desc()))
    return [_evento_dict(b) for b in eventos]


@router.get("/{registro_id}")
def detalle(registro_id: int, usuario: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)) -> dict:
    registro = obtener(db, Registro, registro_id)
    verificar_unidad(usuario, registro.unidad_id)
    return _registro_dict(registro, detalle=True)


@router.put("/{registro_id}/valores")
def guardar_valores(registro_id: int, valores: dict, usuario: Usuario = Depends(puede_escribir),
                    db: Session = Depends(get_db)) -> dict:
    """Guarda lo llenado (parcial o completo). Solo en borrador o rechazado."""
    registro = obtener(db, Registro, registro_id)
    _puede_llenar(usuario, registro)
    editables = ESTADOS_EDITABLES_CERT if es_certificaciones(usuario) else ESTADOS_EDITABLES
    if registro.estado not in editables:
        raise HTTPException(400, "El registro no se puede editar en este estado")
    campos = {c["id"]: c for c in registro.campos}
    limpios = {}
    for cid, valor in valores.items():
        campo = campos.get(cid)
        if campo is None:
            continue
        if campo["tipo"] in TIPOS_ARCHIVO and isinstance(valor, dict) and valor.get("clave"):
            if valor["clave"] != (registro.valores.get(cid) or {}).get("clave") and not almacenamiento.existe(valor["clave"]):
                raise HTTPException(400, f"El archivo de '{campo['etiqueta']}' no se subió correctamente")
        if campo["tipo"] == "checklist":
            validos = {it["id"] for it in campo.get("items", [])}
            opciones = set(campo.get("opciones", OPCIONES_CHECKLIST))
            valor = {k: {"r": v.get("r") if v.get("r") in opciones else None, "obs": (v.get("obs") or "").strip()}
                     for k, v in (valor or {}).items() if k in validos and isinstance(v, dict)}
        if campo["tipo"] == "numero" and valor not in (None, ""):
            try:
                valor = float(valor)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, f"'{campo['etiqueta']}' debe ser un número") from exc
        limpios[cid] = valor
    momento = ahora()
    cambios = _resumen_cambios(registro.campos, registro.valores or {}, limpios, usuario.nombre,
                               momento.isoformat(timespec="minutes"))
    registro.valores = limpios
    if cambios:
        registro.actualizado_en, registro.actualizado_por_id = momento, usuario.id
        if not es_certificaciones(usuario):
            registro.revision_campo_en = momento
        registrar(db, usuario, "guardar", "registro", registro.id,
                  {"cambios": cambios, "avance": avance(registro)["porcentaje"]})
    db.commit()
    return _registro_dict(registro, detalle=True)


@router.post("/{registro_id}/enviar")
def enviar(registro_id: int, usuario: Usuario = Depends(puede_escribir), db: Session = Depends(get_db)) -> dict:
    registro = obtener(db, Registro, registro_id)
    _puede_llenar(usuario, registro)
    if registro.estado not in ESTADOS_EDITABLES:
        raise HTTPException(400, "El registro ya fue enviado")
    faltan = [c["etiqueta"] for c in registro.campos
              if c.get("obligatorio") and not _completo(c, registro.valores.get(c["id"]))]
    if faltan:
        raise HTTPException(400, f"Faltan campos obligatorios: {', '.join(faltan)}")
    registro.estado, registro.enviado_en, registro.observacion = "en_revision", ahora(), None
    if not es_certificaciones(usuario):
        registro.revision_campo_en = registro.enviado_en
    registrar(db, usuario, "enviar", "registro", registro.id)
    db.commit()
    return _registro_dict(registro, detalle=True)


@router.post("/{registro_id}/revision")
def revisar(registro_id: int, datos: Revision, usuario: Usuario = Depends(solo_certificaciones),
            db: Session = Depends(get_db)) -> dict:
    registro = obtener(db, Registro, registro_id)
    if registro.estado != "en_revision":
        raise HTTPException(400, "Solo se revisan registros enviados")
    if not datos.aprobar and not (datos.observacion or "").strip():
        raise HTTPException(400, "El rechazo requiere una observación")
    if datos.aprobar:
        registro.estado, registro.aprobado_por_id, registro.aprobado_en = "aprobado", usuario.id, ahora()
    else:
        registro.estado = "rechazado"
    registro.observacion = datos.observacion
    registrar(db, usuario, "aprobar" if datos.aprobar else "rechazar", "registro", registro.id,
              {"observacion": datos.observacion})
    db.commit()
    return _registro_dict(registro, detalle=True)


@router.get("/{registro_id}/exportar")
def exportar(registro_id: int, formato: str = "pdf", usuario: Usuario = Depends(usuario_actual),
             db: Session = Depends(get_db)) -> Response:
    registro = obtener(db, Registro, registro_id)
    verificar_unidad(usuario, registro.unidad_id)
    if registro.estado != "aprobado" and not es_certificaciones(usuario):
        raise HTTPException(400, "Solo se descargan registros aprobados")
    nombre = nombre_archivo_seguro(f"{registro.titulo} - {registro.unidad.nombre}")
    try:
        if formato == "docx":
            original = almacenamiento.leer(registro.word_clave) if registro.word_clave else None
            contenido = rellenar_word(original, registro.campos, registro.valores or {}) if original \
                else a_word(registro)
            tipo = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif formato == "pdf":
            contenido, tipo = a_pdf(registro), "application/pdf"
        else:
            raise HTTPException(400, "Formato inválido: pdf o docx")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"No se pudo generar el archivo: {exc}") from exc
    return Response(contenido, media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.{formato}"'})


@router.get("/{registro_id}/archivo/{campo_id}")
def ver_archivo(registro_id: int, campo_id: str, usuario: Usuario = Depends(usuario_actual),
                db: Session = Depends(get_db)) -> dict:
    registro = obtener(db, Registro, registro_id)
    verificar_unidad(usuario, registro.unidad_id)
    valor = registro.valores.get(campo_id)
    if not isinstance(valor, dict) or not valor.get("clave"):
        raise HTTPException(404, "Sin archivo")
    return {"url": almacenamiento.url_descarga(valor["clave"], valor.get("nombre"))}
