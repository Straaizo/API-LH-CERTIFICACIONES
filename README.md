<h1 align="center">Certificaciones LH y VS — API</h1>

<p align="center">
  API REST del sistema de certificaciones de <strong>Agrícola La Hornilla</strong> y <strong>Agrícola Viento Sur</strong>.
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
- Dejar cada cambio de negocio en el **historial** (usuario, fecha y hora).

---

## El impacto esperado

- **Un solo lugar** para documentos, registros, auditorías, laboratorio y ambiente de las dos empresas.
- **Nada vence por sorpresa**: avisos a 60, 30 y 7 días.
- **No conformidades con responsable y plazo**, seguidas hasta su cierre con evidencia.
- **Evidencia lista para el auditor** en un clic, en vez de días armando carpetas.

---

## Arquitectura

```
Aplicación web React (PWA)
        │  HTTPS · JSON · JWT
        ▼
API FastAPI (contenedor en Google Cloud Run)  ──►  Cloud Storage (archivos privados, URLs firmadas)
        │
        ▼
MySQL en Cloud SQL (tablas propias + tablas compartidas de la empresa, solo lectura)
```

- La API es la **única** que se conecta a la base: la aplicación le pide todo a la API.
- Los archivos (PDF, fotos de evidencia, Word, planillas) no se guardan en la base: el navegador los sube y descarga directo desde Cloud Storage con enlaces firmados de pocos minutos, y la tabla guarda solo su referencia.
- Despliegue continuo: cada cambio en la rama principal se compila y publica automáticamente en Cloud Run.

### Modelo de datos

| Tipo | Qué guarda |
|---|---|
| Dimensiones | Catálogos que cambian poco: normas y sus versiones, puntos de control, plantillas, tipos de análisis, conceptos ambientales |
| Hechos | Lo que ocurre en el tiempo: auditorías, respuestas, no conformidades, registros, análisis, consumos, reciclaje e historial de cambios |
| Puente | Qué normas aplican a cada sucursal |
| Vistas | Temporadas, vencimientos, huella y análisis por temporada, estado de las no conformidades y tablero |

- **Datos compartidos de la empresa** (empresas, sucursales, temporadas y usuarios) se leen de las tablas que ya existen; esta API nunca las modifica.
- **Acceso y permisos** se administran en el portal web de la empresa: cada usuario necesita acceso a la aplicación, ve solo sus sucursales y, por módulo, puede ver o editar según sus permisos. El historial completo de cambios requiere un permiso aparte.
- **Temporada**: no se guarda en cada dato; se deduce de su fecha y de la empresa de la sucursal.

---

## Seguridad

- **Acceso:** usuario o correo + clave, contraseñas con bcrypt y tokens JWT de acceso y de refresco separados. Los permisos se validan en la API en cada petición, no solo en la interfaz.
- **Inicio de sesión:** pausa ante intentos fallidos por IP y por cuenta, y tiempo de respuesta constante, para que medir la demora no revele si un usuario existe o si una clave estuvo cerca.
- **Contra el abuso y los costos:** límite de peticiones por IP y por usuario (más estricto para lo pesado), bloqueo escalonado de quien insiste, cupo diario y tamaño máximo por archivo firmados en el enlace de subida, y rechazo de peticiones sin tamaño declarado.
- **Archivos:** almacenamiento privado, enlaces firmados de pocos minutos y solo PDF, imágenes, Word y Excel.
- **Producción:** sin documentación pública de la API, credenciales en un gestor de secretos, CORS solo para el dominio de la aplicación, cabeceras de seguridad y errores sin detalles internos.
- **Pruebas automáticas** de permisos, sesión, límites y protecciones.

---

## Módulos

| Módulo | Para qué sirve |
|---|---|
| 🔐 Sesión | Inicio de sesión con usuario o correo + clave del portal web y renovación del token |
| 📍 Catálogos | Empresas, sucursales, temporadas, protocolos y usuarios que usa toda la aplicación |
| 📄 Documentos fijos | Documentos por sección (campo, planta, empresarial), versiones, fichas de certificados y vencimientos |
| 📝 Registros | Plantillas importadas desde Word y registros llenados en terreno, con revisión y aprobación |
| ✅ Auditorías | Programa de auditorías, checklist por versión de norma y respuestas punto por punto |
| 📑 Auditorías externas | Informes de la certificadora como documento de consulta: resumen, versiones y descarga en PDF o Word |
| ⚠️ No conformidades | Hallazgos, análisis de causa, acciones, evidencia, revisión, cierre y reincidencias |
| 🧪 Laboratorio | Análisis de agua, suelo, hoja, fruta y residuos frente a sus límites; residuos (MRL) contra los límites de ASOEX por país de destino |
| 🌿 Medio ambiente | Consumos, reciclaje, huella de carbono y comparativa de temporadas |
| 📊 Tablero e historial | Indicadores de inicio, semáforo por protocolo e historial de cambios |
| 🗂️ Carpeta auditor | Evidencia vigente reunida para una auditoría externa |

---

## Estructura del proyecto

```
API-CERTIFICACIONES/
├── main.py                    # Entrada de la API: módulos bajo /api, seguridad y documentación
├── config.py                  # Configuración
├── routers/                   # Un archivo por módulo
│   ├── auth.py                # Inicio de sesión (JWT)
│   ├── catalogos.py
│   ├── archivos.py            # Subida y descarga de archivos
│   ├── documentos.py          # Documentos fijos, versiones, certificados y vencimientos
│   ├── registros.py
│   ├── laboratorio.py
│   ├── auditorias.py
│   ├── auditorias_externas.py # Informes de la certificadora (solo consulta)
│   ├── no_conformidades.py
│   ├── ambiente.py
│   ├── tablero.py
│   └── carpeta.py
├── schemas/                   # Validación de los datos de entrada
├── utils/
│   ├── modelos.py             # Tablas propias y compartidas
│   ├── auth.py                # Sesión (JWT), acceso a la app y permisos por módulo y sucursal
│   ├── proteccion.py          # Límites de peticiones, bloqueos y cupos contra abuso
│   ├── temporadas.py          # Temporadas por empresa
│   ├── almacenamiento.py      # Archivos en Cloud Storage
│   ├── analizar_documento.py  # Qué documento es un archivo subido y con qué completarlo
│   ├── leer_certificado.py    # Ficha de un certificado desde su PDF
│   ├── importar_checklist.py  # Checklist oficiales de cada norma
│   ├── importadores.py        # Auditorías internas BRCGS
│   ├── importar_plantilla_word.py / rellenar_word.py / exportar_registro.py
│   ├── leer_informe_lab.py    # Valores desde el informe del laboratorio
│   ├── importar_asoex.py / mrl.py / leer_carta_destino.py  # Límites ASOEX, informes MRL y carta de destino
│   ├── leer_auditoria_externa.py / exportar_auditoria_externa.py
│   ├── no_conformidades.py    # No conformidades automáticas y reincidencias
│   └── historial.py           # Historial de cambios
├── jobs/                      # Tareas programadas (aviso de vencimientos)
├── migrations/                # Esquema de la base
└── tests/                     # Pruebas con datos ficticios
```

## Frontend

Esta API la consume una aplicación web en **React + TypeScript** (instalable como app en el celular), desplegada en **Firebase Hosting**.

---

<p align="center">
  Desarrollado por <strong>Enzo Sabattini</strong> · Soporte TI & Desarrollo — La Hornilla
</p>
