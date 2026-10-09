"""
Configuración centralizada, leída de variables de entorno.

Dentro de Docker Compose, ``POSTGRES_HOST`` y ``REDIS_HOST`` valen ``postgres`` y ``redis``
(nombres de servicio). Fuera de Docker (tests locales, CI) se usa ``localhost`` por defecto.
"""

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
import redis
from sqlalchemy import URL, Engine, create_engine

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "dataset"
SQL_DIR = ROOT / "sql"
DEFAULT_SOURCE = DATASET_DIR / "bank-full.csv"

DEFAULT_CACHE_TTL_SECONDS = 300


class ConfigError(RuntimeError):
    """Falta una variable de entorno obligatoria."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"Falta la variable de entorno {name}. "
            "Copia .env.example a .env y arranca con `docker compose`, "
            "o exporta las variables si trabajas fuera de Docker."
        )
    return value


@dataclass(frozen=True)
class PostgresSettings:
    host: str
    port: int
    user: str
    password: str
    dbname: str

    @classmethod
    def from_env(cls) -> PostgresSettings:
        return cls(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            user=_require("POSTGRES_USER"),
            password=_require("POSTGRES_PASSWORD"),
            dbname=_require("POSTGRES_DB"),
        )

    def url(self, dbname: str | None = None) -> URL:
        # URL.create escapa correctamente caracteres especiales en usuario y contraseña
        return URL.create(
            "postgresql+psycopg2",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=dbname or self.dbname,
        )


@dataclass(frozen=True)
class RedisSettings:
    host: str
    port: int
    password: str | None

    @classmethod
    def from_env(cls) -> RedisSettings:
        return cls(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", "6379")),
            password=os.environ.get("REDIS_PASSWORD") or None,
        )


def get_engine(settings: PostgresSettings | None = None, dbname: str | None = None) -> Engine:
    """Motor SQLAlchemy hacia PostgreSQL"""
    settings = settings or PostgresSettings.from_env()
    return create_engine(settings.url(dbname), pool_pre_ping=True)


def get_redis(settings: RedisSettings | None = None) -> redis.Redis:
    """Cliente Redis con timeouts cortos: si Redis cae, la caché se desactiva en vez de colgarse."""
    settings = settings or RedisSettings.from_env()
    return redis.Redis(
        host=settings.host,
        port=settings.port,
        password=settings.password,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def cache_ttl() -> int:
    return int(os.environ.get("CACHE_TTL_SECONDS", DEFAULT_CACHE_TTL_SECONDS))
