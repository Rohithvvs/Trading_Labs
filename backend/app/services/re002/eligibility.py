"""Bull Stock Filter + Relative Strength pre-filter for RE-002."""

from __future__ import annotations

from typing import Any

from .strategy_config import WEAK_RS_THRESHOLD


def _tech_score(technical_results: list[Any]) -> float:
    if not technical_results:
        return 0.0
    t0 = technical_results[0]
    try:
        return float(getattr(t0, "score", None) or t0.get("score") or 0.0)  # type: ignore[union-attr]
    except Exception:
        return 0.0


def _close_and_mas(candles: list[Any]) -> tuple[float | None, float | None, float | None]:
    if not candles or len(candles) < 50:
        return None, None, None
    closes: list[float] = []
    for c in candles:
        try:
            closes.append(float(getattr(c, "close", None) or c["close"]))  # type: ignore[index]
        except Exception:
            continue
    if len(closes) < 50:
        return None, None, None
    price = closes[-1]
    sma50 = sum(closes[-50:]) / 50.0
    sma200 = sum(closes[-200:]) / 200.0 if len(closes) >= 200 else None
    return price, sma50, sma200


def bull_stock_and_rs_prefilter(
    *,
    candles: list[Any],
    technical_results: list[Any],
    sector_rs: float | None = None,
) -> tuple[bool, list[str]]:
    """Return (pass, reason_codes). Failures map to REJECT Decision Objects (never silent skip)."""
    reasons: list[str] = []
    price, sma50, sma200 = _close_and_mas(candles)
    if price is None or sma50 is None:
        return False, ["insufficient_history"]

    if price <= sma50:
        reasons.append("failed_bull_stock_filter")
    if sma200 is not None and price <= sma200:
        if "failed_bull_stock_filter" not in reasons:
            reasons.append("failed_bull_stock_filter")
    if sma200 is not None and sma50 < sma200:
        if "failed_bull_stock_filter" not in reasons:
            reasons.append("failed_bull_stock_filter")

    score = _tech_score(technical_results)
    if score < 52:
        if "failed_bull_stock_filter" not in reasons:
            reasons.append("failed_bull_stock_filter")

    # Relative Strength pre-filter — hard for RE-002 (never invent RS)
    if sector_rs is None:
        reasons.append("missing_relative_strength")
    elif sector_rs < WEAK_RS_THRESHOLD:
        reasons.append("weak_relative_strength")

    return (len(reasons) == 0, reasons)


def exceptional_rs_leader(
    *,
    technical_results: list[Any],
    sector_rs: float | None,
    exceptional_rs: float = 8.0,
) -> bool:
    score = _tech_score(technical_results)
    if score < 78:
        return False
    if sector_rs is None:
        return score >= 88
    return sector_rs >= exceptional_rs and score >= 78
