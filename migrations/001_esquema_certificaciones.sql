-- Esquema Certificaciones (MySQL). Generado desde utils/modelos.py
-- Requiere las tablas compartidas general_empresa/sucursal/temporada/usuario ya existentes.

CREATE TABLE certificaciones_dim_categoriadocumento (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	nombre VARCHAR(120) NOT NULL, 
	ambito VARCHAR(10) NOT NULL, 
	requiere_vencimiento BOOL NOT NULL, 
	requiere_codigo BOOL NOT NULL, 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE certificaciones_dim_conceptoambiental (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	codigo VARCHAR(40) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	categoria VARCHAR(20) NOT NULL, 
	unidad_medida VARCHAR(20) NOT NULL, 
	activo BOOL NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE certificaciones_dim_especie (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	nombre VARCHAR(80) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (nombre)
);

CREATE TABLE certificaciones_dim_protocolo (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	codigo VARCHAR(30) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	ambito VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE certificaciones_dim_tipoanalisis (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	nombre VARCHAR(120) NOT NULL, 
	ambito VARCHAR(10) NOT NULL, 
	usa_fuente_agua BOOL NOT NULL, 
	usa_especie BOOL NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE certificaciones_dim_documento (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	categoria_id INTEGER NOT NULL, 
	empresa_id INTEGER NOT NULL, 
	seccion VARCHAR(12) NOT NULL, 
	titulo VARCHAR(250) NOT NULL, 
	codigo VARCHAR(40), 
	creado_por_id VARCHAR(45) NOT NULL, 
	creado_en DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(categoria_id) REFERENCES certificaciones_dim_categoriadocumento (id), 
	FOREIGN KEY(empresa_id) REFERENCES general_dim_empresa (id), 
	FOREIGN KEY(creado_por_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_dim_documento_codigo ON certificaciones_dim_documento (codigo);

CREATE TABLE certificaciones_dim_factoremision (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	temporada VARCHAR(10) NOT NULL, 
	concepto_id INTEGER NOT NULL, 
	factor_kgco2e FLOAT NOT NULL, 
	fuente VARCHAR(250), 
	PRIMARY KEY (id), 
	FOREIGN KEY(concepto_id) REFERENCES certificaciones_dim_conceptoambiental (id)
);

CREATE TABLE certificaciones_dim_limiteparametro (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tipo_analisis_id INTEGER NOT NULL, 
	parametro VARCHAR(120) NOT NULL, 
	unidad_medida VARCHAR(30), 
	minimo FLOAT, 
	maximo FLOAT, 
	norma VARCHAR(120), 
	PRIMARY KEY (id), 
	FOREIGN KEY(tipo_analisis_id) REFERENCES certificaciones_dim_tipoanalisis (id)
);

CREATE TABLE certificaciones_dim_plantillaregistro (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	codigo VARCHAR(40), 
	version VARCHAR(10) NOT NULL, 
	formato JSON NOT NULL, 
	word_clave VARCHAR(400), 
	nombre VARCHAR(200) NOT NULL, 
	descripcion TEXT, 
	ambito VARCHAR(10) NOT NULL, 
	campos JSON NOT NULL, 
	activa BOOL NOT NULL, 
	creada_por_id VARCHAR(45) NOT NULL, 
	creada_en DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (codigo), 
	FOREIGN KEY(creada_por_id) REFERENCES general_dim_usuario (id)
);

CREATE TABLE certificaciones_dim_versionnorma (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	protocolo_id INTEGER NOT NULL, 
	nombre VARCHAR(60) NOT NULL, 
	vigente BOOL NOT NULL, 
	cargada_en DATETIME, 
	archivo VARCHAR(250), 
	secciones JSON, 
	PRIMARY KEY (id), 
	UNIQUE (protocolo_id, nombre), 
	FOREIGN KEY(protocolo_id) REFERENCES certificaciones_dim_protocolo (id)
);

CREATE TABLE certificaciones_fact_bitacora (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	usuario_id VARCHAR(45), 
	fecha_hora DATETIME NOT NULL, 
	accion VARCHAR(40) NOT NULL, 
	entidad VARCHAR(40) NOT NULL, 
	entidad_id INTEGER, 
	detalle JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(usuario_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_bitacora_fecha_hora ON certificaciones_fact_bitacora (fecha_hora);

CREATE TABLE certificaciones_dim_area (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	sucursal_id INTEGER NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id)
);

CREATE INDEX ix_certificaciones_dim_area_sucursal_id ON certificaciones_dim_area (sucursal_id);

CREATE TABLE certificaciones_dim_fuenteagua (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	nombre VARCHAR(120) NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id)
);

CREATE INDEX ix_certificaciones_dim_fuenteagua_sucursal_id ON certificaciones_dim_fuenteagua (sucursal_id);

CREATE TABLE certificaciones_dim_requisito (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	version_id INTEGER NOT NULL, 
	codigo VARCHAR(40) NOT NULL, 
	seccion VARCHAR(40) NOT NULL, 
	seccion_titulo VARCHAR(300), 
	texto TEXT NOT NULL, 
	nivel VARCHAR(30), 
	orden INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (version_id, codigo), 
	FOREIGN KEY(version_id) REFERENCES certificaciones_dim_versionnorma (id)
);

CREATE TABLE certificaciones_fact_auditoria (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	version_id INTEGER NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	titulo VARCHAR(250), 
	fecha DATE NOT NULL, 
	fecha_fin DATE, 
	auditor VARCHAR(120), 
	secciones JSON NOT NULL, 
	estado VARCHAR(20) NOT NULL, 
	origen VARCHAR(20) NOT NULL, 
	archivo_origen VARCHAR(250), 
	advertencias JSON, 
	emitida_en DATETIME, 
	emitida_por_id VARCHAR(45), 
	PRIMARY KEY (id), 
	FOREIGN KEY(version_id) REFERENCES certificaciones_dim_versionnorma (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	FOREIGN KEY(emitida_por_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_auditoria_sucursal_id ON certificaciones_fact_auditoria (sucursal_id);

CREATE TABLE certificaciones_fact_capacitacion (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	sucursal_id INTEGER NOT NULL, 
	tema VARCHAR(250) NOT NULL, 
	fecha DATE NOT NULL, 
	relator VARCHAR(120), 
	asistentes JSON, 
	vigente_hasta DATE, 
	documento_id INTEGER, 
	creado_por_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	FOREIGN KEY(documento_id) REFERENCES certificaciones_dim_documento (id), 
	FOREIGN KEY(creado_por_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_capacitacion_sucursal_id ON certificaciones_fact_capacitacion (sucursal_id);

CREATE TABLE certificaciones_fact_documentoversion (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	documento_id INTEGER NOT NULL, 
	numero INTEGER NOT NULL, 
	archivo_key VARCHAR(400), 
	nombre_archivo VARCHAR(250), 
	tipo_contenido VARCHAR(100), 
	version_texto VARCHAR(20), 
	fecha_emision DATE, 
	fecha_vencimiento DATE, 
	estado VARCHAR(20) NOT NULL, 
	observacion TEXT, 
	subido_por_id VARCHAR(45) NOT NULL, 
	subido_en DATETIME NOT NULL, 
	revisado_por_id VARCHAR(45), 
	revisado_en DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (documento_id, numero), 
	FOREIGN KEY(documento_id) REFERENCES certificaciones_dim_documento (id), 
	FOREIGN KEY(subido_por_id) REFERENCES general_dim_usuario (id), 
	FOREIGN KEY(revisado_por_id) REFERENCES general_dim_usuario (id)
);

CREATE TABLE certificaciones_fact_registro (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	plantilla_id INTEGER NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	titulo VARCHAR(250) NOT NULL, 
	codigo VARCHAR(40), 
	version VARCHAR(10), 
	formato JSON NOT NULL, 
	word_clave VARCHAR(400), 
	campos JSON NOT NULL, 
	valores JSON NOT NULL, 
	responsable_id VARCHAR(45), 
	revision_campo_en DATETIME, 
	estado VARCHAR(20) NOT NULL, 
	observacion TEXT, 
	creado_por_id VARCHAR(45) NOT NULL, 
	creado_en DATETIME NOT NULL, 
	actualizado_en DATETIME, 
	actualizado_por_id VARCHAR(45), 
	enviado_en DATETIME, 
	aprobado_por_id VARCHAR(45), 
	aprobado_en DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(plantilla_id) REFERENCES certificaciones_dim_plantillaregistro (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	FOREIGN KEY(responsable_id) REFERENCES general_dim_usuario (id), 
	FOREIGN KEY(creado_por_id) REFERENCES general_dim_usuario (id), 
	FOREIGN KEY(actualizado_por_id) REFERENCES general_dim_usuario (id), 
	FOREIGN KEY(aprobado_por_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_registro_sucursal_id ON certificaciones_fact_registro (sucursal_id);

CREATE TABLE certificaciones_fact_registroambiental (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	sucursal_id INTEGER NOT NULL, 
	concepto_id INTEGER NOT NULL, 
	fecha DATE NOT NULL, 
	cantidad FLOAT NOT NULL, 
	creado_por_id VARCHAR(45) NOT NULL, 
	creado_en DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	FOREIGN KEY(concepto_id) REFERENCES certificaciones_dim_conceptoambiental (id), 
	FOREIGN KEY(creado_por_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_registroambiental_sucursal_id ON certificaciones_fact_registroambiental (sucursal_id);

CREATE INDEX ix_certificaciones_fact_registroambiental_fecha ON certificaciones_fact_registroambiental (fecha);

CREATE TABLE certificaciones_pivot_sucursal_protocolo (
	sucursal_id INTEGER NOT NULL, 
	protocolo_id INTEGER NOT NULL, 
	PRIMARY KEY (sucursal_id, protocolo_id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	FOREIGN KEY(protocolo_id) REFERENCES certificaciones_dim_protocolo (id)
);

CREATE TABLE certificaciones_fact_analisis (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tipo_analisis_id INTEGER NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	fuente_agua_id INTEGER, 
	especie_id INTEGER, 
	punto VARCHAR(120), 
	fecha_muestreo DATE NOT NULL, 
	laboratorio VARCHAR(120), 
	archivo_key VARCHAR(400), 
	nombre_archivo VARCHAR(250), 
	creado_por_id VARCHAR(45) NOT NULL, 
	creado_en DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(tipo_analisis_id) REFERENCES certificaciones_dim_tipoanalisis (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	FOREIGN KEY(fuente_agua_id) REFERENCES certificaciones_dim_fuenteagua (id), 
	FOREIGN KEY(especie_id) REFERENCES certificaciones_dim_especie (id), 
	FOREIGN KEY(creado_por_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_analisis_sucursal_id ON certificaciones_fact_analisis (sucursal_id);

CREATE TABLE certificaciones_fact_certificacion (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	protocolo_id INTEGER NOT NULL, 
	empresa_id INTEGER NOT NULL, 
	entidad_certificadora VARCHAR(120), 
	fecha_auditoria DATE, 
	resultado VARCHAR(120), 
	vigente_hasta DATE, 
	documento_version_id INTEGER, 
	numero VARCHAR(40), 
	norma_version VARCHAR(40), 
	vigente_desde DATE, 
	productos JSON, 
	sucursal_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(protocolo_id) REFERENCES certificaciones_dim_protocolo (id), 
	FOREIGN KEY(empresa_id) REFERENCES general_dim_empresa (id), 
	UNIQUE (documento_version_id), 
	FOREIGN KEY(documento_version_id) REFERENCES certificaciones_fact_documentoversion (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id)
);

CREATE TABLE certificaciones_fact_respuesta (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	auditoria_id INTEGER NOT NULL, 
	requisito_id INTEGER NOT NULL, 
	resultado VARCHAR(5), 
	comentario TEXT, 
	area_id INTEGER, 
	advertencia TEXT, 
	PRIMARY KEY (id), 
	UNIQUE (auditoria_id, requisito_id), 
	FOREIGN KEY(auditoria_id) REFERENCES certificaciones_fact_auditoria (id), 
	FOREIGN KEY(requisito_id) REFERENCES certificaciones_dim_requisito (id), 
	FOREIGN KEY(area_id) REFERENCES certificaciones_dim_area (id)
);

CREATE TABLE certificaciones_fact_analisisresultado (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	analisis_id INTEGER NOT NULL, 
	parametro VARCHAR(120) NOT NULL, 
	valor FLOAT, 
	valor_texto VARCHAR(60), 
	unidad_medida VARCHAR(30), 
	limite_min FLOAT, 
	limite_max FLOAT, 
	cumple BOOL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(analisis_id) REFERENCES certificaciones_fact_analisis (id)
);

CREATE TABLE certificaciones_fact_noconformidad (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	auditoria_id INTEGER NOT NULL, 
	respuesta_id INTEGER, 
	requisito_id INTEGER NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	area_id INTEGER, 
	descripcion TEXT NOT NULL, 
	tipo VARCHAR(20), 
	clasificacion VARCHAR(10), 
	responsable_id VARCHAR(45), 
	plazo DATE, 
	estado VARCHAR(20) NOT NULL, 
	reincidente_de_id INTEGER, 
	creada_en DATETIME NOT NULL, 
	fecha_deteccion DATE NOT NULL, 
	cerrada_por_id VARCHAR(45), 
	cerrada_en DATETIME, 
	causa_raiz JSON, 
	accion_correctiva TEXT, 
	accion_preventiva TEXT, 
	plan_por_id VARCHAR(45), 
	plan_en DATETIME, 
	plan_enviado_en DATETIME, 
	revisiones JSON, 
	reincidencias INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(auditoria_id) REFERENCES certificaciones_fact_auditoria (id), 
	FOREIGN KEY(respuesta_id) REFERENCES certificaciones_fact_respuesta (id), 
	FOREIGN KEY(requisito_id) REFERENCES certificaciones_dim_requisito (id), 
	FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	FOREIGN KEY(area_id) REFERENCES certificaciones_dim_area (id), 
	FOREIGN KEY(responsable_id) REFERENCES general_dim_usuario (id), 
	FOREIGN KEY(reincidente_de_id) REFERENCES certificaciones_fact_noconformidad (id), 
	FOREIGN KEY(cerrada_por_id) REFERENCES general_dim_usuario (id), 
	FOREIGN KEY(plan_por_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_noconformidad_sucursal_id ON certificaciones_fact_noconformidad (sucursal_id);

CREATE TABLE certificaciones_fact_accioncorrectiva (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	no_conformidad_id INTEGER NOT NULL, 
	descripcion TEXT NOT NULL, 
	archivo_key VARCHAR(400), 
	nombre_archivo VARCHAR(250), 
	creada_por_id VARCHAR(45) NOT NULL, 
	creada_en DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(no_conformidad_id) REFERENCES certificaciones_fact_noconformidad (id), 
	FOREIGN KEY(creada_por_id) REFERENCES general_dim_usuario (id)
);

-- Vistas de Certificaciones (MySQL). Se aplican después de las tablas; leen general_dim_sucursal y general_dim_temporada.

CREATE OR REPLACE VIEW certificaciones_vw_temporada AS
SELECT t.id AS temporada_id, t.temporada, t.id_empresa, t.fechainicio_produccion AS inicio, t.fechatermino_produccion AS fin
FROM general_dim_temporada t
WHERE t.fechainicio_produccion >= '2024-01-01' AND t.fechatermino_produccion IS NOT NULL;

CREATE OR REPLACE VIEW certificaciones_vw_vencimientos AS
SELECT d.id AS documento_id, d.titulo, d.empresa_id, d.seccion, v.id AS version_id, v.fecha_vencimiento,
       DATEDIFF(v.fecha_vencimiento, CURDATE()) AS dias_para_vencer
FROM certificaciones_dim_documento d
JOIN certificaciones_fact_documentoversion v ON v.documento_id = d.id
WHERE v.fecha_vencimiento IS NOT NULL
  AND v.numero = (SELECT MAX(v2.numero) FROM certificaciones_fact_documentoversion v2 WHERE v2.documento_id = d.id);

CREATE OR REPLACE VIEW certificaciones_vw_huellatemporada AS
SELECT r.sucursal_id, t.temporada_id, t.temporada, c.id AS concepto_id, c.nombre AS concepto, c.categoria, c.unidad_medida,
       SUM(r.cantidad) AS cantidad, SUM(r.cantidad * COALESCE(f.factor_kgco2e, 0)) AS kg_co2e
FROM certificaciones_fact_registroambiental r
JOIN general_dim_sucursal s ON s.id = r.sucursal_id
JOIN certificaciones_vw_temporada t ON t.id_empresa = s.id_empresa AND r.fecha BETWEEN t.inicio AND t.fin
JOIN certificaciones_dim_conceptoambiental c ON c.id = r.concepto_id
LEFT JOIN certificaciones_dim_factoremision f ON f.concepto_id = c.id AND f.temporada = t.temporada
GROUP BY r.sucursal_id, t.temporada_id, t.temporada, c.id, c.nombre, c.categoria, c.unidad_medida;

CREATE OR REPLACE VIEW certificaciones_vw_analisistemporada AS
SELECT a.sucursal_id, t.temporada_id, t.temporada, ta.id AS tipo_analisis_id, ta.nombre AS tipo_analisis,
       COUNT(DISTINCT a.id) AS analisis, COUNT(r.id) AS parametros,
       SUM(CASE WHEN r.cumple = 0 THEN 1 ELSE 0 END) AS fuera_de_norma
FROM certificaciones_fact_analisis a
JOIN general_dim_sucursal s ON s.id = a.sucursal_id
JOIN certificaciones_vw_temporada t ON t.id_empresa = s.id_empresa AND a.fecha_muestreo BETWEEN t.inicio AND t.fin
JOIN certificaciones_dim_tipoanalisis ta ON ta.id = a.tipo_analisis_id
LEFT JOIN certificaciones_fact_analisisresultado r ON r.analisis_id = a.id
GROUP BY a.sucursal_id, t.temporada_id, t.temporada, ta.id, ta.nombre;

CREATE OR REPLACE VIEW certificaciones_vw_ncestado AS
SELECT n.id AS no_conformidad_id, n.sucursal_id, p.id AS protocolo_id, p.nombre AS protocolo,
       t.temporada_id, t.temporada, n.estado, n.clasificacion, n.plazo,
       CASE WHEN n.estado <> 'cerrada' AND n.plazo < CURDATE() THEN 1 ELSE 0 END AS vencida,
       CASE WHEN n.reincidente_de_id IS NOT NULL THEN 1 ELSE 0 END AS reincidente
FROM certificaciones_fact_noconformidad n
JOIN certificaciones_fact_auditoria au ON au.id = n.auditoria_id
JOIN certificaciones_dim_versionnorma vn ON vn.id = au.version_id
JOIN certificaciones_dim_protocolo p ON p.id = vn.protocolo_id
LEFT JOIN general_dim_sucursal s ON s.id = n.sucursal_id
LEFT JOIN certificaciones_vw_temporada t ON t.id_empresa = s.id_empresa AND n.fecha_deteccion BETWEEN t.inicio AND t.fin;

CREATE OR REPLACE VIEW certificaciones_vw_tablero AS
SELECT s.id AS sucursal_id, s.nombre AS sucursal, s.id_empresa, s.id_sucursaltipo,
       (SELECT COUNT(*) FROM certificaciones_fact_registro r WHERE r.sucursal_id = s.id AND r.estado = 'en_revision') AS registros_por_revisar,
       (SELECT COUNT(*) FROM certificaciones_fact_noconformidad n WHERE n.sucursal_id = s.id AND n.estado <> 'cerrada') AS nc_abiertas,
       (SELECT COUNT(*) FROM certificaciones_fact_noconformidad n WHERE n.sucursal_id = s.id AND n.estado <> 'cerrada'
          AND n.plazo < CURDATE()) AS nc_vencidas,
       (SELECT COUNT(*) FROM certificaciones_fact_certificacion c
          WHERE (c.sucursal_id = s.id OR (c.sucursal_id IS NULL AND c.empresa_id = s.id_empresa))
          AND c.vigente_hasta BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 60 DAY)) AS certificados_por_vencer
FROM general_dim_sucursal s
WHERE EXISTS (SELECT 1 FROM certificaciones_pivot_sucursal_protocolo sp WHERE sp.sucursal_id = s.id);
