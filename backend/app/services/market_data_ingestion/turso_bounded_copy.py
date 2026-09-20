"""Approved bounded Turso copy: INFY-EQ daily_ohlcv, max 100 rows.

Reads local Postgres only. Upserts Turso daily_ohlcv. Never writes Postgres.
Never copies index_ohlcv or other symbols. Idempotent ON CONFLICT upsert.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from ...db.turso import DAILY_UPSERT_SQL, TursoClient
from ...db.urls import is_local_postgres_url, public_db_target
from .turso_exclusions import (
    classify_row_for_turso_copy,
    exclusion_set,
    load_exclusion_keys,
    write_exclusion_report,
)
from .turso_repository import daily_row_params

APPROVED_TEST_SYMBOL = "INFY-EQ"
APPROVED_TEST_TABLE = "daily_ohlcv"
APPROVED_MAX_LIMIT = 100
APPROVED_MAX_BATCH = 100


class BoundedCopyError(ValueError):
    pass


def validate_bounded_test_request(
    *,
    symbols: list[str] | None,
    tables: list[str] | None,
    limit: int | None,
    batch_size: int | None,
    local_postgres_url: str | None,
    exclude_json: str | None,
    exclusion_report: str | None,
    result_report: str | None,
    confirm_local_backup: bool,
) -> list[str]:
    errors: list[str] = []
    if not confirm_local_backup:
        errors.append("missing --confirm-local-backup")
    if not symbols:
        errors.append("missing --symbols")
    else:
        cleaned = [s.strip().upper() for s in symbols if s.strip()]
        if cleaned != [APPROVED_TEST_SYMBOL]:
            errors.append(
                f"approved test mode allows only {APPROVED_TEST_SYMBOL}, got {cleaned}"
            )
    if not tables:
        errors.append("missing --tables")
    else:
        cleaned_t = [t.strip() for t in tables if t.strip()]
        if cleaned_t != [APPROVED_TEST_TABLE]:
            errors.append(
                f"approved test mode allows only {APPROVED_TEST_TABLE}, got {cleaned_t}"
            )
    if limit is None:
        errors.append("missing --limit")
    elif int(limit) > APPROVED_MAX_LIMIT:
        errors.append(f"--limit {limit} exceeds approved maximum {APPROVED_MAX_LIMIT}")
    elif int(limit) < 1:
        errors.append("--limit must be >= 1")
    if batch_size is not None and int(batch_size) > APPROVED_MAX_BATCH:
        errors.append(f"--batch-size {batch_size} exceeds approved maximum {APPROVED_MAX_BATCH}")
    if not (exclude_json or "").strip():
        errors.append("missing --exclude-json")
    if not (exclusion_report or "").strip():
        errors.append("missing --exclusion-report")
    if not (result_report or "").strip():
        errors.append("missing --result-report")
    url = (local_postgres_url or "").strip()
    if not url:
        errors.append("LOCAL_POSTGRES_DATABASE_URL is not set")
    elif not is_local_postgres_url(url):
        errors.append(f"non-local source host {public_db_target(url)}")
    return errors


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value is not None else ""


def fetch_daily_symbol_rows(
    url: str,
    *,
    symbol: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Read-only SELECT from local daily_ohlcv. Never writes."""
    from sqlalchemy import create_engine, text

    sync = url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    engine = create_engine(
        sync,
        isolation_level="AUTOCOMMIT",
        connect_args={"options": "-c default_transaction_read_only=on", "connect_timeout": 10},
    )
    sql = (
        "SELECT trade_date, symbol, open, high, low, close, volume, "
        "delivery_qty, delivery_pct, turnover, adtv_20, source, loaded_at "
        "FROM daily_ohlcv WHERE symbol = :symbol ORDER BY trade_date ASC LIMIT :limit"
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
            rows = conn.execute(text(sql), {"symbol": symbol, "limit": int(limit)}).mappings().all()
            return [dict(r) for r in rows]
    finally:
        engine.dispose()


def run_bounded_infy_copy(
    *,
    local_postgres_url: str,
    turso_client: TursoClient,
    exclude_json_paths: list[str],
    exclusion_report_path: str,
    result_report_path: str,
    limit: int = 100,
    batch_size: int = 100,
    fetch_rows: Callable[..., list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Copy INFY-EQ daily bars to Turso. Postgres is read-only."""
    exclusions = load_exclusion_keys([Path(p) for p in exclude_json_paths])
    excluded = exclusion_set(exclusions)
    fetch = fetch_rows or fetch_daily_symbol_rows
    source_rows = fetch(local_postgres_url, symbol=APPROVED_TEST_SYMBOL, limit=int(limit))
    copied: list[dict[str, Any]] = []
    reported: list[dict[str, Any]] = []
    for row in source_rows:
        decision = classify_row_for_turso_copy(
            table=APPROVED_TEST_TABLE, row=row, excluded=excluded
        )
        if not decision["copy"]:
            reported.append(decision)
            continue
        copied.append(row)
    size = max(1, min(int(batch_size), APPROVED_MAX_BATCH, int(limit)))
    upserted = 0
    for i in range(0, len(copied), size):
        chunk = copied[i : i + size]
        upserted += int(
            turso_client.executemany(
                DAILY_UPSERT_SQL,
                [daily_row_params(r, loaded_at=_iso(r.get("loaded_at")) or None) for r in chunk],
            )
            or len(chunk)
        )
    write_exclusion_report(Path(exclusion_report_path), reported)
    result = {
        "status": "COPIED",
        "wrote_turso": True,
        "wrote_postgres": False,
        "deleted": False,
        "source_table": APPROVED_TEST_TABLE,
        "target_table": APPROVED_TEST_TABLE,
        "source_target": public_db_target(local_postgres_url),
        "symbol": APPROVED_TEST_SYMBOL,
        "limit": int(limit),
        "batch_size": size,
        "source_rows_read": len(source_rows),
        "copied": len(copied),
        "excluded_reported": len(reported),
        "upserted": upserted,
        "idempotent": True,
        "candle_history_backend": "postgres",
        "note": (
            "ON CONFLICT(trade_date, symbol) DO UPDATE. Rerun upserts the same keys; "
            "it does not duplicate rows or modify Postgres."
        ),
    }
    Path(result_report_path).write_text(
        json_dumps(result),
        encoding="utf-8",
    )
    result["exclusion_report"] = exclusion_report_path
    result["result_report"] = result_report_path
    return result


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n"
