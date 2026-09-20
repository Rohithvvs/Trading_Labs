"""Bounded INFY-EQ local-vs-Turso compare. Read-only. No DML."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...db.urls import is_local_postgres_url, public_db_target
from .repair_manifest import FingerprintError, canonical_price, canonical_volume
from .turso_bounded_copy import APPROVED_MAX_LIMIT, APPROVED_TEST_SYMBOL, APPROVED_TEST_TABLE

OPTIONAL_NUM = ("delivery_qty", "delivery_pct", "turnover", "adtv_20")
PASSED = "TEST VALIDATION PASSED — NO DATA WAS WRITTEN"
FAILED = "TEST VALIDATION FAILED — NO DATA WAS WRITTEN"


def validate_infy_test_compare_request(
    *,
    symbols: list[str] | None,
    tables: list[str] | None,
    limit: int | None,
    local_postgres_url: str | None,
    output: str | None,
) -> list[str]:
    errors: list[str] = []
    if not symbols or [s.strip().upper() for s in symbols if s.strip()] != [APPROVED_TEST_SYMBOL]:
        errors.append("test validation allows only --symbols INFY-EQ")
    if not tables or [t.strip() for t in tables if t.strip()] != [APPROVED_TEST_TABLE]:
        errors.append("test validation allows only --tables daily_ohlcv")
    if limit is None or int(limit) != APPROVED_MAX_LIMIT:
        errors.append("test validation requires --limit 100")
    if not (output or "").strip():
        errors.append("missing --output turso_test_validation_infy.json")
    url = (local_postgres_url or "").strip()
    if not url:
        errors.append("LOCAL_POSTGRES_DATABASE_URL is not set")
    elif not is_local_postgres_url(url):
        errors.append(f"non-local source host {public_db_target(url)}")
    return errors


def _iso_date(value: Any) -> str:
    return str(value)[:10]


def _pk(row: dict[str, Any]) -> tuple[str, str]:
    return (_iso_date(row.get("trade_date")), str(row.get("symbol") or ""))


def canonical_loaded_at(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _opt_num(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return canonical_price(value)
    except FingerprintError:
        return str(value)


def compare_bounded_daily_rows(
    local_rows: list[dict[str, Any]],
    turso_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    local_keys = [_pk(r) for r in local_rows]
    turso_keys = [_pk(r) for r in turso_rows]
    local_set, turso_set = set(local_keys), set(turso_keys)
    missing = sorted(local_set - turso_set)
    extra = sorted(turso_set - local_set)
    local_dups = len(local_keys) - len(local_set)
    turso_dups = len(turso_keys) - len(turso_set)
    turso_by = {_pk(r): r for r in turso_rows}
    field_mismatches: list[dict[str, Any]] = []
    matched = 0
    for row in local_rows:
        key = _pk(row)
        other = turso_by.get(key)
        if other is None:
            continue
        matched += 1
        diffs: dict[str, Any] = {}
        try:
            for field in ("open", "high", "low", "close"):
                if canonical_price(row.get(field)) != canonical_price(other.get(field)):
                    diffs[field] = {
                        "local": canonical_price(row.get(field)),
                        "turso": canonical_price(other.get(field)),
                    }
            if canonical_volume(row.get("volume")) != canonical_volume(other.get("volume")):
                diffs["volume"] = {
                    "local": canonical_volume(row.get("volume")),
                    "turso": canonical_volume(other.get("volume")),
                }
        except FingerprintError as exc:
            diffs["canonical"] = str(exc)
        for field in OPTIONAL_NUM:
            if _opt_num(row.get(field)) != _opt_num(other.get(field)):
                diffs[field] = {"local": _opt_num(row.get(field)), "turso": _opt_num(other.get(field))}
        if str(row.get("source") or "") != str(other.get("source") or ""):
            diffs["source"] = {"local": row.get("source"), "turso": other.get("source")}
        if canonical_loaded_at(row.get("loaded_at")) != canonical_loaded_at(other.get("loaded_at")):
            diffs["loaded_at"] = {
                "local": canonical_loaded_at(row.get("loaded_at")),
                "turso": canonical_loaded_at(other.get("loaded_at")),
            }
        if diffs:
            field_mismatches.append({"key": list(key), "diffs": diffs})

    ok = (
        len(local_rows) == len(turso_rows)
        and not missing
        and not extra
        and local_dups == 0
        and turso_dups == 0
        and not field_mismatches
    )
    return {
        "ok": ok,
        "wrote": False,
        "live_compare": True,
        "symbol": APPROVED_TEST_SYMBOL,
        "table": APPROVED_TEST_TABLE,
        "local_count": len(local_rows),
        "turso_count": len(turso_rows),
        "matched_keys": matched,
        "missing_in_turso": [list(k) for k in missing],
        "extra_in_turso": [list(k) for k in extra],
        "local_duplicate_pk": local_dups,
        "turso_duplicate_pk": turso_dups,
        "field_mismatches": field_mismatches[:50],
        "field_mismatch_count": len(field_mismatches),
        "final_line": PASSED if ok else FAILED,
    }
