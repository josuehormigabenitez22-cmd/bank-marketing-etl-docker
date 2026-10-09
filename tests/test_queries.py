import pytest

from src.queries import get_query, load_queries, parse_queries

SAMPLE = """
-- cabecera ignorada

-- name: uno
-- comentario que forma parte de la consulta
SELECT 1;

-- name: dos
SELECT 2
"""


def test_parse_queries_splits_by_name_and_strips_semicolon():
    queries = parse_queries(SAMPLE)
    assert list(queries) == ["uno", "dos"]
    assert queries["uno"].endswith("SELECT 1")
    assert queries["dos"] == "SELECT 2"


def test_duplicate_names_are_rejected():
    with pytest.raises(ValueError, match="duplicada"):
        parse_queries("-- name: a\nSELECT 1;\n-- name: a\nSELECT 2;")


def test_empty_query_is_rejected():
    with pytest.raises(ValueError, match="vacía"):
        parse_queries("-- name: a\n\n-- name: b\nSELECT 1;")


def test_unknown_query_lists_available_names():
    with pytest.raises(KeyError, match="ventas_por_mes"):
        get_query("no_existe")


def test_real_file_contains_expected_queries():
    names = set(load_queries())
    assert {
        "ventas_por_mes",
        "top_clientes",
        "ingresos_por_categoria",
        "clientes_sin_pedidos",
        "marketing_resumen",
        "marketing_conversion_cubo",
    } <= names
    assert all(sql.strip() for sql in load_queries().values())


def test_parameterised_query_uses_named_bind():
    assert ":limite" in get_query("top_clientes")
