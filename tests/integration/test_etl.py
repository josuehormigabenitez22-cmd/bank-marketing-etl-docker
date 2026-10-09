"""ETL contra PostgreSQL real: carga, idempotencia, atomicidad e invalidación de caché."""

import fakeredis
import pandas as pd
import pytest
from sqlalchemy import text

from src.cache import DEFAULT_PREFIX
from src.config import DATASET_DIR
from src.etl import run
from src.etl.extract import extract
from src.etl.load import LoadError, load
from src.etl.transform import transform

pytestmark = pytest.mark.integration


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


def test_full_load_matches_known_numbers(demo_engine, marketing_loaded):
    assert marketing_loaded.rows_loaded == 45211
    assert marketing_loaded.dates_inferred is True
    row = pd.read_sql(
        text(
            "SELECT COUNT(*) n, COUNT(*) FILTER (WHERE suscrito) subs, "
            "MIN(fecha_contacto) f0, MAX(fecha_contacto) f1 FROM marketing.contactos"
        ),
        demo_engine,
    ).iloc[0]
    assert (row.n, row.subs) == (45211, 5289)
    assert (str(row.f0), str(row.f1)) == ("2008-05-05", "2010-11-17")


def test_nulls_are_real_nulls_not_the_string_unknown(demo_engine, marketing_loaded):
    assert (
        scalar(demo_engine, "SELECT COUNT(*) FROM marketing.contactos WHERE profesion IS NULL")
        == 288
    )
    assert (
        scalar(demo_engine, "SELECT COUNT(*) FROM marketing.contactos WHERE profesion = 'unknown'")
        == 0
    )
    assert (
        scalar(
            demo_engine,
            "SELECT COUNT(*) FROM marketing.contactos WHERE dias_desde_contacto_previo = -1",
        )
        == 0
    )
    assert marketing_loaded.null_counts["resultado_previo"] == 36959


def test_column_types_in_database(demo_engine, marketing_loaded):
    types = dict(
        pd.read_sql(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'marketing' AND table_name = 'contactos'"
            ),
            demo_engine,
        ).itertuples(index=False)
    )
    assert types["suscrito"] == "boolean"
    assert types["fecha_contacto"] == "date"
    assert types["edad"] == "smallint"
    assert types["saldo"] == "integer"


def test_rerunning_is_idempotent_and_does_not_duplicate(demo_engine, marketing_loaded):
    again = run(DATASET_DIR / "bank.csv", engine=demo_engine, flush_cache=False)
    assert again.rows_loaded == 4521
    assert again.dates_inferred is False  # bank.csv no está ordenado por fecha
    assert scalar(demo_engine, "SELECT COUNT(*) FROM marketing.contactos") == 4521
    assert scalar(demo_engine, "SELECT COUNT(fecha_contacto) FROM marketing.contactos") == 0
    # dejar la tabla como la encontró el resto de tests
    run(engine=demo_engine, flush_cache=False)
    assert scalar(demo_engine, "SELECT COUNT(*) FROM marketing.contactos") == 45211


def test_failed_load_rolls_back_and_keeps_previous_data(demo_engine, marketing_loaded):
    df = transform(extract(DATASET_DIR / "bank.csv", limit=10))
    df.loc[3, "profesion"] = "x" * 100  # excede VARCHAR(30): COPY falla a mitad de la carga
    with pytest.raises(Exception, match="too long"):
        load(df, demo_engine)
    assert scalar(demo_engine, "SELECT COUNT(*) FROM marketing.contactos") == 45211


def test_load_error_and_rollback_when_rows_go_missing(demo_engine, marketing_loaded):
    """Un trigger descarta filas: COPY "funciona", pero la tabla queda con menos de las esperadas."""
    with demo_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION marketing.skip_all() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER skip BEFORE INSERT ON marketing.contactos FOR EACH ROW EXECUTE FUNCTION marketing.skip_all()"
            )
        )
    try:
        df = transform(extract(DATASET_DIR / "bank.csv", limit=5))
        with pytest.raises(LoadError, match="Se esperaban 5 filas y la tabla tiene 0"):
            load(df, demo_engine)
    finally:
        with demo_engine.begin() as conn:
            conn.execute(text("DROP TRIGGER skip ON marketing.contactos"))
            conn.execute(text("DROP FUNCTION marketing.skip_all()"))
    assert scalar(demo_engine, "SELECT COUNT(*) FROM marketing.contactos") == 45211  # rollback


def test_etl_invalidates_cached_queries_but_not_other_keys(demo_engine, marketing_loaded):
    fake = fakeredis.FakeRedis(decode_responses=True)
    fake.set(f"{DEFAULT_PREFIX}abc", "{}")
    fake.set(f"{DEFAULT_PREFIX}def", "{}")
    fake.set("otra_app:clave", "intacta")

    result = run(DATASET_DIR / "bank.csv", engine=demo_engine, redis_client=fake)

    assert result.cache_entries_invalidated == 2
    assert fake.keys(f"{DEFAULT_PREFIX}*") == []
    assert fake.get("otra_app:clave") == "intacta"
    run(engine=demo_engine, flush_cache=False)  # restaurar bank-full


def test_limit_loads_only_first_rows(demo_engine, marketing_loaded):
    result = run(engine=demo_engine, limit=100, flush_cache=False)
    assert result.rows_loaded == 100
    assert scalar(demo_engine, "SELECT MAX(contacto_id) FROM marketing.contactos") == 100
    run(engine=demo_engine, flush_cache=False)
