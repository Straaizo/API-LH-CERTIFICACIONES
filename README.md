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
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" />
  <img src="https://img.shields.io/badge/Cloud_SQL-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white" />
  <img src="https://img.shields.io/badge/Cloud_Run-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white" />
</p>

---

## El problema

El Área de Certificaciones de La Hornilla y Viento Sur mantiene más de diez protocolos al mismo tiempo (GLOBALG.A.P., BRCGS, PrimusGFS, GRASP, GROW, LEAF, SPRING, Tesco, SMETA, Walmart, FSMA PSR) en varios campos y plantas. Hasta ahora todo vivía en planillas Excel, carpetas compartidas y correos:

- Los **certificados** y documentos (procedimientos, análisis de riesgos, instructivos) estaban repartidos, sin historial de versiones ni aviso antes de vencer.
- Las **auditorías internas** se respondían en planillas y cada "No" se seguía a mano hasta cerrarlo.
- Los **registros** de terreno (controles, checklists) se llenaban en papel o Word y se revisaban tarde.
- Los **análisis de laboratorio** y los consumos para la **huella de carbono** no tenían un lugar común ni comparación entre temporadas.

Cuando llega un auditor externo, reunir la evidencia tomaba días.

---

## La solución

Una API propia que concentra el trabajo del área y aplica sus reglas: quién puede ver y editar cada sucursal, qué se revisa, qué vence y qué queda registrado.

**El sistema permite:**

- Guardar los documentos fijos con su historial de versiones y la **ficha de cada certificado** (norma, N°, vigencia, sucursales cubiertas), leída automáticamente desde el PDF.
- Interpretar un archivo recién subido y proponer si es una **versión nueva** de un documento existente o qué datos completar.
- Importar los **checklist oficiales** de cada norma y conservar todas sus versiones.
- Planificar y responder **auditorías** punto por punto. Cada "No" genera una **no conformidad** con plan de acción, evidencia, revisión y cierre, y se detectan las reincidencias.
- Crear **plantillas de registro desde Word** y seguir el llenado, la revisión y la aprobación de cada registro, con firma.
- Registrar **análisis de laboratorio** comparando cada parámetro con su límite, leyendo el informe del laboratorio.
- Calcular la **huella de carbono** y comparar temporadas al mismo período.
- Generar la **carpeta para el auditor** con la evidencia vigente.
- Dejar cada cambio de negocio en la **bitácora** (usuario, fecha y hora).

---

## El impacto esperado

- **Un solo lugar** para documentos, registros, auditorías, laboratorio y ambiente de las dos empresas.
- **Nada vence por sorpresa**: avisos a 60, 30 y 7 días.
- **No conformidades con responsable y plazo**, seguidas hasta su cierre con evidencia.
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
- Los archivos (PDF, fotos de evidencia, Word, planillas) no se guardan en la base: van a Cloud Storage y la tabla guarda solo su referencia.
- Cada cambio de negocio queda en la bitácora.

### Modelo de datos

| Tipo | Prefijo | Qué guarda |
|---|---|---|
| Dimensión | `certificaciones_dim_*` | Catálogos y entidades que cambian poco: empresas, normas y sus versiones, puntos de control, plantillas, tipos de análisis |
| Hecho | `certificaciones_fact_*` | Lo que ocurre en el tiempo: auditorías, respuestas, no conformidades, registros, análisis, consumos, bitácora |
| Puente | `certificaciones_pivot_*` | Relaciones muchos a muchos, como las sucursales que cubre un certificado |

- **Tablas compartidas de la empresa**: usuarios, sucursales y acceso a aplicaciones se leen de las tablas que ya existen en la base de La Hornilla. Certificaciones nunca las modifica.
- La asignación de cada sucursal a su empresa (por ejemplo, Itahue como Viento Sur) vive solo en las tablas de Certificaciones.

---

## Módulos

| Módulo | Para qué sirve |
|---|---|
| 📍 Catálogos | Empresas, sucursales, temporadas, protocolos y usuarios que usa toda la aplicación |
| 📄 Documentos fijos | Documentos por sección (campo, planta, empresarial), versiones, fichas de certificados y vencimientos |
| 📝 Registros | Plantillas importadas desde Word y registros llenados en terreno, con revisión y aprobación |
| ✅ Auditorías | Programa de auditorías, checklist por versión de norma y respuestas punto por punto |
| ⚠️ No conformidades | Hallazgos, análisis de causa, acciones, evidencia, revisión, cierre y reincidencias |
| 🧪 Laboratorio | Análisis de agua, suelo, hoja, fruta y residuos frente a sus límites |
| 🌿 Medio ambiente | Consumos, reciclaje, huella de carbono y comparativa de temporadas |
| 📊 Tablero y bitácora | Indicadores de inicio, semáforo por protocolo e historial de cambios |
| 🗂️ Carpeta auditor | Evidencia vigente reunida para una auditoría externa |

---

## Estructura del proyecto

```
API-CERTIFICACIONES/
├── main.py                    # Entrada de la API: módulos bajo /api, seguridad y documentación
├── config.py                  # Configuración
├── routers/                   # Un archivo por módulo
│   ├── catalogos.py
│   ├── archivos.py            # Subida y descarga de archivos
│   ├── documentos.py          # Documentos fijos, versiones, certificados y vencimientos
│   ├── registros.py
│   ├── laboratorio.py
│   ├── auditorias.py
│   ├── no_conformidades.py
│   ├── ambiente.py
│   ├── tablero.py
│   └── carpeta.py
├── schemas/                   # Validación de los datos de entrada
├── utils/
│   ├── modelos.py             # Tablas
│   ├── auth.py                # Usuario actual y permisos por rol y sucursal
│   ├── almacenamiento.py      # Archivos en Cloud Storage
│   ├── analizar_documento.py  # Qué documento es un archivo subido y con qué completarlo
│   ├── leer_certificado.py    # Ficha de un certificado desde su PDF
│   ├── importar_checklist.py  # Checklist oficiales de cada norma
│   ├── importadores.py        # Auditorías internas BRCGS
│   ├── importar_plantilla_word.py / rellenar_word.py / exportar_registro.py
│   ├── leer_informe_lab.py    # Valores desde el informe del laboratorio
│   ├── no_conformidades.py    # No conformidades automáticas y reincidencias
│   └── bitacora.py            # Registro de cambios
├── jobs/                      # Tareas programadas (aviso de vencimientos)
├── migrations/                # Esquema de la base
└── tests/                     # Pruebas con datos ficticios
```

La API se construyó sobre la estructura de **API-BASE-LH**, el repositorio base de las APIs de La Hornilla: ahí está cómo se organiza y funciona una API de la empresa.

---

## Frontend

Esta API la consume la aplicación web en **React**, desplegada en **Firebase Hosting**.

➡️ Repositorio de la aplicación: [certificaciones_react](https://github.com/Straaizo/certificaciones_react)

---

<p align="center">
  Desarrollado por <strong>Enzo Sabattini</strong> · Soporte TI & Desarrollo — La Hornilla
</p>
