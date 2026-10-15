<h1 align="center">Certificaciones VS y LH — API</h1>

<p align="center">
  API REST del sistema de certificaciones de <strong>Agrícola Viento Sur</strong> y <strong>Agrícola La Hornilla</strong>.
  <br/>
  Documentos fijos y vencimientos, registros, auditorías y no conformidades, laboratorio y medio ambiente en una sola plataforma.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/estado-en_desarrollo-f59e0b?style=for-the-badge" alt="Estado" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.142-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLAlchemy-2.1-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" />
  <img src="https://img.shields.io/badge/Cloud_Run-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" />
</p>

---

## El problema

El Área de Certificaciones de La Hornilla y Viento Sur mantiene más de diez protocolos al mismo tiempo (GLOBALG.A.P., BRCGS, PrimusGFS, GRASP, LEAF, SPRING, Tesco, SMETA, Walmart, FSMA PSR) en varios campos y plantas. Hasta ahora todo vivía en planillas Excel, carpetas compartidas y correos:

- Los **certificados** y documentos (procedimientos, análisis de riesgos, instructivos) estaban repartidos, sin historial de versiones ni alerta antes de vencer.
- Las **auditorías internas** se respondían en planillas y cada "No" se seguía a mano hasta cerrarlo.
- Los **registros** de terreno (controles, checklists) se llenaban en papel o Word y se revisaban tarde.
- Los **análisis de laboratorio** y los consumos para la **huella de carbono** no tenían un lugar común ni comparación entre temporadas.

Cuando llega un auditor externo, reunir la evidencia tomaba días.

---

## La solución

Una API propia que concentra todo el trabajo del área y aplica sus reglas: quién puede ver y editar qué sucursal, qué se aprueba, qué vence y qué queda registrado.

**La API permite:**

- Guardar los documentos fijos con su historial de versiones y la **ficha de cada certificado** (norma, N°, vigencia, sucursales cubiertas), leída automáticamente desde el PDF.
- Interpretar un archivo recién subido y proponer si es una **versión nueva** de un documento existente o qué datos rellenar.
- Importar los **checklist oficiales** de cada norma (Excel) y conservar todas sus versiones.
- Planificar y responder **auditorías** punto por punto; cada "No" genera una **no conformidad** con su plan de acción, evidencia, revisión y cierre, y detecta reincidencias.
- Crear **plantillas de registro desde Word** y llevar el llenado, la revisión y la aprobación de cada registro, con firma y exportación a PDF y Word.
- Registrar **análisis de laboratorio** comparando cada parámetro con su límite, leyendo el informe del laboratorio (PDF o Excel).
- Calcular la **huella de carbono** y comparar temporadas al mismo período.
- Generar la **carpeta para el auditor** (ZIP con documentos vigentes, índice, auditorías y NC).
- Dejar cada cambio de negocio en la **bitácora** (usuario, fecha y hora).

---

## El impacto esperado

- **Un solo lugar** para documentos, registros, auditorías, laboratorio y ambiente de las dos empresas.
- **Nada vence por sorpresa**: vencimientos agrupados a 60, 30 y 7 días.
- **No conformidades con dueño y plazo**, seguidas hasta su cierre con evidencia.
- **Evidencia lista para el auditor** en un clic, en vez de días armando carpetas.

---

## Arquitectura

```
Aplicación React (Firebase Hosting)
        │  HTTPS · /api
        ▼
API FastAPI (Cloud Run, southamerica-west1)  ──►  Cloud Storage (archivos, URLs firmadas)
        │  IP privada
        ▼
Cloud SQL (lahornilla_base_normalizada)
   ├── tablas propias:     certificaciones_dim_* · certificaciones_fact_* · certificaciones_pivot_*
   └── tablas compartidas: general_dim_sucursal · general_dim_usuario · usuario_pivot_app_usuario
```

