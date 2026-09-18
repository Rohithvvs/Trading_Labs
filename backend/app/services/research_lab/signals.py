"""Build SignalBook panels for all 21 research-lab strategies. Rules are not optimized."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .catalog import LAB_STRATEGIES, allow_same_day_rebuy
from .darvas import calculate_darvas_signals
from .darvas_breakeven import calculate_darvas_signals_breakeven
from .indicators import Indicators, build_indicators
from .mrs import MRSBreakoutConfig, generate_signals
from .signals_types import MarketData, SignalBook


def empty_bool(md: MarketData) -> pd.DataFrame:
    return pd.DataFrame(False, index=md.close.index, columns=md.close.columns)


def empty_float(md: MarketData) -> pd.DataFrame:
    return pd.DataFrame(np.nan, index=md.close.index, columns=md.close.columns)


def _stock_frame(md: MarketData, symbol: str) -> Optional[pd.DataFrame]:
    s = md.close[symbol].dropna()
    if len(s) < 253:
        return None
    idx = s.index
    return pd.DataFrame(
        {
            "date": idx,
            "open": md.open_.loc[idx, symbol].values,
            "high": md.high.loc[idx, symbol].values,
            "low": md.low.loc[idx, symbol].values,
            "close": s.values,
            "volume": md.volume.loc[idx, symbol].values,
        }
    )


def darvas_panels(
    md: MarketData,
    sl_type: str,
    vol_multiplier: float,
    market_ok_col: Optional[pd.Series] = None,
    breakeven: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    buy = empty_bool(md)
    sell = empty_bool(md)
    for symbol in md.close.columns:
        df = _stock_frame(md, symbol)
        if df is None:
            continue
        if market_ok_col is not None:
            aligned = market_ok_col.reindex(df["date"]).fillna(False).astype(bool)
            df["market_filter_ok"] = aligned.values
        else:
            df["market_filter_ok"] = True
        try:
            if breakeven is None:
                res = calculate_darvas_signals(df, sl_type=sl_type, vol_multiplier=vol_multiplier)
            else:
                res = calculate_darvas_signals_breakeven(
                    df, sl_type=sl_type, vol_multiplier=vol_multiplier, be_trigger=breakeven
                )
            dates = pd.to_datetime(res["date"])
            buy.loc[dates, symbol] = res["buy_signal"].to_numpy()
            sell.loc[dates, symbol] = res["sell_signal"].to_numpy()
        except Exception:
            continue
    return buy.fillna(False), sell.fillna(False)


def apply_buy_filter(buy: pd.DataFrame, filt: pd.DataFrame) -> pd.DataFrame:
    return buy & filt.fillna(False)


def rebalance_book(
    md: MarketData,
    score: pd.DataFrame,
    top_n: int,
    rebal_every: int,
    warmup: int,
    market_ok: Optional[pd.Series] = None,
    liquidate_if_market_off: bool = True,
    start_date: Optional[pd.Timestamp] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    buy = empty_bool(md)
    sell = empty_bool(md)
    dates = md.close.index
    start_i = 0
    if start_date is not None:
        later = dates[dates >= pd.Timestamp(start_date)]
        if len(later) == 0:
            return buy, sell
        start_i = int(dates.get_loc(later[0]))
    days_since = rebal_every
    for i, day in enumerate(dates):
        if start_date is not None:
            if i < start_i:
                continue
        elif i < warmup:
            continue
        days_since += 1
        if days_since < rebal_every:
            continue
        days_since = 0
        sell.iloc[i] = True
        if market_ok is not None and not bool(market_ok.loc[day]) and liquidate_if_market_off:
            continue
        row = score.iloc[i].dropna()
        if row.empty:
            continue
        top = row.sort_values(ascending=False).head(top_n)
        buy.loc[day, top.index] = True
    return buy, sell


def last_down_candle_levels(
    open_: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, lookback: int = 15
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    down = close < open_
    ob_low = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    ob_high = ob_low.copy()
    assigned = pd.DataFrame(False, index=close.index, columns=close.columns)
    for i in range(1, lookback + 1):
        hit = (down.shift(i) == True) & ~assigned
        ob_low = ob_low.mask(hit, low.shift(i))
        ob_high = ob_high.mask(hit, high.shift(i))
        assigned = assigned | hit
    return ob_high, ob_low


def build_all_signals(
    md: MarketData,
    dataset=None,
    ind: Optional[Indicators] = None,
    trade_start: Optional[pd.Timestamp] = None,
) -> Dict[str, SignalBook]:
    books: Dict[str, SignalBook] = {}
    close = md.close
    if ind is None:
        ind = build_indicators(md)
    market50 = ind.market_ok50
    mom60 = ind.mom60

    d_buy, d_sell = darvas_panels(md, "2close", 2)
    books["01_darvas_classic"] = SignalBook(
        buy=d_buy,
        sell=d_sell,
        rank=mom60,
        notes=LAB_STRATEGIES[0].description,
    )

    a_buy, a_sell = darvas_panels(md, "atr", 5)
    filt_mf = pd.DataFrame({c: market50.to_numpy() for c in close.columns}, index=close.index)

    books["02_darvas_atr5_mf50"] = SignalBook(
        buy=apply_buy_filter(a_buy, filt_mf),
        sell=a_sell,
        rank=mom60,
        notes=LAB_STRATEGIES[1].description,
    )

    stock_trend = (close > ind.sma50) & (ind.sma50 > ind.sma200)
    books["03_super_trend_align"] = SignalBook(
        buy=apply_buy_filter(a_buy, filt_mf & stock_trend),
        sell=a_sell,
        rank=mom60,
        notes=LAB_STRATEGIES[2].description,
    )

    rs_ok = (ind.mom126 > pd.DataFrame({c: ind.nifty_ret126.values for c in close.columns}, index=close.index)) & (
        ind.mom126 > 0
    )
    books["04_rs_darvas"] = SignalBook(
        buy=apply_buy_filter(a_buy, filt_mf & rs_ok),
        sell=a_sell,
        rank=ind.mom126,
        notes=LAB_STRATEGIES[3].description,
    )

    be_buy, be_sell = darvas_panels(md, "atr", 5, market_ok_col=market50, breakeven="profit_10")
    books["05_darvas_breakeven"] = SignalBook(
        buy=be_buy,
        sell=be_sell,
        rank=mom60,
        notes=LAB_STRATEGIES[4].description,
    )

    rsi = ind.rsi14
    books["06_mean_reversion"] = SignalBook(
        buy=(ind.sma200 > 0) & (close > ind.sma200) & (rsi < 30),
        rank=rsi.rsub(30),
        hard_stop_pct=0.15,
        sell=rsi > 70,
        notes=LAB_STRATEGIES[5].description,
    )

    prev_width = ind.bb_width.shift(1)
    books["07_vol_squeeze"] = SignalBook(
        buy=(prev_width < 0.10) & (close > ind.bb_upper) & (md.volume > ind.vol_sma20 * 3.0),
        rank=mom60,
        exit_below=ind.sma20,
        notes=LAB_STRATEGIES[6].description,
    )

    books["08_golden_cross_20_50"] = SignalBook(
        buy=(ind.sma20.shift(1) <= ind.sma50.shift(1)) & (ind.sma20 > ind.sma50),
        rank=mom60,
        sell=ind.sma20 < ind.sma50,
        notes=LAB_STRATEGIES[7].description,
    )

    books["09_52w_breakout"] = SignalBook(
        buy=filt_mf & (close >= ind.high252.shift(1)) & (md.volume > ind.vol_sma20),
        rank=mom60,
        trail_atr_mult=3.0,
        atr=ind.atr14,
        notes=LAB_STRATEGIES[8].description,
    )

    ema_cross = (ind.ema9.shift(1) <= ind.ema21.shift(1)) & (ind.ema9 > ind.ema21)
    books["10_ema_9_21"] = SignalBook(
        buy=filt_mf & ema_cross,
        rank=mom60,
        sell=ind.ema9 < ind.ema21,
        entry_atr_stop_mult=2.0,
        atr=ind.atr14,
        notes=LAB_STRATEGIES[9].description,
    )

    rsi_cross_down = (rsi.shift(1) > 30) & (rsi < 30)
    books["11_refined_mean_reversion"] = SignalBook(
        buy=rsi_cross_down & (ind.sma50 > ind.sma200) & (close > ind.sma200),
        rank=rsi.rsub(30),
        sell=rsi > 60,
        hard_stop_pct=0.10,
        notes=LAB_STRATEGIES[10].description,
    )

    books["12_golden_cross_50_200"] = SignalBook(
        buy=(ind.sma50.shift(1) <= ind.sma200.shift(1)) & (ind.sma50 > ind.sma200),
        rank=ind.mom252,
        sell=ind.sma50 < ind.sma200,
        notes=LAB_STRATEGIES[11].description,
    )

    books["13_trend_pullback"] = SignalBook(
        buy=(close > ind.sma200) & (close.shift(1) <= ind.sma50.shift(1)) & (close > ind.sma50),
        rank=ind.mom252,
        sell=close < ind.sma200,
        notes=LAB_STRATEGIES[12].description,
    )

    if trade_start is not None:
        later = close.index[close.index >= pd.Timestamp(trade_start)]
        first_idx = int(close.index.get_loc(later[0])) if len(later) else 0
        lookback = first_idx - 252 if first_idx >= 252 else 0
        yr_ret = close.iloc[first_idx] / close.iloc[lookback] - 1.0
    else:
        first_idx = 252 if len(close.index) > 252 else max(len(close.index) - 1, 0)
        yr_ret = close.iloc[first_idx] / close.iloc[0] - 1.0
    first_day = close.index[first_idx]
    bh_buy = empty_bool(md)
    eligible = yr_ret.dropna()
    eligible = eligible[eligible > 0.50].sort_values(ascending=False)
    if not eligible.empty:
        bh_buy.loc[first_day, eligible.index] = True
    bh_rank = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    bh_rank.loc[first_day] = yr_ret
    books["14_bh_top_momentum"] = SignalBook(
        buy=bh_buy,
        rank=bh_rank,
        notes=LAB_STRATEGIES[13].description,
    )

    if dataset is not None:
        panel = generate_signals(dataset, MRSBreakoutConfig())
        books["15_mrs_breakout"] = SignalBook(
            buy=panel.buy.reindex(index=close.index, columns=close.columns).fillna(False),
            rank=panel.rs12m_rating.reindex(index=close.index, columns=close.columns),
            exit_below=panel.ema20.reindex(index=close.index, columns=close.columns),
            initial_stop=panel.base_low.reindex(index=close.index, columns=close.columns),
            notes=LAB_STRATEGIES[14].description,
        )
    else:
        books["15_mrs_breakout"] = SignalBook(
            buy=empty_bool(md),
            rank=empty_float(md),
            notes=LAB_STRATEGIES[14].description,
        )

    prev_20_high = md.high.shift(1).rolling(20).max()
    _, ob_low = last_down_candle_levels(md.open_, md.high, md.low, close, lookback=15)
    bos = (close > prev_20_high) & (close > ind.sma50) & filt_mf & ob_low.notna()
    books["16_order_block"] = SignalBook(
        buy=bos,
        rank=ind.mom60,
        initial_stop=ob_low * 0.99,
        trail_stop=md.low.shift(1).rolling(3).min(),
        take_profit_rr=2.0,
        notes=LAB_STRATEGIES[15].description,
    )

    long_score = ind.mom252.where(ind.mom252 > 0.50)
    lb, ls = rebalance_book(md, long_score, top_n=10, rebal_every=252, warmup=252, start_date=trade_start)
    books["17_long_term_mom"] = SignalBook(
        buy=lb,
        sell=ls,
        rank=ind.mom252,
        allow_same_day_rebuy=allow_same_day_rebuy("17_long_term_mom"),
        notes=LAB_STRATEGIES[16].description,
    )

    fast_score = ind.mom60.where(close > ind.sma20)
    fb, fs = rebalance_book(md, fast_score, top_n=3, rebal_every=20, warmup=60, start_date=trade_start)
    books["18_fast_mom"] = SignalBook(
        buy=fb,
        sell=fs,
        rank=ind.mom60,
        allow_same_day_rebuy=allow_same_day_rebuy("18_fast_mom"),
        notes=LAB_STRATEGIES[17].description,
    )

    low_score = ind.mom60.where(close > ind.sma20)
    ldb, lds = rebalance_book(
        md,
        low_score,
        top_n=3,
        rebal_every=10,
        warmup=60,
        market_ok=ind.market_ok20,
        start_date=trade_start,
    )
    books["19_low_dd_mom"] = SignalBook(
        buy=ldb,
        sell=lds,
        rank=ind.mom60,
        tsl_pct=0.05,
        allow_same_day_rebuy=allow_same_day_rebuy("19_low_dd_mom"),
        notes=LAB_STRATEGIES[18].description,
    )

    ultra_el = (close > ind.sma20) & (ind.mom20 > 0) & (ind.mom60 > 0)
    ultra_score = (ind.mom20 + ind.mom60).where(ultra_el)
    ub, us = rebalance_book(
        md,
        ultra_score,
        top_n=2,
        rebal_every=5,
        warmup=60,
        market_ok=ind.market_ok10,
        start_date=trade_start,
    )
    books["20_ultra_yield_mom"] = SignalBook(
        buy=ub,
        sell=us,
        rank=ultra_score,
        tsl_pct=0.04,
        allow_same_day_rebuy=allow_same_day_rebuy("20_ultra_yield_mom"),
        notes=LAB_STRATEGIES[19].description,
    )

    books["21_sma_10_50"] = SignalBook(
        buy=ind.sma10 > ind.sma50,
        rank=mom60,
        sell=ind.sma10 < ind.sma50,
        notes=LAB_STRATEGIES[20].description,
    )

    for book in books.values():
        book.buy = book.buy.fillna(False).astype(bool)
        if book.sell is not None:
            book.sell = book.sell.fillna(False).astype(bool)
    return books
