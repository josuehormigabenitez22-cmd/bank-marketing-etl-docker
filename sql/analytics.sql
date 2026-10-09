-- =====================================================================
-- Consultas analíticas con nombre. src/queries.py las carga por su nombre:
--     from src.queries import get_query
--     get_query("ventas_por_mes")
-- Los parámetros usan la sintaxis de SQLAlchemy (:nombre).
-- Los importes se devuelven como float8 para que pandas los trate como números.
-- =====================================================================


-- ---------------------------------------------------------------------
--  PARTE 1 · Tienda online (schema public: clientes, productos, pedidos)
-- ---------------------------------------------------------------------

-- name: ventas_por_mes
-- Ingresos y nº de pedidos por mes (los pedidos cancelados no cuentan).
SELECT date_trunc('month', p.fecha)::date AS mes,
       COUNT(DISTINCT p.id) AS pedidos,
       SUM(d.cantidad * d.precio_unitario)::float8 AS ingresos
FROM pedidos p
JOIN detalle_pedidos d ON d.pedido_id = p.id
WHERE p.estado <> 'cancelado'
GROUP BY 1
ORDER BY 1;


-- name: gasto_acumulado_mensual
-- Ingresos mensuales y total acumulado (función de ventana SUM() OVER).
WITH mensual AS (
    SELECT date_trunc('month', p.fecha)::date AS mes,
           SUM(d.cantidad * d.precio_unitario) AS ingresos
    FROM pedidos p
    JOIN detalle_pedidos d ON d.pedido_id = p.id
    WHERE p.estado <> 'cancelado'
    GROUP BY 1
)
SELECT mes,
       ingresos::float8 AS ingresos,
       SUM(ingresos) OVER (ORDER BY mes)::float8 AS acumulado
FROM mensual
ORDER BY mes;


-- name: top_clientes
-- Clientes que más gastan, con ranking (RANK() OVER). Parámetro: :limite
WITH gasto AS (
    SELECT c.id, c.nombre, c.comunidad,
           COUNT(DISTINCT p.id) AS pedidos,
           SUM(d.cantidad * d.precio_unitario) AS gasto
    FROM clientes c
    JOIN pedidos p ON p.cliente_id = c.id
    JOIN detalle_pedidos d ON d.pedido_id  = p.id
    WHERE p.estado <> 'cancelado'
    GROUP BY c.id, c.nombre, c.comunidad
)
SELECT RANK() OVER (ORDER BY gasto DESC) AS ranking,
       nombre,
       comunidad,
       pedidos,
       gasto::float8 AS gasto
FROM gasto
ORDER BY ranking, nombre
LIMIT :limite;


-- name: ingresos_por_categoria
-- Ingresos por categoría de producto y su peso sobre el total.
SELECT pr.categoria,
       SUM(d.cantidad) AS unidades,
       SUM(d.cantidad * d.precio_unitario)::float8 AS ingresos,
       ROUND(100.0 * SUM(d.cantidad * d.precio_unitario)
             / SUM(SUM(d.cantidad * d.precio_unitario)) OVER (), 1)::float8 AS porcentaje
FROM detalle_pedidos d
JOIN pedidos p ON p.id  = d.pedido_id
JOIN productos pr ON pr.id = d.producto_id
WHERE p.estado <> 'cancelado'
GROUP BY pr.categoria
ORDER BY ingresos DESC;


-- name: clientes_sin_pedidos
-- Clientes que nunca han comprado (LEFT JOIN + IS NULL).
SELECT c.id, c.nombre, c.ciudad, c.comunidad, c.fecha_registro
FROM clientes c
LEFT JOIN pedidos p ON p.cliente_id = c.id
WHERE p.id IS NULL
ORDER BY c.id;


-- name: ticket_medio_por_comunidad
-- Ticket medio (importe medio por pedido) y nº de pedidos por comunidad autónoma.
WITH importe_pedido AS (
    SELECT p.id AS pedido_id, p.cliente_id,
           SUM(d.cantidad * d.precio_unitario) AS importe
    FROM pedidos p
    JOIN detalle_pedidos d ON d.pedido_id = p.id
    WHERE p.estado <> 'cancelado'
    GROUP BY p.id, p.cliente_id
)
SELECT c.comunidad,
       COUNT(*) AS pedidos,
       ROUND(AVG(i.importe), 2)::float8 AS ticket_medio