- La API es la **única** que se conecta a la base: la aplicación le pide todo a la API.
- Los archivos (PDF, fotos de evidencia, Word, planillas) no van a la base: se suben y descargan directo de Cloud Storage con URLs firmadas, y la tabla guarda solo su clave.
- **Nomenclatura de tablas**: `certificaciones_dim_*` (catálogos y entidades), `certificaciones_fact_*` (hechos y movimientos) y `certificaciones_pivot_*` (relaciones muchos a muchos).
- **Tablas compartidas de la empresa**: usuarios, sucursales y acceso a aplicaciones se leen de las tablas que ya existen; Certificaciones nunca las modifica.

> **Estado actual:** funciona en modo **demo** con una base SQLite local. La conexión a Cloud SQL, el inicio de sesión con `general_dim_usuario` (igual que LH Inventario) y los permisos por aplicación se completan al pasar a producción.

---

## Requisitos

- Python **3.12+** (la imagen de Docker usa 3.13)
- Para la demo: nada más (SQLite)
- Para producción: Cloud SQL vía Cloud SQL Auth Proxy y Google Cloud CLI

---

## Instalación local

```bash
# 1. Entorno virtual
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux / macOS

# 2. Dependencias
pip install -r requirements.txt

# 3. Variables de entorno: run_dev.py copia env.ejemplo como .env si no existe
```

### Base de demo

```bash
python -m scripts.crear_demo
```

Crea `privado/demo.db` (SQLite) y `privado/archivos/` desde cero: catálogos, usuarios de prueba, datos de ejemplo y, si existe la carpeta `../referencias/` (fuera del repositorio), los checklist, certificados y auditorías reales. Se niega a correr si `DB_MOTOR` no es `sqlite`, así que nunca toca Cloud SQL.

> `privado/` no se versiona: contiene datos reales.

---

## Ejecutar

```bash
python run_dev.py        # muestra la configuración, hot-reload y abre la documentación
```

o manual: `uvicorn main:app --reload --host 127.0.0.1 --port 8080`

| Interfaz | URL |
|---|---|
| Documentación (Swagger) | http://localhost:8080/docs |
| ReDoc | http://localhost:8080/redoc |
| OpenAPI JSON | http://localhost:8080/openapi.json |

En producción y en la demo publicada (con clave) la documentación queda deshabilitada.

### Otros comandos

```bash
python -m pytest -q tests                      # pruebas (con datos ficticios)
python -m jobs.alertas_vencimiento             # aviso diario de vencimientos (correo por definir)
python -m scripts.generar_sql mysql            # DDL del esquema para revisarlo antes de aplicarlo
```

---

## Variables de entorno

Plantilla en `env.ejemplo` (sin valores reales).

