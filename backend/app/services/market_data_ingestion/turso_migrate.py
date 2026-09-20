"""Local-Postgres → Turso migration helpers (v1 daily_ohlcv + index_ohlcv).

Default paths are dry-run and never open Turso or the local production database.
Live writes require --execute and --confirm-local-backup and are not invoked by
unit tests.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ...db.turso import apply_v1_schema
from ...db.turso_schema import FORBIDDEN_V1_TABLES, V1_TABLES
from ...db.urls import public_db_target
from ...models.strategy_market_data import DailyOhlcv, IndexOhlcv

EXPECTED_DAILY_COLUMNS = (
    "trade_date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "delivery_qty",
    "delivery_pct",
    "turnover",
    "adtv_20",
    "source",
    "loaded_at",
)
EXPECTED_INDEX_COLUMNS = (
    "trade_date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "loaded_at",
)


def _model_columns(model: type) -> tuple[str, ...]:
    return tuple(col.name for col in model.__table__.columns)


def plan_v1_migration(
    *,
    source_url: str | None,
    symbols: list[str] | None = None,
    limit: int | None = None,
    tables: Sequence[str] | None = None,
    batch_size: int = 500,
    exclude_json_paths: Sequence[str] | None = None,
) -> dict[str, Any]:
    requested = tuple(tables or V1_TABLES)
    forbidden = [t for t in requested if t in FORBIDDEN_V1_TABLES]
    if forbidden:
        raise ValueError(
            f"v1 migration forbids {forbidden}. historical_candles is a later phase."
        )
    unknown = [t for t in requested if t not in V1_TABLES]
    if unknown:
        raise ValueError(f"Unknown v1 tables: {unknown}. Allowed: {list(V1_TABLES)}")

    daily_cols = _model_columns(DailyOhlcv)
    index_cols = _model_columns(IndexOhlcv)
    missing_daily = [c for c in EXPECTED_DAILY_COLUMNS if c not in daily_cols]
    missing_index = [c for c in EXPECTED_INDEX_COLUMNS if c not in index_cols]
    if missing_daily or missing_index:
        raise ValueError(
            f"Model/schema mismatch daily_missing={missing_daily} index_missing={missing_index}"
        )

    from pathlib import Path

    from .turso_exclusions import expected_turso_v1_count, load_exclusion_keys
    from .turso_migration_policy import MIGRATION_POLICY

    paths = [Path(p) for p in (exclude_json_paths or [])]
    exclusions = load_exclusion_keys(paths)
    return {
        "status": "DRY_RUN",
        "wrote": False,
        "deleted": False,
        "source_target": public_db_target(source_url),
        "tables": list(requested),
        "daily_columns": list(daily_cols),
        "index_columns": list(index_cols),
        "symbols": symbols or [],
        "limit": limit,
        "batch_size": int(batch_size),
        "local_postgres_source_set": bool((source_url or "").strip()),
        "exclusion_count": len(exclusions),
        "exclusions": exclusions,
        "migration_policy": MIGRATION_POLICY,
        "expected_count": expected_turso_v1_count(source_valid_rows=None),
        "note": (
            "Code-level plan only. No connection to local Postgres or Turso. "
            "Excluded keys are reported, never silently dropped, and never deleted locally. "
            "Live copy requires --execute --confirm-local-backup and "
            "LOCAL_POSTGRES_DATABASE_URL (no DATABASE_URL fallback)."
        ),
    }


def refuse_execute_without_backup(confirm_local_backup: bool) -> str | None:
    if not confirm_local_backup:
        return (
            "Refusing to write to Turso: pass --confirm-local-backup after taking a "
            "local PostgreSQL dump of trading_data."
        )
    return None


def refuse_live_migration(
    *,
    execute: bool,
    confirm_local_backup: bool,
    local_postgres_url: str | None,
) -> str | None:
    """Guards for a future live copy. Never falls back to DATABASE_URL."""
    if not execute:
        return None
    backup_msg = refuse_execute_without_backup(confirm_local_backup)
    if backup_msg:
        return backup_msg
    if not (local_postgres_url or "").strip():
        return (
            "Refusing live migration: LOCAL_POSTGRES_DATABASE_URL is not set. "
            "DATABASE_URL is operational-only and will not be used as the copy source."
        )
    return (
        "Live Turso upsert is gated for a later approved phase. Flags were accepted "
        "but this command will not open LOCAL_POSTGRES_DATABASE_URL or Turso yet."
    )


def schema_apply_result(*, execute: bool, client: Any | None = None) -> dict[str, Any]:
    if not execute:
        return apply_v1_schema(client or _NullClient(), execute=False)
    if client is None:
        raise RuntimeError("schema-apply --execute requires an injected or live Turso client")
    return apply_v1_schema(client, execute=True)


class _NullClient:
    def execute(self, sql: str, params=None):
        raise RuntimeError("dry-run client does not execute SQL")

    def executemany(self, sql: str, seq_of_params):
        raise RuntimeError("dry-run client does not execute SQL")

    def close(self) -> None:
        return None


def validate_models_against_v1_schema() -> dict[str, Any]:
    """Compare SQLAlchemy models to the committed Turso SQL (no live DB)."""
    from ...db.turso_schema import load_v1_schema_sql

    sql = load_v1_schema_sql().lower()
    missing: list[str] = []
    for col in EXPECTED_DAILY_COLUMNS:
        if col not in sql:
            missing.append(f"daily_ohlcv.{col}")
    for col in EXPECTED_INDEX_COLUMNS:
        if col not in sql:
            missing.append(f"index_ohlcv.{col}")
    created = {line.strip() for line in sql.splitlines() if "create table" in line}
    if any("historical_candles" in line for line in created):
        missing.append("unexpected historical_candles in v1 SQL")
    ok = not missing
    return {
        "ok": ok,
        "live_compare": False,
        "missing": missing,
        "tables": list(V1_TABLES),
        "note": "Static validation only. Live local-vs-Turso counts require a later --live run.",
    }
