"""Identity for the 21 long-only NSE cash-equity research-lab strategies."""

from __future__ import annotations

from dataclasses import dataclass


INITIAL_CAPITAL = 100_000.0
ALLOC_PCT = 0.10
MAX_POSITIONS = 10
SAME_DAY_REBUY_IDS = frozenset(
    {"17_long_term_mom", "18_fast_mom", "19_low_dd_mom", "20_ultra_yield_mom"}
)


@dataclass(frozen=True)
class LabStrategy:
    strategy_id: str
    number: str
    name: str
    scan_title: str
    description: str
    rank: str
    pine_kind: str  # vector | stateful | universe | rebalance


TOP_5_STRATEGIES: tuple[LabStrategy, ...] = (
    LabStrategy(
        "top_01_momentum",
        "TOP1",
        "App Preset: Momentum",
        "Top 1: App Preset Momentum [SCAN]",
        "Research Rank #1 (+24.40% CAGR, 0.60 Sharpe, 3.21 PF): Close > SMA50 > SMA200, RSI > 55, Volume > SMA20.",
        "mom200",
        "vector",
    ),
    LabStrategy(
        "top_02_12_1_mom",
        "TOP2",
        "12-1 Cross-Sectional Momentum",
        "Top 2: 12-1 Cross-Sectional Momentum [SCAN]",
        "Research Rank #2 (+22.86% CAGR, 18.88% Max DD, 2.60 PF): Jegadeesh & Titman 12-1 Momentum > 0, Volume > SMA20.",
        "mom252",
        "vector",
    ),
    LabStrategy(
        "top_03_52w_breakout",
        "TOP3",
        "52-Week High Breakout",
        "Top 3: 52-Week High Breakout [SCAN]",
        "Research Rank #3 (+20.41% CAGR, 11.08% Max DD, 2.83 PF): 52W High Breakout, Nifty > SMA50, 3-ATR Trailing Stop.",
        "mom60",
        "vector",
    ),
    LabStrategy(
        "top_04_52w_atr",
        "TOP4",
        "52-Week Breakout ATR Sizing",
        "Top 4: 52-Week Breakout ATR Sizing [SCAN]",
        "Research Rank #4 (+18.14% CAGR, 26.38% Max DD, 2.32 PF): 52-Week High Breakout with ATR volatility sizing and Nifty > SMA50.",
        "mom60",
        "vector",
    ),
    LabStrategy(
        "top_05_minervini_vcp",
        "TOP5",
        "Minervini Stage-2 VCP",
        "Top 5: Minervini Stage-2 VCP [SCAN]",
        "Research Rank #5 (+16.96% CAGR, 23.91% Max DD, 1.74 PF): Stage-2 Trend Template + 20d/126d VCP Contraction (<=40%) + 15d Pivot Breakout.",
        "mom252",
        "vector",
    ),
)


