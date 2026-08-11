"""Pre-scanner freshness gate for strategy-grade market data."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ...config.settings import settings
from .calendar_utils import expected_last_completed_session
from . import repository
from .load_tracking import latest_loads

logger = logging.getLogger("app.market_data_ingestion.freshness")


@dataclass
class FreshnessResult:
    ok: bool
    code: str
    expected_trade_date: date | None = None
    latest_equity_trade_date: date | None = None
    latest_index_trade_date: date | None = None
    equity_coverage_ratio: float = 0.0
    missing_symbol_count: int = 0
    missing_symbols_sample: list[str] = field(default_factory=list)
    index_present: bool = False
    reason: str | None = None
    remediation: str | None = None
    gate_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "expected_trade_date": self.expected_trade_date.isoformat() if self.expected_trade_date else None,
            "latest_equity_trade_date": self.latest_equity_trade_date.isoformat()
            if self.latest_equity_trade_date
            else None,
            "latest_index_trade_date": self.latest_index_trade_date.isoformat()
            if self.latest_index_trade_date
            else None,
            "equity_coverage_ratio": self.equity_coverage_ratio,
            "missing_symbol_count": self.missing_symbol_count,
            "missing_symbols_sample": self.missing_symbols_sample,
            "index_present": self.index_present,
            "reason": self.reason,
            "remediation": self.remediation,
            "gate_enabled": self.gate_enabled,
            "message": (
                "Strategy market data is fresh"
                if self.ok
                else "Strategy market data is not fresh enough to start scanner"
            ),
        }


async def evaluate_freshness(
    *,
    active_symbols: list[str] | None = None,
    expected: date | None = None,
) -> FreshnessResult:
    gate_on = settings.is_strategy_market_data_gate_enabled()
    threshold = float(settings.strategy_market_data_coverage_threshold)
    store_index = settings.strategy_index_store_symbol

    try:
        expected_date = expected or expected_last_completed_session()
    except Exception:
        return FreshnessResult(
            ok=False if gate_on else True,
            code="MARKET_DATA_STALE" if gate_on else "OK",
            reason="calendar_error",
            remediation="Check NSE holiday calendar configuration",
            gate_enabled=gate_on,
        )

    try:
        if active_symbols is None:
            from ...services.universe_service import UniverseService

            active_symbols = await UniverseService.get_active_nifty500_symbols()
    except Exception as exc:
        logger.warning("FRESHNESS_UNIVERSE_FAIL | %s", exc)
        return FreshnessResult(
            ok=not gate_on,
            code="MARKET_DATA_STALE" if gate_on else "OK",
            expected_trade_date=expected_date,
            reason="db_unavailable",
            remediation="Check database connectivity",
            gate_enabled=gate_on,
        )

    if not active_symbols:
        res = FreshnessResult(
            ok=not gate_on,
            code="MARKET_DATA_STALE" if gate_on else "OK",
            expected_trade_date=expected_date,
            reason="universe_empty",
            remediation="Seed NIFTY500 universe (import_stocks_master / CSV)",
            gate_enabled=gate_on,
        )
        return res

    try:
        present = await repository.symbols_present_on(expected_date, active_symbols)
        idx_ok = await repository.index_present(expected_date, store_index)
        latest_eq = await repository.max_equity_trade_date(active_symbols)
        latest_ix = await repository.max_index_trade_date(store_index)
    except Exception as exc:
        logger.warning("FRESHNESS_DB_FAIL | %s", exc)
        return FreshnessResult(
            ok=not gate_on,
            code="MARKET_DATA_STALE" if gate_on else "OK",
            expected_trade_date=expected_date,
            reason="db_unavailable",
            remediation="Check database / run migrations for daily_ohlcv",
            gate_enabled=gate_on,
        )

    missing = [s for s in active_symbols if s not in present]
    coverage = (len(active_symbols) - len(missing)) / len(active_symbols)

    if not present and latest_eq is None:
        reason = "no_equity_data"
    elif not idx_ok:
        reason = "index_missing"
    elif coverage < threshold:
        reason = "equity_incomplete"
    else:
        reason = None

    ok_data = reason is None
    # When gate disabled, report truth but do not block (ok=True for callers that only check ok when gate on)
    if not gate_on:
        return FreshnessResult(
            ok=True,
            code="OK" if ok_data else "MARKET_DATA_STALE",
            expected_trade_date=expected_date,
            latest_equity_trade_date=latest_eq,
            latest_index_trade_date=latest_ix,
            equity_coverage_ratio=coverage,
            missing_symbol_count=len(missing),
            missing_symbols_sample=missing[:25],
            index_present=idx_ok,
            reason=reason,
            remediation=(
                None
                if ok_data
                else "Run: python -m app.cli.market_data_cli daily-update  (or wait for post-close schedule)"
            ),
            gate_enabled=False,
        )

    if ok_data:
        return FreshnessResult(
            ok=True,
            code="OK",
            expected_trade_date=expected_date,
            latest_equity_trade_date=latest_eq,
            latest_index_trade_date=latest_ix,
            equity_coverage_ratio=coverage,
            missing_symbol_count=0,
            missing_symbols_sample=[],
            index_present=True,
            gate_enabled=True,
        )

    return FreshnessResult(
        ok=False,
        code="MARKET_DATA_STALE",
        expected_trade_date=expected_date,
        latest_equity_trade_date=latest_eq,
        latest_index_trade_date=latest_ix,
        equity_coverage_ratio=coverage,
        missing_symbol_count=len(missing),
        missing_symbols_sample=missing[:25],
        index_present=idx_ok,
        reason=reason,
        remediation="Run: python -m app.cli.market_data_cli daily-update  (or wait for post-close schedule)",
        gate_enabled=True,
    )


async def check_delivery_for_strategy(
    symbol: str,
    trade_date: date | None = None,
) -> dict[str, Any]:
    """STR-041 hard check: delivery fields required for signal generation."""
    d = trade_date or expected_last_completed_session()
    rows = await repository.fetch_equity_history(symbol, from_date=d)
    row = next((r for r in rows if r["trade_date"] == d), None)
    if not row:
        return {
            "ok": False,
            "code": "DELIVERY_DATA_MISSING",
            "symbol": symbol,
            "trade_date": d.isoformat(),
            "message": "No equity bar for session",
        }
    if row.get("delivery_qty") is None and row.get("delivery_pct") is None:
        return {
            "ok": False,
            "code": "DELIVERY_DATA_MISSING",
            "symbol": symbol,
            "trade_date": d.isoformat(),
            "message": "Delivery fields required for STR-041 are null",
        }
    return {
        "ok": True,
        "code": "OK",
        "symbol": symbol,
        "trade_date": d.isoformat(),
        "delivery_pct": row.get("delivery_pct"),
        "delivery_qty": row.get("delivery_qty"),
    }


async def status_snapshot() -> dict[str, Any]:
    freshness = await evaluate_freshness()
    loads = await latest_loads(5)
    return {
        "market_data_freshness": freshness.to_dict(),
        "last_loads": loads,
        "gate_enabled": settings.is_strategy_market_data_gate_enabled(),
    }
