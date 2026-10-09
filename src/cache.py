"""Caché de consultas SQL en Redis.

``QueryCache.read_sql`` devuelve un DataFrame: la primera vez ejecuta la consulta en PostgreSQL y
guarda el resultado en Redis (JSON + TTL); las siguientes lo lee directamente de Redis.
"""

from __future__ import annotations
import hashlib
import io
import json
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd
import redis
from sqlalchemy import Engine, text
from src.config import cache_ttl

logger = logging.getLogger(__name__)

DEFAULT_PREFIX = "bigdata:cache:"


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    errors: int = 0

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


def _to_json(df: pd.DataFrame) -> str:
    # orient="table" conserva el tipo de cada columna
    return df.to_json(orient="table", index=False, date_format="iso")


def _from_json(payload: str) -> pd.DataFrame:
    return pd.read_json(io.StringIO(payload), orient="table")


def _normalize_dates(df: pd.DataFrame, parse_dates: Sequence[str] | None) -> pd.DataFrame:
    """Deja las fechas con el mismo tipo tanto si el resultado viene de PostgreSQL como de Redis"""
    for column in df.columns:
        is_date_objects = (
            df[column].dtype == object
            and pd.api.types.infer_dtype(df[column], skipna=True) == "date"
        )
        if column in (parse_dates or ()) or is_date_objects:
            df[column] = pd.to_datetime(df[column]).astype("datetime64[ns]")
        elif df[column].dtype == object:
            # pandas 2: PostgreSQL devuelve None y el JSON de Redis NaN; se unifican en NaN
            df[column] = df[column].where(df[column].notna(), np.nan)
    return df


class QueryCache:
    """Caché de resultados de consultas. Con ``client=None`` queda desactivada."""

    def __init__(
        self,
        client: redis.Redis | None,
        *,
        prefix: str = DEFAULT_PREFIX,
        ttl: int | None = None,
    ) -> None:
        self.client = client
        self.prefix = prefix
        self.ttl = ttl if ttl is not None else cache_ttl()
        self.stats = CacheStats()

    # Claves
    def make_key(
        self,
        sql: str,
        params: Mapping[str, Any] | None = None,
        parse_dates: Sequence[str] | None = None,
    ) -> str:
        canonical = json.dumps(
            {
                "sql": " ".join(sql.split()),  # los saltos de línea/espacios no cambian la clave
                "params": dict(params or {}),
                "parse_dates": sorted(parse_dates or []),
            },
            sort_keys=True,
            default=str,
        )
        return self.prefix + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    # Lectura
    def read_sql(
        self,
        engine: Engine,
        sql: str,
        params: Mapping[str, Any] | None = None,
        *,
        parse_dates: Sequence[str] | None = None,
        ttl: int | None = None,
    ) -> pd.DataFrame:
        key = self.make_key(sql, params, parse_dates)

        payload = self._redis_get(key)
        if payload is not None:
            try:
                df = _from_json(payload)
            except ValueError:
                logger.warning("Entrada de caché corrupta (%s); se vuelve a consultar", key)
                self.stats.errors += 1
            else:
                self.stats.hits += 1
                return _normalize_dates(df, parse_dates)

        self.stats.misses += 1
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=dict(params or {}))
        df = _normalize_dates(df, parse_dates)
        self._redis_set(key, df, ttl)
        return df

    # Invalidación
    def forget(
        self,
        sql: str,
        params: Mapping[str, Any] | None = None,
        parse_dates: Sequence[str] | None = None,
    ) -> None:
        """Borra de la caché el resultado de una consulta concreta."""
        if self.client is None:
            return
        try:
            self.client.delete(self.make_key(sql, params, parse_dates))
        except redis.RedisError as exc:
            logger.warning("No se pudo borrar la entrada de caché: %s", exc)
            self.stats.errors += 1

    def invalidate(self) -> int:
        """Borra todas las entradas de este prefijo. Devuelve cuántas eliminó."""
        if self.client is None:
            return 0
        deleted = 0
        try:
            batch: list[str] = []
            for key in self.client.scan_iter(match=f"{self.prefix}*", count=500):
                batch.append(key)
                if len(batch) >= 500:
                    deleted += self.client.delete(*batch)
                    batch.clear()
            if batch:
                deleted += self.client.delete(*batch)
        except redis.RedisError as exc:
            logger.warning("No se pudo invalidar la caché: %s", exc)
            self.stats.errors += 1
        return deleted

    # Acceso a Redis tolerante a fallos
    def _redis_get(self, key: str) -> str | None:
        if self.client is None:
            return None
        try:
            return self.client.get(key)
        except redis.RedisError as exc:
            logger.warning("Redis no disponible al leer (%s); se consulta PostgreSQL", exc)
            self.stats.errors += 1
            return None

    def _redis_set(self, key: str, df: pd.DataFrame, ttl: int | None) -> None:
        if self.client is None:
            return
        try:
            self.client.set(key, _to_json(df), ex=ttl if ttl is not None else self.ttl)
        except redis.RedisError as exc:
            logger.warning("Redis no disponible al escribir (%s)", exc)
            self.stats.errors += 1


def benchmark(
    cache: QueryCache,
    engine: Engine,
    sql: str,
    params: Mapping[str, Any] | None = None,
    *,
    repeats: int = 20,
) -> dict[str, float]:
    """Compara el tiempo de la consulta directa en PostgreSQL con la lectura desde Redis"""
    if repeats < 1:
        raise ValueError("repeats debe ser >= 1")

    def _time(fn) -> float:
        start = time.perf_counter()
        fn()
        return (time.perf_counter() - start) * 1000

    def _direct() -> None:
        with engine.connect() as conn:
            pd.read_sql(text(sql), conn, params=dict(params or {}))

    db_times = [_time(_direct) for _ in range(repeats)]

    cache.forget(sql, params)
    cold = _time(lambda: cache.read_sql(engine, sql, params))
    warm_times = [_time(lambda: cache.read_sql(engine, sql, params)) for _ in range(repeats)]

    db_ms = sum(db_times) / repeats
    warm_ms = sum(warm_times) / repeats
    return {
        "db_ms": db_ms,
        "cold_ms": cold,
        "warm_ms": warm_ms,
        "speedup": db_ms / warm_ms if warm_ms else float("inf"),
    }
