import fakeredis
import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from src.cache import QueryCache, benchmark

SQL = "SELECT id, nombre, precio, activo, creado FROM items WHERE id >= :minimo ORDER BY id"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool)
    pd.DataFrame(
        {
            "id": [1, 2, 3],
            "nombre": ["a", "b", None],
            "precio": [1.5, 2.25, 3.0],
            "activo": [1, 0, 1],  # SQLite no tiene booleanos; el tipo bool se prueba en integración
            "creado": ["2024-01-05", "2024-02-10", "2024-03-15"],
        }
    ).to_sql("items", eng, index=False)
    eng.query_count = 0

    @event.listens_for(eng, "before_cursor_execute")
    def _count(*_args):
        eng.query_count += 1

    return eng


@pytest.fixture
def server():
    return fakeredis.FakeServer()


@pytest.fixture
def cache(server):
    return QueryCache(fakeredis.FakeRedis(server=server, decode_responses=True), ttl=60)


# ---------------------------------------------------------------- claves
def test_key_ignores_whitespace_but_not_params_or_sql(cache):
    base = cache.make_key("SELECT 1", {"a": 1})
    assert cache.make_key("SELECT   1\n", {"a": 1}) == base
    assert cache.make_key("SELECT 1", {"a": 2}) != base
    assert cache.make_key("SELECT 2", {"a": 1}) != base
    assert cache.make_key("SELECT 1", {"a": 1}, parse_dates=["d"]) != base
    assert cache.make_key("SELECT 1", {"a": 1}).startswith(cache.prefix)


def test_key_is_independent_of_param_order(cache):
    assert cache.make_key("q", {"a": 1, "b": 2}) == cache.make_key("q", {"b": 2, "a": 1})


# ---------------------------------------------------------------- aciertos y fallos
def test_second_read_comes_from_redis_without_touching_the_database(cache, engine):
    first = cache.read_sql(engine, SQL, {"minimo": 1})
    queries_after_first = engine.query_count
    second = cache.read_sql(engine, SQL, {"minimo": 1})

    assert engine.query_count == queries_after_first  # ni una consulta más
    assert (cache.stats.hits, cache.stats.misses) == (1, 1)
    assert cache.stats.hit_ratio == 0.5
    pd.testing.assert_frame_equal(first, second)


def test_cached_frame_keeps_types_and_nulls(cache, engine):
    cache.read_sql(engine, SQL, {"minimo": 1})
    cached = cache.read_sql(engine, SQL, {"minimo": 1})
    assert cached["id"].dtype == "int64"
    assert cached["precio"].dtype == "float64"
    assert cached["activo"].dtype == "int64"
    assert pd.isna(cached.loc[2, "nombre"])


def test_different_params_are_cached_separately(cache, engine):
    a = cache.read_sql(engine, SQL, {"minimo": 1})
    b = cache.read_sql(engine, SQL, {"minimo": 3})
    assert (len(a), len(b)) == (3, 1)
    assert cache.stats.misses == 2
    assert len(cache.client.keys(cache.prefix + "*")) == 2


def test_entries_expire_with_ttl(cache, engine):
    cache.read_sql(engine, SQL, {"minimo": 1}, ttl=30)
    key = cache.make_key(SQL, {"minimo": 1})
    assert 0 < cache.client.ttl(key) <= 30


def test_parse_dates_gives_same_dtype_on_miss_and_hit(cache, engine):
    miss = cache.read_sql(engine, SQL, {"minimo": 1}, parse_dates=["creado"])
    hit = cache.read_sql(engine, SQL, {"minimo": 1}, parse_dates=["creado"])
    assert pd.api.types.is_datetime64_any_dtype(miss["creado"])
    assert pd.api.types.is_datetime64_any_dtype(hit["creado"])
    pd.testing.assert_frame_equal(miss, hit)


# ---------------------------------------------------------------- invalidación
def test_invalidate_removes_only_own_prefix(cache, engine):
    cache.read_sql(engine, SQL, {"minimo": 1})
    cache.client.set("otra_app:clave", "intacta")
    assert cache.invalidate() == 1
    assert cache.client.get("otra_app:clave") == "intacta"
    cache.read_sql(engine, SQL, {"minimo": 1})
    assert cache.stats.misses == 2  # tras invalidar, vuelve a consultar la base de datos


def test_forget_removes_a_single_query(cache, engine):
    cache.read_sql(engine, SQL, {"minimo": 1})
    cache.read_sql(engine, SQL, {"minimo": 3})
    cache.forget(SQL, {"minimo": 1})
    assert len(cache.client.keys(cache.prefix + "*")) == 1


# ---------------------------------------------------------------- tolerancia a fallos
def test_disabled_cache_always_queries_the_database(engine):
    cache = QueryCache(None)
    cache.read_sql(engine, SQL, {"minimo": 1})
    before = engine.query_count
    cache.read_sql(engine, SQL, {"minimo": 1})
    assert engine.query_count > before
    assert cache.invalidate() == 0


def test_redis_down_falls_back_to_database(server, engine):
    cache = QueryCache(fakeredis.FakeRedis(server=server, decode_responses=True))
    server.connected = False  # simula Redis caído
    df = cache.read_sql(engine, SQL, {"minimo": 1})
    assert len(df) == 3
    assert cache.stats.errors >= 1
    assert cache.invalidate() == 0  # tampoco lanza excepción


def test_corrupt_cache_entry_is_treated_as_miss_and_repaired(cache, engine):
    key = cache.make_key(SQL, {"minimo": 1})
    cache.client.set(key, "{esto no es json")
    df = cache.read_sql(engine, SQL, {"minimo": 1})
    assert len(df) == 3
    assert cache.stats.errors == 1
    cache.read_sql(engine, SQL, {"minimo": 1})
    assert cache.stats.hits == 1  # la entrada se ha reparado


# ---------------------------------------------------------------- benchmark
def test_benchmark_reports_all_metrics(cache, engine):
    result = benchmark(cache, engine, SQL, {"minimo": 1}, repeats=3)
    assert set(result) == {"db_ms", "cold_ms", "warm_ms", "speedup"}
    assert all(value > 0 for value in result.values())
    assert cache.stats.hits == 3  # las 3 lecturas "calientes" salieron de Redis


def test_benchmark_rejects_invalid_repeats(cache, engine):
    with pytest.raises(ValueError):
        benchmark(cache, engine, SQL, {"minimo": 1}, repeats=0)
