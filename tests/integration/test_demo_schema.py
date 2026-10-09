"""Comprueba init.sql: datos de la tienda de demostración, relaciones y limpieza de ciudades."""

import pandas as pd
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


def test_row_counts_are_deterministic(demo_engine):
    counts = {
        t: scalar(demo_engine, f"SELECT COUNT(*) FROM {t}")
        for t in ["clientes", "productos", "pedidos", "detalle_pedidos"]
    }
    assert counts == {"clientes": 50, "productos": 12, "pedidos": 100, "detalle_pedidos": 200}


def test_clients_whose_id_is_multiple_of_five_have_no_orders(demo_engine):
    ids = pd.read_sql(
        text("SELECT c.id FROM clientes c LEFT JOIN pedidos p ON p.cliente_id = c.id "
             "WHERE p.id IS NULL ORDER BY c.id"),
        demo_engine,
    )["id"].tolist()  # fmt: skip
    assert ids == list(range(5, 51, 5))


def test_order_status_distribution(demo_engine):
    df = pd.read_sql(text("SELECT estado, COUNT(*) n FROM pedidos GROUP BY 1"), demo_engine)
    assert dict(zip(df["estado"], df["n"], strict=True)) == {
        "entregado": 70,
        "cancelado": 10,
        "pendiente": 10,
        "enviado": 10,
    }


def test_no_order_is_dated_before_the_customer_signed_up(demo_engine):
    assert (
        scalar(
            demo_engine,
            "SELECT COUNT(*) FROM pedidos p JOIN clientes c ON c.id = p.cliente_id "
            "WHERE p.fecha < c.fecha_registro",
        )
        == 0
    )


def test_foreign_keys_are_enforced(demo_engine):
    with pytest.raises(Exception, match="foreign key"), demo_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO pedidos (cliente_id, fecha, estado) VALUES (999, now(), 'enviado')")
        )


def test_order_status_check_constraint(demo_engine):
    with pytest.raises(Exception, match="check constraint"), demo_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO pedidos (cliente_id, fecha, estado) VALUES (1, now(), 'perdido')")
        )


def test_serial_sequence_continues_after_manual_ids(demo_engine):
    with demo_engine.begin() as conn:
        new_id = conn.execute(
            text(
                "INSERT INTO pedidos (cliente_id, fecha, estado) VALUES (1, now(), 'pendiente') RETURNING id"
            )
        ).scalar_one()
        conn.rollback()
    # Sin el setval() de init.sql la secuencia devolvería 1 y chocaría con un pedido existente.
    # (No se compara con 101 exacto: los INSERT fallidos de otros tests también consumen valores.)
    assert new_id > 100


def test_city_column_has_cities_not_islands(demo_engine):
    """Regresión: 'Tenerife', 'Gran Canaria'... son islas, y 'Gran Canaria' duplicaba a Las Palmas."""
    cities = set(pd.read_sql(text("SELECT ciudad FROM clientes"), demo_engine)["ciudad"])
    assert not cities & {"Tenerife", "Gran Canaria", "Fuerteventura", "Lanzarote", "La Palma"}
    assert len(cities) == 50  # una ciudad distinta por cliente
    assert scalar(demo_engine, "SELECT COUNT(*) FROM clientes WHERE comunidad = 'Canarias'") == 7


def test_every_client_has_a_region_and_unique_email(demo_engine):
    assert scalar(demo_engine, "SELECT COUNT(*) FROM clientes WHERE comunidad IS NULL") == 0
    assert scalar(demo_engine, "SELECT COUNT(DISTINCT email) FROM clientes") == 50
