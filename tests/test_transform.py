import pandas as pd
import pytest

from src.config import DATASET_DIR
from src.etl.extract import EXPECTED_COLUMNS, ExtractError, extract
from src.etl.transform import (
    TARGET_COLUMNS,
    TransformError,
    infer_contact_dates,
    transform,
    validate,
)


def make_raw(rows: list[dict] | None = None) -> pd.DataFrame:
    """DataFrame con el formato del CSV original; ``rows`` sobrescribe valores por fila."""
    base = {
        "age": 40, "job": "management", "marital": "married", "education": "tertiary",
        "default": "no", "balance": 1000, "housing": "yes", "loan": "no",
        "contact": "cellular", "day": 10, "month": "may", "duration": 120, "campaign": 1,
        "pdays": -1, "previous": 0, "poutcome": "unknown", "y": "no",
    }  # fmt: skip
    rows = rows or [{}]
    return pd.DataFrame([{**base, **r} for r in rows])[EXPECTED_COLUMNS]


# ---------------------------------------------------------------- limpieza y tipado
def test_columns_are_renamed_and_ordered():
    out = transform(make_raw())
    assert list(out.columns) == TARGET_COLUMNS


def test_categories_are_translated_and_unknown_becomes_null():
    out = transform(
        make_raw(
            [
                {"job": "admin.", "education": "secondary", "contact": "telephone"},
                {
                    "job": "unknown",
                    "education": "unknown",
                    "contact": "unknown",
                    "poutcome": "unknown",
                    "marital": "divorced",
                },
                {"poutcome": "success", "pdays": 90, "previous": 2},
            ]
        )  # fmt: skip
    )
    assert out.loc[0, ["profesion", "educacion", "canal_contacto"]].tolist() == [
        "administrativo",
        "secundaria",
        "fijo",
    ]
    assert out.loc[1, ["profesion", "educacion", "canal_contacto", "resultado_previo"]].isna().all()
    assert out.loc[1, "estado_civil"] == "divorciado_viudo"
    assert out.loc[2, "resultado_previo"] == "éxito"


def test_yes_no_columns_become_booleans():
    out = transform(make_raw([{"default": "yes", "housing": "no", "loan": "yes", "y": "yes"}]))
    row = out.iloc[0]
    assert (row.impago, row.vivienda, row.prestamo, row.suscrito) == (True, False, True, True)
    assert out["suscrito"].dtype == bool


def test_pdays_minus_one_becomes_null_and_flag_is_derived():
    out = transform(make_raw([{"pdays": -1}, {"pdays": 0, "previous": 1}, {"pdays": 250}]))
    assert out["contactado_antes"].tolist() == [False, True, True]
    assert pd.isna(out.loc[0, "dias_desde_contacto_previo"])
    assert out["dias_desde_contacto_previo"].iloc[1:].tolist() == [0, 250]


def test_month_names_become_numbers():
    out = transform(make_raw([{"month": "jan"}, {"month": "dec"}]))
    assert out["mes"].tolist() == [1, 12]


def test_contacto_id_is_sequential_from_one():
    out = transform(make_raw([{}, {}, {}]))
    assert out["contacto_id"].tolist() == [1, 2, 3]


def test_transform_does_not_mutate_input():
    raw = make_raw()
    before = raw.copy()
    transform(raw)
    pd.testing.assert_frame_equal(raw, before)


# ---------------------------------------------------------------- fechas
def test_dates_are_left_empty_when_inference_is_off():
    out = transform(make_raw())
    assert out["fecha_contacto"].isna().all()


def test_year_is_inferred_when_month_wraps_around():
    rows = [
        {"month": "may", "day": 5},
        {"month": "dec", "day": 30},
        {"month": "jan", "day": 2},  # retrocede → 2009
        {"month": "nov", "day": 17},
        {"month": "feb", "day": 1},  # retrocede → 2010
    ]
    out = transform(make_raw(rows), infer_dates=True)
    assert out["fecha_contacto"].dt.strftime("%Y-%m-%d").tolist() == [
        "2008-05-05",
        "2008-12-30",
        "2009-01-02",
        "2009-11-17",
        "2010-02-01",
    ]


def test_inference_rejects_rows_not_in_chronological_order():
    rows = [{"month": "may", "day": 20}, {"month": "may", "day": 3}]  # el día retrocede
    with pytest.raises(TransformError, match="ordenadas"):
        transform(make_raw(rows), infer_dates=True)


def test_inference_rejects_impossible_dates():
    with pytest.raises(TransformError, match="imposibles"):
        infer_contact_dates(pd.Series([2]), pd.Series([31]))  # 31 de febrero


# ---------------------------------------------------------------- validación
def test_unexpected_category_is_rejected_not_silently_loaded():
    with pytest.raises(TransformError, match="job"):
        transform(make_raw([{"job": "astronaut"}]))


def test_unexpected_yes_no_value_is_rejected():
    with pytest.raises(TransformError, match="loan"):
        transform(make_raw([{"loan": "maybe"}]))


def test_empty_cells_in_source_are_rejected():
    raw = make_raw()
    raw.loc[0, "balance"] = None
    with pytest.raises(TransformError, match="balance"):
        transform(raw)


def test_out_of_range_values_are_reported():
    with pytest.raises(TransformError, match="edad"):
        transform(make_raw([{"age": 5}]))
    with pytest.raises(TransformError, match="duracion_seg"):
        transform(make_raw([{"duration": -3}]))


def test_pdays_below_minus_one_is_rejected():
    with pytest.raises(TransformError, match="pdays"):
        transform(make_raw([{"pdays": -5}]))


def test_validate_reports_all_problems_at_once():
    out = transform(make_raw([{}, {}]))
    out.loc[0, "edad"] = 3
    out.loc[1, "dia"] = 40
    with pytest.raises(TransformError) as exc:
        validate(out)
    assert "edad" in str(exc.value) and "dia" in str(exc.value)


# ---------------------------------------------------------------- extracción
def test_extract_missing_file(tmp_path):
    with pytest.raises(ExtractError, match="No existe"):
        extract(tmp_path / "nope.csv")


def test_extract_rejects_wrong_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a;b\n1;2\n", encoding="utf-8")
    with pytest.raises(ExtractError, match="Columnas inesperadas"):
        extract(bad)


def test_extract_rejects_empty_file(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text(";".join(EXPECTED_COLUMNS) + "\n", encoding="utf-8")
    with pytest.raises(ExtractError, match="no contiene filas"):
        extract(empty)


def test_extract_limit():
    assert len(extract(DATASET_DIR / "bank.csv", limit=25)) == 25


# ---------------------------------------------------------------- datos reales del repo
def test_real_sample_file_transforms_without_dates():
    out = transform(extract(DATASET_DIR / "bank.csv"))
    assert len(out) == 4521
    assert out["fecha_contacto"].isna().all()


def test_real_full_file_golden_numbers():
    """Cifras comprobadas a mano sobre bank-full.csv (45.211 filas, 5.289 suscripciones)."""
    out = transform(extract(DATASET_DIR / "bank-full.csv"), infer_dates=True)
    assert len(out) == 45211
    assert int(out["suscrito"].sum()) == 5289
    assert out["fecha_contacto"].min() == pd.Timestamp("2008-05-05")
    assert out["fecha_contacto"].max() == pd.Timestamp("2010-11-17")
    assert out["fecha_contacto"].is_monotonic_increasing
    assert int(out["profesion"].isna().sum()) == 288
    assert int(out["contactado_antes"].sum()) == 8257