| Variable | Uso |
|---|---|
| `DEBUG`, `ENTORNO` | `desarrollo` o `produccion`. En producción no se permite `AUTH_MODO=demo`, `DB_MOTOR=sqlite` ni `ALMACENAMIENTO=local` |
| `DEV_PORT` | Puerto local (8080; el frontend local apunta ahí) |
| `ORIGENES_PERMITIDOS` | CORS: direcciones de la aplicación, separadas por coma |
| `DB_MOTOR`, `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | Conexión. `sqlite` = demo local |
| `DATABASE_URL` | URL SQLAlchemy completa (Cloud Run, desde Secret Manager) |
| `AUTH_MODO` | `demo` (selector de usuario) o `firebase` |
| `ALMACENAMIENTO`, `BUCKET_DOCUMENTOS`, `GCP_PROJECT_ID` | `local` (disco) o `gcs` (Cloud Storage con URLs firmadas) |
| `URL_PUBLICA_API`, `CLAVE_FIRMA_LOCAL` | Solo con almacenamiento local: dirección pública de la API y clave para firmar descargas |
| `DEMO_CLAVE` | Demo publicada: clave de acceso que pide la pantalla de ingreso. Vacía = demo local sin clave |
| `SEMILLA_DIR` | Demo publicada: carpeta (bucket montado) con la base y los archivos de partida |
| `DIAS_ALERTA` | Días de aviso antes de un vencimiento (60,30,7) |

> **Importante:** `.env` tiene credenciales. Nunca se sube al repositorio (está en `.gitignore`).

---

## Endpoints

Todos bajo `/api`. Autenticación: cabecera `X-Usuario-Demo: <id>` (demo; más `X-Clave-Demo` en la demo publicada) o `Authorization: Bearer <token>`. Los permisos por rol y sucursal se validan en la API.

| Módulo | Endpoints principales |
|---|---|
| ⚙️ Sistema | `GET /api/` · `GET /api/db/ping` |
| 📍 Catálogos | `GET /api/catalogos` · `GET /api/yo` · `GET /api/usuarios-demo` · `GET /api/versiones/{id}/requisitos` |
| 📎 Archivos | `POST /api/archivos/url-subida` (URL firmada para subir directo) |
| 📄 Documentos fijos | `GET/POST /api/documentos` · `GET/PATCH /api/documentos/{id}` · `POST /api/documentos/analizar` · `POST /api/documentos/{id}/versiones` · `GET /api/documentos/versiones/{id}/descarga` · `GET /api/documentos/exportar` · `GET /api/documentos/codigos` · `GET/POST /api/capacitaciones` · `GET /api/vencimientos` |
| 📝 Registros | `GET/POST /api/registros/plantillas` · `PUT /api/registros/plantillas/{id}` · `POST /api/registros/plantillas/importar-word` · `GET/POST /api/registros` · `GET /api/registros/{id}` · `PUT /api/registros/{id}/valores` · `POST /api/registros/{id}/enviar` · `POST /api/registros/{id}/revision` · `GET /api/registros/{id}/exportar` · `GET /api/registros/{id}/historial` · `GET /api/registros/actividad` |
| 🧪 Laboratorio | `GET/POST /api/laboratorio/analisis` · `POST /api/laboratorio/leer-informe` · `GET /api/laboratorio/analisis/{id}/informe` |
| ✅ Auditorías | `GET/POST /api/auditorias` · `GET/PATCH /api/auditorias/{id}` · `PUT /api/auditorias/{id}/respuestas/{requisito_id}` · `POST /api/auditorias/{id}/emitir` · `GET /api/auditorias/{id}/exportar` · `GET /api/programa` · `POST /api/importaciones/brcgs` · `POST /api/importaciones/checklist` |
| ⚠️ No conformidades | `GET /api/no-conformidades` · `GET/PATCH /api/no-conformidades/{id}` · `PUT /api/no-conformidades/{id}/plan` · `POST /api/no-conformidades/{id}/acciones` · `POST /api/no-conformidades/{id}/revision` · `POST /api/no-conformidades/{id}/cerrar` · `GET /api/no-conformidades/acciones/{id}/evidencia` |
| 🌿 Medio ambiente | `GET/POST /api/ambiente/consumos` · `GET/POST /api/ambiente/reciclaje` · `GET /api/ambiente/huella` · `GET /api/ambiente/comparativa` · `GET /api/ambiente/factores` · `GET /api/ambiente/conceptos` |
| 📊 Tablero y bitácora | `GET /api/dashboard` · `GET /api/bitacora` |
| 🗂️ Carpeta auditor | `GET /api/carpeta-auditor` (ZIP) |

Detalle de cada endpoint en `/docs`.

---

## Estructura del proyecto

```
API-CERTIFICACIONES/
├── main.py                    # Entrada: routers bajo /api, CORS, seguridad y /docs
├── config.py                  # Configuración desde variables de entorno
├── run_dev.py                 # Desarrollo: banner, hot-reload y navegador
├── usar_venv.py               # Asegura que los scripts corran con el venv
├── env.ejemplo                # Plantilla de variables (sin valores reales)
├── Dockerfile                 # Imagen para Cloud Run (usuario no-root, puerto 8080)
├── requirements.txt
├── routers/                   # Endpoints por módulo (ver routers/README.md)
│   ├── catalogos.py           # Empresas, sucursales, protocolos, usuarios
│   ├── archivos.py            # URLs firmadas de subida y descarga
│   ├── documentos.py          # Documentos fijos, versiones, certificados y vencimientos
│   ├── registros.py           # Plantillas y registros
│   ├── laboratorio.py
│   ├── auditorias.py          # Auditorías, respuestas e importación de checklist
│   ├── no_conformidades.py
│   ├── ambiente.py            # Consumos, reciclaje, huella y comparativa de temporadas
│   ├── tablero.py             # Inicio y bitácora
│   └── carpeta.py             # ZIP para el auditor
├── schemas/                   # Modelos Pydantic de entrada
├── utils/
│   ├── modelos.py             # Tablas (SQLAlchemy)
│   ├── db.py                  # Conexión (SQLite demo / MySQL / PostgreSQL)
│   ├── auth.py                # Usuario actual, clave de demo y permisos por sucursal
│   ├── almacenamiento.py      # Cloud Storage o disco local, con URLs firmadas
│   ├── analizar_documento.py  # Qué documento es un archivo subido y con qué rellenarlo
│   ├── leer_certificado.py    # Ficha de un certificado desde su PDF
│   ├── importar_checklist.py  # Checklist oficiales de cada norma
│   ├── importadores.py        # Auditorías internas BRCGS
│   ├── importar_plantilla_word.py / rellenar_word.py / exportar_registro.py
│   ├── leer_informe_lab.py    # Valores desde el informe del laboratorio
│   ├── exportar_auditoria.py
│   ├── no_conformidades.py    # NC automáticas y reincidencias
│   ├── bitacora.py            # Registro de cambios
│   └── docs_html.py           # Documentación personalizada
├── scripts/
│   ├── crear_demo.py          # Base de demo
│   ├── cargar_semilla.py      # Demo publicada: copia la base de partida al arrancar
│   └── generar_sql.py         # DDL del esquema
├── jobs/alertas_vencimiento.py
├── migrations/                # Solo esquema, sin datos
├── tests/                     # Pruebas con datos ficticios
└── privado/                   # Base demo y archivos locales (no se versiona)
```

---

## Despliegue

Manual, desde esta carpeta. Un `git push` no despliega nada.

```bash
gcloud run deploy <servicio> --source . --region southamerica-west1 --project <id-del-proyecto>
```

- Producción: credenciales en **Secret Manager**, base en **Cloud SQL** por IP privada y archivos en **Cloud Storage**. Las migraciones se revisan y se aplican a mano.
- Demo publicada (antes de producción): misma imagen en modo demo, con `DEMO_CLAVE` (Secret Manager) y la base de partida en un bucket privado montado en `SEMILLA_DIR`.

---

## Dependencias principales

| Librería | Uso |
|---|---|
| fastapi, uvicorn, python-multipart | Framework web y servidor |
| SQLAlchemy, pydantic | Acceso a datos portable y validación |
| openpyxl | Importar checklist y planillas, exportar Excel |
| pypdf | Leer certificados e informes de laboratorio en PDF |
| python-docx, fpdf2 | Plantillas de registro desde Word; exportar registros a Word y PDF |
| firebase_admin | Verificar tokens de inicio de sesión |
| google-cloud-storage | Archivos en Cloud Storage con URLs firmadas |
| pytest, httpx | Pruebas |

---

## Frontend

Esta API la consume la aplicación web en **React**, desplegada en **Firebase Hosting**.

➡️ Repositorio de la aplicación: [certificaciones_react](https://github.com/Straaizo/certificaciones_react)

---

<p align="center">
  Desarrollado por <strong>Enzo Sabattini</strong> · Soporte TI & Desarrollo — La Hornilla
</p>
