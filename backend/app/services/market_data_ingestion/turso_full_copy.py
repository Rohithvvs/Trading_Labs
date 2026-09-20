"""Full Turso V1 copy: local Postgres daily_ohlcv + index_ohlcv.

Reads local Postgres only. Upserts Turso. Never writes/deletes Postgres.
Never deletes/truncates Turso. Idempotent ON CONFLICT upsert.
Live execution is gated by CLI --full --execute --confirm-local-backup.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ...db.turso import DAILY_UPSERT_SQL, INDEX_UPSERT_SQL, TursoClient
from ...db.turso_schema import FORBIDDEN_V1_TABLES, V1_TABLES
from ...db.urls import is_local_postgres_url, public_db_target
from .turso_exclusions import (
    classify_row_for_turso_copy,
    exclusion_set,
    load_exclusion_keys,
)
from .turso_migration_policy import MIGRATION_POLICY, ist_now
from .turso_repository import daily_row_params, index_row_params

DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 2000
FULL_TABLES = ("daily_ohlcv", "index_ohlcv")

DAILY_COLUMNS = (
    "trade_date, symbol, open, high, low, close, volume, "
    "delivery_qty, delivery_pct, turnover, adtv_20, source, loaded_at"
)
INDEX_COLUMNS = "trade_date, symbol, open, high, low, close, volume, source, loaded_at"

FetchPage = Callable[[str, str, str | None, str | None, int], list[dict[str, Any]]]


class FullCopyError(ValueError):
    pass


def validate_full_copy_request(
    *,
    full: bool,
    confirm_local_backup: bool,
    symbols: list[str] | None,
    tables: list[str] | None,
    limit: int | None,
    batch_size: int | None,
    local_postgres_url: str | None,
    exclude_json: str | None,
    exclusion_report: str | None,
    result_report: str | None,
    migration_policy: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not full:
        errors.append("missing --full")
    if not confirm_local_backup:
        errors.append("missing --confirm-local-backup")
    if symbols:
        errors.append("--full refuses --symbols; copy both V1 tables unfiltered")
    if limit is not None:
        errors.append("--full refuses --limit; use the bounded INFY test path instead")
    cleaned_t = [t.strip() for t in (tables or []) if t.strip()] or list(FULL_TABLES)
    forbidden = [t for t in cleaned_t if t in FORBIDDEN_V1_TABLES]
    if forbidden:
        errors.append(f"v1 copy forbids {forbidden}")
    unknown = [t for t in cleaned_t if t not in V1_TABLES]
    if unknown:
        errors.append(f"unknown v1 tables: {unknown}")
    if cleaned_t != list(FULL_TABLES):
        errors.append(f"--full requires tables {list(FULL_TABLES)}, got {cleaned_t}")
    size = DEFAULT_BATCH_SIZE if batch_size is None else int(batch_size)
    if size < 1 or size > MAX_BATCH_SIZE:
        errors.append(f"--batch-size must be 1..{MAX_BATCH_SIZE}")
    if not (exclude_json or "").strip():
        errors.append("missing --exclude-json")
    if not (exclusion_report or "").strip():
        errors.append("missing --exclusion-report")
    if not (result_report or "").strip():
        errors.append("missing --result-report")
    if (migration_policy or "").strip() != MIGRATION_POLICY:
        errors.append(f"full copy requires --migration-policy {MIGRATION_POLICY}")
    url = (local_postgres_url or "").strip()
    if not url:
        errors.append("LOCAL_POSTGRES_DATABASE_URL is not set")
    elif not is_local_postgres_url(url):
        errors.append(f"non-local source host {public_db_target(url)}")
    return errors


def _iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _iso_ts(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _columns(table: str) -> str:
    if table == "daily_ohlcv":
        return DAILY_COLUMNS
    return INDEX_COLUMNS


def _upsert_sql(table: str) -> str:
    if table == "daily_ohlcv":
        return DAILY_UPSERT_SQL
    return INDEX_UPSERT_SQL


def _row_params(table: str, row: dict[str, Any]) -> tuple[Any, ...]:
    loaded_at = _iso_ts(row.get("loaded_at"))
    if table == "daily_ohlcv":
        return daily_row_params(row, loaded_at=loaded_at)
    return index_row_params(row, loaded_at=loaded_at)


def fetch_v1_page(
    url: str,
    table: str,
    last_trade_date: str | None,
    last_symbol: str | None,
    batch_size: int,
) -> list[dict[str, Any]]:
    """Read-only keyset page from local V1 tables. Never writes."""
    if table not in V1_TABLES:
        raise FullCopyError(f"refusing to read non-v1 table {table}")
    from sqlalchemy import create_engine, text

    sync = url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    engine = create_engine(
        sync,
        isolation_level="AUTOCOMMIT",
        connect_args={"options": "-c default_transaction_read_only=on", "connect_timeout": 10},
    )
    cols = _columns(table)
    if last_trade_date is None:
        sql = (
            f"SELECT {cols} FROM {table} "
            "ORDER BY trade_date ASC, symbol ASC LIMIT :lim"
        )
        params: dict[str, Any] = {"lim": int(batch_size)}
    else:
        sql = (
            f"SELECT {cols} FROM {table} "
            "WHERE (trade_date > CAST(:d AS date)) "
            "OR (trade_date = CAST(:d AS date) AND symbol > :s) "
            "ORDER BY trade_date ASC, symbol ASC LIMIT :lim"
        )
        params = {"d": last_trade_date, "s": last_symbol or "", "lim": int(batch_size)}
    try:
        with engine.connect() as conn:
            conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
            rows = conn.execute(text(sql), params).mappings().all()
            return [dict(r) for r in rows]
    finally:
        engine.dispose()


def _append_progress(path: Path | None, event: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        import json

        handle.write(json.dumps(event, default=str, ensure_ascii=False) + "\n")


def run_full_v1_copy(
    *,
    local_postgres_url: str,
    turso_client: TursoClient,
    exclude_json_paths: list[str],
    exclusion_report_path: str,
    result_report_path: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    tables: tuple[str, ...] = FULL_TABLES,
    progress_path: str | None = None,
    fetch_page: FetchPage | None = None,
    now_ist: datetime | None = None,
) -> dict[str, Any]:
    """Copy both V1 tables to Turso. Postgres remains read-only."""
    if any(t in FORBIDDEN_V1_TABLES for t in tables):
        raise FullCopyError(f"v1 copy forbids {FORBIDDEN_V1_TABLES}")
    if tuple(tables) != FULL_TABLES:
        raise FullCopyError(f"full copy requires {FULL_TABLES}")
    size = max(1, min(int(batch_size), MAX_BATCH_SIZE))
    exclusions = load_exclusion_keys([Path(p) for p in exclude_json_paths])
    excluded = exclusion_set(exclusions)
    fetch = fetch_page or fetch_v1_page
    progress = Path(progress_path) if (progress_path or "").strip() else None
    clock = ist_now(now_ist)

    reported: list[dict[str, Any]] = []
    by_table: dict[str, dict[str, int]] = {}
    categories: dict[str, int] = {}
    copied_by_source: dict[str, int] = {}
    excluded_by_source: dict[str, int] = {}
    seen_keys: set[tuple[str, str, str]] = set()
    batches = 0
    for table in tables:
        last_date: str | None = None
        last_symbol: str | None = None
        stats = {
            "source_rows_read": 0,
            "copied": 0,
            "excluded": 0,
            "upserted": 0,
            "batches": 0,
        }
        while True:
            page = fetch(local_postgres_url, table, last_date, last_symbol, size)
            if not page:
                break
            copy_rows: list[dict[str, Any]] = []
            for row in page:
                stats["source_rows_read"] += 1
                symbol = str(row.get("symbol") or "")
                trade_date = _iso_date(row.get("trade_date"))
                key = (table, symbol, trade_date)
                source_label = str(row.get("source") or "") or "(empty)"
                if key in seen_keys:
                    decision = {
                        "action": "EXCLUDE_REPORTED",
                        "copy": False,
                        "category": "duplicate_unresolved",
                        "table": table,
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "source": row.get("source"),
                        "reason": "duplicate (trade_date, symbol) in source stream",
                        "migration_policy": MIGRATION_POLICY,
                    }
                else:
                    seen_keys.add(key)
                    decision = classify_row_for_turso_copy(
                        table=table, row=row, excluded=excluded, now_ist=clock
                    )
                if not decision["copy"]:
                    stats["excluded"] += 1
                    cat = str(decision.get("category") or "unknown")
                    categories[cat] = categories.get(cat, 0) + 1
                    excluded_by_source[source_label] = excluded_by_source.get(source_label, 0) + 1
                    reported.append(decision)
                    continue
                copied_by_source[source_label] = copied_by_source.get(source_label, 0) + 1
                copy_rows.append(row)
            if copy_rows:
                sql = _upsert_sql(table)
                upserted = int(
                    turso_client.executemany(
                        sql, [_row_params(table, r) for r in copy_rows]
                    )
                    or len(copy_rows)
                )
                stats["copied"] += len(copy_rows)
                stats["upserted"] += upserted
            stats["batches"] += 1
            batches += 1
            last = page[-1]
            last_date = _iso_date(last.get("trade_date"))
            last_symbol = str(last.get("symbol") or "")
            _append_progress(
                progress,
                {
                    "table": table,
                    "batch": stats["batches"],
                    "last_key": [last_date, last_symbol],
                    "copied": stats["copied"],
                    "excluded": stats["excluded"],
                    "read": stats["source_rows_read"],
                },
            )
            if len(page) < size:
                break
        by_table[table] = stats

    _write_full_exclusion_report(Path(exclusion_report_path), reported, categories)
    source_rows = sum(v["source_rows_read"] for v in by_table.values())
    copied = sum(v["copied"] for v in by_table.values())
    excluded_n = sum(v["excluded"] for v in by_table.values())
    upserted = sum(v["upserted"] for v in by_table.values())
    result = {
        "status": "COPIED",
        "wrote_turso": True,
        "wrote_postgres": False,
        "deleted": False,
        "source_target": public_db_target(local_postgres_url),
        "tables": list(tables),
        "batch_size": size,
        "batches": batches,
        "source_rows_read": source_rows,
        "copied": copied,
        "excluded_reported": excluded_n,
        "upserted": upserted,
        "exclusion_categories": categories,
        "copied_by_source": copied_by_source,
        "excluded_by_source": excluded_by_source,
        "migration_policy": MIGRATION_POLICY,
        "ist_today": clock.date().isoformat(),
        "by_table": by_table,
        "idempotent": True,
        "restart": "ON CONFLICT upsert; rerun copies the same keys without duplicates or deletes",
        "candle_history_backend": "postgres",
        "note": (
            "ON CONFLICT(trade_date, symbol) DO UPDATE. Source Postgres was not modified. "
            "Turso rows were not deleted. Original source labels were preserved. "
            "Runtime daily/index writes remain FYERS-only."
        ),
    }
    Path(result_report_path).write_text(
        _json_dumps(result),
        encoding="utf-8",
    )
    result["exclusion_report"] = exclusion_report_path
    result["result_report"] = result_report_path
    if progress is not None:
        result["progress_log"] = str(progress)
    return result


def _write_full_exclusion_report(
    path: Path,
    reported: list[dict[str, Any]],
    categories: dict[str, int],
) -> None:
    """Write every excluded key. Large sets use JSON summary + JSONL; never silent."""
    import json

    compact = [
        {
            "table": r.get("table"),
            "symbol": r.get("symbol"),
            "trade_date": r.get("trade_date"),
            "category": r.get("category"),
            "reason": r.get("reason"),
            "source": r.get("source"),
        }
        for r in reported
    ]
    jsonl_path = path.with_suffix(".jsonl")
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for item in compact:
            handle.write(json.dumps(item, default=str, ensure_ascii=False) + "\n")
    summary = {
        "wrote": False,
        "deleted": False,
        "item_count": len(compact),
        "categories": categories,
        "jsonl": str(jsonl_path.name),
        "items_sample": compact[:100],
        "note": (
            "Every excluded key is in the JSONL file. Local source rows were not deleted. "
            "Turso rows were not deleted."
        ),
    }
    path.write_text(json.dumps(summary, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")


def _json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n"
