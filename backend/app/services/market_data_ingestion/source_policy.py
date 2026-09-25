"""Source allowlist for strategy-store daily_ohlcv / index_ohlcv writes.

ACS / historical_candles / live quote cache keep their own tables and are not
governed by this module. New daily-store sources require an explicit allowlist
update and code review.

Do not silently rename or rewrite ``source``. Rejected rows must not be upserted.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.market_data.source_policy")

# Official EOD from FyersEodProvider and live session forming bar (scanner overlay).
ALLOWED_DAILY_INDEX_SOURCES = frozenset({"FYERS", "FYERS_LIVE_1D"})

# Known cache/ACS/in-session tags that must never land in the scanner SoT.
FORBIDDEN_DAILY_INDEX_SOURCES = frozenset(
    {
        "historical_candles",
        "ACS",
        "acs",
        "authoritative_candle_store",
        "market_data.candles",
        "CANDLE_CACHE_DB",
        "MEMORY_CACHE",
    }
)


def classify_daily_index_source(source: Any) -> dict[str, Any]:
    raw = "" if source is None else str(source).strip()
    if raw in ALLOWED_DAILY_INDEX_SOURCES:
        return {"decision": "accept", "reason": None, "source": raw}
    if not raw:
        return {"decision": "reject", "reason": "missing_source", "source": raw}
    if raw in FORBIDDEN_DAILY_INDEX_SOURCES:
        return {"decision": "reject", "reason": f"forbidden_source:{raw}", "source": raw}
    return {"decision": "reject", "reason": f"unrecognized_source:{raw}", "source": raw}


def filter_strategy_store_sources(
    rows: list[dict[str, Any]],
    *,
    table_name: str,
    log_context: str = "daily_index_write",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (allowed, rejected). Does not mutate OHLC or substitute source names."""
    allowed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        classified = classify_daily_index_source(row.get("source"))
        if classified["decision"] == "accept":
            allowed.append(row)
            continue
        rejected.append({**row, "_source_policy_reason": classified["reason"]})
    if rejected:
        sample = [
            {
                "table": table_name,
                "symbol": r.get("symbol"),
                "trade_date": str(r.get("trade_date")) if r.get("trade_date") is not None else None,
                "source": r.get("source"),
                "reason": r.get("_source_policy_reason"),
            }
            for r in rejected[:10]
        ]
        logger.warning(
            "DAILY_STORE_SOURCE_REJECTED | context=%s | table=%s | rejected=%s | allowed=%s | sample=%s",
            log_context,
            table_name,
            len(rejected),
            len(allowed),
            sample,
        )
    return allowed, rejected
