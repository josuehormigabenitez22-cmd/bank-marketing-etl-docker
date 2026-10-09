"""Las consultas analíticas de sql/analytics.sql, verificadas contra cálculos independientes."""

import pandas as pd
import pytest
from sqlalchemy import text

from src.queries import get_query, load_queries

pytestmark = pytest.mark.integration

PARAMS = {"top_clientes": {"limite": 10}}


def q(engine, name, **params):
    params = params or PARAMS.get(name, {})
    return pd.read_sql(text(get_query(name)), engine, params=params)


@pytest.fixture(scope="module")
def sales(demo_engine):
    """Líneas de pedido no canceladas, leídas directamente de las tablas (cálculo de referencia)."""
    return pd.read_sql(
        text(
            "SELECT p.id pedido_id, p.cliente_id, p.fecha, d.producto_id, d.cantidad, d.precio_unitario::float8 precio "
            "FROM pedidos p JOIN detalle_pedidos d ON d.pedido_id = p.id WHERE p.estado <> 'cancelado'"
        ),
        demo_engine,
    ).assign(importe=lambda d: d.cantidad * d.precio)


def test_every_named_query_runs(demo_engine, marketing_loaded):
    for name in load_queries():
        df = q(demo_engine, name)
        assert len(df) > 0, f"La consulta {name} no devuelve filas"


# ---------------------------------------------------------------- tienda
def test_ventas_por_mes_matches_independent_computation(demo_engine, sales):
    out = q(demo_engine, "ventas_por_mes")
    expected = sales.groupby(pd.to_datetime(sales["fecha"]).dt.to_period("M"))["importe"].sum()
    assert out["ingresos"].sum() == pytest.approx(sales["importe"].sum())
    assert len(out) == len(expected)
    assert out["pedidos"].sum() == sales["pedido_id"].nunique() == 90
    assert out["mes"].is_monotonic_increasing


def test_gasto_acumulado_ends_at_total_revenue(demo_engine, sales):
    out = q(demo_engine, "gasto_acumulado_mensual")
    assert out["acumulado"].iloc[-1] == pytest.approx(sales["importe"].sum())
    assert out["acumulado"].is_monotonic_increasing


def test_top_clientes_ranking(demo_engine, sales):
    out = q(demo_engine, "top_clientes")
    assert len(out) == 10
    assert out["ranking"].iloc[0] == 1
    assert out["gasto"].is_monotonic_decreasing
    best = sales.groupby("cliente_id")["importe"].sum().max()
    assert out["gasto"].iloc[0] == pytest.approx(best)


def test_ingresos_por_categoria(demo_engine, sales):
    out = q(demo_engine, "ingresos_por_categoria")
    assert set(out["categoria"]) == {"Informática", "Hogar", "Deporte", "Libros"}
    assert out["porcentaje"].sum() == pytest.approx(100, abs=0.3)  # redondeo a 1 decimal
    assert out["ingresos"].sum() == pytest.approx(sales["importe"].sum())
    assert out["unidades"].sum() == sales["cantidad"].sum()


def test_clientes_sin_pedidos(demo_engine):
    assert q(demo_engine, "clientes_sin_pedidos")["id"].tolist() == list(range(5, 51, 5))


def test_ticket_medio_por_comunidad(demo_engine, sales):
    out = q(demo_engine, "ticket_medio_por_comunidad")
    assert out["pedidos"].sum() == 90
    assert out["ticket_medio"].is_monotonic_decreasing
    overall = sales.groupby("pedido_id")["importe"].sum().mean()
    weighted = (out["ticket_medio"] * out["pedidos"]).sum() / out["pedidos"].sum()
    assert weighted == pytest.approx(overall, abs=0.5)  # redondeo a 2 decimales por comunidad


# ---------------------------------------------------------------- marketing
def test_marketing_resumen(demo_engine, marketing_loaded):
    row = q(demo_engine, "marketing_resumen").iloc[0]
    assert (row.contactos, row.suscritos) == (45211, 5289)
    assert row.tasa_conversion_pct == pytest.approx(100 * 5289 / 45211, abs=0.005)
    assert (str(row.primer_contacto), str(row.ultimo_contacto)) == ("2008-05-05", "2010-11-17")


def test_conversion_por_profesion_covers_everyone(demo_engine, marketing_loaded):
    out = q(demo_engine, "marketing_conversion_por_profesion")
    assert out["contactos"].sum() == 45211
    assert out["suscritos"].sum() == 5289
    assert out.set_index("profesion").loc["desconocida", "contactos"] == 288
    assert out["tasa_conversion_pct"].is_monotonic_decreasing


def test_conversion_por_resultado_previo(demo_engine, marketing_loaded):
    out = q(demo_engine, "marketing_conversion_por_resultado_previo").set_index("resultado_previo")
    assert out["contactos"].sum() == 45211
    assert out.loc["sin campaña previa", "contactos"] == 36959
    assert out.loc["éxito", "contactos"] == 1511


def test_conversion_por_edad(demo_engine, marketing_loaded):
    out = q(demo_engine, "marketing_conversion_por_edad")
    assert out["tramo_edad"].tolist() == ["<25", "25-34", "35-44", "45-54", "55-64", "65+"]
    assert out["contactos"].sum() == 45211


def test_conversion_mensual(demo_engine, marketing_loaded):
    out = q(demo_engine, "marketing_conversion_mensual")
    assert out["contactos"].sum() == 45211
    assert str(out["mes"].iloc[0]) == "2008-05-01"
    assert str(out["mes"].iloc[-1]) == "2010-11-01"
    assert len(out) == 30  # el dataset no tiene contactos en septiembre de 2008


def test_duracion_percentiles_match_pandas(demo_engine, marketing_loaded):
    out = q(demo_engine, "marketing_duracion_percentiles").set_index("suscrito")
    df = pd.read_sql(text("SELECT suscrito, duracion_seg FROM marketing.contactos"), demo_engine)
    for flag, group in df.groupby("suscrito"):
        assert out.loc[flag, "mediana_seg"] == pytest.approx(group["duracion_seg"].median())
        assert out.loc[flag, "p25_seg"] == pytest.approx(group["duracion_seg"].quantile(0.25))
        assert out.loc[flag, "p75_seg"] == pytest.approx(group["duracion_seg"].quantile(0.75))
    assert out.loc[True, "mediana_seg"] > out.loc[False, "mediana_seg"]


def test_conversion_cubo_grand_total_row(demo_engine, marketing_loaded):
    out = q(demo_engine, "marketing_conversion_cubo")
    total = out[out[["profesion", "estado_civil", "educacion"]].isna().all(axis=1)]
    # puede haber más de una fila "todo NULL" (profesion y educacion también son NULL en los datos),
    # pero la de mayor tamaño es el total general
    assert out.iloc[0]["contactos"] == 45211
    assert out.iloc[0]["tasa_conversion_pct"] == pytest.approx(100 * 5289 / 45211, abs=0.005)
    assert len(total) >= 1
