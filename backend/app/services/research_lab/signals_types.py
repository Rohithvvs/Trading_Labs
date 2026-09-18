"""Shared market/signal containers for the research-lab book."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd


@dataclass
class MarketData:
    close: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    open_: pd.DataFrame
    volume: pd.DataFrame
    bench: pd.Series
    company: Dict[str, str] = field(default_factory=dict)
    industry: Dict[str, str] = field(default_factory=dict)
    sector: Dict[str, str] = field(default_factory=dict)


@dataclass
class SignalBook:
    buy: pd.DataFrame
    rank: pd.DataFrame
    sell: Optional[pd.DataFrame] = None
    hard_stop_pct: Optional[float] = None
    trail_atr_mult: Optional[float] = None
    atr: Optional[pd.DataFrame] = None
    tsl_pct: Optional[float] = None
    exit_below: Optional[pd.DataFrame] = None
    entry_atr_stop_mult: Optional[float] = None
    take_profit_rr: Optional[float] = None
    initial_stop: Optional[pd.DataFrame] = None
    trail_stop: Optional[pd.DataFrame] = None
    allow_same_day_rebuy: bool = False
    notes: str = ""