FROM importe_pedido i
JOIN clientes c ON c.id = i.cliente_id
GROUP BY c.comunidad
ORDER BY ticket_medio DESC;


-- ---------------------------------------------------------------------
--  PARTE 2 · Marketing bancario (schema marketing; lo carga el ETL)
-- ---------------------------------------------------------------------

-- name: marketing_resumen
-- Cifras globales de la campaña.
SELECT COUNT(*) AS contactos,
       COUNT(*) FILTER (WHERE suscrito) AS suscritos,
       ROUND(100.0 * AVG(suscrito::int), 2)::float8 AS tasa_conversion_pct,
       MIN(fecha_contacto) AS primer_contacto,
       MAX(fecha_contacto) AS ultimo_contacto
FROM marketing.contactos;


-- name: marketing_conversion_por_profesion
-- Tasa de conversión por profesión (n = contactos, para valorar la fiabilidad).
SELECT COALESCE(profesion, 'desconocida') AS profesion,
       COUNT(*) AS contactos,
       COUNT(*) FILTER (WHERE suscrito) AS suscritos,
       ROUND(100.0 * AVG(suscrito::int), 2)::float8 AS tasa_conversion_pct
FROM marketing.contactos
GROUP BY 1
ORDER BY tasa_conversion_pct DESC;


-- name: marketing_conversion_por_resultado_previo
-- ¿Influye el resultado de la campaña anterior?
SELECT COALESCE(resultado_previo, 'sin campaña previa')  AS resultado_previo,
       COUNT(*) AS contactos,
       ROUND(100.0 * AVG(suscrito::int), 2)::float8 AS tasa_conversion_pct
FROM marketing.contactos
GROUP BY 1
ORDER BY tasa_conversion_pct DESC;


-- name: marketing_conversion_por_edad
-- Tasa de conversión por tramo de edad (columna "orden" para ordenar el gráfico).
SELECT CASE WHEN edad < 25 THEN 1 WHEN edad < 35 THEN 2 WHEN edad < 45 THEN 3
            WHEN edad < 55 THEN 4 WHEN edad < 65 THEN 5 ELSE 6 END   AS orden,
       CASE WHEN edad < 25 THEN '<25'   WHEN edad < 35 THEN '25-34' WHEN edad < 45 THEN '35-44'
            WHEN edad < 55 THEN '45-54' WHEN edad < 65 THEN '55-64' ELSE '65+' END AS tramo_edad,
       COUNT(*) AS contactos,
       ROUND(100.0 * AVG(suscrito::int), 2)::float8 AS tasa_conversion_pct
FROM marketing.contactos
GROUP BY 1, 2
ORDER BY 1;


-- name: marketing_conversion_mensual
-- Evolución mensual (solo filas con fecha inferida, es decir, bank-full.csv).
SELECT date_trunc('month', fecha_contacto)::date AS mes,
       COUNT(*) AS contactos,
       ROUND(100.0 * AVG(suscrito::int), 2)::float8 AS tasa_conversion_pct
FROM marketing.contactos
WHERE fecha_contacto IS NOT NULL
GROUP BY 1
ORDER BY 1;


-- name: marketing_duracion_percentiles
-- Percentiles de la duración de la llamada según el resultado (consulta algo más pesada).
SELECT suscrito,
       COUNT(*) AS contactos,
       percentile_cont(0.25) WITHIN GROUP (ORDER BY duracion_seg)::float8 AS p25_seg,
       percentile_cont(0.50) WITHIN GROUP (ORDER BY duracion_seg)::float8 AS mediana_seg,
       percentile_cont(0.75) WITHIN GROUP (ORDER BY duracion_seg)::float8 AS p75_seg
FROM marketing.contactos
GROUP BY suscrito
ORDER BY suscrito;


-- name: marketing_conversion_cubo
-- Conversión para TODAS las combinaciones de profesión, estado civil y educación
-- (GROUP BY CUBE). Es la consulta más costosa: buen candidato para cachear en Redis.
SELECT profesion, estado_civil, educacion,
       COUNT(*) AS contactos,
       ROUND(100.0 * AVG(suscrito::int), 2)::float8 AS tasa_conversion_pct
FROM marketing.contactos
GROUP BY CUBE (profesion, estado_civil, educacion)
ORDER BY contactos DESC, profesion, estado_civil, educacion;
