"""
utils/docs_html.py — Template HTML para Swagger UI personalizado (copiado de API-BASE-LH).

Personalizar por app editando las constantes al inicio:
  APP_TITLE    — nombre en header (soporta HTML: 'Mi <span>App</span>')
  APP_SUBTITLE — subtítulo del header en uppercase (ej: 'API DE INVENTARIO')
  PANEL_TITLE  — título dentro del panel verde
  PANEL_SUB    — subtítulo del panel
  MODULES      — cards de módulos del sistema
  HIDE_TAGS    — tags de Swagger que se ocultan (aparecen en el panel de estado)
"""

APP_TITLE    = "Certificaciones <span>VS y LH</span>"
APP_SUBTITLE = "API DE CERTIFICACIONES"
PANEL_TITLE  = "API Certificaciones"
PANEL_SUB    = "Documentos, auditorías, no conformidades, laboratorio y medio ambiente · Viento Sur y La Hornilla"

# tipo: "fact" (verde) | "dim" (azul) | "view" (violeta)
MODULES = [
    {"tipo": "dim",  "icono": "&#128205;",        "nombre": "Catálogos",        "desc": "DIM &middot; Sitios, temporadas, protocolos y usuarios"},
    {"tipo": "fact", "icono": "&#128196;",        "nombre": "Documentos fijos", "desc": "FACT &middot; Versiones, revisión y vencimientos"},
    {"tipo": "fact", "icono": "&#128221;",        "nombre": "Registros",        "desc": "FACT &middot; Plantillas, llenado, aprobación y Word/PDF"},
    {"tipo": "fact", "icono": "&#129514;",        "nombre": "Laboratorio",      "desc": "FACT &middot; Análisis y comparación con límites"},
    {"tipo": "fact", "icono": "&#9989;",          "nombre": "Auditorías",       "desc": "FACT &middot; Checklist, programa anual e importación"},
    {"tipo": "fact", "icono": "&#9888;&#65039;",  "nombre": "No conformidades", "desc": "FACT &middot; Levantamientos, cierre y reincidencias"},
    {"tipo": "fact", "icono": "&#127807;",        "nombre": "Medio ambiente",   "desc": "FACT &middot; Huella de carbono y reciclaje"},
    {"tipo": "view", "icono": "&#128202;",        "nombre": "Tablero",          "desc": "VIEW &middot; Resumen de inicio, bitácora y carpeta del auditor"},
]

