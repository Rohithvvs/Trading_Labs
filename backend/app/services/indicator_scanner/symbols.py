"""Symbol mapping between Pine-style identifiers and TradingLabs stores."""

from __future__ import annotations

from ...config.settings import settings
from ...utils.symbol import canonical_symbol

BENCHMARK_ALIASES = {
    "NSE:CNX500": "NIFTY500",
    "CNX500": "NIFTY500",
    "NIFTY500": "NIFTY500",
    "NIFTY 500": "NIFTY500",
    "NSE:NIFTY500": "NIFTY500",
    "NSE:NIFTY_500": "NIFTY500",
    "INDIA500": "NIFTY500",
}


def map_benchmark_symbol(raw: str) -> str:
    key = (raw or "").strip().upper().replace("_", "")
    compact = key.replace(" ", "")
    for alias, mapped in BENCHMARK_ALIASES.items():
        if compact == alias.replace(" ", "").replace("_", "").upper():
            return mapped
    configured = getattr(settings, "strategy_index_store_symbol", None) or "NIFTY500"
    if compact in {"NSE:CNX500", "CNX500"}:
        return str(configured)
    return canonical_symbol(raw) or raw


def display_symbol(raw: str) -> str:
    return canonical_symbol(raw) or (raw or "").upper()


def is_supported_timeframe(timeframe: str | None) -> bool:
    value = (timeframe or "1D").strip().upper()
    return value in {"1D", "D", "DAILY"}


def normalize_timeframe(timeframe: str | None) -> str:
    if not is_supported_timeframe(timeframe):
        return "1D"
    return "1D"
