"""Strategy-grade market data ingestion package.

Public surface for strategies:
- reader: equity history, delivery fields, NIFTY500 index series
- derived: turnover, delivery_pct, ADTV-20, weekly resample
- freshness: global gate + STR-041 delivery check helper
- ensure: auto-fetch latest session before scanners
- pipelines: full_load, daily_update
"""
from .derived import adtv_20, compute_delivery_pct, compute_turnover, weekly_ohlcv
from .ensure import ensure_latest_market_data
from .freshness import check_delivery_for_strategy, evaluate_freshness
from .reader import get_equity_history, get_index_history

__all__ = [
    "adtv_20",
    "compute_delivery_pct",
    "compute_turnover",
    "weekly_ohlcv",
    "check_delivery_for_strategy",
    "evaluate_freshness",
    "ensure_latest_market_data",
    "get_equity_history",
    "get_index_history",
]