HIDE_TAGS = ["Sistema", "Base de Datos"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _modules_html() -> str:
    parts = []
    for m in MODULES:
        parts.append(
            f'<div class="lh-module lh-module-{m["tipo"]}">'
            f'<div class="lh-module-icon">{m["icono"]}</div>'
            f'<div>'
            f'<div class="lh-module-name">{m["nombre"]}</div>'
            f'<div class="lh-module-desc">{m["desc"]}</div>'
            f'</div>'
            f'</div>'
        )
    return "".join(parts)  # sin saltos de línea — JS-safe


def get_docs_html() -> str:
    return (
        _HTML_TEMPLATE
        .replace("__APP_TITLE__",    APP_TITLE)
        .replace("__APP_SUBTITLE__", APP_SUBTITLE)
        .replace("__PANEL_TITLE__",  PANEL_TITLE)
        .replace("__PANEL_SUB__",    PANEL_SUB)
        .replace("__MODULES__",      _modules_html())
        .replace("__HIDE_TAGS__",    str(HIDE_TAGS))
    )


# ─────────────────────────────────────────────────────────────────────────────
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Certificaciones VS y LH — API</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"/>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  font-family: 'Montserrat', sans-serif;
  background: #052e16;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #14532d; }
::-webkit-scrollbar-thumb { background: #16a34a88; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #4ade80; }

/* ── Header ── */
#lh-header {
  position: sticky; top: 0; z-index: 1000;
  background: linear-gradient(135deg, #052e16 0%, #14532d 60%, #052e16 100%);
  border-bottom: 2px solid #16a34a;
  padding: 0 2rem; min-height: 68px;
  display: flex; align-items: center; justify-content: space-between;
  box-shadow: 0 4px 24px rgba(0,0,0,.5);
}
.lh-brand { display: flex; align-items: center; gap: 14px; }
.lh-logo  { height: 42px; object-fit: contain; border-radius: 6px; filter: drop-shadow(0 0 6px #4ade8066); }
.lh-logo-fallback {
  display: none; width: 42px; height: 42px;
  background: #166534; border: 2px solid #16a34a; border-radius: 8px;
  align-items: center; justify-content: center;
  font-size: 1rem; font-weight: 800; color: #4ade80; letter-spacing: -1px;
}
.lh-brand-text { display: flex; flex-direction: column; gap: 2px; }
.lh-title      { font-size: 1.35rem; font-weight: 700; color: #f0fdf4; letter-spacing: -.3px; }
.lh-title span { color: #4ade80; }
.lh-subtitle   { font-size: .72rem; color: #86efac; text-transform: uppercase; letter-spacing: .5px; opacity: .8; }
.lh-nav { display: flex; gap: 10px; align-items: center; }
.lh-nav a { font-size: .72rem; color: #4ade8099; text-decoration: none; transition: color .15s; }
.lh-nav a:hover { color: #4ade80; }

/* ── Swagger container ── */
#swagger-ui { background: #f8fafc; min-height: calc(100vh - 68px); padding-top: 18px; }

/* ── Swagger overrides ── */
.swagger-ui .topbar,
.swagger-ui .filter-container,
.swagger-ui .auth-wrapper,
.swagger-ui .scheme-container { display: none !important; }

.swagger-ui, .swagger-ui * { font-family: 'Montserrat', sans-serif !important; }

.swagger-ui .info .title {
  font-family: 'Montserrat', sans-serif !important;
  font-size: 1.6rem !important; font-weight: 700 !important; color: #052e16 !important;
}
.swagger-ui .info .title small {
  background: #16a34a !important; color: #f0fdf4 !important;
  border-radius: 6px; padding: 2px 8px; font-size: .7rem; font-weight: 700;
}
.swagger-ui .opblock-tag {
  font-family: 'Montserrat', sans-serif !important;
  font-size: .95rem !important; font-weight: 600 !important;
  color: #14532d !important; border-bottom: 1px solid #dcfce7 !important;
  padding: 14px 0 !important;
}
.swagger-ui .opblock-tag:hover { background: #f0fdf4 !important; }
.swagger-ui .opblock-tag small {
  font-family: 'Montserrat', sans-serif !important;
  font-size: .75rem !important; color: #4b7c5e !important; font-weight: 400 !important;
}
.swagger-ui .opblock {
  border-radius: 8px !important; margin: 6px 0 !important;
  box-shadow: 0 1px 4px rgba(0,0,0,.07) !important;
}
.swagger-ui .opblock .opblock-summary-method {
  border-radius: 6px !important; font-family: 'Montserrat', sans-serif !important;
  font-size: .72rem !important; font-weight: 700 !important; min-width: 60px !important;
}
.swagger-ui .opblock .opblock-summary-description {
  font-family: 'Montserrat', sans-serif !important; font-size: .82rem !important; color: #475569 !important;
}
.swagger-ui .opblock-get    { border-color: #3b82f6 !important; }
.swagger-ui .opblock-get    .opblock-summary { background: #eff6ff !important; }
.swagger-ui .opblock-get    .opblock-summary-method { background: #3b82f6 !important; }
.swagger-ui .opblock-post   { border-color: #16a34a !important; }
.swagger-ui .opblock-post   .opblock-summary { background: #f0fdf4 !important; }
.swagger-ui .opblock-post   .opblock-summary-method { background: #16a34a !important; }
.swagger-ui .opblock-put    { border-color: #f59e0b !important; }
.swagger-ui .opblock-put    .opblock-summary { background: #fffbeb !important; }
.swagger-ui .opblock-put    .opblock-summary-method { background: #f59e0b !important; }
.swagger-ui .opblock-delete { border-color: #ef4444 !important; }
.swagger-ui .opblock-delete .opblock-summary { background: #fef2f2 !important; }
.swagger-ui .opblock-delete .opblock-summary-method { background: #ef4444 !important; }
.swagger-ui .btn.execute {
  background: #14532d !important; border-color: #14532d !important;
  border-radius: 8px !important; font-family: 'Montserrat', sans-serif !important;
}

/* ── Separadores de sección ── */
.lh-sep {
  display: flex; align-items: center; gap: 12px;
  padding: 18px 20px 4px; background: #f8fafc;
}
.lh-sep::before, .lh-sep::after {
  content: ''; flex: 1; height: 1.5px;
  background: linear-gradient(to right, transparent, #16a34a88, transparent);
}
.lh-sep span {
  font-family: 'Montserrat', sans-serif;
  font-size: .6rem; font-weight: 700; letter-spacing: 2.5px; text-transform: uppercase;
  color: #16a34a; white-space: nowrap; padding: 3px 10px;
  border: 1px solid #16a34a44; border-radius: 999px; background: #f0fdf4;
}

/* ── Panel info (inyectado en .information-container) ── */
.lh-info-panel {
  font-family: 'Montserrat', sans-serif;
  background: #f0fdf4; border: 1px solid #bbf7d0;
  border-radius: 12px; padding: 20px 24px; margin: 16px 0 8px;
  -webkit-font-smoothing: antialiased;
}
.lh-info-title { font-size: 1.25rem; font-weight: 700; color: #052e16; letter-spacing: -.3px; margin-bottom: 3px; }
.lh-info-sub   { font-size: .78rem; color: #166534; margin-bottom: 16px; }
.lh-section-label {
  font-size: .65rem; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase;
  color: #16a34a; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid #bbf7d0;
}
/* Módulos */
.lh-modules {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 8px; margin-bottom: 16px;
}
.lh-module {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: 8px; border-left: 3px solid transparent;
}
.lh-module-fact { background: #fff; border-color: #16a34a; }
.lh-module-dim  { background: #fff; border-color: #3b82f6; }
.lh-module-view { background: #fff; border-color: #8b5cf6; }
.lh-module-icon { font-size: 1.1rem; line-height: 1; }
.lh-module-name { font-size: .78rem; font-weight: 600; color: #0f172a; line-height: 1.3; }
.lh-module-desc { font-size: .67rem; color: #64748b; margin-top: 1px; }
/* Status cards */
.lh-status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 540px) { .lh-status-grid { grid-template-columns: 1fr; } }
.lh-status-card {
  background: #fff; border: 1px solid #dcfce7; border-radius: 8px;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 8px;
}
.lh-status-header { display: flex; align-items: center; gap: 10px; }
.lh-status-icon  { font-size: 1.2rem; line-height: 1; }
.lh-status-label { font-size: .8rem; font-weight: 600; color: #052e16; line-height: 1.2; }
.lh-status-desc  { font-size: .65rem; color: #64748b; }
.lh-status-dot {
  margin-left: auto; width: 10px; height: 10px; border-radius: 50%;
  background: #cbd5e1; flex-shrink: 0; transition: background .3s;
}
.lh-status-dot.ok  { background: #16a34a; box-shadow: 0 0 6px #16a34a88; }
.lh-status-dot.err { background: #ef4444; box-shadow: 0 0 6px #ef444488; }
.lh-check-row { display: flex; gap: 6px; align-items: center; }
.lh-status-result {
  flex: 1; font-family: 'Montserrat', sans-serif; font-size: .67rem; color: #475569;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 5px;
  padding: 5px 8px; min-height: 26px;
}
.lh-check-btn {
  color: #fff; background: #16a34a; border: none; border-radius: 5px;
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  cursor: pointer; flex-shrink: 0; transition: background .15s;
}
.lh-check-btn:hover    { background: #15803d; }
.lh-check-btn:disabled { background: #86efac; cursor: not-allowed; opacity: .7; }
@keyframes lh-spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<!-- Header -->
<div id="lh-header">
  <div class="lh-brand">
    <img class="lh-logo" src="/static/logo.png" alt="La Hornilla"
         onerror="this.style.display='none';document.getElementById('lh-fb').style.display='flex';"/>
    <div id="lh-fb" class="lh-logo-fallback">LH</div>
    <div class="lh-brand-text">
      <div class="lh-title">__APP_TITLE__</div>
      <div class="lh-subtitle">__APP_SUBTITLE__</div>
    </div>
  </div>
  <nav class="lh-nav">
    <a href="/redoc">ReDoc</a>
    <a href="/openapi.json">OpenAPI</a>
  </nav>
</div>

<!--
  Panel info como <template> — HTML estático, no visible, sin conflictos JS.
  El JS lo clona y lo inyecta en .information-container cuando Swagger renderiza.
-->
<template id="lh-tpl">
  <div class="lh-info-panel">
    <div class="lh-info-title">__PANEL_TITLE__</div>
    <div class="lh-info-sub">__PANEL_SUB__</div>

    <div class="lh-section-label">M&oacute;dulos del Sistema</div>
    <div class="lh-modules">
      __MODULES__
    </div>

    <div class="lh-section-label">Estado del Servicio</div>
    <div class="lh-status-grid">

      <div class="lh-status-card">
        <div class="lh-status-header">
          <span class="lh-status-icon">&#9881;&#65039;</span>
          <div>
            <div class="lh-status-label">Sistema</div>
            <div class="lh-status-desc">Estado general de la API</div>
          </div>
          <span class="lh-status-dot" id="lh-api-dot"></span>
        </div>
        <div class="lh-check-row">
          <div class="lh-status-result" id="lh-api-result">Verificando&hellip;</div>
          <button class="lh-check-btn" id="lh-btn-api" onclick="checkApi()"></button>
        </div>
      </div>

      <div class="lh-status-card">
        <div class="lh-status-header">
          <span class="lh-status-icon">&#128452;&#65039;</span>
          <div>
            <div class="lh-status-label">Base de Datos</div>
            <div class="lh-status-desc">Conexi&oacute;n con la base de datos</div>
          </div>
          <span class="lh-status-dot" id="lh-db-dot"></span>
        </div>
        <div class="lh-check-row">
          <div class="lh-status-result" id="lh-db-result">Verificando&hellip;</div>
          <button class="lh-check-btn" id="lh-btn-db" onclick="checkDb()"></button>
        </div>
      </div>

    </div>
  </div>
</template>

<!-- Swagger UI -->
<div id="swagger-ui"></div>

<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
var SVG_REFRESH = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>';
var SVG_SPIN   = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="animation:lh-spin .7s linear infinite"><path d="M12 2a10 10 0 0 1 10 10"/><circle cx="12" cy="12" r="10" stroke-opacity=".2"/></svg>';

// ── Checks ────────────────────────────────────────────────────────────────
async function checkApi() {
  var btn = document.getElementById('lh-btn-api');
  var res = document.getElementById('lh-api-result');
  var dot = document.getElementById('lh-api-dot');
  if (!btn) return;
  btn.disabled = true; btn.innerHTML = SVG_SPIN;
  try {
    var r = await fetch('/api/'), d = await r.json();
    dot.className = 'lh-status-dot ok';
    res.textContent = d.message || 'API activa';
  } catch(e) {
    dot.className = 'lh-status-dot err';
    res.textContent = 'No disponible';
  }
  btn.disabled = false; btn.innerHTML = SVG_REFRESH;
}

async function checkDb() {
  var btn = document.getElementById('lh-btn-db');
  var res = document.getElementById('lh-db-result');
  var dot = document.getElementById('lh-db-dot');
  if (!btn) return;
  btn.disabled = true; btn.innerHTML = SVG_SPIN;
  try {
    var r = await fetch('/api/db/ping'), d = await r.json();
    dot.className = r.ok ? 'lh-status-dot ok' : 'lh-status-dot err';
    res.textContent = d.message || (r.ok ? 'Conexi\u00f3n exitosa' : 'Error');
  } catch(e) {
    dot.className = 'lh-status-dot err';
    res.textContent = 'No disponible';
  }
  btn.disabled = false; btn.innerHTML = SVG_REFRESH;
}

// ── Inyección del panel ───────────────────────────────────────────────────
function injectPanel() {
  var info = document.querySelector('.swagger-ui .information-container');
  if (!info || info.dataset.lhDone) return;
  info.dataset.lhDone = '1';
  var tpl = document.getElementById('lh-tpl');
  info.innerHTML = '';
  info.appendChild(document.importNode(tpl.content, true));
  var btnApi = document.getElementById('lh-btn-api');
  var btnDb  = document.getElementById('lh-btn-db');
  if (btnApi) btnApi.innerHTML = SVG_REFRESH;
  if (btnDb)  btnDb.innerHTML  = SVG_REFRESH;
  setTimeout(function() { checkApi(); checkDb(); }, 600);
}

// ── Tags: ocultar sistema + separadores ──────────────────────────────────
var HIDE    = __HIDE_TAGS__;
var sepDone = false;

function processTags() {
  if (sepDone) return;
  var sections = document.querySelectorAll('.opblock-tag-section');
  if (!sections.length) return;
  sections.forEach(function(sec) {
    var h4 = sec.querySelector('h4[data-tag]');
    if (!h4) return;
    var tag = h4.getAttribute('data-tag') || '';
    if (HIDE.some(function(h) { return tag.indexOf(h) !== -1; })) {
      sec.style.display = 'none'; return;
    }
    var sep = document.createElement('div');
    sep.className = 'lh-sep';
    sep.innerHTML = '<span>' + tag + '</span>';
    sec.parentNode.insertBefore(sep, sec);
  });
  sepDone = true;
}

// ── MutationObserver — arranca ANTES de SwaggerUIBundle ──────────────────
var panelDone = false;
var observer = new MutationObserver(function() {
  if (!panelDone && document.querySelector('.swagger-ui .information-container')) {
    injectPanel(); panelDone = true;
  }
  if (!sepDone && document.querySelectorAll('.opblock-tag-section').length > 0) {
    processTags();
  }
  if (panelDone && sepDone) observer.disconnect();
});
observer.observe(document.getElementById('swagger-ui'), { childList: true, subtree: true });

// ── SwaggerUIBundle ───────────────────────────────────────────────────────
SwaggerUIBundle({
  url: '/openapi.json',
  dom_id: '#swagger-ui',
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
  layout: 'BaseLayout',
  docExpansion: 'none',
  defaultModelsExpandDepth: -1,
  filter: false,
  persistAuthorization: true,
  tryItOutEnabled: false,
  deepLinking: true,
  displayRequestDuration: true,
});
</script>
</body>
</html>
"""
