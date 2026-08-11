"""Technical pre-qualification for RE lab engines (no decision scoring).

Used to gate pre-recommendation backtests: only technically qualified symbols
are backtested. Does not change engine thresholds or indicator math.
"""

from __future__ import annotations

from typing import Any

from .re001.eligibility import bull_stock_filter_pass as re001_eligible
from .re001.earnings import earnings_info_from_override, lookup_next_earnings
from .re001.regime import is_regime_usable as re001_regime_ok
from .re001.regime import map_market_regime as re001_map_regime
from .re001.technicals import build_re001_technicals
from .re002.eligibility import bull_stock_and_rs_prefilter as re002_eligible
from .re002.regime import is_regime_usable as re002_regime_ok
from .re002.regime import map_market_regime as re002_map_regime
from .re002.rs_features import extract_sector_rs
from .re002.technicals import build_re002_technicals


def precheck_re001(
    *,
    candles: list[Any],
    technical_results: list[Any],
    market_regime: Any,
    sector_overlay: Any = None,
    symbol: str = "",
    earnings_info: dict[str, Any] | None = None,
    capital: float | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Return (qualified, reason, technical_analysis_snapshot)."""
    regime = re001_map_regime(market_regime)
    if not re001_regime_ok(regime):
        return False, "missing_market_context", {}

    rs = None
    if sector_overlay is not None:
        try:
            v = getattr(sector_overlay, "sector_rs_20", None)
            if v is None and isinstance(sector_overlay, dict):
                v = sector_overlay.get("sector_rs_20")
            rs = float(v) if v is not None else None
        except (TypeError, ValueError):
            rs = None

    eligible, reasons = re001_eligible(
        candles=candles,
        technical_results=technical_results,
        sector_rs=rs,
    )
    if not eligible:
        return False, (reasons[0] if reasons else "bull_stock_filter_failed"), {}

    earn = earnings_info_from_override(earnings_info)
    if earn is None:
        earn = lookup_next_earnings(symbol)
    tech = build_re001_technicals(
        candles,
        technical_results,
        earnings_info=earn,
        capital=capital,
    )
    if tech.get("error"):
        return False, "technicals_error", tech
    if not tech.get("mandatory_gates_pass"):
        failed = (tech.get("decision") or {}).get("failed_gates") or []
        return False, f"gates_failed:{','.join(failed) or 'unknown'}", tech
    return True, "qualified", tech


def precheck_re002(
    *,
    candles: list[Any],
    technical_results: list[Any],
    market_regime: Any,
    sector_overlay: Any = None,
    benchmark_candles: list[Any] | None = None,
    benchmark_symbol: str | None = None,
    symbol: str = "",
    earnings_info: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Return (qualified, reason, technical_analysis_snapshot)."""
    regime = re002_map_regime(market_regime)
    if not re002_regime_ok(regime):
        return False, "missing_market_context", {}

    rs = extract_sector_rs(sector_overlay)
    eligible, reasons = re002_eligible(
        candles=candles,
        technical_results=technical_results,
        sector_rs=rs,
    )
    if not eligible:
        return False, (reasons[0] if reasons else "rs_prefilter_failed"), {}

    mr = market_regime
    if mr is not None and hasattr(mr, "model_dump"):
        mr = mr.model_dump()
    elif not isinstance(mr, dict):
        mr = {}
    so = sector_overlay
    if so is not None and hasattr(so, "model_dump"):
        so = so.model_dump()
    elif not isinstance(so, dict):
        so = {}

    tech = build_re002_technicals(
        candles,
        so,
        mr,
        benchmark_candles=benchmark_candles,
        benchmark_symbol=benchmark_symbol,
        symbol=symbol,
        earnings_info=earnings_info,
        load_benchmark_if_missing=True,
    )
    if tech.get("status") == "INSUFFICIENT_HISTORY" or tech.get("error"):
        return False, "insufficient_history", tech
    cond = tech.get("conditions") or {}
    # Core RE-002 technical breakout is the primary qualification gate for backtest.
    if not cond.get("relative_breakout"):
        return False, "relative_breakout_failed", tech
    return True, "qualified", tech
