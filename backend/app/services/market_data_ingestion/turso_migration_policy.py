"""One-time Turso V1 copy source policy. Separate from runtime writes.

Runtime daily/index upserts remain FYERS-only (``source_policy.py``).
This module is used only by the local→Turso migrator.

Policy name: ``validated_legacy_backfill_v1``.

Allowed copy sources (original ``source`` is preserved, never rewritten):
  - FYERS
  - historical_candles (validated OHLC, not in the phantom/invalid exclusion set)
  - FYERS_LIVE_1D when the session is finalized under the IST next-day rule

FYERS_LIVE_1D finalization (IST next-day rule):
  NSE cash session is 09:15–15:30 IST. Official EOD is scheduled 16:45 IST.
  A LIVE_1D bar for session D is finalized only when the current IST calendar
  date is strictly after D. Today's (and future) LIVE_1D rows are classified
  ``live_1d_in_progress`` and excluded for review — they are not copied and
  not deleted.

Duplicate ``(trade_date, symbol)`` precedence if more than one row is seen
(should not happen: source PK is unique; preflight found 0 duplicate groups):
  1. FYERS
  2. finalized FYERS_LIVE_1D
  3. historical_candles
  Same-rank duplicates → EXCLUDE_REPORTED ``duplicate_unresolved``.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NSE_CASH_CLOSE_IST = time(15, 30)
EOD_JOB_IST = time(16, 45)

MIGRATION_POLICY = "validated_legacy_backfill_v1"

MIGRATION_ALLOWED_SOURCES = frozenset({"FYERS", "historical_candles", "FYERS_LIVE_1D"})
MIGRATION_FORBIDDEN_SOURCES = frozenset(
    {
        "ACS",
        "acs",
        "authoritative_candle_store",
        "market_data.candles",
        "CANDLE_CACHE_DB",
        "MEMORY_CACHE",
    }
)
SOURCE_PRECEDENCE = ("FYERS", "FYERS_LIVE_1D", "historical_candles")


def ist_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(IST)
    if now.tzinfo is None:
        return now.replace(tzinfo=IST)
    return now.astimezone(IST)


def ist_today(now: datetime | None = None) -> date:
    return ist_now(now).date()


def classify_live_1d_finalization(
    trade_date: date | str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Next-day IST rule. Never copies today's in-progress session."""
    if isinstance(trade_date, str):
        day = date.fromisoformat(str(trade_date)[:10])
    else:
        day = trade_date
    today = ist_today(now)
    clock = ist_now(now)
    if day < today:
        return {
            "decision": "finalized",
            "copy": True,
            "reason": "live_1d_prior_ist_session",
            "ist_today": today.isoformat(),
            "trade_date": day.isoformat(),
            "ist_now": clock.isoformat(),
            "rule": "next_day_ist: trade_date < ist_today",
        }
    return {
        "decision": "in_progress",
        "copy": False,
        "reason": "live_1d_in_progress",
        "ist_today": today.isoformat(),
        "trade_date": day.isoformat(),
        "ist_now": clock.isoformat(),
        "nse_cash_close_ist": NSE_CASH_CLOSE_IST.isoformat(timespec="minutes"),
        "eod_job_ist": EOD_JOB_IST.isoformat(timespec="minutes"),
        "rule": (
            "next_day_ist: do not copy FYERS_LIVE_1D for ist_today or later; "
            "same-day bars stay on review even after 15:30/16:45"
        ),
    }


def classify_migration_source(source: Any) -> dict[str, Any]:
    raw = "" if source is None else str(source).strip()
    if raw in MIGRATION_ALLOWED_SOURCES:
        return {"decision": "accept", "reason": None, "source": raw}
    if not raw:
        return {"decision": "reject", "reason": "missing_source", "source": raw}
    if raw in MIGRATION_FORBIDDEN_SOURCES:
        return {"decision": "reject", "reason": f"forbidden_source:{raw}", "source": raw}
    return {"decision": "reject", "reason": f"unrecognized_source:{raw}", "source": raw}


def resolve_duplicate_key(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic winner for the same (trade_date, symbol). Never mutates rows."""
    if not rows:
        return {"action": "EXCLUDE_REPORTED", "copy": False, "category": "duplicate_unresolved", "reason": "empty"}
    if len(rows) == 1:
        return {"action": "COPY", "copy": True, "category": "copy", "row": rows[0], "reason": None}
    rank = {name: i for i, name in enumerate(SOURCE_PRECEDENCE)}
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        source = str(row.get("source") or "")
        if source not in rank:
            continue
        scored.append((rank[source], row))
    if not scored:
        return {
            "action": "EXCLUDE_REPORTED",
            "copy": False,
            "category": "duplicate_unresolved",
            "reason": "duplicate_key_no_ranked_source",
        }
    scored.sort(key=lambda item: item[0])
    best_rank = scored[0][0]
    winners = [row for rnk, row in scored if rnk == best_rank]
    if len(winners) != 1:
        return {
            "action": "EXCLUDE_REPORTED",
            "copy": False,
            "category": "duplicate_unresolved",
            "reason": f"duplicate_key_same_rank:{winners[0].get('source')}",
        }
    return {
        "action": "COPY",
        "copy": True,
        "category": "copy",
        "row": winners[0],
        "reason": f"duplicate_key_precedence:{SOURCE_PRECEDENCE[best_rank]}",
    }
