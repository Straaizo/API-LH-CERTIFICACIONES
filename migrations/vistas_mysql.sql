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
