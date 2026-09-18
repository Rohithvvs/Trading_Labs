"""Shared indicator panel. Formulas match Trading-main run_all_baseline.py."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .signals_types import MarketData


def rsi_sma(close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(period).mean()
    loss = (-delta.clip(upper=0.0)).rolling(period).mean()
    rs = gain / loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def atr_sma(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    tr = np.maximum(high - low, np.maximum((high - close.shift(1)).abs(), (low - close.shift(1)).abs()))
    return tr.rolling(period).mean()


@dataclass
class Indicators:
    sma10: pd.DataFrame
    sma20: pd.DataFrame
    sma50: pd.DataFrame
    sma200: pd.DataFrame
    ema9: pd.DataFrame
    ema21: pd.DataFrame
    ema20: pd.DataFrame
    rsi14: pd.DataFrame
    atr14: pd.DataFrame
    vol_sma20: pd.DataFrame
    high252: pd.DataFrame
    bb_upper: pd.DataFrame
    bb_width: pd.DataFrame
    mom20: pd.DataFrame
    mom60: pd.DataFrame
    mom126: pd.DataFrame
    mom252: pd.DataFrame
    nifty_sma10: pd.Series
    nifty_sma20: pd.Series
    nifty_sma50: pd.Series
    nifty_ret126: pd.Series
    market_ok50: pd.Series
    market_ok20: pd.Series
    market_ok10: pd.Series


def build_indicators(md: MarketData) -> Indicators:
    close, high, volume, bench = md.close, md.high, md.volume, md.bench
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = sma20 + 2.0 * std20
    return Indicators(
        sma10=close.rolling(10).mean(),
        sma20=sma20,
        sma50=close.rolling(50).mean(),
        sma200=close.rolling(200).mean(),
        ema9=close.ewm(span=9, adjust=False).mean(),
        ema21=close.ewm(span=21, adjust=False).mean(),
        ema20=close.ewm(span=20, adjust=False).mean(),
        rsi14=rsi_sma(close, 14),
        atr14=atr_sma(high, md.low, close, 14),
        vol_sma20=volume.rolling(20).mean(),
        high252=high.rolling(252).max(),
        bb_upper=bb_upper,
        bb_width=(bb_upper - (sma20 - 2.0 * std20)) / sma20,
        mom20=close.pct_change(20, fill_method=None),
        mom60=close.pct_change(60, fill_method=None),
        mom126=close.pct_change(126, fill_method=None),
        mom252=close.pct_change(252, fill_method=None),
        nifty_sma10=bench.rolling(10).mean(),
        nifty_sma20=bench.rolling(20).mean(),
        nifty_sma50=bench.rolling(50).mean(),
        nifty_ret126=bench / bench.shift(126) - 1.0,
        market_ok50=bench > bench.rolling(50).mean(),
        market_ok20=bench > bench.rolling(20).mean(),
        market_ok10=bench >= bench.rolling(10).mean(),
    )
