-- Esquema Certificaciones (MySQL). Generado desde utils/modelos.py
-- Requiere las tablas compartidas general_empresa/sucursal/temporada/usuario ya existentes.

CREATE TABLE certificaciones_dim_asoex (
	id VARCHAR(45) NOT NULL, 
	nombre_archivo VARCHAR(250) NOT NULL, 
	archivo_key VARCHAR(200), 
	fecha DATE, 
	resumen JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	PRIMARY KEY (id)
);

CREATE TABLE certificaciones_dim_categoriadocumento (
	id VARCHAR(45) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	ambito VARCHAR(45) NOT NULL DEFAULT 'ambos', 
	requiere_vencimiento BOOL NOT NULL DEFAULT 0, 
	requiere_codigo BOOL NOT NULL DEFAULT 0, 
	orden INTEGER NOT NULL DEFAULT 0, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	PRIMARY KEY (id)
);

CREATE TABLE certificaciones_dim_conceptoambiental (
	id VARCHAR(45) NOT NULL, 
	codigo VARCHAR(45) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	categoria VARCHAR(45) NOT NULL, 
	unidad_medida VARCHAR(45) NOT NULL, 
	activo BOOL NOT NULL DEFAULT 1, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE certificaciones_dim_especie (
	id VARCHAR(45) NOT NULL, 
	nombre VARCHAR(45) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	PRIMARY KEY (id), 
	UNIQUE (nombre)
);

CREATE TABLE certificaciones_dim_plantillaregistro (
	id VARCHAR(45) NOT NULL, 
	codigo VARCHAR(45), 
	version VARCHAR(45) NOT NULL DEFAULT '01', 
	formato JSON NOT NULL, 
	word_clave VARCHAR(200), 
	nombre VARCHAR(120) NOT NULL, 
	descripcion TEXT, 
	ambito VARCHAR(45) NOT NULL DEFAULT 'campo', 
	campos JSON NOT NULL, 
	activa BOOL NOT NULL DEFAULT 1, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE certificaciones_dim_protocolo (
	id VARCHAR(45) NOT NULL, 
	codigo VARCHAR(45) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	ambito VARCHAR(45) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	PRIMARY KEY (id), 
	UNIQUE (codigo)
);

CREATE TABLE certificaciones_dim_tipoanalisis (
	id VARCHAR(45) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	ambito VARCHAR(45) NOT NULL, 
	usa_fuente_agua BOOL NOT NULL DEFAULT 0, 
	usa_especie BOOL NOT NULL DEFAULT 0, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	PRIMARY KEY (id)
);

CREATE TABLE certificaciones_fact_historial (
	id VARCHAR(45) NOT NULL, 
	accion VARCHAR(45) NOT NULL, 
	entidad VARCHAR(45) NOT NULL, 
	referencia VARCHAR(45), 
	detalle JSON, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	PRIMARY KEY (id)
);

CREATE INDEX ix_historial_created_at ON certificaciones_fact_historial (created_at);

CREATE TABLE certificaciones_dim_asoexlimite (
	id VARCHAR(45) NOT NULL, 
	fruta VARCHAR(60) NOT NULL, 
	sustancia VARCHAR(120) NOT NULL, 
	tipo_producto VARCHAR(45), 
	pais VARCHAR(45) NOT NULL, 
	ppm FLOAT, 
	condicion VARCHAR(45), 
	carencia_dias INTEGER, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	asoex_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_asoex_asoexlimite FOREIGN KEY(asoex_id) REFERENCES certificaciones_dim_asoex (id)
);

CREATE INDEX ix_certificaciones_dim_asoexlimite_asoex_id ON certificaciones_dim_asoexlimite (asoex_id);

CREATE TABLE certificaciones_dim_cartadestino (
	id VARCHAR(45) NOT NULL, 
	temporada VARCHAR(45), 
	destinatario VARCHAR(200), 
	fecha DATE, 
	destinos JSON NOT NULL, 
	nombre_archivo VARCHAR(250) NOT NULL, 
	archivo_key VARCHAR(200), 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	empresa_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_empresa_cartadestino FOREIGN KEY(empresa_id) REFERENCES general_dim_empresa (id)
);

CREATE TABLE certificaciones_dim_documento (
	id VARCHAR(45) NOT NULL, 
	seccion VARCHAR(45) NOT NULL DEFAULT 'empresarial', 
	titulo VARCHAR(250) NOT NULL, 
	codigo VARCHAR(45), 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	categoriadocumento_id VARCHAR(45) NOT NULL, 
	empresa_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_categoriadocumento_documento FOREIGN KEY(categoriadocumento_id) REFERENCES certificaciones_dim_categoriadocumento (id), 
	CONSTRAINT fk_empresa_documento FOREIGN KEY(empresa_id) REFERENCES general_dim_empresa (id)
);

CREATE INDEX ix_certificaciones_dim_documento_codigo ON certificaciones_dim_documento (codigo);

CREATE TABLE certificaciones_dim_factoremision (
	id VARCHAR(45) NOT NULL, 
	temporada VARCHAR(45) NOT NULL, 
	factor FLOAT NOT NULL, 
	fuente VARCHAR(250), 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	conceptoambiental_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_conceptoambiental_factoremision FOREIGN KEY(conceptoambiental_id) REFERENCES certificaciones_dim_conceptoambiental (id)
);

CREATE TABLE certificaciones_dim_limiteparametro (
	id VARCHAR(45) NOT NULL, 
	parametro VARCHAR(120) NOT NULL, 
	unidad_medida VARCHAR(45), 
	minimo FLOAT, 
	maximo FLOAT, 
	norma VARCHAR(120), 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	tipoanalisis_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_tipoanalisis_limiteparametro FOREIGN KEY(tipoanalisis_id) REFERENCES certificaciones_dim_tipoanalisis (id)
);

CREATE TABLE certificaciones_dim_versionnorma (
	id VARCHAR(45) NOT NULL, 
	nombre VARCHAR(60) NOT NULL, 
	vigente BOOL NOT NULL DEFAULT 1, 
	archivo VARCHAR(250), 
	secciones JSON, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	protocolo_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_versionnorma_protocolo_nombre UNIQUE (protocolo_id, nombre), 
	CONSTRAINT fk_protocolo_versionnorma FOREIGN KEY(protocolo_id) REFERENCES certificaciones_dim_protocolo (id)
);

CREATE TABLE certificaciones_fact_auditoriaexterna (
	id VARCHAR(45) NOT NULL, 
	tipo_informe VARCHAR(45) NOT NULL DEFAULT 'final', 
	numero VARCHAR(45), 
	titulo VARCHAR(250) NOT NULL, 
	entidad VARCHAR(120), 
	auditor VARCHAR(120), 
	fecha DATE, 
	sucursales_auditadas JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	protocolo_id VARCHAR(45), 
	empresa_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_protocolo_auditoriaexterna FOREIGN KEY(protocolo_id) REFERENCES certificaciones_dim_protocolo (id), 
	CONSTRAINT fk_empresa_auditoriaexterna FOREIGN KEY(empresa_id) REFERENCES general_dim_empresa (id)
);

CREATE INDEX ix_certificaciones_fact_auditoriaexterna_numero ON certificaciones_fact_auditoriaexterna (numero);

CREATE TABLE certificaciones_dim_area (
	id VARCHAR(45) NOT NULL, 
	nombre VARCHAR(45) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	sucursal_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_sucursal_area FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id)
);

CREATE INDEX ix_certificaciones_dim_area_sucursal_id ON certificaciones_dim_area (sucursal_id);

CREATE TABLE certificaciones_dim_fuenteagua (
	id VARCHAR(45) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	sucursal_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_sucursal_fuenteagua FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id)
);

