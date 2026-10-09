"""Fixtures compartidas.

Los tests de integración usan PostgreSQL y Redis reales, pero NUNCA tocan la base de datos
de trabajo: crean una base temporal (``test_<aleatorio>``) y la borran al terminar.

Si los servicios no están disponibles, los tests de integración se saltan, salvo que
``REQUIRE_INTEGRATION=1`` (es lo que hace la CI, para que un fallo de infraestructura
no pase desapercibido).
"""

from __future__ import annotations

import os
import uuid

import pytest
import redis
from sqlalchemy import Engine, create_engine, text

from src.cache import QueryCache
from src.config import ROOT, ConfigError, PostgresSettings, get_redis
from src.etl import run as run_etl

REQUIRE_INTEGRATION = os.environ.get("REQUIRE_INTEGRATION") == "1"


def _skip_or_fail(reason: str):
    if REQUIRE_INTEGRATION:
        pytest.fail(reason)
    pytest.skip(reason)


def _run_script(engine: Engine, path) -> None:
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()


@pytest.fixture(scope="session")
def pg_settings() -> PostgresSettings:
    try:
        return PostgresSettings.from_env()
    except ConfigError as exc:
        _skip_or_fail(f"Sin configuración de PostgreSQL: {exc}")


@pytest.fixture(scope="session")
def demo_engine(pg_settings: PostgresSettings):
    """Base temporal con init.sql y el esquema marketing aplicados (como en Docker)."""
    name = f"test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(pg_settings.url(), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:
        admin.dispose()
        _skip_or_fail(f"No se pudo crear la base temporal en PostgreSQL: {exc}")

    engine = create_engine(pg_settings.url(name))
    try:
        _run_script(engine, ROOT / "init.sql")
        _run_script(engine, ROOT / "sql" / "marketing_schema.sql")
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def marketing_loaded(demo_engine: Engine):
    """Ejecuta el ETL completo (bank-full.csv) una sola vez para toda la sesión de tests."""
    return run_etl(engine=demo_engine, flush_cache=False)


@pytest.fixture
def real_redis():
    client = get_redis()
    try:
        client.ping()
    except redis.RedisError as exc:
        client.close()
        _skip_or_fail(f"Redis no disponible: {exc}")
    yield client
    client.close()


@pytest.fixture
def real_cache(real_redis):
    """QueryCache sobre Redis real con un prefijo único, que se limpia al terminar."""
    cache = QueryCache(real_redis, prefix=f"test:{uuid.uuid4().hex[:8]}:", ttl=60)
    yield cache
    cache.invalidate()
