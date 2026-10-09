import pytest

from src.config import ConfigError, PostgresSettings, RedisSettings, get_redis


def test_postgres_settings_from_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    s = PostgresSettings.from_env()
    assert (s.host, s.port, s.user, s.password, s.dbname) == ("localhost", 5432, "u", "p", "d")


@pytest.mark.parametrize("missing", ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"])
def test_missing_required_variable_gives_helpful_error(monkeypatch, missing):
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        monkeypatch.setenv(name, "x")
    monkeypatch.delenv(missing)
    with pytest.raises(ConfigError, match=missing):
        PostgresSettings.from_env()


def test_url_escapes_special_characters_in_password():
    s = PostgresSettings("db", 5432, "user", "p@ss:w/rd", "mydb")
    rendered = s.url().render_as_string(hide_password=False)
    assert "p%40ss%3Aw%2Frd" in rendered
    assert s.url().password == "p@ss:w/rd"


def test_url_can_target_another_database():
    s = PostgresSettings("db", 5432, "user", "pw", "mydb")
    assert s.url("otra").database == "otra"


def test_redis_settings_empty_password_means_no_auth(monkeypatch):
    monkeypatch.setenv("REDIS_PASSWORD", "")
    assert RedisSettings.from_env().password is None


def test_get_redis_builds_client_without_connecting():
    client = get_redis(RedisSettings("redis", 6379, "secreto"))
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["host"] == "redis"
    assert kwargs["password"] == "secreto"
    assert kwargs["decode_responses"] is True
