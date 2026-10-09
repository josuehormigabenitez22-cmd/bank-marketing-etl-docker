"""Carga de consultas SQL con nombre desde ``sql/analytics.sql``.

El fichero marca cada consulta con una línea ``-- name: <identificador>``; todo lo que
sigue, hasta la siguiente marca, es la consulta (los comentarios ``--`` forman parte de ella).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from src.config import SQL_DIR

DEFAULT_QUERIES_FILE = SQL_DIR / "analytics.sql"
_NAME_RE = re.compile(r"^--\s*name:\s*(\w+)\s*$", re.MULTILINE)


def parse_queries(text: str) -> dict[str, str]:
    """Convierte el contenido de un fichero SQL en ``{nombre: consulta}``."""
    matches = list(_NAME_RE.finditer(text))
    queries: dict[str, str] = {}
    for i, match in enumerate(matches):
        name = match.group(1)
        if name in queries:
            raise ValueError(f"Consulta duplicada en el fichero SQL: {name!r}")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sql = text[match.end() : end].strip().rstrip(";").strip()
        if not sql:
            raise ValueError(f"La consulta {name!r} está vacía")
        queries[name] = sql
    return queries


@lru_cache(maxsize=4)
def load_queries(path: Path = DEFAULT_QUERIES_FILE) -> dict[str, str]:
    return parse_queries(Path(path).read_text(encoding="utf-8"))


def get_query(name: str, path: Path = DEFAULT_QUERIES_FILE) -> str:
    queries = load_queries(path)
    try:
        return queries[name]
    except KeyError:
        available = ", ".join(queries)
        raise KeyError(f"No existe la consulta {name!r}. Disponibles: {available}") from None
