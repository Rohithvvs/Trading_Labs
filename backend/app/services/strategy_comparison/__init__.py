"""Strategy Comparison: compose existing Strategy Tester and LEAN backtest data."""

from .comparison_service import (
    MAX_SLOTS,
    MIN_SLOTS,
    CompareError,
    catalog,
    compare_slots,
    config_mismatches,
    extract_logic,
    list_runs_for_strategy,
    monthly_yearly_from_equity,
    signal_comparison,
    trade_distribution,
)

__all__ = [
    "MAX_SLOTS",
    "MIN_SLOTS",
    "CompareError",
    "catalog",
    "compare_slots",
    "config_mismatches",
    "extract_logic",
    "list_runs_for_strategy",
    "monthly_yearly_from_equity",
    "signal_comparison",
    "trade_distribution",
]
