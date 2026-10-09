"""Extracción: lee el CSV de UCI Bank Marketing (separador ;, 17 columnas)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

EXPECTED_COLUMNS = [
    "age", "job", "marital", "education", "default", "balance", "housing", "loan",
    "contact", "day", "month", "duration", "campaign", "pdays", "previous", "poutcome", "y",
]  # fmt: skip

_INT_COLUMNS = ["age", "balance", "day", "duration", "campaign", "pdays", "previous"]


class ExtractError(RuntimeError):
    """El fichero de origen no existe o no tiene el formato esperado."""


def extract(source: Path | str, *, limit: int | None = None) -> pd.DataFrame:
    """Lee ``source`` sin modificar los valores (la limpieza se hace en ``transform``)"""
    path = Path(source)
    if not path.is_file():
        raise ExtractError(f"No existe el fichero de origen: {path}")

    try:
        df = pd.read_csv(path, sep=";", nrows=limit, dtype={c: "int64" for c in _INT_COLUMNS})
    except (ValueError, pd.errors.ParserError) as exc:
        msg = f"No se pudo leer {path.name} como CSV de Bank Marketing: {exc}"
        raise ExtractError(msg) from exc

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    if missing or extra:
        raise ExtractError(
            f"Columnas inesperadas en {path.name}. Faltan: {missing or 'ninguna'}; "
            f"sobran: {extra or 'ninguna'}"
        )
    if df.empty:
        raise ExtractError(f"{path.name} no contiene filas")
    return df[EXPECTED_COLUMNS]
