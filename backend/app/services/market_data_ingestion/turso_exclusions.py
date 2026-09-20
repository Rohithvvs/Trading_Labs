"""Explicit Turso V1 copy exclusions. Never deletes local rows.

Skip list:
  - every key in phantom_rows_delete_review.json
  - hardcoded material-invalid NIFTY500 2009-05-18
  - any row that fails the OHLC gate at copy time

Skips are recorded in an exclusion report. They are not silent.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .turso_migration_policy import (
    MIGRATION_POLICY,
    classify_live_1d_finalization,
    classify_migration_source,
    ist_now,
)
from .validators.ohlcv_gate import validate_ohlcv_bar

HARDCODED_EXCLUSIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "index_ohlcv",
        "NIFTY500",
        "2009-05-18",
        "material_invalid_ohlc: close above high (FYERS and local); not one-tick",
    ),
)

PHANTOM_COUNT = 48
NIFTY_INVALID_COUNT = 1


def _iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def load_exclusion_keys(paths: list[Path] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in paths or []:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in data.get("items") or []:
            key = (
                str(item.get("table") or "daily_ohlcv"),
                str(item.get("symbol") or ""),
                _iso_date(item.get("trade_date")),
            )
            if not key[1] or not key[2] or key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "table": key[0],
                    "symbol": key[1],
                    "trade_date": key[2],
                    "reason": item.get("reason")
                    or item.get("calendar_status")
                    or "exclusion_file",
                    "source_file": Path(path).name,
                }
            )
    for table, symbol, trade_date, reason in HARDCODED_EXCLUSIONS:
        key = (table, symbol, trade_date)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "table": table,
                "symbol": symbol,
                "trade_date": trade_date,
                "reason": reason,
                "source_file": "hardcoded",
            }
        )
    out.sort(key=lambda r: (r["table"], r["symbol"], r["trade_date"]))
    return out


def exclusion_set(entries: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return {(e["table"], e["symbol"], e["trade_date"]) for e in entries}


def classify_row_for_turso_copy(
    *,
    table: str,
    row: dict[str, Any],
    excluded: set[tuple[str, str, str]],
    now_ist: datetime | None = None,
) -> dict[str, Any]:
    """Decide copy vs skip under validated_legacy_backfill_v1. Never mutates source."""
    symbol = str(row.get("symbol") or "")
    trade_date = _iso_date(row.get("trade_date"))
    source = row.get("source")
    key = (table, symbol, trade_date)
    clock = ist_now(now_ist)
    base = {
        "table": table,
        "symbol": symbol,
        "trade_date": trade_date,
        "source": source,
        "migration_policy": MIGRATION_POLICY,
    }
    if key in excluded:
        return {
            "action": "EXCLUDE_REPORTED",
            "copy": False,
            "category": "exclusion_set",
            "reason": "key listed in exclusion set",
            **base,
        }
    if not symbol or not trade_date:
        return {
            "action": "EXCLUDE_REPORTED",
            "copy": False,
            "category": "missing_required",
            "reason": "missing_symbol_or_trade_date",
            **base,
        }
    source_decision = classify_migration_source(source)
    if source_decision["decision"] != "accept":
        return {
            "action": "EXCLUDE_REPORTED",
            "copy": False,
            "category": "migration_source_rejected",
            "reason": f"migration_source:{source_decision['reason']}",
            **base,
        }
    if str(source or "").strip() == "FYERS_LIVE_1D":
        live = classify_live_1d_finalization(trade_date, now=clock)
        if not live["copy"]:
            return {
                "action": "EXCLUDE_REPORTED",
                "copy": False,
                "category": "live_1d_in_progress",
                "reason": live["reason"],
                "ist_today": live.get("ist_today"),
                **base,
            }
    reasons = validate_ohlcv_bar(
        {
            "trade_date": row.get("trade_date"),
            "symbol": symbol,
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("volume"),
            "source": source,
        }
    )
    if reasons:
        return {
            "action": "EXCLUDE_REPORTED",
            "copy": False,
            "category": "ohlc_gate",
            "reason": f"ohlc_gate:{reasons}",
            **base,
        }
    return {
        "action": "COPY",
        "copy": True,
        "category": "copy",
        "reason": None,
        **base,
    }


def expected_turso_v1_count(
    *,
    source_valid_rows: int | None,
    repaired_weekday_replacements: int = 0,
    phantom_saturday_rows: int = PHANTOM_COUNT,
    nifty_invalid_rows: int = NIFTY_INVALID_COUNT,
) -> dict[str, Any]:
    """Documented formula. Does not query a database."""
    formula = (
        "source_valid_rows - 48 Saturday phantom rows - 1 NIFTY500 invalid row "
        "+ successfully repaired weekday replacements"
    )
    expected = None
    if source_valid_rows is not None:
        expected = (
            int(source_valid_rows)
            - int(phantom_saturday_rows)
            - int(nifty_invalid_rows)
            + int(repaired_weekday_replacements)
        )
    return {
        "formula": formula,
        "source_valid_rows": source_valid_rows,
        "minus_saturday_phantoms": phantom_saturday_rows,
        "minus_nifty500_invalid": nifty_invalid_rows,
        "plus_repaired_weekday_replacements": repaired_weekday_replacements,
        "expected_turso_v1_count": expected,
        "note": (
            "Post-repair, repaired weekday rows are already in the source as valid FYERS "
            "bars and are not extra inserts. Prefer source_row_count - excluded_count."
        ),
    }


def write_exclusion_report(path: Path, entries: list[dict[str, Any]]) -> None:
    payload = {
        "wrote": False,
        "deleted": False,
        "item_count": len(entries),
        "items": entries,
        "note": "Exclusion report only. Local source rows were not deleted.",
    }
    Path(path).write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
