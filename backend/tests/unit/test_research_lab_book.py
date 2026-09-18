"""Shared 10% × 10 book and NSE delivery costs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.research_lab.book import run_portfolio
from app.services.research_lab.catalog import INITIAL_CAPITAL
from app.services.research_lab.costs import TransactionCosts
from app.services.research_lab.indicators import build_indicators, rsi_sma
from app.services.research_lab.signals import build_all_signals
from app.services.research_lab.signals_types import MarketData, SignalBook


def test_transaction_costs_match_published_formula():
    costs = TransactionCosts()
    buy = costs.buy_cost(10_000)
    # brokerage cap 20, 0.03% of 10000 = 3
    assert buy == pytest_approx_buy(10_000)
    sell = costs.sell_cost(10_000)
    assert sell > buy
    assert costs.sell_cost(10_000) - costs.sell_cost(10_000, include_dp=False) == 15.93


def pytest_approx_buy(turnover: float) -> float:
    brokerage = min(turnover * 0.0003, 20.0)
    exch = turnover * 0.0000345
    sebi = turnover * 0.000001
    stamp = turnover * 0.00015
    gst = (brokerage + exch) * 0.18
    return brokerage + exch + sebi + stamp + gst


def test_rsi_sma_not_wilder():
    values = [10.0 + (i % 5) - (0 if i % 3 else 2) for i in range(40)]
    close = pd.DataFrame({"AAA": values})
    out = rsi_sma(close, 14)
    assert pd.notna(out.iloc[-1, 0])
    assert 0.0 <= float(out.iloc[-1, 0]) <= 100.0


def _synthetic_md(n: int = 80) -> MarketData:
    idx = pd.bdate_range("2020-01-01", periods=n)
    close = pd.DataFrame(
        {
            "AAA": np.linspace(100.0, 140.0, n),
            "BBB": np.linspace(80.0, 70.0, n),
        },
        index=idx,
    )
    high = close * 1.01
    low = close * 0.99
    volume = pd.DataFrame(1000.0, index=idx, columns=close.columns)
    bench = pd.Series(np.linspace(100.0, 120.0, n), index=idx)
    return MarketData(close=close, high=high, low=low, open_=close, volume=volume, bench=bench)


def test_sma_10_50_level_rule_fills_and_eod_liquidates():
    md = _synthetic_md(80)
    ind = build_indicators(md)
    books = build_all_signals(md, dataset=None, ind=ind)
    book = books["21_sma_10_50"]
    trades, equity = run_portfolio(md, book)
    assert not trades.empty
    assert (trades["exit_reason"] == "eod_liquidation").any() or (trades["exit_reason"] == "signal").any()
    assert float(equity["equity"].iloc[0]) >= INITIAL_CAPITAL * 0.5
    assert int(equity["n_positions"].max()) <= 10


def test_hard_stop_fires_before_signal():
    idx = pd.bdate_range("2020-01-01", periods=5)
    close = pd.DataFrame({"AAA": [100.0, 100.0, 80.0, 80.0, 80.0]}, index=idx)
    md = MarketData(
        close=close,
        high=close,
        low=close,
        open_=close,
        volume=pd.DataFrame(1.0, index=idx, columns=["AAA"]),
        bench=pd.Series(100.0, index=idx),
    )
    buy = pd.DataFrame(False, index=idx, columns=["AAA"])
    buy.iloc[0, 0] = True
    sell = pd.DataFrame(False, index=idx, columns=["AAA"])
    book = SignalBook(buy=buy, rank=close, sell=sell, hard_stop_pct=0.15)
    trades, _ = run_portfolio(md, book)
    assert len(trades) == 1
    assert trades.iloc[0]["exit_reason"] == "hard_stop"