LAB_STRATEGIES: tuple[LabStrategy, ...] = TOP_5_STRATEGIES + (
    LabStrategy(
        "01_darvas_classic",
        "01",
        "Darvas Box Classic",
        "01 Darvas Box Classic [SCAN]",
        "Box breakout with volume > 2x SMA20; exit after two closes below box bottom. No market filter.",
        "mom60",
        "stateful",
    ),
    LabStrategy(
        "02_darvas_atr5_mf50",
        "02",
        "Darvas ATR-5 + Nifty SMA50",
        "02 Darvas ATR-5 + Nifty SMA50 [SCAN]",
        "Darvas breakout, volume > 5x SMA20, Nifty > SMA50. ATR stop: close < box_top - 2*ATR.",
        "mom60",
        "stateful",
    ),
    LabStrategy(
        "03_super_trend_align",
        "03",
        "Super Trend Alignment",
        "03 Super Trend Alignment [SCAN]",
        "Darvas ATR-5 plus Nifty > SMA50, stock close > SMA50, SMA50 > SMA200.",
        "mom60",
        "stateful",
    ),
    LabStrategy(
        "04_rs_darvas",
        "04",
        "Relative Strength Darvas",
        "04 Relative Strength Darvas [SCAN]",
        "Darvas ATR-5 plus Nifty > SMA50 and 126-day stock return > 126-day Nifty return (and > 0).",
        "mom126",
        "stateful",
    ),
    LabStrategy(
        "05_darvas_breakeven",
        "05",
        "Darvas Breakeven +10%",
        "05 Darvas Breakeven +10% [SCAN]",
        "Darvas ATR-5 + Nifty SMA50. After +10% the stop floor is the entry price.",
        "mom60",
        "stateful",
    ),
    LabStrategy(
        "06_mean_reversion",
        "06",
        "Mean Reversion",
        "06 Mean Reversion [SCAN]",
        "Buy RSI<30 while close > SMA200. Exit RSI>70 or -15% from entry. RSI is SMA-of-gains, not Wilder.",
        "30 - RSI",
        "vector",
    ),
    LabStrategy(
        "07_vol_squeeze",
        "07",
        "Volatility Squeeze",
        "07 Volatility Squeeze [SCAN]",
        "Prior BB width < 10%, close above upper band, volume > 3x SMA20. Exit close < SMA20.",
        "mom60",
        "vector",
    ),
    LabStrategy(
        "08_golden_cross_20_50",
        "08",
        "Golden Cross 20/50",
        "08 Golden Cross 20/50 [SCAN]",
        "SMA20 crosses above SMA50. Exit SMA20 < SMA50.",
        "mom60",
        "vector",
    ),
    LabStrategy(
        "09_52w_breakout",
        "09",
        "52-Week High Breakout",
        "09 52-Week High Breakout [SCAN]",
        "Close at/above prior 252-day high, volume > SMA20, Nifty > SMA50. 3-ATR trailing stop on close.",
        "mom60",
        "vector",
    ),
    LabStrategy(
        "10_ema_9_21",
        "10",
        "Fast EMA Crossover 9/21",
        "10 Fast EMA Crossover 9/21 [SCAN]",
        "EMA9 crosses above EMA21, Nifty > SMA50. Exit EMA9 < EMA21 or close < entry - 2*ATR.",
        "mom60",
        "vector",
    ),
    LabStrategy(
        "11_refined_mean_reversion",
        "11",
        "Refined Mean Reversion",
        "11 Refined Mean Reversion [SCAN]",
        "RSI crosses below 30, SMA50 > SMA200, close > SMA200. Exit RSI>60 or -10% stop.",
        "30 - RSI",
        "vector",
    ),
    LabStrategy(
        "12_golden_cross_50_200",
        "12",
        "Golden Cross 50/200",
        "12 Golden Cross 50/200 [SCAN]",
        "SMA50 crosses above SMA200. Exit SMA50 < SMA200.",
        "mom252",
        "vector",
    ),
    LabStrategy(
        "13_trend_pullback",
        "13",
        "Trend Pullback",
        "13 Trend Pullback [SCAN]",
        "Close > SMA200 and close crosses back above SMA50. Exit close < SMA200.",
        "mom252",
        "vector",
    ),
    LabStrategy(
        "14_bh_top_momentum",
        "14",
        "Buy and Hold Top Momentum",
        "14 Buy and Hold Top Momentum [SCAN]",
        "At the first 252-bar date, buy names with first-year return > 50%. Hold to the last session. No rebalance.",
        "first-year return",
        "rebalance",
    ),
    LabStrategy(
        "15_mrs_breakout",
        "15",
        "MRS Tight-Base Breakout",
        "15 MRS Tight-Base Breakout [SCAN]",
        "All eight Section-2 MRS gates. Exit close < 20-EMA or close < entry-bar base low.",
        "RS12M percentile",
        "universe",
    ),
    LabStrategy(
        "16_order_block",
        "16",
        "Order Block Break of Structure",
        "16 Order Block Break of Structure [SCAN]",
        "Nifty > SMA50, close > SMA50, close > prior 20-day high, last down-candle OB. Stop = OB low * 0.99, trail 3-day low, target 2R.",
        "mom60",
        "vector",
    ),
    LabStrategy(
        "17_long_term_mom",
        "17",
        "Long-Term Buy & Hold Momentum",
        "17 Long-Term Buy & Hold Momentum [SCAN]",
        "Annual rebalance. Hold top 10 names with 252-day return > 50%. allow_same_day_rebuy.",
        "mom252",
        "rebalance",
    ),
    LabStrategy(
        "18_fast_mom",
        "18",
        "Hyper-Concentrated Fast Momentum",
        "18 Hyper-Concentrated Fast Momentum [SCAN]",
        "Every 20 sessions buy the top 3 by 60-day momentum among names above SMA20. 10% of equity per name.",
        "mom60",
        "rebalance",
    ),
    LabStrategy(
        "19_low_dd_mom",
        "19",
        "Low-Drawdown Regime Momentum",
        "19 Low-Drawdown Regime Momentum [SCAN]",
        "Top 3 by 60-day momentum above SMA20, rebalance every 10 sessions, Nifty > SMA20 else flatten, 5% TSL.",
        "mom60",
        "rebalance",
    ),
    LabStrategy(
        "20_ultra_yield_mom",
        "20",
        "Ultra-Yield Multi-Timeframe",
        "20 Ultra-Yield Multi-Timeframe [SCAN]",
        "Top 2 by (20d+60d) momentum, both positive, close > SMA20. Rebalance every 5 sessions, Nifty >= SMA10 else flatten, 4% TSL.",
        "mom20+mom60",
        "rebalance",
    ),
    LabStrategy(
        "21_sma_10_50",
        "21",
        "Short-Term SMA 10/50",
        "21 Short-Term SMA 10/50 [SCAN]",
        "Level rule: hold while SMA10 > SMA50; exit when SMA10 < SMA50. Refills empty slots in an uptrend.",
        "mom60",
        "vector",
    ),
)

LAB_BY_ID = {item.strategy_id: item for item in LAB_STRATEGIES}
LAB_BY_TITLE = {item.scan_title: item for item in LAB_STRATEGIES}


def strategy_id_from_indicator_name(name: str | None) -> str | None:
    raw = (name or "").strip()
    if not raw:
        return None
    if raw in LAB_BY_TITLE:
        return LAB_BY_TITLE[raw].strategy_id
    lowered = raw.lower()
    for item in LAB_STRATEGIES:
        if item.scan_title.lower() == lowered:
            return item.strategy_id
        if lowered.startswith(item.number + " ") or lowered.startswith(item.strategy_id):
            return item.strategy_id
    return None


def allow_same_day_rebuy(strategy_id: str) -> bool:
    return strategy_id in SAME_DAY_REBUY_IDS
