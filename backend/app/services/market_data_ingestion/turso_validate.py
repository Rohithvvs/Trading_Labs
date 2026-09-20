"""Local Postgres vs Turso validation helpers (v1 daily/index).

Live compare is not run in this phase. Unit tests feed in-memory snapshots.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def _iso(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _symbol_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by.setdefault(str(row["symbol"]), []).append(row)
    out: dict[str, dict[str, Any]] = {}
    for symbol, items in by.items():
        dates = sorted(_iso(r["trade_date"]) for r in items)
        keys = [(symbol, _iso(r["trade_date"])) for r in items]
        out[symbol] = {
            "count": len(items),
            "min_trade_date": dates[0] if dates else None,
            "max_trade_date": dates[-1] if dates else None,
            "duplicate_pk": len(keys) - len(set(keys)),
        }
    return out


def _sample_mismatches(
    local_rows: list[dict[str, Any]],
    turso_rows: list[dict[str, Any]],
    *,
    close_tolerance: float,
    sample_size: int,
) -> list[dict[str, Any]]:
    turso_by = {(str(r["symbol"]), _iso(r["trade_date"])): r for r in turso_rows}
    mismatches: list[dict[str, Any]] = []
    for row in local_rows[: max(sample_size, 0)]:
        key = (str(row["symbol"]), _iso(row["trade_date"]))
        other = turso_by.get(key)
        if other is None:
            mismatches.append({"key": key, "reason": "missing_in_turso"})
            continue
        for field in ("open", "high", "low", "close"):
            left = float(row[field])
            right = float(other[field])
            if abs(left - right) > close_tolerance:
                mismatches.append(
                    {
                        "key": key,
                        "field": field,
                        "local": left,
                        "turso": right,
                        "reason": "ohlcv_mismatch",
                    }
                )
                break
        loc_vol = int(row.get("volume") or 0)
        tur_vol = int(other.get("volume") or 0)
        if loc_vol != tur_vol:
            mismatches.append(
                {
                    "key": key,
                    "field": "volume",
                    "local": loc_vol,
                    "turso": tur_vol,
                    "reason": "volume_mismatch",
                }
            )
    return mismatches


def compare_history_snapshots(
    *,
    local_daily: list[dict[str, Any]],
    turso_daily: list[dict[str, Any]],
    local_index: list[dict[str, Any]] | None = None,
    turso_index: list[dict[str, Any]] | None = None,
    close_tolerance: float = 1e-6,
    sample_size: int = 20,
) -> dict[str, Any]:
    local_index = local_index or []
    turso_index = turso_index or []
    local_stats = _symbol_stats(local_daily)
    turso_stats = _symbol_stats(turso_daily)
    missing_symbols = sorted(set(local_stats) - set(turso_stats))
    extra_symbols = sorted(set(turso_stats) - set(local_stats))
    sample = _sample_mismatches(
        local_daily, turso_daily, close_tolerance=close_tolerance, sample_size=sample_size
    )
    local_dups = sum(v["duplicate_pk"] for v in local_stats.values())
    turso_dups = sum(v["duplicate_pk"] for v in turso_stats.values())
    mismatches: list[str] = []
    if len(local_daily) != len(turso_daily):
        mismatches.append("daily_row_count")
    if len(local_index) != len(turso_index):
        mismatches.append("index_row_count")
    if missing_symbols:
        mismatches.append("missing_symbols")
    if local_dups or turso_dups:
        mismatches.append("duplicate_pk")
    if sample:
        mismatches.append("sample_ohlcv")
    for symbol in sorted(set(local_stats) & set(turso_stats)):
        if local_stats[symbol]["count"] != turso_stats[symbol]["count"]:
            mismatches.append(f"count:{symbol}")
        if local_stats[symbol]["min_trade_date"] != turso_stats[symbol]["min_trade_date"]:
            mismatches.append(f"min:{symbol}")
        if local_stats[symbol]["max_trade_date"] != turso_stats[symbol]["max_trade_date"]:
            mismatches.append(f"max:{symbol}")
    ok = not mismatches
    return {
        "ok": ok,
        "live_compare": False,
        "daily_row_count": {"local": len(local_daily), "turso": len(turso_daily)},
        "index_row_count": {"local": len(local_index), "turso": len(turso_index)},
        "per_symbol_local": local_stats,
        "per_symbol_turso": turso_stats,
        "missing_symbols": missing_symbols,
        "extra_symbols": extra_symbols,
        "duplicate_pk": {"local": local_dups, "turso": turso_dups},
        "sample_mismatches": sample,
        "close_tolerance": close_tolerance,
        "mismatch_codes": sorted(set(mismatches)),
    }
