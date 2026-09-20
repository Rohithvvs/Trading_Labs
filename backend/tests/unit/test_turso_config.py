"""Unit tests for Turso/Postgres settings. No live database connections."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config.settings import Settings
from backend.app.db.turso import assert_startup_candle_history_config
from backend.app.db.urls import public_db_target

pytestmark = pytest.mark.unit

_TURSO_ENV = (
    "CANDLE_HISTORY_BACKEND",
    "TURSO_DATABASE_URL",
    "TURSO_AUTH_TOKEN",
    "NOVA_DATABASE_URL",
    "LOCAL_DATABASE_URL",
    "LOCAL_POSTGRES_DATABASE_URL",
    "DATABASE_URL",
)


@pytest.fixture
def clean_db_env(monkeypatch: pytest.MonkeyPatch):
    for key in _TURSO_ENV:
        monkeypatch.delenv(key, raising=False)
    yield monkeypatch


def test_default_backend_is_postgres(clean_db_env):
    s = Settings(_env_file=None)
    assert s.candle_history_backend_name() == "postgres"
    assert s.uses_turso_candle_history() is False
    assert_startup_candle_history_config(s)


def test_postgres_does_not_require_turso_credentials(clean_db_env):
    s = Settings(_env_file=None)
    assert s.turso_configured() is False
    assert s.local_postgres_source_url() == ""


def test_turso_backend_requires_credentials(clean_db_env):
    clean_db_env.setenv("CANDLE_HISTORY_BACKEND", "turso")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "TURSO_DATABASE_URL" in str(exc.value)
    assert "eyJ" not in str(exc.value)


def test_turso_backend_accepts_placeholders(clean_db_env):
    clean_db_env.setenv("CANDLE_HISTORY_BACKEND", "turso")
    clean_db_env.setenv("TURSO_DATABASE_URL", "libsql://example.invalid")
    clean_db_env.setenv("TURSO_AUTH_TOKEN", "test-token-not-real")
    s = Settings(_env_file=None)
    assert s.candle_history_backend_name() == "turso"
    assert s.turso_configured() is True
    assert_startup_candle_history_config(s)


def test_app_uses_database_url_not_local_postgres(clean_db_env):
    clean_db_env.setenv("DATABASE_URL", "postgresql://app-user:secret@db.example:5432/app")
    clean_db_env.setenv(
        "LOCAL_POSTGRES_DATABASE_URL",
        "postgresql://local-user:secret@localhost:5432/trading_data",
    )
    s = Settings(_env_file=None)
    assert "db.example" in s.database_url
    assert "trading_data" in s.local_postgres_source_url()
    assert s.database_url != s.local_postgres_source_url()


def test_local_postgres_does_not_fallback_to_database_url(clean_db_env):
    clean_db_env.setenv("DATABASE_URL", "postgresql://db.example/app")
    s = Settings(_env_file=None)
    assert s.local_postgres_source_url() == ""


def test_public_db_target_strips_userinfo():
    target = public_db_target(
        "postgresql+asyncpg://user:p%40ss@db.example:5432/trading_data?sslmode=require"
    )
    assert "p%40ss" not in target
    assert "user:" not in target
    assert "db.example:5432/trading_data" == target


def test_invalid_backend_rejected(clean_db_env):
    clean_db_env.setenv("CANDLE_HISTORY_BACKEND", "both")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
