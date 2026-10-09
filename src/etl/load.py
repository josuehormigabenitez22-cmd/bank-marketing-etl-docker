"""Carga: vuelca el DataFrame en PostgreSQL con COPY (mucho más rápido que INSERT fila a fila)."""

from __future__ import annotations
import io
import pandas as pd
from sqlalchemy import Engine
from src.config import SQL_DIR
from src.etl.transform import TARGET_COLUMNS

SCHEMA_FILE = SQL_DIR / "marketing_schema.sql"
TABLE = "marketing.contactos"


class LoadError(RuntimeError):
    """La carga no dejó la tabla en el estado esperado."""


def apply_schema(engine: Engine) -> None:
    """Crea el esquema y la tabla si no existen (idempotente)."""
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def load(df: pd.DataFrame, engine: Engine) -> int:
    """Sustituye el contenido de ``marketing.contactos`` por ``df`` (carga completa e idempotente)"""
    buffer = io.StringIO()
    df[TARGET_COLUMNS].to_csv(buffer, index=False, header=False, na_rep="", date_format="%Y-%m-%d")
    buffer.seek(0)

    copy_sql = f"COPY {TABLE} ({', '.join(TARGET_COLUMNS)}) FROM STDIN WITH (FORMAT csv)"

    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
            cur.execute(f"TRUNCATE {TABLE}")
            cur.copy_expert(copy_sql, buffer)
            cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
            loaded = cur.fetchone()[0]
            if loaded != len(df):
                raise LoadError(f"Se esperaban {len(df)} filas y la tabla tiene {loaded}")
            cur.execute(f"ANALYZE {TABLE}")  # estadísticas frescas para el planificador
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
    return loaded
