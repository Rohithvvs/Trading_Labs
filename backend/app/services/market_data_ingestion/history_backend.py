"""Candle-history backend router.

Default is postgres (existing SQLAlchemy repository). Turso is selected only when
CANDLE_HISTORY_BACKEND=turso. Callers of repository.py are unchanged until Phase 7;
this module is the explicit routing point.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from ...config.settings import settings

POSTGRES = "postgres"
TURSO = "turso"


def candle_history_backend() -> str:
    return settings.candle_history_backend_name()


def uses_turso() -> bool:
    return candle_history_backend() == TURSO


def uses_postgres() -> bool:
    return not uses_turso()


def assert_not_writing_candles_to_wrong_backend(*, want_turso: bool) -> None:
    """Guard used by tests and future writers."""
    if want_turso and uses_postgres():
        raise RuntimeError("Refusing Turso candle write while CANDLE_HISTORY_BACKEND=postgres")
    if not want_turso and uses_turso():
        raise RuntimeError("Refusing Postgres candle write while CANDLE_HISTORY_BACKEND=turso")


async def fetch_equity_history(
    symbol: str,
    *,
    from_date: date | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if uses_turso():
        from . import turso_repository as impl
    else:
        from . import repository as impl
    return await impl.fetch_equity_history(symbol, from_date=from_date, limit=limit)


async def fetch_index_history(
    symbol: str,
    *,
    from_date: date | None = None,
) -> list[dict[str, Any]]:
    if uses_turso():
        from . import turso_repository as impl
    else:
        from . import repository as impl
    return await impl.fetch_index_history(symbol, from_date=from_date)
