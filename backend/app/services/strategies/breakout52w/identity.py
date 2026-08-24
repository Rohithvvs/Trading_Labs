"""Stable identity, lock, and first-failure codes for 52-Week High Breakout."""

from __future__ import annotations

STRATEGY_ID = "09_52w_breakout"
STRATEGY_VERSION = "1"
DISPLAY_NAME = "52-Week High Breakout"
SHORT_NAME = "52W"
UNIVERSE_ID = "nifty500"
TIMEFRAME = "1D"
# Board / stock-detail window only. Does not change entry, exit, or sizing rules.
ATTRIBUTION_WINDOW = "3Y"
ATTRIBUTION_YEARS = 3
ATTRIBUTION_PERIODS = ("1D", "1W", "1M", "1Y", "3Y", "5Y", "7Y", "8Y", "18Y")
HISTORICAL_PERIOD = "18Y"
# Calendar pad so ~252 trading sessions exist before the longest board window.
WARMUP_CALENDAR_DAYS = 400

WARMUP_SESSIONS = 252
MAX_POSITIONS = 10
ALLOC_PCT = 0.10
DEFAULT_MODE = "B"
DEFAULT_CAPITAL = 100_000.0
ATR_PERIOD = 14
ATR_MULT = 3.0
NAN_ATR_STOP_FRAC = 0.90
VOL_SMA_PERIOD = 20
HIGH_LOOKBACK = 252
MARKET_SMA_PERIOD = 50
RANK_LOOKBACK = 60
# Data-access bound only — not a trading threshold.
# 260 = 252-session prior high + 8-session buffer (TimeframeConfig.lookback_window).
DEFAULT_OHLCV_LOOKBACK = HIGH_LOOKBACK + 8
LOCK_NAME = "scan:09_52w_breakout"
CACHE_KEY_LATEST = "scanner:latest:09_52w_breakout:v1"

FAILURE_CODES: tuple[str, ...] = (
    "not_in_universe",
    "insufficient_history",
    "missing_bar",
    "close_below_prior_high",
    "volume_not_above_average",
    "market_filter_off",
    "sold_today",
    "no_free_slot",
    "data_source_failure",
    "other",
)

FAILURE_LABELS: dict[str, str] = {
    "not_in_universe": "Not in investable universe",
    "insufficient_history": "Insufficient historical data",
    "missing_bar": "Missing or invalid close, high, or volume",
    "close_below_prior_high": "Close below the prior 252-session high",
    "volume_not_above_average": "Volume not above the 20-session average",
    "market_filter_off": "Market filter off",
    "sold_today": "Sold today (same-day rebuy blocked)",
    "no_free_slot": "Buy signal but no free slot",
    "data_source_failure": "Data source failure",
    "other": "Other",
}
