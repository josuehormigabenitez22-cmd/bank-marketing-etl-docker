-- Esquema de demostración: mini tienda online (clientes, productos, pedidos)
-- Se ejecuta automáticamente la primera vez que arranca PostgreSQL.
--
-- Los datos son SINTÉTICOS y DETERMINISTAS (sin random()): cada instalación
-- obtiene exactamente las mismas filas, de modo que los tests pueden comprobarlas.
--   50 clientes · 12 productos · 100 pedidos · 200 líneas de pedido


CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    email VARCHAR(200) UNIQUE NOT NULL,
    ciudad VARCHAR(50),
    comunidad VARCHAR(50),
    fecha_registro DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS productos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    categoria VARCHAR(50)  NOT NULL,
    precio NUMERIC(10, 2) NOT NULL CHECK (precio > 0)
);

CREATE TABLE IF NOT EXISTS pedidos (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes (id),
    fecha DATE NOT NULL,
    estado VARCHAR(20) NOT NULL
               CHECK (estado IN ('pendiente', 'enviado', 'entregado', 'cancelado'))
);

CREATE TABLE IF NOT EXISTS detalle_pedidos (
    pedido_id INTEGER NOT NULL REFERENCES pedidos (id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos (id),
    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(10, 2) NOT NULL CHECK (precio_unitario > 0),
    PRIMARY KEY (pedido_id, producto_id)
);

CREATE INDEX IF NOT EXISTS idx_pedidos_cliente ON pedidos (cliente_id);
CREATE INDEX IF NOT EXISTS idx_pedidos_fecha ON pedidos (fecha);
CREATE INDEX IF NOT EXISTS idx_detalle_producto ON detalle_pedidos (producto_id);


-- Clientes (50): una ciudad por cliente, con su comunidad autónoma
INSERT INTO clientes (nombre, email, ciudad, comunidad) VALUES
('Ana García', 'ana.garcia@ejemplo.com', 'Madrid', 'Comunidad de Madrid'),
('Carlos López', 'carlos.lopez@ejemplo.com', 'Barcelona', 'Cataluña'),
('María Fernández', 'maria.fernandez@ejemplo.com', 'Valencia', 'Comunidad Valenciana'),
('Javier Martínez', 'javier.martinez@ejemplo.com', 'Sevilla', 'Andalucía'),
('Laura Sánchez', 'laura.sanchez@ejemplo.com', 'Bilbao', 'País Vasco'),
('David Rodríguez', 'david.rodriguez@ejemplo.com', 'Málaga', 'Andalucía'),
('Carmen González', 'carmen.gonzalez@ejemplo.com', 'Zaragoza', 'Aragón'),
('Pablo Ruiz', 'pablo.ruiz@ejemplo.com', 'Alicante', 'Comunidad Valenciana'),
('Lucía Díaz', 'lucia.diaz@ejemplo.com', 'Murcia', 'Región de Murcia'),
('Daniel Moreno', 'daniel.moreno@ejemplo.com', 'Palma', 'Islas Baleares'),
('Elena Muñoz', 'elena.munoz@ejemplo.com', 'Las Palmas de Gran Canaria', 'Canarias'),
('Sergio Álvarez', 'sergio.alvarez@ejemplo.com', 'Santa Cruz de Tenerife', 'Canarias'),
('Marta Romero', 'marta.romero@ejemplo.com', 'Valladolid', 'Castilla y León'),
('Alberto Alonso', 'alberto.alonso@ejemplo.com', 'Vigo', 'Galicia'),
('Paula Navarro', 'paula.navarro@ejemplo.com', 'Gijón', 'Asturias'),
('Álvaro Torres', 'alvaro.torres@ejemplo.com', 'A Coruña', 'Galicia'),
('Cristina Domínguez', 'cristina.dominguez@ejemplo.com', 'Granada', 'Andalucía'),
('Miguel Vázquez', 'miguel.vazquez@ejemplo.com', 'Córdoba', 'Andalucía'),
('Sara Ramos', 'sara.ramos@ejemplo.com', 'Toledo', 'Castilla-La Mancha'),
('Fernando Ramírez', 'fernando.ramirez@ejemplo.com', 'Salamanca', 'Castilla y León'),
('Natalia Gil', 'natalia.gil@ejemplo.com', 'Pamplona', 'Navarra'),
('Jorge Serrano', 'jorge.serrano@ejemplo.com', 'Logroño', 'La Rioja'),
('Patricia Molina', 'patricia.molina@ejemplo.com', 'Santander', 'Cantabria'),
('Rubén Suárez', 'ruben.suarez@ejemplo.com', 'Oviedo', 'Asturias'),
('Isabel Blanco', 'isabel.blanco@ejemplo.com', 'Burgos', 'Castilla y León'),
('Alejandro Iglesias', 'alejandro.iglesias@ejemplo.com', 'León', 'Castilla y León'),
('Beatriz Medina', 'beatriz.medina@ejemplo.com', 'Cádiz', 'Andalucía'),
('Óscar Castro', 'oscar.castro@ejemplo.com', 'Huelva', 'Andalucía'),
('Andrea Ortiz', 'andrea.ortiz@ejemplo.com', 'Almería', 'Andalucía'),
('Iván Rubio', 'ivan.rubio@ejemplo.com', 'Jaén', 'Andalucía'),
('Silvia Núñez', 'silvia.nunez@ejemplo.com', 'Badajoz', 'Extremadura'),
('Raúl Garrido', 'raul.garrido@ejemplo.com', 'Cáceres', 'Extremadura'),
('Teresa Santos', 'teresa.santos@ejemplo.com', 'Segovia', 'Castilla y León'),
('Manuel Cortés', 'manuel.cortes@ejemplo.com', 'Ávila', 'Castilla y León'),
('Rocío Castillo', 'rocio.castillo@ejemplo.com', 'Cuenca', 'Castilla-La Mancha'),
('Francisco Marín', 'francisco.marin@ejemplo.com', 'Albacete', 'Castilla-La Mancha'),
('Nuria Iglesias', 'nuria.iglesias@ejemplo.com', 'Guadalajara', 'Castilla-La Mancha'),
('Víctor Prieto', 'victor.prieto@ejemplo.com', 'Huesca', 'Aragón'),
('Alicia Esteban', 'alicia.esteban@ejemplo.com', 'Teruel', 'Aragón'),
('Enrique Hidalgo', 'enrique.hidalgo@ejemplo.com', 'Soria', 'Castilla y León'),
('Claudia Santana', 'claudia.santana@ejemplo.com', 'Puerto del Rosario', 'Canarias'),
('Mario Cabrera', 'mario.cabrera@ejemplo.com', 'Arrecife', 'Canarias'),
('Irene Herrera', 'irene.herrera@ejemplo.com', 'Santa Cruz de La Palma', 'Canarias'),
('Gonzalo Reyes', 'gonzalo.reyes@ejemplo.com', 'Telde', 'Canarias'),
('Verónica Vega', 'veronica.vega@ejemplo.com', 'San Cristóbal de La Laguna', 'Canarias'),
('Héctor Campos', 'hector.campos@ejemplo.com', 'Ceuta', 'Ceuta'),
('Lorena Pastor', 'lorena.pastor@ejemplo.com', 'Melilla', 'Melilla'),
('Adrián Soler', 'adrian.soler@ejemplo.com', 'Castellón de la Plana', 'Comunidad Valenciana'),
('Eva Ferrer', 'eva.ferrer@ejemplo.com', 'Tarragona', 'Cataluña'),
('Tomás Pascual', 'tomas.pascual@ejemplo.com', 'Girona', 'Cataluña');

-- Fechas de alta repartidas entre enero de 2024 y junio de 2025 (determinista)
UPDATE clientes SET fecha_registro = DATE '2024-01-01' + ((id * 17) % 540);


-- Productos (12) en 4 categorías
INSERT INTO productos (nombre, categoria, precio) VALUES
('Portátil 14"', 'Informática', 649.00),
('Monitor 27"', 'Informática', 229.90),
('Teclado mecánico', 'Informática', 59.95),
('Cafetera de cápsulas', 'Hogar', 79.00),
('Aspirador robot', 'Hogar', 249.00),
('Lámpara LED de escritorio', 'Hogar', 24.50),
('Zapatillas de running', 'Deporte', 89.90),
('Esterilla de yoga', 'Deporte', 19.95),
('Mochila de senderismo 30 L', 'Deporte', 54.90),
('Manual de Python práctico', 'Libros', 29.90),
('Guía de estadística básica', 'Libros', 34.50),
('Cuaderno de ejercicios SQL', 'Libros', 19.90);


-- Pedidos (100): el cliente n genera (n mod 5) pedidos, así que los clientes cuyo id es múltiplo de 5 NO tienen pedidos (útil para mostrar LEFT JOIN).
WITH base AS (
    SELECT c.id AS cliente_id, c.fecha_registro, g.k
    FROM clientes c
    CROSS JOIN LATERAL generate_series(1, c.id % 5) AS g(k)
),
numerados AS (
    SELECT (ROW_NUMBER() OVER (ORDER BY cliente_id, k))::int AS id,
           cliente_id, fecha_registro, k
    FROM base
)
INSERT INTO pedidos (id, cliente_id, fecha, estado)
SELECT id,
       cliente_id,
       fecha_registro + ((id * 7 + k * 29) % 120),
       CASE id % 10
           WHEN 0 THEN 'cancelado'
           WHEN 1 THEN 'pendiente'
           WHEN 2 THEN 'enviado'
           ELSE 'entregado'
       END
FROM numerados;

-- Como los ids se han insertado a mano, se sincroniza la secuencia
SELECT setval(pg_get_serial_sequence('pedidos', 'id'), (SELECT MAX(id) FROM pedidos));

-- ---------------------------------------------------------------------
-- Líneas de pedido (200): de 1 a 3 productos distintos por pedido
-- ---------------------------------------------------------------------
INSERT INTO detalle_pedidos (pedido_id, producto_id, cantidad, precio_unitario)
SELECT p.id,
       pr.id,
       ((p.id + l) % 4) + 1,
       pr.precio
FROM pedidos p
CROSS JOIN LATERAL generate_series(1, (p.id % 3) + 1) AS l
JOIN productos pr ON pr.id = ((p.id * 5 + l * 7) % 12) + 1;
