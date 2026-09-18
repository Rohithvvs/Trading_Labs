"""Unit tests for Mansfield RS Tight-Base Breakout formulas and gates."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.research_lab.mrs import (
    MIN_HISTORY_BARS,
    MRSBreakoutConfig,
    MRSDataset,
    compute_base_metrics,
    compute_event_ok,
    compute_mrs,
    compute_relative_returns,
    compute_rs_leading_high,
    compute_rs_ratings,
    compute_rsd,
    generate_signals,
    gate_funnel,
)


def _dates(n: int, start: str = "2018-01-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def test_rsd_formula():
    idx = _dates(5)
    close = pd.DataFrame({"AAA": [200.0, 210.0, 220.0, 230.0, 240.0]}, index=idx)
    bench = pd.Series([100.0, 100.0, 110.0, 115.0, 120.0], index=idx)
    rsd = compute_rsd(close, bench)
    expected = pd.Series([200.0, 210.0, 200.0, 200.0, 200.0], index=idx)
    pd.testing.assert_series_equal(rsd["AAA"], expected, check_names=False)


def test_mrs_requires_200_observations_and_matches_formula():
    idx = _dates(205)
    rsd = pd.DataFrame({"AAA": np.full(205, 100.0)}, index=idx)
    rsd.iloc[204, 0] = 110.0
    mrs, valid = compute_mrs(rsd, period=200)

    assert not bool(valid.iloc[198, 0])
    assert bool(valid.iloc[199, 0])
    assert pd.isna(mrs.iloc[198, 0])

    sma = rsd["AAA"].iloc[5:205].mean()
    expected = (110.0 / sma - 1.0) * 100.0
    assert mrs.iloc[204, 0] == pytest.approx(expected)


def test_base_window_excludes_breakout_bar():
    idx = _dates(20)
    high = pd.DataFrame({"AAA": np.arange(20, dtype=float) + 10.0}, index=idx)
    low = pd.DataFrame({"AAA": np.arange(20, dtype=float)}, index=idx)
    # Spike the current bar so a bug that includes t would show up.
    high.iloc[-1, 0] = 999.0
    low.iloc[-1, 0] = -999.0

    base_high, base_low, base_median, width = compute_base_metrics(high, low, lookback=15)
    t = idx[-1]
    assert base_high.loc[t, "AAA"] == float(np.max(np.arange(4, 19) + 10.0))
    assert base_low.loc[t, "AAA"] == float(np.min(np.arange(4, 19)))
    expected_median = (base_high.loc[t, "AAA"] + base_low.loc[t, "AAA"]) / 2.0
    assert base_median.loc[t, "AAA"] == pytest.approx(expected_median)
    expected_width = (
        (base_high.loc[t, "AAA"] - base_low.loc[t, "AAA"]) / expected_median
    ) * 100.0
    assert width.loc[t, "AAA"] == pytest.approx(expected_width)


def test_base_width_gate_boundary():
    idx = _dates(16)
    high = pd.DataFrame({"AAA": np.full(16, 110.0)}, index=idx)
    low = pd.DataFrame({"AAA": np.full(16, 100.0)}, index=idx)
    _, _, _, width = compute_base_metrics(high, low, lookback=15)
    # (110-100)/105*100 = 9.523... <= 10
    assert width.iloc[-1, 0] == pytest.approx((10.0 / 105.0) * 100.0)
    assert width.iloc[-1, 0] <= 10.0

    high["AAA"] = 111.0
    _, _, _, width_fail = compute_base_metrics(high, low, lookback=15)
    assert width_fail.iloc[-1, 0] > 10.0


def test_rs_ratings_are_point_in_time_percentiles():
    n = 130
    idx = _dates(n)
    bench = pd.Series(np.full(n, 100.0), index=idx)
    data = {}
    # 5 names, last one doubled over 126 sessions.
    for i, sym in enumerate(["A", "B", "C", "D", "E"]):
        px = np.full(n, 100.0)
        if sym == "E":
            px[-1] = 200.0
        elif sym == "D":
            px[-1] = 150.0
        else:
            px[-1] = 100.0 + i
        data[sym] = px
    close = pd.DataFrame(data, index=idx)
    rs6m, _ = compute_rs_ratings(close, bench, lookback_6m=126, lookback_12m=252)
    # E has the highest 6M relative return.
    assert rs6m.iloc[-1].idxmax() == "E"
    assert rs6m.iloc[-1, rs6m.columns.get_loc("E")] == pytest.approx(100.0)


def test_rs_leading_high_looks_strictly_before_t():
    n = 270
    idx = _dates(n)
    rsd = pd.DataFrame({"AAA": np.linspace(100.0, 150.0, n)}, index=idx)
    # New high on the last bar only — must NOT count for day t.
    rsd.iloc[-1, 0] = 1_000.0
    leading = compute_rs_leading_high(rsd, new_high_lookback=252, leading_window=15)
    assert bool(leading.iloc[-1, 0])  # earlier uptrend days inside [t-15, t-1]

    # Flat series, single spike on t: no prior new high in the window.
    flat = pd.DataFrame({"AAA": np.full(n, 100.0)}, index=idx)
    flat.iloc[-1, 0] = 200.0
    leading_flat = compute_rs_leading_high(flat, new_high_lookback=252, leading_window=15)
    assert not bool(leading_flat.iloc[-1, 0])

    # Spike on t-1 only.
    prior = pd.DataFrame({"AAA": np.full(n, 100.0)}, index=idx)
    prior.iloc[-2, 0] = 200.0
    leading_prior = compute_rs_leading_high(prior, new_high_lookback=252, leading_window=15)
    assert bool(leading_prior.iloc[-1, 0])


def test_earnings_blocks_t_minus_1_through_t_minus_5_and_fail_closed():
    idx = _dates(20)
    event = idx[10]
    ok, avail = compute_event_ok(
        idx,
        ["HAS", "MISSING"],
        {"HAS": pd.DatetimeIndex([event])},
        {"HAS"},
        forward_sessions=5,
        allow_missing_events=False,
    )
    assert bool(avail["HAS"].iloc[0])
    assert not bool(avail["MISSING"].iloc[0])
    assert not bool(ok["MISSING"].iloc[0])
    # Signal days t where event is in [t+1, t+5] => t = event-1 .. event-5
    for offset in range(1, 6):
        assert not bool(ok["HAS"].iloc[10 - offset])
    assert bool(ok["HAS"].iloc[10])  # event day itself is not in (t+1, t+5) when t is the event
    assert bool(ok["HAS"].iloc[4])  # well before the window


def _build_breakout_dataset(mutate=None, extra_after: int = 0) -> MRSDataset:
    """One outperformer (WIN) plus nine benchmark-trackers.

    Breakout prints on bar 399. extra_after appends follow-through sessions
    so the portfolio backtester can hold the name past the entry bar.
    """
    n = 400 + extra_after
    breakout_i = 399
    idx = _dates(n)
    rng = np.random.default_rng(7)

    bench = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0.00015, 0.002, n)), index=idx)
    # Quiet tape over the 15-session base and any follow-through.
    quiet_start = breakout_i - 15
    bench.iloc[quiet_start:] = bench.iloc[quiet_start] * np.linspace(
        1.0, 0.995, n - quiet_start
    )

    symbols = [f"S{i:02d}" for i in range(9)] + ["WIN"]
    close = pd.DataFrame(index=idx, columns=symbols, dtype=float)
    high = pd.DataFrame(index=idx, columns=symbols, dtype=float)
    low = pd.DataFrame(index=idx, columns=symbols, dtype=float)
    volume = pd.DataFrame(index=idx, columns=symbols, dtype=float)

    for i, sym in enumerate(symbols[:-1]):
        noise = np.cumprod(1.0 + rng.normal(0.0, 0.003, n))
        px = bench.to_numpy() * (0.95 + 0.01 * i) * noise / noise[0]
        close[sym] = px
        high[sym] = px * 1.005
        low[sym] = px * 0.995
        volume[sym] = 1000.0

    # WIN steadily outperforms so 6M / 12M relative returns sit at the top.
    win = bench.to_numpy() * np.linspace(1.0, 2.4, n)
    base_level = float(win[quiet_start])
    win[quiet_start:breakout_i] = base_level * np.linspace(1.0, 1.004, 15)
    win[breakout_i] = base_level * 1.025
    if extra_after:
        win[breakout_i + 1 :] = win[breakout_i] * np.linspace(1.01, 1.05, extra_after)

    close["WIN"] = win
    high["WIN"] = np.asarray(win) * 1.004
    low["WIN"] = np.asarray(win) * 0.996
    # Tight base: width (1.02 - 0.98) / 1.00 * 100 = 4%.
    high.iloc[quiet_start:breakout_i, high.columns.get_loc("WIN")] = base_level * 1.02
    low.iloc[quiet_start:breakout_i, low.columns.get_loc("WIN")] = base_level * 0.98
    high.iloc[breakout_i, high.columns.get_loc("WIN")] = base_level * 1.03
    low.iloc[breakout_i, low.columns.get_loc("WIN")] = base_level * 1.01
    volume["WIN"] = 1000.0
    volume.iloc[breakout_i, volume.columns.get_loc("WIN")] = 2000.0

    sector_close = pd.DataFrame({"NIFTY_IT": bench.to_numpy() * np.linspace(1.0, 1.6, n)}, index=idx)
    symbol_to_sector = {s: "NIFTY_IT" for s in symbols}
    earnings = {s: pd.DatetimeIndex([idx[20]]) for s in symbols}

    if mutate is not None:
        close, high, low, volume, bench, sector_close, symbol_to_sector, earnings = mutate(
            close, high, low, volume, bench, sector_close, symbol_to_sector, earnings
        )

    return MRSDataset(
        close=close,
        high=high,
        low=low,
        volume=volume,
        bench_close=bench,
        sector_close=sector_close,
        symbol_to_sector=symbol_to_sector,
        earnings=earnings,
        symbols_with_event_data=set(close.columns),
    )


def test_full_setup_fires_only_on_win_at_breakout():
    ds = _build_breakout_dataset()
    panel = generate_signals(ds, MRSBreakoutConfig())
    last = ds.close.index[399]
    winners = panel.buy.loc[last]
    assert bool(winners["WIN"])
    assert int(winners.sum()) == 1
    assert panel.reject_reason.loc[last, "WIN"] == "PASS"
    # Breakout bar itself is excluded from the base.
    assert ds.close.loc[last, "WIN"] > panel.base_high.loc[last, "WIN"]
    assert panel.base_width_pct.loc[last, "WIN"] <= 10.0
    assert panel.rs6m_rating.loc[last, "WIN"] > 80.0
    assert panel.rs12m_rating.loc[last, "WIN"] > 80.0


def test_width_gate_rejects_wide_base():
    def mutate(close, high, low, volume, bench, sector_close, mapping, earnings):
        high.iloc[-16:-1, high.columns.get_loc("WIN")] = 120.0
        low.iloc[-16:-1, low.columns.get_loc("WIN")] = 80.0
        return close, high, low, volume, bench, sector_close, mapping, earnings

    panel = generate_signals(_build_breakout_dataset(mutate), MRSBreakoutConfig())
    last = panel.buy.index[-1]
    assert not bool(panel.buy.loc[last, "WIN"])
    assert panel.reject_reason.loc[last, "WIN"] == "base_width"


def test_volume_gate_rejects_quiet_breakout():
    def mutate(close, high, low, volume, bench, sector_close, mapping, earnings):
        volume.iloc[-1, volume.columns.get_loc("WIN")] = 1000.0
        return close, high, low, volume, bench, sector_close, mapping, earnings

    panel = generate_signals(_build_breakout_dataset(mutate), MRSBreakoutConfig())
    last = panel.buy.index[-1]
    assert not bool(panel.buy.loc[last, "WIN"])
    assert panel.reject_reason.loc[last, "WIN"] == "volume"


def test_breakout_gate_requires_close_above_base_high():
    def mutate(close, high, low, volume, bench, sector_close, mapping, earnings):
        # Stay almost at the breakout print so RS ratings still pass; finish
        # a tick under the 15-session base high so only the breakout gate fails.
        base_high = high.iloc[-16:-1, high.columns.get_loc("WIN")].max()
        close.iloc[-1, close.columns.get_loc("WIN")] = float(base_high) * 0.999
        high.iloc[-1, high.columns.get_loc("WIN")] = float(base_high)
        return close, high, low, volume, bench, sector_close, mapping, earnings

    panel = generate_signals(_build_breakout_dataset(mutate), MRSBreakoutConfig())
    last = panel.buy.index[-1]
    assert not bool(panel.buy.loc[last, "WIN"])
    assert panel.reject_reason.loc[last, "WIN"] == "breakout"


def test_sector_fail_closed_without_mapping():
    def mutate(close, high, low, volume, bench, sector_close, mapping, earnings):
        mapping = {k: v for k, v in mapping.items() if k != "WIN"}
        return close, high, low, volume, bench, sector_close, mapping, earnings

    panel = generate_signals(_build_breakout_dataset(mutate), MRSBreakoutConfig())
    last = panel.buy.index[-1]
    assert not bool(panel.buy.loc[last, "WIN"])
    assert panel.reject_reason.loc[last, "WIN"] == "sector_alignment"


def test_event_data_unavailable_fail_closed():
    ds = _build_breakout_dataset()
    ds.symbols_with_event_data = set(ds.close.columns) - {"WIN"}
    ds.earnings = {k: v for k, v in ds.earnings.items() if k != "WIN"}
    panel = generate_signals(ds, MRSBreakoutConfig())
    last = panel.buy.index[-1]
    assert not bool(panel.buy.loc[last, "WIN"])
    assert panel.reject_reason.loc[last, "WIN"] == "EVENT_DATA_UNAVAILABLE"


def test_event_override_allows_missing_history():
    ds = _build_breakout_dataset()
    ds.symbols_with_event_data = set(ds.close.columns) - {"WIN"}
    ds.earnings = {k: v for k, v in ds.earnings.items() if k != "WIN"}
    panel = generate_signals(ds, MRSBreakoutConfig(allow_missing_events=True))
    last = panel.buy.index[-1]
    assert bool(panel.buy.loc[last, "WIN"])


def test_quiet_market_gate_rejects_hot_benchmark():
    def mutate(close, high, low, volume, bench, sector_close, mapping, earnings):
        bench.iloc[-1] = bench.iloc[-16] * 1.05  # +5% in 15 sessions
        return close, high, low, volume, bench, sector_close, mapping, earnings

    panel = generate_signals(_build_breakout_dataset(mutate), MRSBreakoutConfig())
    last = panel.buy.index[-1]
    assert not bool(panel.buy.loc[last, "WIN"])
    assert panel.reject_reason.loc[last, "WIN"] == "consolidation_maturity"


def test_gate_funnel_is_monotone():
    panel = generate_signals(_build_breakout_dataset(), MRSBreakoutConfig())
    funnel = gate_funnel(panel)
    counts = funnel["bars_passing"].tolist()
    assert counts == sorted(counts, reverse=True)
    assert funnel.iloc[-1]["bars_passing"] == int(panel.buy.sum().sum())


def test_portfolio_backtest_takes_the_breakout_and_exits():
    from app.services.research_lab.book import run_portfolio
    from app.services.research_lab.signals_types import MarketData, SignalBook

    ds = _build_breakout_dataset(extra_after=8)
    panel = generate_signals(ds, MRSBreakoutConfig())
    md = MarketData(
        close=ds.close,
        high=ds.high,
        low=ds.low,
        open_=ds.close,
        volume=ds.volume,
        bench=ds.bench_close,
    )
    book = SignalBook(
        buy=panel.buy,
        rank=panel.rs12m_rating,
        exit_below=panel.ema20,
        initial_stop=panel.base_low,
    )
    trades, equity = run_portfolio(md, book)
    assert not trades.empty
    win_trades = trades[trades["symbol"] == "WIN"]
    assert len(win_trades) >= 1
    assert win_trades.iloc[0]["entry_date"] == ds.close.index[399]
    assert float(equity["equity"].iloc[-1]) > 0


def test_relative_return_is_stock_minus_benchmark():
    idx = _dates(5)
    close = pd.DataFrame({"AAA": [100.0, 100.0, 100.0, 100.0, 110.0]}, index=idx)
    bench = pd.Series([100.0, 100.0, 100.0, 100.0, 105.0], index=idx)
    rel = compute_relative_returns(close, bench, lookback=4)
    assert rel.iloc[-1, 0] == pytest.approx((110 / 100 - 1) - (105 / 100 - 1))
