"""RE-002 technical calculation layer — CRS, alignment, RVOL, RSI bounds, etc."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.re002.technicals import (
    MIN_ALIGNED_SESSIONS,
    RVOL_THRESHOLD,
    align_stock_benchmark,
    atr_stop,
    benchmark_rsi_pass,
    build_re002_technicals,
    candles_to_ohlcv_df,
    compute_crs_series,
    compute_crs_slope_3,
    compute_crs_sma21,
    earnings_clear,
    relative_breakout_pass,
    rvol_pass,
    stock_rsi_in_range,
)


def _candle(d: date, close: float, volume: float = 100_000.0, **kw):
    return SimpleNamespace(
        timestamp=d,
        open=kw.get("open", close),
        high=kw.get("high", close + 1),
        low=kw.get("low", close - 1),
        close=close,
        volume=volume,
    )


def _weekday_sessions(n: int, start: date) -> list[date]:
    days: list[date] = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _series(n: int, start: date, base_close: float, step: float = 1.0, vol: float = 100_000.0):
    days = _weekday_sessions(n, start)
    return [_candle(days[i], base_close + i * step, volume=vol) for i in range(n)]


# ---------------------------------------------------------------------------
# TEST 1 — CRS
# ---------------------------------------------------------------------------


def test_crs_price_ratio():
    stock = [_candle(date(2026, 1, 2), 1500.0)]
    bench = [_candle(date(2026, 1, 2), 12000.0)]
    sdf = candles_to_ohlcv_df(stock)
    bdf = candles_to_ohlcv_df(bench)
    aligned = align_stock_benchmark(sdf, bdf)
    crs = compute_crs_series(aligned)
    assert float(crs.iloc[0]) == pytest.approx(0.125)


# ---------------------------------------------------------------------------
# TEST 2 — CRS SMA21
# ---------------------------------------------------------------------------


def test_crs_sma21_is_mean_of_crs():
    # 21 known CRS values via constant stock/bench pairs
    stock_closes = [100 + i for i in range(21)]
    bench_closes = [1000.0] * 21
    expected_crs = [s / 1000.0 for s in stock_closes]
    expected_sma = sum(expected_crs) / 21.0

    start = date(2026, 1, 5)  # Monday
    stock = []
    bench = []
    d = start
    i = 0
    while len(stock) < 21:
        if d.weekday() < 5:
            stock.append(_candle(d, stock_closes[i]))
            bench.append(_candle(d, bench_closes[i]))
            i += 1
        d += timedelta(days=1)

    aligned = align_stock_benchmark(candles_to_ohlcv_df(stock), candles_to_ohlcv_df(bench))
    crs = compute_crs_series(aligned)
    sma = compute_crs_sma21(crs)
    assert float(sma.iloc[-1]) == pytest.approx(expected_sma)


# ---------------------------------------------------------------------------
# TEST 3 — CRS slope
# ---------------------------------------------------------------------------


def test_crs_slope_exact_difference():
    # Build synthetic CRS SMA series
    sma = pd.Series([0.10] * 20 + [0.120, 0.122, 0.123, 0.125])
    slope = compute_crs_slope_3(sma)
    # last: 0.125 - 0.120 = 0.005
    assert float(slope.iloc[-1]) == pytest.approx(0.005)


# ---------------------------------------------------------------------------
# TEST 4 / 5 — Relative breakout
# ---------------------------------------------------------------------------


def test_relative_breakout_pass_and_fail():
    assert relative_breakout_pass(0.125, 0.120) is True
    assert relative_breakout_pass(0.119, 0.120) is False
    assert relative_breakout_pass(0.120, 0.120) is False  # must be strictly greater


# ---------------------------------------------------------------------------
# TEST 6 — RSI boundary
# ---------------------------------------------------------------------------


def test_stock_rsi_boundaries():
    assert stock_rsi_in_range(50.0) is True
    assert stock_rsi_in_range(70.0) is True
    assert stock_rsi_in_range(49.99) is False
    assert stock_rsi_in_range(70.01) is False
    assert stock_rsi_in_range(None) is False


# ---------------------------------------------------------------------------
# TEST 7 — RVOL boundary
# ---------------------------------------------------------------------------


def test_rvol_boundaries():
    assert rvol_pass(1.20) is True
    assert rvol_pass(1.19) is False
    assert rvol_pass(RVOL_THRESHOLD) is True
    assert rvol_pass(None) is False


# ---------------------------------------------------------------------------
# TEST 8 — Benchmark RSI
# ---------------------------------------------------------------------------


def test_benchmark_rsi_boundaries():
    assert benchmark_rsi_pass(40.0) is True
    assert benchmark_rsi_pass(39.99) is False
    assert benchmark_rsi_pass(None) is False


# ---------------------------------------------------------------------------
# TEST 9 — CRS alignment (missing benchmark session)
# ---------------------------------------------------------------------------


def test_alignment_drops_missing_benchmark_session():
    stock = [
        _candle(date(2026, 1, 5), 100),
        _candle(date(2026, 1, 6), 101),
        _candle(date(2026, 1, 7), 102),
    ]
    # Missing 2026-01-06 on benchmark
    bench = [
        _candle(date(2026, 1, 5), 1000),
        _candle(date(2026, 1, 7), 1002),
    ]
    aligned = align_stock_benchmark(candles_to_ohlcv_df(stock), candles_to_ohlcv_df(bench))
    assert len(aligned) == 2
    sessions = set(aligned["session_date"].tolist())
    assert date(2026, 1, 6) not in sessions
    # Must not invent a pair for missing day
    crs = compute_crs_series(aligned)
    assert float(crs.iloc[0]) == pytest.approx(0.1)
    assert float(crs.iloc[1]) == pytest.approx(102 / 1002)


# ---------------------------------------------------------------------------
# TEST 10 — Chronological ordering
# ---------------------------------------------------------------------------


def test_unsorted_candles_are_sorted_before_crs():
    # Provide reverse-order dates
    stock = [
        _candle(date(2026, 1, 7), 102),
        _candle(date(2026, 1, 5), 100),
        _candle(date(2026, 1, 6), 101),
    ]
    bench = [
        _candle(date(2026, 1, 7), 1002),
        _candle(date(2026, 1, 5), 1000),
        _candle(date(2026, 1, 6), 1001),
    ]
    sdf = candles_to_ohlcv_df(stock)
    bdf = candles_to_ohlcv_df(bench)
    assert list(sdf["session_date"]) == sorted(sdf["session_date"])
    aligned = align_stock_benchmark(sdf, bdf)
    assert list(aligned["session_date"]) == sorted(aligned["session_date"])
    crs = compute_crs_series(aligned)
    # Chronological CRS: 100/1000, 101/1001, 102/1002
    assert float(crs.iloc[0]) == pytest.approx(0.1)
    assert float(crs.iloc[-1]) == pytest.approx(102 / 1002)


# ---------------------------------------------------------------------------
# TEST 11 — Insufficient history
# ---------------------------------------------------------------------------


def test_insufficient_history_status():
    stock = _series(10, date(2026, 1, 5), 100.0)
    bench = _series(10, date(2026, 1, 5), 1000.0)
    tech = build_re002_technicals(
        stock,
        {},
        {},
        benchmark_candles=bench,
        benchmark_symbol="NIFTY500",
        load_benchmark_if_missing=False,
        earnings_info={"earnings_clear": True, "trading_sessions_until": 20},
    )
    assert tech["status"] == "INSUFFICIENT_HISTORY"
    assert tech["relative_strength"]["crs"] is None
    assert tech["baseline"] == {} or tech.get("error")


# ---------------------------------------------------------------------------
# Full technical payload with enough history
# ---------------------------------------------------------------------------


def test_full_technicals_payload_with_aligned_history():
    n = 80
    stock = _series(n, date(2025, 10, 1), 100.0, step=0.5, vol=100_000)
    # Last bar volume spike for RVOL visibility
    last = stock[-1]
    stock[-1] = _candle(last.timestamp, last.close, volume=200_000)
    bench = _series(n, date(2025, 10, 1), 1000.0, step=0.2, vol=1_000_000)

    tech = build_re002_technicals(
        stock,
        {},
        {"market_state": "FAVORABLE"},
        benchmark_candles=bench,
        benchmark_symbol="NIFTY500",
        symbol="TEST",
        load_benchmark_if_missing=False,
        earnings_info={
            "next_earnings_date": "2026-12-01",
            "trading_sessions_until": 30,
            "earnings_clear": True,
        },
    )
    assert tech["status"] == "OK"
    assert tech["engine_id"] == "RE-002"
    assert tech["benchmark"]["symbol"] == "NIFTY500"
    assert tech["relative_strength"]["crs"] is not None
    assert tech["relative_strength"]["crs_sma21"] is not None
    assert tech["relative_strength"]["crs_slope_3"] is not None
    assert isinstance(tech["relative_strength"]["relative_breakout"], bool)
    assert tech["momentum"]["lower_threshold"] == 50.0
    assert tech["momentum"]["upper_threshold"] == 70.0
    assert tech["volume"]["threshold"] == 1.2
    assert tech["benchmark"]["rsi_threshold"] == 40.0
    assert tech["volatility"]["atr_multiplier"] == 2.0
    assert tech["volatility"]["atr14"] is not None
    assert tech["volatility"]["atr_stop"] == pytest.approx(
        atr_stop(tech["volatility"]["entry"], tech["volatility"]["atr14"])
    )
    assert tech["earnings"]["threshold"] == 7
    # CRS = stock/bench at last aligned session
    assert tech["relative_strength"]["crs"] == pytest.approx(
        tech["baseline"]["stock_price"] / tech["benchmark"]["close"]
    )
    # No sector_rs_20 proxy
    assert tech["relative_strength"]["crs"] != tech.get("sector_rs_20")


def test_atr_stop_formula():
    assert atr_stop(1520.0, 34.5, 2.0) == pytest.approx(1451.0)


def test_earnings_clear_threshold_7():
    assert earnings_clear(7) is False  # within 7 → not clear
    assert earnings_clear(8) is True
    assert earnings_clear(0) is False
    assert earnings_clear(None) is True  # unknown fail-open


def test_does_not_use_sector_rs_proxy_as_crs():
    """Even if sector_overlay has sector_rs_20, CRS must be price ratio."""
    n = 40
    stock = _series(n, date(2025, 11, 3), 1500.0, step=0.0)
    bench = _series(n, date(2025, 11, 3), 12000.0, step=0.0)
    tech = build_re002_technicals(
        stock,
        {"sector_rs_20": 99.9, "sector_index_symbol": "NIFTY50"},
        {},
        benchmark_candles=bench,
        benchmark_symbol="NIFTY500",
        load_benchmark_if_missing=False,
        earnings_info={"trading_sessions_until": 30},
    )
    assert tech["status"] == "OK"
    assert tech["relative_strength"]["crs"] == pytest.approx(0.125)
    assert tech["benchmark"]["symbol"] == "NIFTY500"
    # Must not equal the proxy
    assert tech["relative_strength"]["crs"] != pytest.approx(99.9)


def test_min_aligned_constant():
    assert MIN_ALIGNED_SESSIONS == 24
