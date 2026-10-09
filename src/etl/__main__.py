"""Punto de entrada:  python -m src.etl [--source dataset/bank.csv] [--limit 1000]"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from src.config import DEFAULT_SOURCE, ConfigError
from src.etl.extract import ExtractError
from src.etl.load import LoadError
from src.etl.pipeline import run
from src.etl.transform import TransformError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.etl",
        description="ETL de Bank Marketing: CSV -> pandas -> PostgreSQL (schema marketing).",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="CSV de origen (por defecto dataset/bank-full.csv; "
        "dataset/bank.csv es la muestra del 10%%)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Leer solo las N primeras filas")
    parser.add_argument(
        "--infer-dates",
        choices=["auto", "yes", "no"],
        default="auto",
        help="Deducir el año del contacto (solo válido si el CSV está ordenado por fecha). "
        "auto = solo con bank-full.csv",
    )
    parser.add_argument(
        "--no-cache-flush",
        action="store_true",
        help="No invalidar la caché de Redis al terminar",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    infer = {"auto": None, "yes": True, "no": False}[args.infer_dates]

    try:
        result = run(
            args.source,
            limit=args.limit,
            infer_dates=infer,
            flush_cache=not args.no_cache_flush,
        )
    except (ConfigError, ExtractError, TransformError, LoadError) as exc:
        logging.error("%s", exc)
        return 1
    except SQLAlchemyError as exc:
        logging.error("Error de base de datos: %s", getattr(exc, "orig", exc))
        return 1

    logging.info("ETL completado en %.2f s (%s filas)", result.seconds["total"], result.rows_loaded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
