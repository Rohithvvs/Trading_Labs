"""Non-secret candle-backend identity for health checks and scan summaries."""
from __future__ import annotations

from datetime import date
from typing import Any

from ...config.settings import settings
from ...db.urls import public_db_target
from .symbol_parity import canonical_scan_symbol


def candle_backend_identity() -> dict[str, Any]:
    """Which candle store is selected. Never includes credentials."""
    backend = settings.candle_history_backend_name()
    if backend == "turso":
        return {
            "candle_backend": "turso",
            "database_type": "turso",
            "database_target": public_db_target(settings.turso_database_url),
            "silent_postgres_fallback": False,
        }
    return {
        "candle_backend": "postgres",
        "database_type": "postgres",
        "database_target": public_db_target(settings.database_url),
        "silent_postgres_fallback": False,
    }


def count_scan_repairs(fetch_report: dict[str, Any] | None) -> tuple[int, int]:
    """Return (repair_attempts, repair_failures) from a scan fetch report."""
    report = fetch_report or {}
    attempts = 0
    failures = 0
    daily = report.get("daily_sync") if isinstance(report.get("daily_sync"), dict) else {}
    if daily.get("history_from"):
        attempts += 1
        if daily.get("status") in {"TIMEOUT", "FAILED"} or daily.get("history_budget"):
            failures += 1
    elif daily.get("status") in {"TIMEOUT", "FAILED"}:
        attempts += 1
        failures += 1
    ensure = report.get("ensure") if isinstance(report.get("ensure"), dict) else {}
    ensure_status = str(ensure.get("status") or "")
    if ensure_status and ensure_status != "ALREADY_FRESH":
        attempts += 1
        if ensure_status in {"FAILED", "TIMEOUT"}:
            failures += 1
    repair = report.get("repair") if isinstance(report.get("repair"), dict) else {}
    if repair.get("error"):
        attempts += 1
        failures += 1
    if int(repair.get("cloned_rows_deleted") or 0) > 0:
        attempts += 1
    refill = repair.get("last_session_refill") if isinstance(repair.get("last_session_refill"), dict) else {}
    if refill.get("error"):
        failures += 1
    for row in repair.get("thin_history") or []:
        if isinstance(row, dict):
            attempts += 1
            if row.get("error"):
                failures += 1
    return attempts, failures


def build_scan_candle_diagnostics(
    *,
    evaluated: int,
    skipped: int,
    matched: int,
    latest_candle_date: str | None,
    symbols_on_scan_date: int,
    symbols_with_sufficient_history: int,
    fetch_report: dict[str, Any] | None,
    scan_started_at: str | None,
    scan_finished_at: str | None,
) -> dict[str, Any]:
    attempts, failures = count_scan_repairs(fetch_report)
    return {
        **candle_backend_identity(),
        "symbols_evaluated": int(evaluated),
        "symbols_skipped": int(skipped),
        "symbols_matched": int(matched),
        "latest_candle_date": latest_candle_date,
        "symbols_on_scan_date": int(symbols_on_scan_date),
        "symbols_with_sufficient_history": int(symbols_with_sufficient_history),
        "repair_attempts": attempts,
        "repair_failures": failures,
        "scan_started_at": scan_started_at,
        "scan_finished_at": scan_finished_at,
    }


async def coverage_snapshot(trade_date: date | None = None) -> dict[str, Any]:
    """Symbol coverage for one session on the selected candle backend only."""
    from .repository import max_equity_trade_date, symbols_on_trade_date

    latest = await max_equity_trade_date()
    target = trade_date or latest
    raw: set[str] = set()
    if target is not None:
        raw = await symbols_on_trade_date(target)
    symbols = sorted({canonical_scan_symbol(item) for item in raw if canonical_scan_symbol(item)})
    return {
        **candle_backend_identity(),
        "latest_trade_date": latest.isoformat() if isinstance(latest, date) else None,
        "trade_date": target.isoformat() if isinstance(target, date) else None,
        "symbol_count": len(symbols),
        "symbols": symbols,
    }
