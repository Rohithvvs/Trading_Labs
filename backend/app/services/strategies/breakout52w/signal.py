"""BuySignal (state, not a cross) and first-failure assignment."""

from __future__ import annotations

import math

from .identity import MAX_POSITIONS


def _finite_pos(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value)) and float(value) > 0


def screener_pass(
    *,
    market_ok_flag: bool | None,
    close: float | None,
    prior_high: float | None,
    volume: float | None,
    vol_sma: float | None,
) -> bool:
    """TradingView Pine Screener legs: market + close vs prior 252-high + volume vs SMA20.

    Book constraints (held / sold today / free slots) are applied in ``buy_signal``.
    """
    if market_ok_flag is not True:
        return False
    if not _finite_pos(close) or prior_high is None or vol_sma is None:
        return False
    if volume is None or not math.isfinite(float(volume)):
        return False
    return float(close) >= float(prior_high) and float(volume) > float(vol_sma)


def buy_signal(
    *,
    market_ok_flag: bool | None,
    close: float | None,
    prior_high: float | None,
    volume: float | None,
    vol_sma: float | None,
    held: bool = False,
    sold_today: bool = False,
) -> bool:
    if held or sold_today:
        return False
    return screener_pass(
        market_ok_flag=market_ok_flag,
        close=close,
        prior_high=prior_high,
        volume=volume,
        vol_sma=vol_sma,
    )


def first_failure(
    *,
    in_universe: bool,
    data_source_failed: bool = False,
    prior_high: float | None = None,
    close: float | None = None,
    high: float | None = None,
    volume: float | None = None,
    vol_sma: float | None = None,
    market_ok_flag: bool | None = None,
    sold_today: bool = False,
    held: bool = False,
    buy_rank: int | None = None,
    free_slots: int = 0,
) -> str | None:
    """Earliest failing new-entry rule. HOLD names should not call this."""
    if held:
        return None
    if data_source_failed:
        return "data_source_failure"
    if not in_universe:
        return "not_in_universe"
    if prior_high is None:
        return "insufficient_history"
    if close is None or not math.isfinite(float(close)) or float(close) <= 0:
        return "missing_bar"
    if high is None or not math.isfinite(float(high)):
        return "missing_bar"
    if volume is None or not math.isfinite(float(volume)):
        return "missing_bar"
    if vol_sma is None:
        return "missing_bar"
    if float(close) < float(prior_high):
        return "close_below_prior_high"
    if float(volume) <= float(vol_sma):
        return "volume_not_above_average"
    if market_ok_flag is not True:
        return "market_filter_off"
    if sold_today:
        return "sold_today"
    if buy_rank is None or buy_rank > min(MAX_POSITIONS, max(free_slots, 0)) or free_slots <= 0:
        if buy_signal(
            market_ok_flag=market_ok_flag,
            close=close,
            prior_high=prior_high,
            volume=volume,
            vol_sma=vol_sma,
            held=False,
            sold_today=sold_today,
        ):
            return "no_free_slot"
        return "other"
    return None


def rank_candidates(pairs: list[tuple[str, float | None]]) -> list[tuple[str, float, int]]:
    """Momentum_60 desc, undefined last, then symbol asc. Rank is 1-based."""
    defined = [(s, float(m)) for s, m in pairs if m is not None and math.isfinite(float(m))]
    missing = [(s, float("-inf")) for s, m in pairs if m is None or not math.isfinite(float(m))]
    defined.sort(key=lambda item: (-item[1], item[0]))
    missing.sort(key=lambda item: item[0])
    ordered = defined + missing
    return [(sym, mom, i + 1) for i, (sym, mom) in enumerate(ordered)]
