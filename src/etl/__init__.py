"""Pipeline ETL: extracción (CSV) -> transformación (pandas) -> carga (PostgreSQL)."""

from src.etl.pipeline import EtlResult, run

__all__ = ["EtlResult", "run"]
