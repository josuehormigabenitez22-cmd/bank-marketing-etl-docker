"""Orquestación del pipeline: extract -> transform -> load (+ invalidación de la caché Redis)."""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
import redis
from sqlalchemy import Engine
from src.cache import QueryCache
from src.config import DEFAULT_SOURCE, get_engine, get_redis
from src.etl.extract import extract
from src.etl.load import load
from src.etl.transform import transform

logger = logging.getLogger(__name__)

# Solo este fichero está ordenado por fecha, condición necesaria para deducir el año.
ORDERED_BY_DATE_FILES = {"bank-full.csv"}


@dataclass
class EtlResult:
    rows_extracted: int
    rows_loaded: int
    dates_inferred: bool
    null_counts: dict[str, int]
    cache_entries_invalidated: int
    seconds: dict[str, float] = field(default_factory=dict)


def run(
    source: Path | str = DEFAULT_SOURCE,
    *,
    engine: Engine | None = None,
    redis_client: redis.Redis | None = None,
    limit: int | None = None,
    infer_dates: bool | None = None,
    flush_cache: bool = True,
) -> EtlResult:
    """Ejecuta el ETL completo"""
    source = Path(source)
    engine = engine or get_engine()
    if infer_dates is None:
        infer_dates = source.name in ORDERED_BY_DATE_FILES
    seconds: dict[str, float] = {}
    t_start = time.perf_counter()

    t0 = time.perf_counter()
    raw = extract(source, limit=limit)
    seconds["extract"] = time.perf_counter() - t0
    logger.info("EXTRACT  %s filas leídas de %s", len(raw), source.name)

    t0 = time.perf_counter()
    clean = transform(raw, infer_dates=infer_dates)
    seconds["transform"] = time.perf_counter() - t0
    null_counts = {c: int(n) for c, n in clean.isna().sum().items() if n}
    logger.info(
        "TRANSFORM  %s filas válidas | fechas deducidas: %s | NULLs por columna: %s",
        len(clean),
        "sí" if infer_dates else "no",
        null_counts or "ninguno",
    )

    t0 = time.perf_counter()
    loaded = load(clean, engine)
    seconds["load"] = time.perf_counter() - t0
    logger.info("LOAD  %s filas en marketing.contactos", loaded)

    invalidated = 0
    if flush_cache:
        client = redis_client
        if client is None:
            try:
                client = get_redis()
            except Exception as exc:  # configuración inválida: la caché es opcional
                logger.warning("Redis no configurado, no se invalida la caché: %s", exc)
        if client is not None:
            invalidated = QueryCache(client).invalidate()
            logger.info("CACHE  %s consultas cacheadas invalidadas", invalidated)

    seconds["total"] = time.perf_counter() - t_start
    return EtlResult(
        rows_extracted=len(raw),
        rows_loaded=loaded,
        dates_inferred=bool(infer_dates),
        null_counts=null_counts,
        cache_entries_invalidated=invalidated,
        seconds=seconds,
    )
