"""Transformación: limpieza, tipado y enriquecimiento del dataset Bank Marketing.

Se hace todo en pandas, sin tocar la base de datos. El procedimiento es:
1. Renombra las columnas al español y traduce las categorías.
2. Convierte ``yes``/``no`` en booleanos.
3. Trata ``unknown`` como valor ausente (NULL) en las columnas categóricas.
4. Convierte ``pdays = -1`` ("no contactado antes") en NULL y deriva ``contactado_antes``.
5. Deduce la fecha completa del contacto (el CSV solo trae día y mes) cuando el fichero está
   ordenado cronológicamente, como ``bank-full.csv``.
6. Valida rangos y rechaza valores no previstos en vez de cargarlos en silencio.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

START_YEAR = 2008  # bank-full.csv empieza en mayo de 2008 (ver dataset/bank-names.txt)

COLUMN_MAP = {
    "age": "edad",
    "job": "profesion",
    "marital": "estado_civil",
    "education": "educacion",
    "default": "impago",
    "balance": "saldo",
    "housing": "vivienda",
    "loan": "prestamo",
    "contact": "canal_contacto",
    "day": "dia",
    "month": "mes",
    "duration": "duracion_seg",
    "campaign": "campana",
    "pdays": "dias_desde_contacto_previo",
    "previous": "contactos_previos",
    "poutcome": "resultado_previo",
    "y": "suscrito",
}

# None = "unknown" en el CSV, que se carga como NULL
CATEGORY_MAPS: dict[str, dict[str, str | None]] = {
    "job": {
        "admin.": "administrativo",
        "blue-collar": "obrero",
        "entrepreneur": "empresario",
        "housemaid": "empleado_hogar",
        "management": "directivo",
        "retired": "jubilado",
        "self-employed": "autónomo",
        "services": "servicios",
        "student": "estudiante",
        "technician": "técnico",
        "unemployed": "desempleado",
        "unknown": None,
    },
    "marital": {
        "married": "casado",
        "single": "soltero",
        "divorced": "divorciado_viudo",  # el dataset agrupa divorciados y viudos
    },
    "education": {
        "primary": "primaria",
        "secondary": "secundaria",
        "tertiary": "universitaria",
        "unknown": None,
    },
    "contact": {"cellular": "móvil", "telephone": "fijo", "unknown": None},
    "poutcome": {"failure": "fracaso", "success": "éxito", "other": "otro", "unknown": None},
}

BOOL_COLUMNS = ["default", "housing", "loan", "y"]
_BOOL_MAP = {"yes": True, "no": False}

MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}

TARGET_COLUMNS = [
    "contacto_id", "edad", "profesion", "estado_civil", "educacion", "impago", "saldo",
    "vivienda", "prestamo", "canal_contacto", "dia", "mes", "fecha_contacto", "duracion_seg",
    "campana", "contactado_antes", "dias_desde_contacto_previo", "contactos_previos",
    "resultado_previo", "suscrito",
]  # fmt: skip

_REQUIRED_NOT_NULL = [
    "edad", "estado_civil", "impago", "saldo", "vivienda", "prestamo", "dia", "mes",
    "duracion_seg", "campana", "contactado_antes", "contactos_previos", "suscrito",
]  # fmt: skip

_INT32_MAX = 2**31 - 1


class TransformError(ValueError):
    """Los datos no cumplen lo esperado; el mensaje enumera todos los problemas encontrados."""


def _clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.lower()


def _map_strict(series: pd.Series, mapping: dict, column: str) -> pd.Series:
    """Aplica ``mapping`` y falla si aparece un valor que no está contemplado."""
    cleaned = _clean_text(series)
    unexpected = sorted(set(cleaned.dropna().unique()) - set(mapping))
    if unexpected:
        raise TransformError(f"Valores no previstos en '{column}': {unexpected}")
    return cleaned.map(mapping).astype("object")


def infer_contact_dates(
    month: pd.Series, day: pd.Series, start_year: int = START_YEAR
) -> pd.Series:
    """Deduce la fecha completa a partir de mes y día, asumiendo un fichero ordenado por fecha.

    Cada vez que el mes retrocede (p. ej. de diciembre a enero) empieza un año nuevo. Se exige
    que el resultado sea una fecha válida y que quede ordenado cronológicamente; si no, el
    supuesto no se cumple y se lanza ``TransformError`` en lugar de inventar fechas.
    """
    months = month.to_numpy()
    year_offsets = np.concatenate(([0], np.cumsum(np.diff(months) < 0)))
    dates = pd.to_datetime(
        {"year": start_year + year_offsets, "month": months, "day": day.to_numpy()},
        errors="coerce",
    )
    dates = pd.Series(dates, index=month.index, name="fecha_contacto")
    if dates.isna().any():
        raise TransformError(
            f"No se puede deducir el año: {int(dates.isna().sum())} fechas imposibles "
            "(p. ej. 31 de febrero). ¿El fichero está ordenado por fecha?"
        )
    if not dates.is_monotonic_increasing:
        raise TransformError(
            "No se puede deducir el año: las filas no están ordenadas cronológicamente "
            "(bank.csv es una muestra aleatoria; usa bank-full.csv o desactiva la inferencia)."
        )
    return dates


def validate(df: pd.DataFrame) -> None:
    """Comprueba rangos y nulos sobre el DataFrame ya transformado"""
    problems: list[str] = []

    for column in _REQUIRED_NOT_NULL:
        nulls = int(df[column].isna().sum())
        if nulls:
            problems.append(f"'{column}' tiene {nulls} valores nulos")

    ranges = {
        "edad": (16, 110),
        "dia": (1, 31),
        "mes": (1, 12),
        "duracion_seg": (0, _INT32_MAX),
        "campana": (1, 32767),
        "contactos_previos": (0, 32767),
        "saldo": (-_INT32_MAX, _INT32_MAX),
    }
    for column, (low, high) in ranges.items():
        bad = int(((df[column] < low) | (df[column] > high)).sum())
        if bad:
            problems.append(f"'{column}' tiene {bad} valores fuera del rango [{low}, {high}]")

    if df["contacto_id"].duplicated().any():
        problems.append("'contacto_id' tiene valores duplicados")

    if problems:
        raise TransformError("Validación fallida: " + "; ".join(problems))


def transform(
    raw: pd.DataFrame, *, infer_dates: bool = False, start_year: int = START_YEAR
) -> pd.DataFrame:
    """Devuelve el DataFrame listo para cargar, con las columnas de ``TARGET_COLUMNS``"""
    df = raw.copy()

    if df.isna().any().any():
        cols = df.columns[df.isna().any()].tolist()
        raise TransformError(f"El CSV de origen tiene valores vacíos en: {cols}")

    for column, mapping in CATEGORY_MAPS.items():
        df[column] = _map_strict(df[column], mapping, column)

    for column in BOOL_COLUMNS:
        df[column] = _map_strict(df[column], _BOOL_MAP, column).astype("bool")

    df["month"] = _map_strict(df["month"], MONTHS, "month").astype("int64")

    if (df["pdays"] < -1).any():
        raise TransformError("'pdays' contiene valores menores que -1")
    df["contactado_antes"] = df["pdays"] != -1
    df["pdays"] = df["pdays"].where(df["pdays"] >= 0).astype("Int64")  # -1 → NULL

    df["fecha_contacto"] = (
        infer_contact_dates(df["month"], df["day"], start_year)
        if infer_dates
        else pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    )

    df = df.rename(columns=COLUMN_MAP)
    df["contacto_id"] = np.arange(1, len(df) + 1)

    df = df[TARGET_COLUMNS].reset_index(drop=True)
    validate(df)
    return df
