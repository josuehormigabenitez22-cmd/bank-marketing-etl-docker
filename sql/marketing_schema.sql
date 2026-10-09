-- =====================================================================
-- Esquema "marketing": campañas de telemarketing de un banco portugués
-- Dataset: UCI Bank Marketing (Moro, Rita y Cortez), licencia CC BY 4.0.
--
-- Lo rellena el pipeline ETL (python -m src.etl). El script es idempotente:
-- se ejecuta al crear el volumen de PostgreSQL y de nuevo en cada carga.
-- Un registro = un contacto telefónico con un cliente (el dataset no trae
-- identificador de cliente, así que contacto_id es una clave sustituta).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS marketing;

CREATE TABLE IF NOT EXISTS marketing.contactos (
    contacto_id                 INTEGER PRIMARY KEY,
    -- Datos del cliente
    edad                        SMALLINT    NOT NULL CHECK (edad BETWEEN 16 AND 110),
    profesion                   VARCHAR(30),
    estado_civil                VARCHAR(20) NOT NULL,
    educacion                   VARCHAR(20),
    impago                      BOOLEAN NOT NULL,
    saldo                       INTEGER NOT NULL,
    vivienda                    BOOLEAN NOT NULL,
    prestamo                    BOOLEAN NOT NULL,
    -- Último contacto de la campaña actual
    canal_contacto              VARCHAR(20),
    dia                         SMALLINT NOT NULL CHECK (dia BETWEEN 1 AND 31),
    mes                         SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    fecha_contacto              DATE,
    duracion_seg                INTEGER NOT NULL CHECK (duracion_seg >= 0),
    campana                     SMALLINT NOT NULL CHECK (campana >= 1),
    -- Historial con campañas anteriores
    contactado_antes            BOOLEAN NOT NULL,
    dias_desde_contacto_previo  INTEGER,
    contactos_previos           SMALLINT NOT NULL CHECK (contactos_previos >= 0),
    resultado_previo            VARCHAR(10),
    -- Variable objetivo
    suscrito                    BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contactos_profesion ON marketing.contactos (profesion);
CREATE INDEX IF NOT EXISTS idx_contactos_fecha ON marketing.contactos (fecha_contacto);
CREATE INDEX IF NOT EXISTS idx_contactos_suscrito ON marketing.contactos (suscrito);

COMMENT ON TABLE marketing.contactos IS
    'Contactos de telemarketing bancario (UCI Bank Marketing, bank-full.csv). Cargada por src.etl.';
COMMENT ON COLUMN marketing.contactos.contacto_id IS
    'Clave sustituta: posición de la fila en el CSV (el dataset no incluye ID de cliente).';
COMMENT ON COLUMN marketing.contactos.profesion IS 'NULL cuando el CSV indica "unknown".';
COMMENT ON COLUMN marketing.contactos.estado_civil IS
    'divorciado_viudo: el dataset agrupa divorciados y viudos.';
COMMENT ON COLUMN marketing.contactos.saldo IS 'Saldo medio anual en euros (puede ser negativo).';
COMMENT ON COLUMN marketing.contactos.fecha_contacto IS
    'Inferida: el CSV solo trae día y mes. bank-full.csv está ordenado por fecha (mayo 2008 a noviembre 2010), '
    'así que el año se deduce de los saltos de mes. NULL si el fichero no está ordenado (bank.csv).';
COMMENT ON COLUMN marketing.contactos.duracion_seg IS
    'Duración de la llamada: solo se conoce DESPUÉS de llamar, no sirve para predecir.';
COMMENT ON COLUMN marketing.contactos.campana IS 'Nº de contactos en esta campaña con este cliente (incluye el último).';
COMMENT ON COLUMN marketing.contactos.contactado_antes IS 'Derivada: pdays distinto de -1 en el CSV.';
COMMENT ON COLUMN marketing.contactos.dias_desde_contacto_previo IS 'NULL si no hubo contacto previo (pdays = -1).';
COMMENT ON COLUMN marketing.contactos.resultado_previo IS 'Resultado de la campaña anterior; NULL si "unknown".';
COMMENT ON COLUMN marketing.contactos.suscrito IS '¿Contrató el depósito a plazo? (variable "y" del CSV).';