CREATE INDEX ix_certificaciones_dim_fuenteagua_sucursal_id ON certificaciones_dim_fuenteagua (sucursal_id);

CREATE TABLE certificaciones_dim_requisito (
	id VARCHAR(45) NOT NULL, 
	codigo VARCHAR(45) NOT NULL, 
	seccion VARCHAR(45) NOT NULL, 
	seccion_titulo VARCHAR(250), 
	texto TEXT NOT NULL, 
	nivel VARCHAR(45), 
	orden INTEGER NOT NULL DEFAULT 0, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	versionnorma_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_requisito_version_codigo UNIQUE (versionnorma_id, codigo), 
	CONSTRAINT fk_versionnorma_requisito FOREIGN KEY(versionnorma_id) REFERENCES certificaciones_dim_versionnorma (id)
);

CREATE TABLE certificaciones_fact_auditoria (
	id VARCHAR(45) NOT NULL, 
	titulo VARCHAR(120), 
	fecha DATE NOT NULL, 
	fecha_fin DATE, 
	auditor VARCHAR(120), 
	secciones JSON NOT NULL, 
	estado VARCHAR(45) NOT NULL DEFAULT 'planificada', 
	origen VARCHAR(45) NOT NULL DEFAULT 'app', 
	archivo_origen VARCHAR(250), 
	advertencias JSON, 
	emitida_en DATETIME, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	versionnorma_id VARCHAR(45) NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	usuario_emisor_id VARCHAR(45), 
	PRIMARY KEY (id), 
	CONSTRAINT fk_versionnorma_auditoria FOREIGN KEY(versionnorma_id) REFERENCES certificaciones_dim_versionnorma (id), 
	CONSTRAINT fk_sucursal_auditoria FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	CONSTRAINT fk_usuario_emisor_auditoria FOREIGN KEY(usuario_emisor_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_auditoria_sucursal_id ON certificaciones_fact_auditoria (sucursal_id);

CREATE TABLE certificaciones_fact_auditoriaexternaversion (
	id VARCHAR(45) NOT NULL, 
	numero INTEGER NOT NULL, 
	archivo_key VARCHAR(200) NOT NULL, 
	nombre_archivo VARCHAR(250) NOT NULL, 
	resumen JSON NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	auditoriaexterna_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_auditoriaexternaversion_numero UNIQUE (auditoriaexterna_id, numero), 
	CONSTRAINT fk_auditoriaexterna_auditoriaexternaversion FOREIGN KEY(auditoriaexterna_id) REFERENCES certificaciones_fact_auditoriaexterna (id)
);

CREATE TABLE certificaciones_fact_capacitacion (
	id VARCHAR(45) NOT NULL, 
	tema VARCHAR(120) NOT NULL, 
	fecha DATE NOT NULL, 
	relator VARCHAR(120), 
	asistentes JSON, 
	vigente_hasta DATE, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	sucursal_id INTEGER NOT NULL, 
	documento_id VARCHAR(45), 
	PRIMARY KEY (id), 
	CONSTRAINT fk_sucursal_capacitacion FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	CONSTRAINT fk_documento_capacitacion FOREIGN KEY(documento_id) REFERENCES certificaciones_dim_documento (id)
);

CREATE INDEX ix_certificaciones_fact_capacitacion_sucursal_id ON certificaciones_fact_capacitacion (sucursal_id);

CREATE TABLE certificaciones_fact_documentoversion (
	id VARCHAR(45) NOT NULL, 
	numero INTEGER NOT NULL, 
	archivo_key VARCHAR(200), 
	nombre_archivo VARCHAR(250), 
	tipo_contenido VARCHAR(100), 
	version_texto VARCHAR(45), 
	fecha_emision DATE, 
	fecha_vencimiento DATE, 
	estado VARCHAR(45) NOT NULL DEFAULT 'pendiente', 
	observacion TEXT, 
	revisado_en DATETIME, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	documento_id VARCHAR(45) NOT NULL, 
	usuario_revisor_id VARCHAR(45), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_documentoversion_documento_numero UNIQUE (documento_id, numero), 
	CONSTRAINT fk_documento_documentoversion FOREIGN KEY(documento_id) REFERENCES certificaciones_dim_documento (id), 
	CONSTRAINT fk_usuario_revisor_documentoversion FOREIGN KEY(usuario_revisor_id) REFERENCES general_dim_usuario (id)
);

CREATE TABLE certificaciones_fact_registro (
	id VARCHAR(45) NOT NULL, 
	titulo VARCHAR(250) NOT NULL, 
	codigo VARCHAR(45), 
	version VARCHAR(45), 
	formato JSON NOT NULL, 
	word_clave VARCHAR(200), 
	campos JSON NOT NULL, 
	valores JSON NOT NULL, 
	revision_campo DATETIME, 
	estado VARCHAR(45) NOT NULL DEFAULT 'borrador', 
	observacion TEXT, 
	enviado DATETIME, 
	aprobado DATETIME, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	plantillaregistro_id VARCHAR(45) NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	usuario_responsable_id VARCHAR(45), 
	usuario_aprobador_id VARCHAR(45), 
	PRIMARY KEY (id), 
	CONSTRAINT fk_plantillaregistro_registro FOREIGN KEY(plantillaregistro_id) REFERENCES certificaciones_dim_plantillaregistro (id), 
	CONSTRAINT fk_sucursal_registro FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	CONSTRAINT fk_usuario_responsable_registro FOREIGN KEY(usuario_responsable_id) REFERENCES general_dim_usuario (id), 
	CONSTRAINT fk_usuario_aprobador_registro FOREIGN KEY(usuario_aprobador_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_registro_sucursal_id ON certificaciones_fact_registro (sucursal_id);

CREATE TABLE certificaciones_fact_registroambiental (
	id VARCHAR(45) NOT NULL, 
	fecha DATE NOT NULL, 
	cantidad FLOAT NOT NULL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	sucursal_id INTEGER NOT NULL, 
	conceptoambiental_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_sucursal_registroambiental FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	CONSTRAINT fk_conceptoambiental_registroambiental FOREIGN KEY(conceptoambiental_id) REFERENCES certificaciones_dim_conceptoambiental (id)
);

CREATE INDEX ix_certificaciones_fact_registroambiental_sucursal_id ON certificaciones_fact_registroambiental (sucursal_id);

CREATE INDEX ix_certificaciones_fact_registroambiental_fecha ON certificaciones_fact_registroambiental (fecha);

CREATE TABLE certificaciones_pivot_sucursal_protocolo (
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	sucursal_id INTEGER NOT NULL, 
	protocolo_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (sucursal_id, protocolo_id), 
	CONSTRAINT fk_sucursal_sucursal_protocolo FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	CONSTRAINT fk_protocolo_sucursal_protocolo FOREIGN KEY(protocolo_id) REFERENCES certificaciones_dim_protocolo (id)
);

CREATE TABLE certificaciones_fact_analisis (
	id VARCHAR(45) NOT NULL, 
	punto VARCHAR(120), 
	fecha_muestreo DATE NOT NULL, 
	laboratorio VARCHAR(120), 
	archivo_key VARCHAR(200), 
	nombre_archivo VARCHAR(250), 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	tipoanalisis_id VARCHAR(45) NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	fuenteagua_id VARCHAR(45), 
	especie_id VARCHAR(45), 
	PRIMARY KEY (id), 
	CONSTRAINT fk_tipoanalisis_analisis FOREIGN KEY(tipoanalisis_id) REFERENCES certificaciones_dim_tipoanalisis (id), 
	CONSTRAINT fk_sucursal_analisis FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	CONSTRAINT fk_fuenteagua_analisis FOREIGN KEY(fuenteagua_id) REFERENCES certificaciones_dim_fuenteagua (id), 
	CONSTRAINT fk_especie_analisis FOREIGN KEY(especie_id) REFERENCES certificaciones_dim_especie (id)
);

CREATE INDEX ix_certificaciones_fact_analisis_sucursal_id ON certificaciones_fact_analisis (sucursal_id);

CREATE TABLE certificaciones_fact_certificacion (
	id VARCHAR(45) NOT NULL, 
	entidad_certificadora VARCHAR(120), 
	fecha_auditoria DATE, 
	resultado VARCHAR(120), 
	vigente_hasta DATE, 
	numero VARCHAR(45), 
	norma_version VARCHAR(45), 
	vigente_desde DATE, 
	productos JSON, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	protocolo_id VARCHAR(45) NOT NULL, 
	empresa_id INTEGER NOT NULL, 
	documentoversion_id VARCHAR(45), 
	sucursal_id INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_protocolo_certificacion FOREIGN KEY(protocolo_id) REFERENCES certificaciones_dim_protocolo (id), 
	CONSTRAINT fk_empresa_certificacion FOREIGN KEY(empresa_id) REFERENCES general_dim_empresa (id), 
	UNIQUE (documentoversion_id), 
	CONSTRAINT fk_documentoversion_certificacion FOREIGN KEY(documentoversion_id) REFERENCES certificaciones_fact_documentoversion (id), 
	CONSTRAINT fk_sucursal_certificacion FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id)
);

CREATE TABLE certificaciones_fact_respuesta (
	id VARCHAR(45) NOT NULL, 
	resultado VARCHAR(45), 
	comentario TEXT, 
	advertencia TEXT, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	auditoria_id VARCHAR(45) NOT NULL, 
	requisito_id VARCHAR(45) NOT NULL, 
	area_id VARCHAR(45), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_respuesta_auditoria_requisito UNIQUE (auditoria_id, requisito_id), 
	CONSTRAINT fk_auditoria_respuesta FOREIGN KEY(auditoria_id) REFERENCES certificaciones_fact_auditoria (id), 
	CONSTRAINT fk_requisito_respuesta FOREIGN KEY(requisito_id) REFERENCES certificaciones_dim_requisito (id), 
	CONSTRAINT fk_area_respuesta FOREIGN KEY(area_id) REFERENCES certificaciones_dim_area (id)
);

CREATE TABLE certificaciones_fact_analisisresultado (
	id VARCHAR(45) NOT NULL, 
	parametro VARCHAR(120) NOT NULL, 
	valor FLOAT, 
	valor_texto VARCHAR(60), 
	unidad_medida VARCHAR(45), 
	limite_min FLOAT, 
	limite_max FLOAT, 
	cumple BOOL, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	analisis_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_analisis_analisisresultado FOREIGN KEY(analisis_id) REFERENCES certificaciones_fact_analisis (id)
);

CREATE TABLE certificaciones_fact_noconformidad (
	id VARCHAR(45) NOT NULL, 
	descripcion TEXT NOT NULL, 
	tipo VARCHAR(45), 
	clasificacion VARCHAR(45), 
	plazo DATE, 
	estado VARCHAR(45) NOT NULL DEFAULT 'abierta', 
	fecha_deteccion DATE NOT NULL, 
	cerrada_en DATETIME, 
	causa_raiz JSON, 
	accion_correctiva TEXT, 
	accion_preventiva TEXT, 
	plan_en DATETIME, 
	plan_enviado_en DATETIME, 
	revisiones JSON, 
	reincidencias INTEGER NOT NULL DEFAULT 0, 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	auditoria_id VARCHAR(45) NOT NULL, 
	respuesta_id VARCHAR(45), 
	requisito_id VARCHAR(45) NOT NULL, 
	sucursal_id INTEGER NOT NULL, 
	area_id VARCHAR(45), 
	usuario_responsable_id VARCHAR(45), 
	noconformidad_original_id VARCHAR(45), 
	usuario_cierre_id VARCHAR(45), 
	usuario_plan_id VARCHAR(45), 
	PRIMARY KEY (id), 
	CONSTRAINT fk_auditoria_noconformidad FOREIGN KEY(auditoria_id) REFERENCES certificaciones_fact_auditoria (id), 
	CONSTRAINT fk_respuesta_noconformidad FOREIGN KEY(respuesta_id) REFERENCES certificaciones_fact_respuesta (id), 
	CONSTRAINT fk_requisito_noconformidad FOREIGN KEY(requisito_id) REFERENCES certificaciones_dim_requisito (id), 
	CONSTRAINT fk_sucursal_noconformidad FOREIGN KEY(sucursal_id) REFERENCES general_dim_sucursal (id), 
	CONSTRAINT fk_area_noconformidad FOREIGN KEY(area_id) REFERENCES certificaciones_dim_area (id), 
	CONSTRAINT fk_usuario_responsable_noconformidad FOREIGN KEY(usuario_responsable_id) REFERENCES general_dim_usuario (id), 
	CONSTRAINT fk_noconformidad_original_noconformidad FOREIGN KEY(noconformidad_original_id) REFERENCES certificaciones_fact_noconformidad (id), 
	CONSTRAINT fk_usuario_cierre_noconformidad FOREIGN KEY(usuario_cierre_id) REFERENCES general_dim_usuario (id), 
	CONSTRAINT fk_usuario_plan_noconformidad FOREIGN KEY(usuario_plan_id) REFERENCES general_dim_usuario (id)
);

CREATE INDEX ix_certificaciones_fact_noconformidad_sucursal_id ON certificaciones_fact_noconformidad (sucursal_id);

CREATE TABLE certificaciones_fact_accioncorrectiva (
	id VARCHAR(45) NOT NULL, 
	descripcion TEXT NOT NULL, 
	archivo_key VARCHAR(200), 
	nombre_archivo VARCHAR(250), 
	created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
	created_by CHAR(36), 
	updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP, 
	updated_by CHAR(36), 
	noconformidad_id VARCHAR(45) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_noconformidad_accioncorrectiva FOREIGN KEY(noconformidad_id) REFERENCES certificaciones_fact_noconformidad (id)
);

-- Vistas de Certificaciones (MySQL), nomenclatura v_<aplicación>_<qué hace>. Se aplican después de las tablas y leen general_dim_sucursal y general_dim_temporada.

CREATE OR REPLACE VIEW v_certificaciones_temporada AS
SELECT t.id AS temporada_id, t.temporada, t.id_empresa, t.fechainicio_produccion AS inicio, t.fechatermino_produccion AS fin
FROM general_dim_temporada t
WHERE t.fechainicio_produccion >= '2024-01-01' AND t.fechatermino_produccion IS NOT NULL;

CREATE OR REPLACE VIEW v_certificaciones_vencimientos AS
SELECT d.id AS documento_id, d.titulo, d.empresa_id, d.seccion, v.id AS documentoversion_id, v.fecha_vencimiento,
       DATEDIFF(v.fecha_vencimiento, CURDATE()) AS dias_para_vencer
FROM certificaciones_dim_documento d
JOIN certificaciones_fact_documentoversion v ON v.documento_id = d.id
WHERE v.fecha_vencimiento IS NOT NULL
  AND v.numero = (SELECT MAX(v2.numero) FROM certificaciones_fact_documentoversion v2 WHERE v2.documento_id = d.id);

CREATE OR REPLACE VIEW v_certificaciones_huellatemporada AS
SELECT r.sucursal_id, t.temporada_id, t.temporada, c.id AS conceptoambiental_id, c.nombre AS concepto, c.categoria, c.unidad_medida,
       SUM(r.cantidad) AS cantidad, SUM(r.cantidad * COALESCE(f.factor, 0)) AS kg_co2e
FROM certificaciones_fact_registroambiental r
JOIN general_dim_sucursal s ON s.id = r.sucursal_id
JOIN v_certificaciones_temporada t ON t.id_empresa = s.id_empresa AND r.fecha BETWEEN t.inicio AND t.fin
JOIN certificaciones_dim_conceptoambiental c ON c.id = r.conceptoambiental_id
LEFT JOIN certificaciones_dim_factoremision f ON f.conceptoambiental_id = c.id AND f.temporada = t.temporada
GROUP BY r.sucursal_id, t.temporada_id, t.temporada, c.id, c.nombre, c.categoria, c.unidad_medida;

CREATE OR REPLACE VIEW v_certificaciones_analisistemporada AS
SELECT a.sucursal_id, t.temporada_id, t.temporada, ta.id AS tipoanalisis_id, ta.nombre AS tipo_analisis,
       COUNT(DISTINCT a.id) AS analisis, COUNT(r.id) AS parametros,
       SUM(CASE WHEN r.cumple = 0 THEN 1 ELSE 0 END) AS fuera_de_norma
FROM certificaciones_fact_analisis a
JOIN general_dim_sucursal s ON s.id = a.sucursal_id
JOIN v_certificaciones_temporada t ON t.id_empresa = s.id_empresa AND a.fecha_muestreo BETWEEN t.inicio AND t.fin
JOIN certificaciones_dim_tipoanalisis ta ON ta.id = a.tipoanalisis_id
LEFT JOIN certificaciones_fact_analisisresultado r ON r.analisis_id = a.id
GROUP BY a.sucursal_id, t.temporada_id, t.temporada, ta.id, ta.nombre;

CREATE OR REPLACE VIEW v_certificaciones_ncestado AS
SELECT n.id AS noconformidad_id, n.sucursal_id, p.id AS protocolo_id, p.nombre AS protocolo,
       t.temporada_id, t.temporada, n.estado, n.clasificacion, n.plazo,
       CASE WHEN n.estado <> 'cerrada' AND n.plazo < CURDATE() THEN 1 ELSE 0 END AS vencida,
       CASE WHEN n.noconformidad_original_id IS NOT NULL THEN 1 ELSE 0 END AS reincidente
FROM certificaciones_fact_noconformidad n
JOIN certificaciones_fact_auditoria au ON au.id = n.auditoria_id
JOIN certificaciones_dim_versionnorma vn ON vn.id = au.versionnorma_id
JOIN certificaciones_dim_protocolo p ON p.id = vn.protocolo_id
LEFT JOIN general_dim_sucursal s ON s.id = n.sucursal_id
LEFT JOIN v_certificaciones_temporada t ON t.id_empresa = s.id_empresa AND n.fecha_deteccion BETWEEN t.inicio AND t.fin;

CREATE OR REPLACE VIEW v_certificaciones_tablero AS
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
