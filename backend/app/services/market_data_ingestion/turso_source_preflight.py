"""Read-only preflight of local Postgres V1 candle tables.

Never uses DATABASE_URL, never opens Turso, never writes rows/files/checkpoints.
The default executor opens a read-only session; unit tests inject a fake executor
and must not call the default.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ...db.turso_schema import FORBIDDEN_V1_TABLES, V1_TABLES
from ...db.urls import is_local_postgres_url, public_db_target
from .source_policy import classify_daily_index_source
from .turso_exclusions import (
    NIFTY_INVALID_COUNT,
    PHANTOM_COUNT,
    classify_row_for_turso_copy,
    exclusion_set,
    load_exclusion_keys,
)
from .turso_migration_policy import MIGRATION_POLICY, ist_today
from .turso_migrate import EXPECTED_DAILY_COLUMNS, EXPECTED_INDEX_COLUMNS
from .validators.ohlcv_gate import validate_ohlcv_bar

FetchAll = Callable[[str, Mapping[str, Any]], list[dict[str, Any]]]

REQUIRED_KEY_OHLC = ("trade_date", "symbol", "open", "high", "low", "close", "volume")
PASSED_LINE = "PREFLIGHT PASSED — NO DATA WAS WRITTEN"
FAILED_LINE = "PREFLIGHT FAILED — NO DATA WAS WRITTEN"
FINAL_PASSED_LINE = "FINAL SOURCE PREFLIGHT PASSED — NO DATA WAS WRITTEN"
FINAL_FAILED_LINE = "FINAL SOURCE PREFLIGHT FAILED — NO DATA WAS WRITTEN"
HARDCODED_NIFTY_KEY = ("index_ohlcv", "NIFTY500", "2009-05-18")


class PreflightError(ValueError):
    """Configuration/source error before or during read-only inspect."""


def _expected_columns(table: str) -> tuple[str, ...]:
    if table == "daily_ohlcv":
        return EXPECTED_DAILY_COLUMNS
    return EXPECTED_INDEX_COLUMNS


def _symbol_where(symbols: list[str] | None) -> tuple[str, dict[str, Any]]:
    if not symbols:
        return "", {}
    params = {f"s{i}": sym for i, sym in enumerate(symbols)}
    placeholders = ", ".join(f":s{i}" for i in range(len(symbols)))
    return f" WHERE symbol IN ({placeholders})", params


def _sync_postgres_url(url: str) -> str:
    return (
        url.replace("postgresql+asyncpg://", "postgresql://", 1)
        .replace("postgresql+psycopg2://", "postgresql://", 1)
    )


def readonly_postgres_fetchall(url: str, sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
    """SELECT-only executor. Not used by unit tests."""
    from sqlalchemy import create_engine, text

    engine = create_engine(
        _sync_postgres_url(url),
        isolation_level="AUTOCOMMIT",
        connect_args={"options": "-c default_transaction_read_only=on"},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
            result = conn.execute(text(sql), dict(params))
            if not result.returns_rows:
                return []
            return [dict(row._mapping) for row in result]
    finally:
        engine.dispose()


def _require_local_source(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        raise PreflightError(
            "LOCAL_POSTGRES_DATABASE_URL is not set. DATABASE_URL is operational-only "
            "and will not be used as the inspect source."
        )
    if not is_local_postgres_url(raw):
        raise PreflightError(
            "Refusing non-local source "
            f"{public_db_target(raw)}. Source inspect only allows localhost / 127.0.0.1."
        )
    return raw


def _inspect_table(
    fetchall: FetchAll,
    table: str,
    *,
    symbols: list[str] | None,
) -> dict[str, Any]:
    exists_rows = fetchall(
        "SELECT EXISTS ("
        " SELECT 1 FROM information_schema.tables"
        " WHERE table_schema = 'public' AND table_name = :table"
        ") AS exists",
        {"table": table},
    )
    exists = bool(exists_rows and exists_rows[0].get("exists"))
    report: dict[str, Any] = {
        "table": table,
        "exists": exists,
        "row_count": None,
        "distinct_symbols": None,
        "min_trade_date": None,
        "max_trade_date": None,
        "columns_present": [],
        "columns_missing": list(_expected_columns(table)),
        "null_counts": {},
        "duplicate_pk_groups": None,
        "duplicate_pk_extra_rows": None,
        "invalid_ohlc": {},
    }
    if not exists:
        return report

    col_rows = fetchall(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = :table",
        {"table": table},
    )
    present = {str(r["column_name"]) for r in col_rows}
    expected = _expected_columns(table)
    report["columns_present"] = [c for c in expected if c in present]
    report["columns_missing"] = [c for c in expected if c not in present]
    if report["columns_missing"]:
        return report

    where_sql, where_params = _symbol_where(symbols)
    null_select = ", ".join(
        f"COUNT(*) FILTER (WHERE {col} IS NULL) AS null_{col}" for col in REQUIRED_KEY_OHLC
    )
    agg_rows = fetchall(
        f"SELECT COUNT(*) AS n, COUNT(DISTINCT symbol) AS symbols, "
        f"MIN(trade_date) AS min_d, MAX(trade_date) AS max_d, {null_select}, "
        "COUNT(*) FILTER (WHERE high < low) AS high_lt_low, "
        "COUNT(*) FILTER (WHERE open < low OR open > high) AS open_outside, "
        "COUNT(*) FILTER (WHERE close < low OR close > high) AS close_outside, "
        "COUNT(*) FILTER (WHERE volume < 0) AS neg_volume "
        f"FROM {table}{where_sql}",
        where_params,
    )
    agg = agg_rows[0] if agg_rows else {}
    report["row_count"] = int(agg.get("n") or 0)
    report["distinct_symbols"] = int(agg.get("symbols") or 0)
    report["min_trade_date"] = agg.get("min_d")
    report["max_trade_date"] = agg.get("max_d")
    report["null_counts"] = {col: int(agg.get(f"null_{col}") or 0) for col in REQUIRED_KEY_OHLC}
    report["invalid_ohlc"] = {
        "high_lt_low": int(agg.get("high_lt_low") or 0),
        "open_outside": int(agg.get("open_outside") or 0),
        "close_outside": int(agg.get("close_outside") or 0),
        "negative_volume": int(agg.get("neg_volume") or 0),
    }
    dup_rows = fetchall(
        "SELECT COUNT(*) AS duplicate_groups, "
        "COALESCE(SUM(cnt - 1), 0) AS extra_rows FROM ("
        f" SELECT COUNT(*) AS cnt FROM {table}{where_sql}"
        " GROUP BY trade_date, symbol HAVING COUNT(*) > 1"
        ") d",
        where_params,
    )
    dup = dup_rows[0] if dup_rows else {}
    report["duplicate_pk_groups"] = int(dup.get("duplicate_groups") or 0)
    report["duplicate_pk_extra_rows"] = int(dup.get("extra_rows") or 0)
    return report


def _table_failures(report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    name = report["table"]
    if not report["exists"]:
        failures.append(f"{name}: missing table")
        return failures
    if report["columns_missing"]:
        failures.append(f"{name}: missing columns {report['columns_missing']}")
    nulls = report.get("null_counts") or {}
    for col, n in nulls.items():
        if n:
            failures.append(f"{name}: {n} null {col} values")
    if report.get("duplicate_pk_groups"):
        failures.append(
            f"{name}: {report['duplicate_pk_groups']} duplicate (trade_date, symbol) groups"
        )
    invalid = report.get("invalid_ohlc") or {}
    for key, n in invalid.items():
        if n:
            failures.append(f"{name}: {n} {key} rows")
    return failures


def run_source_preflight(
    *,
    local_postgres_url: str | None,
    symbols: list[str] | None = None,
    tables: Sequence[str] | None = None,
    limit: int | None = None,
    batch_size: int = 500,
    fetchall: FetchAll | None = None,
) -> dict[str, Any]:
    """Inspect local V1 source tables. `fetchall` is required in tests (no live DB)."""
    url = _require_local_source(local_postgres_url)
    requested = tuple(tables or V1_TABLES)
    forbidden = [t for t in requested if t in FORBIDDEN_V1_TABLES]
    if forbidden:
        raise PreflightError(f"v1 preflight forbids {forbidden}")
    unknown = [t for t in requested if t not in V1_TABLES]
    if unknown:
        raise PreflightError(f"Unknown v1 tables: {unknown}. Allowed: {list(V1_TABLES)}")
    if fetchall is None:
        def fetchall(sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
            return readonly_postgres_fetchall(url, sql, params)

    table_reports = [
        _inspect_table(fetchall, table, symbols=symbols) for table in requested
    ]
    failures: list[str] = []
    for report in table_reports:
        failures.extend(_table_failures(report))
    size = max(int(batch_size), 1)
    for report in table_reports:
        rows = int(report.get("row_count") or 0)
        if limit is not None:
            rows = min(rows, int(limit))
        report["rows_planned"] = rows
        report["expected_batches"] = int(math.ceil(rows / size)) if rows else 0
    ok = not failures
    return {
        "ok": ok,
        "wrote": False,
        "turso_connected": False,
        "mode": "source-inspect",
        "source_target": public_db_target(url),
        "tables": table_reports,
        "filters": {
            "symbols": symbols or [],
            "tables": list(requested),
            "limit": limit,
            "batch_size": size,
        },
        "failures": failures,
        "final_line": PASSED_LINE if ok else FAILED_LINE,
    }


def format_preflight_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Source: {payload.get('source_target')}",
        f"Filters: {payload.get('filters')}",
        "Turso: not connected",
        "Wrote: false",
    ]
    for report in payload.get("tables") or []:
        lines.append(
            f"{report['table']}: exists={report['exists']} rows={report.get('row_count')} "
            f"symbols={report.get('distinct_symbols')} "
            f"min={report.get('min_trade_date')} max={report.get('max_trade_date')} "
            f"missing_cols={report.get('columns_missing')} "
            f"nulls={report.get('null_counts')} "
            f"dup_pk_groups={report.get('duplicate_pk_groups')} "
            f"invalid_ohlc={report.get('invalid_ohlc')} "
            f"batches={report.get('expected_batches')}"
        )
    if payload.get("failures"):
        lines.append("Failures:")
        lines.extend(f"  - {item}" for item in payload["failures"])
    lines.append(payload.get("final_line") or FAILED_LINE)
    return "\n".join(lines)


def _iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _load_repair_keys(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in data.get("items") or []:
        key = (
            str(item.get("table") or "daily_ohlcv"),
            str(item.get("symbol") or ""),
            _iso_date(item.get("trade_date")),
        )
        if not key[1] or not key[2] or key in seen:
            continue
        seen.add(key)
        items.append({"table": key[0], "symbol": key[1], "trade_date": key[2]})
    return items


def _fetch_invalid_ohlc_rows(fetchall: FetchAll, table: str) -> list[dict[str, Any]]:
    return fetchall(
        "SELECT trade_date, symbol, open, high, low, close, volume, source "
        f"FROM {table} WHERE high < low OR open < low OR open > high "
        "OR close < low OR close > high OR volume < 0 "
        "/* invalid_ohlc_keys */",
        {},
    )


def _fetch_source_counts(fetchall: FetchAll, table: str) -> list[dict[str, Any]]:
    rows = fetchall(
        "SELECT COALESCE(source, '') AS source, COUNT(*) AS n, "
        "MIN(trade_date) AS min_d, MAX(trade_date) AS max_d "
        f"FROM {table} GROUP BY source /* source_counts */",
        {},
    )
    out = []
    for row in rows:
        out.append(
            {
                "source": row.get("source") or "",
                "n": int(row.get("n") or 0),
                "min_trade_date": row.get("min_d"),
                "max_trade_date": row.get("max_d"),
            }
        )
    out.sort(key=lambda r: (-r["n"], r["source"]))
    return out


def _fetch_non_fyers_rows(fetchall: FetchAll, table: str, *, sample_limit: int = 200) -> dict[str, Any]:
    count_rows = fetchall(
        f"SELECT COUNT(*) AS n FROM {table} WHERE source IS DISTINCT FROM 'FYERS' /* non_fyers_count */",
        {},
    )
    sample = fetchall(
        "SELECT trade_date, symbol, source "
        f"FROM {table} WHERE source IS DISTINCT FROM 'FYERS' "
        "ORDER BY trade_date, symbol LIMIT :lim /* non_fyers_keys */",
        {"lim": int(sample_limit)},
    )
    return {
        "count": int((count_rows[0] or {}).get("n") or 0) if count_rows else 0,
        "sample": [
            {
                "table": table,
                "symbol": str(r.get("symbol") or ""),
                "trade_date": _iso_date(r.get("trade_date")),
                "source": r.get("source"),
            }
            for r in sample
        ],
    }


def _fetch_live_1d_split(fetchall: FetchAll, table: str, today: str) -> dict[str, int]:
    in_progress = fetchall(
        f"SELECT COUNT(*) AS n FROM {table} "
        "WHERE source = 'FYERS_LIVE_1D' AND trade_date >= CAST(:d AS date) "
        "/* live_1d_in_progress */",
        {"d": today},
    )
    finalized = fetchall(
        f"SELECT COUNT(*) AS n FROM {table} "
        "WHERE source = 'FYERS_LIVE_1D' AND trade_date < CAST(:d AS date) "
        "/* live_1d_finalized */",
        {"d": today},
    )
    return {
        "in_progress": int((in_progress[0] or {}).get("n") or 0) if in_progress else 0,
        "finalized": int((finalized[0] or {}).get("n") or 0) if finalized else 0,
    }


def _fetch_repair_rows(
    fetchall: FetchAll,
    keys: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not keys:
        return []
    by_table: dict[str, list[dict[str, str]]] = {}
    for key in keys:
        by_table.setdefault(key["table"], []).append(key)
    found: list[dict[str, Any]] = []
    for table, table_keys in by_table.items():
        params: dict[str, Any] = {}
        clauses: list[str] = []
        for i, key in enumerate(table_keys):
            params[f"s{i}"] = key["symbol"]
            params[f"d{i}"] = key["trade_date"]
            clauses.append(f"(symbol = :s{i} AND trade_date = CAST(:d{i} AS date))")
        rows = fetchall(
            "SELECT trade_date, symbol, open, high, low, close, volume, source "
            f"FROM {table} WHERE {' OR '.join(clauses)} /* repair_keys */",
            params,
        )
        for row in rows:
            found.append({"table": table, **dict(row)})
    return found


def _classify_invalid_rows(
    *,
    table: str,
    rows: list[dict[str, Any]],
    excluded: set[tuple[str, str, str]],
) -> dict[str, Any]:
    expected_phantoms: list[dict[str, Any]] = []
    expected_nifty: list[dict[str, Any]] = []
    untracked_material: list[dict[str, Any]] = []
    rounding_accepted: list[dict[str, Any]] = []
    source_policy: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "")
        trade_date = _iso_date(row.get("trade_date"))
        key = (table, symbol, trade_date)
        payload = {
            "table": table,
            "symbol": symbol,
            "trade_date": trade_date,
            "source": row.get("source"),
        }
        if key in excluded:
            if key == HARDCODED_NIFTY_KEY:
                expected_nifty.append({**payload, "category": "hardcoded_nifty"})
            else:
                expected_phantoms.append({**payload, "category": "phantom_saturday"})
            continue
        decision = classify_row_for_turso_copy(table=table, row=row, excluded=excluded)
        if decision["category"] == "source_policy":
            source_policy.append({**payload, "reason": decision["reason"]})
            continue
        if decision["category"] == "ohlc_gate":
            untracked_material.append({**payload, "reason": decision["reason"]})
            continue
        reasons = validate_ohlcv_bar(row)
        if reasons:
            untracked_material.append({**payload, "reason": f"ohlc_gate:{reasons}"})
        else:
            rounding_accepted.append({**payload, "category": "sql_suspect_python_accept"})
    return {
        "expected_phantoms": expected_phantoms,
        "expected_nifty": expected_nifty,
        "untracked_material": untracked_material,
        "rounding_accepted": rounding_accepted,
        "source_policy": source_policy,
    }


def _assess_repair_rows(rows: list[dict[str, Any]], expected_keys: list[dict[str, str]]) -> dict[str, Any]:
    found = {
        (str(r.get("table") or "daily_ohlcv"), str(r.get("symbol") or ""), _iso_date(r.get("trade_date"))): r
        for r in rows
    }
    repaired: list[dict[str, Any]] = []
    unrepaired: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for key in expected_keys:
        tuple_key = (key["table"], key["symbol"], key["trade_date"])
        row = found.get(tuple_key)
        if row is None:
            missing.append(key)
            continue
        source_ok = classify_daily_index_source(row.get("source"))["decision"] == "accept"
        ohlc_reasons = validate_ohlcv_bar(row)
        item = {
            **key,
            "source": row.get("source"),
            "source_fyers": source_ok,
            "ohlc_ok": not ohlc_reasons,
            "ohlc_reasons": ohlc_reasons,
        }
        if source_ok and not ohlc_reasons:
            repaired.append(item)
        else:
            unrepaired.append(item)
    return {
        "expected": len(expected_keys),
        "repaired": repaired,
        "unrepaired": unrepaired,
        "missing": missing,
        "repaired_count": len(repaired),
        "unrepaired_count": len(unrepaired),
        "missing_count": len(missing),
    }


def run_final_source_preflight(
    *,
    local_postgres_url: str | None,
    exclude_json_paths: Sequence[str] | None = None,
    repair_manifest_path: str | None = None,
    tables: Sequence[str] | None = None,
    batch_size: int = 500,
    fetchall: FetchAll | None = None,
    now_ist: datetime | None = None,
) -> dict[str, Any]:
    """Read-only V1 source inspect plus exclusion/repair classification."""
    payload = run_source_preflight(
        local_postgres_url=local_postgres_url,
        tables=tables,
        batch_size=batch_size,
        fetchall=fetchall,
    )
    url = _require_local_source(local_postgres_url)
    if fetchall is None:
        def fetchall(sql: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
            return readonly_postgres_fetchall(url, sql, params)

    paths = [Path(p) for p in (exclude_json_paths or [])]
    exclusions = load_exclusion_keys(paths)
    excluded = exclusion_set(exclusions)
    repair_path = Path(repair_manifest_path) if (repair_manifest_path or "").strip() else None
    repair_keys = _load_repair_keys(repair_path)

    classified_by_table: dict[str, Any] = {}
    expected_phantoms: list[dict[str, Any]] = []
    expected_nifty: list[dict[str, Any]] = []
    untracked_material: list[dict[str, Any]] = []
    rounding_accepted: list[dict[str, Any]] = []
    source_policy_rows: list[dict[str, Any]] = []
    source_counts: dict[str, list[dict[str, Any]]] = {}
    non_fyers: dict[str, Any] = {}
    additional_source_policy: list[dict[str, Any]] = []
    live_1d_split: dict[str, dict[str, int]] = {}
    repair_rows: list[dict[str, Any]] = []
    today_iso = ist_today(now_ist).isoformat()

    requested = tuple(tables or V1_TABLES)
    for table in requested:
        source_counts[table] = _fetch_source_counts(fetchall, table)
        non_fyers[table] = _fetch_non_fyers_rows(fetchall, table)
        live_1d_split[table] = _fetch_live_1d_split(fetchall, table, today_iso)
        for item in non_fyers[table]["sample"]:
            key = (table, item["symbol"], item["trade_date"])
            if key not in excluded:
                additional_source_policy.append(item)
        invalid_rows = _fetch_invalid_ohlc_rows(fetchall, table)
        classified = _classify_invalid_rows(table=table, rows=invalid_rows, excluded=excluded)
        classified_by_table[table] = {
            "sql_invalid_count": len(invalid_rows),
            "expected_phantoms": len(classified["expected_phantoms"]),
            "expected_nifty": len(classified["expected_nifty"]),
            "untracked_material": len(classified["untracked_material"]),
            "rounding_accepted": len(classified["rounding_accepted"]),
            "source_policy": len(classified["source_policy"]),
            "non_fyers_count": non_fyers[table]["count"],
            "live_1d_in_progress": live_1d_split[table]["in_progress"],
            "live_1d_finalized": live_1d_split[table]["finalized"],
        }
        expected_phantoms.extend(classified["expected_phantoms"])
        expected_nifty.extend(classified["expected_nifty"])
        untracked_material.extend(classified["untracked_material"])
        rounding_accepted.extend(classified["rounding_accepted"])
        source_policy_rows.extend(classified["source_policy"])

    if repair_keys:
        repair_rows = _fetch_repair_rows(fetchall, repair_keys)
    repair_assessment = _assess_repair_rows(repair_rows, repair_keys)

    source_total = sum(int(t.get("row_count") or 0) for t in payload.get("tables") or [])
    non_fyers_total = sum(int(v.get("count") or 0) for v in non_fyers.values())
    fyers_by_table = {
        table: next((int(item["n"]) for item in rows if item["source"] == "FYERS"), 0)
        for table, rows in source_counts.items()
    }
    fyers_total = sum(fyers_by_table.values())
    nifty_is_fyers = any(item.get("source") == "FYERS" for item in expected_nifty)
    fyers_material_invalid = len(expected_nifty) if nifty_is_fyers else 0
    fyers_material_invalid += sum(
        1 for item in untracked_material if item.get("source") == "FYERS"
    )
    expected_fyers_only = fyers_total - fyers_material_invalid
    live_1d_in_progress_total = sum(v["in_progress"] for v in live_1d_split.values())
    live_1d_finalized_total = sum(v["finalized"] for v in live_1d_split.values())
    v1_excluded = (
        len(expected_phantoms)
        + len(expected_nifty)
        + len(untracked_material)
        + live_1d_in_progress_total
    )
    expected_legacy = source_total - v1_excluded
    non_fyers_counts: dict[str, int] = {}
    for table, rows in source_counts.items():
        for item in rows:
            if item["source"] != "FYERS":
                non_fyers_counts[f"{table}:{item['source'] or '(empty)'}"] = item["n"]

    failures = []
    for report in payload.get("tables") or []:
        name = report["table"]
        if not report.get("exists"):
            failures.append(f"{name}: missing table")
            continue
        if report.get("columns_missing"):
            failures.append(f"{name}: missing columns {report['columns_missing']}")
        for col, n in (report.get("null_counts") or {}).items():
            if n:
                failures.append(f"{name}: {n} null {col} values")
        if report.get("duplicate_pk_groups"):
            failures.append(
                f"{name}: {report['duplicate_pk_groups']} duplicate (trade_date, symbol) groups"
            )

    if len(expected_phantoms) != PHANTOM_COUNT:
        failures.append(
            f"expected {PHANTOM_COUNT} Saturday phantom exclusions, found {len(expected_phantoms)}"
        )
    if len(expected_nifty) != NIFTY_INVALID_COUNT:
        failures.append(
            f"expected {NIFTY_INVALID_COUNT} NIFTY500 2009-05-18 exclusion, found {len(expected_nifty)}"
        )
    if untracked_material:
        failures.append(
            f"{len(untracked_material)} untracked material-invalid rows would be excluded at copy time"
        )
    if repair_keys and repair_assessment["unrepaired_count"]:
        failures.append(
            f"{repair_assessment['unrepaired_count']} repair-manifest rows are not FYERS+valid OHLC"
        )
    if repair_keys and repair_assessment["missing_count"]:
        failures.append(
            f"{repair_assessment['missing_count']} repair-manifest rows are missing from source"
        )

    ok = not failures
    return {
        "ok": ok,
        "wrote": False,
        "turso_connected": False,
        "mode": "final-source-preflight",
        "migration_policy": MIGRATION_POLICY,
        "ist_today": today_iso,
        "source_target": payload.get("source_target"),
        "tables": payload.get("tables"),
        "source_counts": source_counts,
        "non_fyers": {
            "by_table": {k: v["count"] for k, v in non_fyers.items()},
            "total": non_fyers_total,
            "additional_not_in_exclusion_sample": additional_source_policy[:20],
            "note": (
                "Under validated_legacy_backfill_v1, valid historical_candles and "
                "finalized FYERS_LIVE_1D rows are copied with original source preserved. "
                "Runtime writes remain FYERS-only. Saturday phantoms stay excluded."
            ),
        },
        "live_1d": {
            "rule": "next_day_ist: copy only trade_date < ist_today",
            "ist_today": today_iso,
            "in_progress": live_1d_in_progress_total,
            "finalized": live_1d_finalized_total,
            "by_table": live_1d_split,
        },
        "classified_by_table": classified_by_table,
        "non_fyers_source_counts": non_fyers_counts,
        "exclusions": {
            "file_keys": len(exclusions),
            "saturday_phantoms": {
                "expected": PHANTOM_COUNT,
                "found": len(expected_phantoms),
                "items": expected_phantoms,
            },
            "nifty500_2009_05_18": {
                "expected": NIFTY_INVALID_COUNT,
                "found": len(expected_nifty),
                "items": expected_nifty,
            },
            "untracked_material_invalid": {
                "count": len(untracked_material),
                "items": untracked_material,
            },
            "sql_invalid_python_accepted": {
                "count": len(rounding_accepted),
                "items": rounding_accepted[:20],
            },
            "source_policy_on_sql_invalid": {
                "count": len(source_policy_rows),
                "items": source_policy_rows[:20],
            },
        },
        "repair_manifest": repair_assessment,
        "expected_copy": {
            "source_row_count": source_total,
            "fyers_rows_by_table": fyers_by_table,
            "fyers_rows_total": fyers_total,
            "non_fyers_rows_total": non_fyers_total,
            "minus_saturday_phantoms": len(expected_phantoms),
            "minus_nifty500_invalid": len(expected_nifty),
            "minus_untracked_material_invalid": len(untracked_material),
            "minus_live_1d_in_progress": live_1d_in_progress_total,
            "minus_fyers_material_invalid": fyers_material_invalid,
            "expected_turso_v1_rows": expected_legacy,
            "expected_turso_v1_rows_fyers_only_not_used": expected_fyers_only,
            "policy": MIGRATION_POLICY,
            "note": (
                "validated_legacy_backfill_v1 copies FYERS + valid historical_candles + "
                "finalized FYERS_LIVE_1D. Excludes 48 Saturday phantoms, NIFTY500 "
                "2009-05-18, material-invalid OHLC, missing required fields, unresolved "
                "duplicate keys, and FYERS_LIVE_1D for ist_today or later. "
                "Original source is preserved. Runtime writes stay FYERS-only."
            ),
        },
        "filters": {
            "tables": list(requested),
            "exclude_json": [str(p) for p in paths],
            "repair_manifest": str(repair_path) if repair_path else "",
            "batch_size": max(int(batch_size), 1),
        },
        "failures": failures,
        "final_line": FINAL_PASSED_LINE if ok else FINAL_FAILED_LINE,
    }


def format_final_preflight_text(payload: dict[str, Any]) -> str:
    lines = [
        f"Source: {payload.get('source_target')}",
        f"Mode: {payload.get('mode')}",
        "Turso: not connected",
        "Wrote: false",
    ]
    for report in payload.get("tables") or []:
        lines.append(
            f"{report['table']}: rows={report.get('row_count')} "
            f"symbols={report.get('distinct_symbols')} "
            f"min={report.get('min_trade_date')} max={report.get('max_trade_date')} "
            f"dups={report.get('duplicate_pk_groups')} "
            f"invalid_ohlc={report.get('invalid_ohlc')}"
        )
    excl = payload.get("exclusions") or {}
    phantoms = excl.get("saturday_phantoms") or {}
    nifty = excl.get("nifty500_2009_05_18") or {}
    untracked = excl.get("untracked_material_invalid") or {}
    lines.append(
        f"Phantoms excluded (not deleted): {phantoms.get('found')}/{phantoms.get('expected')}"
    )
    lines.append(
        f"NIFTY500 2009-05-18 excluded (not repaired): {nifty.get('found')}/{nifty.get('expected')}"
    )
    lines.append(f"Untracked material-invalid: {untracked.get('count')}")
    repair = payload.get("repair_manifest") or {}
    lines.append(
        f"Repair manifest: expected={repair.get('expected')} "
        f"repaired={repair.get('repaired_count')} "
        f"unrepaired={repair.get('unrepaired_count')} "
        f"missing={repair.get('missing_count')}"
    )
    expected = payload.get("expected_copy") or {}
    live = payload.get("live_1d") or {}
    lines.append(f"Migration policy: {payload.get('migration_policy')}")
    lines.append(
        f"LIVE_1D finalized={live.get('finalized')} in_progress={live.get('in_progress')} "
        f"ist_today={live.get('ist_today')}"
    )
    lines.append(
        f"Source rows={expected.get('source_row_count')} "
        f"expected Turso {expected.get('policy')}={expected.get('expected_turso_v1_rows')}"
    )
    if payload.get("failures"):
        lines.append("Failures:")
        lines.extend(f"  - {item}" for item in payload["failures"])
    lines.append(payload.get("final_line") or FINAL_FAILED_LINE)
    return "\n".join(lines)
