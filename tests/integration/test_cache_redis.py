"""QueryCache contra Redis y PostgreSQL reales (incluida la autenticación)."""

import os

import pandas as pd
import pytest
import redis

from src.cache import QueryCache
from src.config import RedisSettings, get_redis
from src.queries import get_query

pytestmark = pytest.mark.integration

PRODUCTS_SQL = "SELECT id, nombre, categoria, precio::float8 AS precio FROM productos ORDER BY id"


def test_miss_then_hit_returns_identical_frames(demo_engine, real_cache):
    first = real_cache.read_sql(demo_engine, PRODUCTS_SQL)
    second = real_cache.read_sql(demo_engine, PRODUCTS_SQL)
    assert (real_cache.stats.misses, real_cache.stats.hits) == (1, 1)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 12


def test_boolean_and_date_columns_survive_the_roundtrip(demo_engine, marketing_loaded, real_cache):
    sql = (
        "SELECT contacto_id, suscrito, fecha_contacto FROM marketing.contactos "
        "ORDER BY contacto_id LIMIT 50"
    )
    miss = real_cache.read_sql(demo_engine, sql)
    hit = real_cache.read_sql(demo_engine, sql)
    assert real_cache.stats.hits == 1
    assert hit["suscrito"].dtype == bool
    assert pd.api.types.is_datetime64_any_dtype(hit["fecha_contacto"])
    pd.testing.assert_frame_equal(miss, hit)


def test_date_column_from_postgres_is_consistent_on_miss_and_hit(demo_engine, real_cache):
    """Regresión: DATE llegaba como objetos date la 1ª vez y como texto la 2ª."""
    sql = get_query("ventas_por_mes")
    miss = real_cache.read_sql(demo_engine, sql)
    hit = real_cache.read_sql(demo_engine, sql)
    assert pd.api.types.is_datetime64_any_dtype(miss["mes"])
    pd.testing.assert_frame_equal(miss, hit)


def test_parameterised_query_is_cached_per_parameter(demo_engine, real_cache):
    sql = get_query("top_clientes")
    three = real_cache.read_sql(demo_engine, sql, {"limite": 3})
    five = real_cache.read_sql(demo_engine, sql, {"limite": 5})
    assert (len(three), len(five)) == (3, 5)
    assert real_cache.stats.misses == 2


def test_ttl_is_applied_in_redis(demo_engine, real_cache, real_redis):
    real_cache.read_sql(demo_engine, PRODUCTS_SQL, ttl=30)
    assert 0 < real_redis.ttl(real_cache.make_key(PRODUCTS_SQL)) <= 30


@pytest.mark.skipif(not os.environ.get("REDIS_PASSWORD"), reason="Redis sin contraseña")
def test_redis_rejects_connections_without_the_password():
    settings = RedisSettings.from_env()
    anonymous = redis.Redis(host=settings.host, port=settings.port, socket_timeout=2)
    with pytest.raises(redis.AuthenticationError):
        anonymous.ping()


@pytest.mark.skipif(not os.environ.get("REDIS_PASSWORD"), reason="Redis sin contraseña")
def test_wrong_password_degrades_to_database_instead_of_failing(demo_engine):
    settings = RedisSettings.from_env()
    bad = get_redis(RedisSettings(settings.host, settings.port, "contraseña-incorrecta"))
    cache = QueryCache(bad)
    df = cache.read_sql(demo_engine, PRODUCTS_SQL)
    assert len(df) == 12  # los datos llegan igualmente
    assert cache.stats.errors >= 1
