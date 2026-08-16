"""Stable identity, gates, and first-failure codes for LTM."""

from __future__ import annotations

STRATEGY_ID = "17_long_term_mom"
DISPLAY_NAME = "Long-Term Buy & Hold Momentum"
SHORT_NAME = "LTM"

WARMUP_SESSIONS = 252
REBALANCE_EVERY = 252
MOMENTUM_GATE = 0.50  # exclusive: must be strictly greater
MAX_SELECTED = 10
DEFAULT_MODE = "A"
DEFAULT_CAPITAL = 100_000.0
RESEARCH_BPS = 0.0025
LOCK_NAME = "scan:17_long_term_mom"
CACHE_KEY_LATEST = "scanner:latest:17_long_term_mom:v1"

FAILURE_CODES: tuple[str, ...] = (
    "not_in_universe",
    "insufficient_history",
    "missing_close_t",
    "momentum_undefined",
    "failed_momentum_gate",
    "ranked_outside_top_10",
    "data_source_failure",
    "other",
)

FAILURE_LABELS: dict[str, str] = {
    "not_in_universe": "Not in investable universe",
    "insufficient_history": "Insufficient historical data",
    "missing_close_t": "Missing or invalid close",
    "momentum_undefined": "Undefined momentum",
    "failed_momentum_gate": "Failed +50% momentum gate",
    "ranked_outside_top_10": "Eligible but ranked outside top 10",
    "data_source_failure": "Data source failure",
    "other": "Other",
}
