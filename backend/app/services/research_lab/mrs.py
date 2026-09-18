"""
Mansfield RS Tight-Base Breakout.

Section 1 computes structural / volatility fields.
Section 2 fires a BUY only when every listed gate is True on the same bar.

Exits are not specified in Sections 1–2. The backtester applies documented
exit rules separately (see backtest_mrs_breakout.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


BENCHMARK_FILENAME = "NIFTY500.csv"
STOCK_DIRNAME = "stocks"
INDEX_DIRNAME = "indices"
UNIVERSE_DIRNAME = "universe"
EARNINGS_DIRNAME = "earnings"
CONSTITUENTS_FILENAME = "constituents.csv"

# Longest lookback is the 252-session RS new-high window, which needs a prior bar.
MIN_HISTORY_BARS = 253


@dataclass
class MRSBreakoutConfig:
    """Defaults match the specification exactly."""

    rsd_sma_period: int = 200
    base_lookback: int = 15
    base_width_max_pct: float = 10.0
    rs_lookback_6m: int = 126
    rs_lookback_12m: int = 252
    rs_percentile_gate: float = 80.0
    bench_ret_15_max: float = 0.02
    vol_sma_period: int = 20
    vol_mult: float = 1.5
    rs_new_high_lookback: int = 252
    rs_leading_window: int = 15
    ema_period: int = 20
    earnings_forward_sessions: int = 5
    allow_missing_events: bool = False
    allow_missing_sectors: bool = False


@dataclass
class MRSDataset:
    close: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    volume: pd.DataFrame
    bench_close: pd.Series
    sector_close: pd.DataFrame
    symbol_to_sector: Dict[str, str]
    earnings: Dict[str, pd.DatetimeIndex]
    symbols_with_event_data: set


@dataclass
class SignalPanel:
    buy: pd.DataFrame
    rsd: pd.DataFrame
    mrs: pd.DataFrame
    mrs_valid: pd.DataFrame
    ema20: pd.DataFrame
    rs6m_rating: pd.DataFrame
    rs12m_rating: pd.DataFrame
    base_high: pd.DataFrame
    base_low: pd.DataFrame
    base_median: pd.DataFrame
    base_width_pct: pd.DataFrame
    sector_mrs: pd.DataFrame
    gates: Dict[str, pd.DataFrame]
    reject_reason: pd.DataFrame


def normalize_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series).dt.tz_localize(None).dt.normalize()


def _read_ohlcv_csv(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(filepath)
    required = {"date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{filepath} missing columns: {sorted(missing)}")
    df = df.copy()
    df["date"] = normalize_dates(df["date"])
    if "volume" not in df.columns:
        df["volume"] = np.nan
    df = df.dropna(subset=["date", "close"])
    df = df.drop_duplicates(subset=["date"], keep="last")
    df = df.sort_values("date").set_index("date")
    return df[["open", "high", "low", "close", "volume"]]


def load_mrs_dataset(data_dir: str) -> MRSDataset:
    """Load the structured data_mrs/ tree produced by download_mrs_data.py."""
    stock_dir = os.path.join(data_dir, STOCK_DIRNAME)
    index_dir = os.path.join(data_dir, INDEX_DIRNAME)
    universe_path = os.path.join(data_dir, UNIVERSE_DIRNAME, CONSTITUENTS_FILENAME)
    earnings_dir = os.path.join(data_dir, EARNINGS_DIRNAME)
    bench_path = os.path.join(index_dir, BENCHMARK_FILENAME)

    if not os.path.isfile(bench_path):
        raise FileNotFoundError(
            f"Benchmark file not found: {bench_path}. Run download_mrs_data.py first."
        )
    if not os.path.isdir(stock_dir):
        raise FileNotFoundError(f"Stock directory not found: {stock_dir}")

    bench = _read_ohlcv_csv(bench_path)
    bench_close = bench["close"].rename("benchmark")

    close_parts: Dict[str, pd.Series] = {}
    high_parts: Dict[str, pd.Series] = {}
    low_parts: Dict[str, pd.Series] = {}
    volume_parts: Dict[str, pd.Series] = {}

    for name in sorted(os.listdir(stock_dir)):
        if not name.lower().endswith(".csv"):
            continue
        symbol = os.path.splitext(name)[0].upper()
        if symbol in {"NIFTY500", "NIFTY50", "NIFTY_500"}:
            continue
        try:
            df = _read_ohlcv_csv(os.path.join(stock_dir, name))
        except Exception:
            continue
        if len(df) < MIN_HISTORY_BARS:
            continue
        close_parts[symbol] = df["close"].rename(symbol)
        high_parts[symbol] = df["high"].rename(symbol)
        low_parts[symbol] = df["low"].rename(symbol)
        volume_parts[symbol] = df["volume"].rename(symbol)

    if not close_parts:
        raise RuntimeError(f"No usable stock CSVs in {stock_dir}")

    # Align every series onto the benchmark calendar (same trading-date index).
    close = pd.concat(close_parts, axis=1).reindex(bench_close.index)
    high = pd.concat(high_parts, axis=1).reindex(bench_close.index)
    low = pd.concat(low_parts, axis=1).reindex(bench_close.index)
    volume = pd.concat(volume_parts, axis=1).reindex(bench_close.index)
    close.columns = [str(c).upper() for c in close.columns]
    high.columns = close.columns
    low.columns = close.columns
    volume.columns = close.columns

    sector_close = pd.DataFrame(index=bench_close.index)
    if os.path.isdir(index_dir):
        for name in sorted(os.listdir(index_dir)):
            if not name.lower().endswith(".csv"):
                continue
            key = os.path.splitext(name)[0].upper()
            if key in {"NIFTY500", "NIFTY50", "NIFTY_500"}:
                continue
            try:
                sdf = _read_ohlcv_csv(os.path.join(index_dir, name))
            except Exception:
                continue
            sector_close[key] = sdf["close"].reindex(bench_close.index)

    symbol_to_sector: Dict[str, str] = {}
    if os.path.isfile(universe_path):
        uni = pd.read_csv(universe_path)
        cols = {c.lower().strip(): c for c in uni.columns}
        sym_col = cols.get("symbol")
        sec_col = cols.get("sector_index") or cols.get("sector")
        if sym_col is not None and sec_col is not None:
            for _, row in uni.iterrows():
                sym = str(row[sym_col]).strip().upper()
                sec = str(row[sec_col]).strip().upper()
                if sym and sec and sec not in {"NAN", "NONE", ""}:
                    symbol_to_sector[sym] = sec

    earnings: Dict[str, pd.DatetimeIndex] = {}
    symbols_with_event_data: set = set()
    if os.path.isdir(earnings_dir):
        for name in os.listdir(earnings_dir):
            if not name.lower().endswith(".csv"):
                continue
            symbol = os.path.splitext(name)[0].upper()
            path = os.path.join(earnings_dir, name)
            try:
                edf = pd.read_csv(path)
            except Exception:
                continue
            date_col = None
            for candidate in ("earnings_date", "date", "Earnings Date"):
                if candidate in edf.columns:
                    date_col = candidate
                    break
            if date_col is None and len(edf.columns):
                date_col = edf.columns[0]
            symbols_with_event_data.add(symbol)
            if date_col is None or edf.empty:
                earnings[symbol] = pd.DatetimeIndex([])
                continue
            dates = pd.to_datetime(edf[date_col], errors="coerce", utc=True)
            dates = dates.dropna().dt.tz_localize(None).dt.normalize()
            earnings[symbol] = pd.DatetimeIndex(sorted(dates.unique()))

    return MRSDataset(
        close=close,
        high=high,
        low=low,
        volume=volume,
        bench_close=bench_close,
        sector_close=sector_close,
        symbol_to_sector=symbol_to_sector,
        earnings=earnings,
        symbols_with_event_data=symbols_with_event_data,
    )


def compute_rsd(close: pd.DataFrame, bench_close: pd.Series) -> pd.DataFrame:
    """RSD_t = (Close_Stock,t / Close_Benchmark,t) * 100."""
    aligned = bench_close.reindex(close.index)
    return close.div(aligned, axis=0) * 100.0


def compute_mrs(rsd: pd.DataFrame, period: int = 200) -> tuple[pd.DataFrame, pd.DataFrame]:
    """MRS_t = (RSD_t / SMA(RSD, period)_t - 1) * 100. Valid after `period` RSD prints."""
    sma = rsd.rolling(window=period, min_periods=period).mean()
    mrs = (rsd / sma - 1.0) * 100.0
    valid = rsd.notna().rolling(window=period, min_periods=period).sum() >= period
    mrs = mrs.where(valid)
    return mrs, valid


def compute_ema(close: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def compute_base_metrics(
    high: pd.DataFrame, low: pd.DataFrame, lookback: int = 15
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Base window is [t-lookback, t-1]; the breakout bar t is excluded."""
    base_high = high.shift(1).rolling(window=lookback, min_periods=lookback).max()
    base_low = low.shift(1).rolling(window=lookback, min_periods=lookback).min()
    base_median = (base_high + base_low) / 2.0
    base_width_pct = ((base_high - base_low) / base_median) * 100.0
    return base_high, base_low, base_median, base_width_pct


def compute_relative_returns(
    close: pd.DataFrame, bench_close: pd.Series, lookback: int
) -> pd.DataFrame:
    stock_ret = close / close.shift(lookback) - 1.0
    bench_ret = bench_close.reindex(close.index) / bench_close.reindex(close.index).shift(lookback) - 1.0
    return stock_ret.sub(bench_ret, axis=0)


def compute_rs_ratings(
    close: pd.DataFrame, bench_close: pd.Series, lookback_6m: int = 126, lookback_12m: int = 252
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Point-in-time percentile rank of relative 6M / 12M returns across the universe."""
    rel_6m = compute_relative_returns(close, bench_close, lookback_6m)
    rel_12m = compute_relative_returns(close, bench_close, lookback_12m)
    rs6m = rel_6m.rank(axis=1, pct=True, method="average") * 100.0
    rs12m = rel_12m.rank(axis=1, pct=True, method="average") * 100.0
    return rs6m, rs12m


def compute_rs_leading_high(
    rsd: pd.DataFrame, new_high_lookback: int = 252, leading_window: int = 15
) -> pd.DataFrame:
    """True when some d in [t-leading_window, t-1] printed a fresh 1-year RSD high."""
    prior_max = rsd.shift(1).rolling(window=new_high_lookback, min_periods=new_high_lookback).max()
    rs_new_high = rsd > prior_max
    leading = (
        rs_new_high.astype(float)
        .shift(1)
        .rolling(window=leading_window, min_periods=leading_window)
        .max()
        >= 1.0
    )
    return leading


def compute_sector_mrs(
    sector_close: pd.DataFrame,
    bench_close: pd.Series,
    symbols: Iterable[str],
    symbol_to_sector: Dict[str, str],
    period: int = 200,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Sector_RSD = Sector_Index_Close / NIFTY500_Close * 100
    Sector_MRS = (Sector_RSD / SMA(Sector_RSD, 200) - 1) * 100
    Returns (sector_mrs_by_stock, has_mapping).
    """
    symbols = list(symbols)
    index = bench_close.index
    if sector_close is None or sector_close.empty:
        blank = pd.DataFrame(np.nan, index=index, columns=symbols)
        mapped = pd.DataFrame(False, index=index, columns=symbols)
        return blank, mapped

    sector_rsd = compute_rsd(sector_close, bench_close)
    sector_mrs_idx, _ = compute_mrs(sector_rsd, period=period)

    out = pd.DataFrame(np.nan, index=index, columns=symbols)
    mapped = pd.DataFrame(False, index=index, columns=symbols)
    available = {c.upper(): c for c in sector_mrs_idx.columns}

    for sym in symbols:
        sec = symbol_to_sector.get(sym)
        if not sec:
            continue
        col = available.get(sec.upper())
        if col is None:
            continue
        out[sym] = sector_mrs_idx[col]
        mapped[sym] = sector_mrs_idx[col].notna()

    return out, mapped


def compute_event_ok(
    index: pd.DatetimeIndex,
    symbols: Iterable[str],
    earnings: Dict[str, pd.DatetimeIndex],
    symbols_with_event_data: set,
    forward_sessions: int = 5,
    allow_missing_events: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Pass when no scheduled earnings land on sessions [t+1, t+forward].
    Missing event history fails closed unless allow_missing_events is set.
    """
    symbols = list(symbols)
    event_ok = pd.DataFrame(False, index=index, columns=symbols)
    data_available = pd.DataFrame(False, index=index, columns=symbols)

    n = len(index)
    if n == 0:
        return event_ok, data_available

    for sym in symbols:
        has_data = sym in symbols_with_event_data
        data_available[sym] = has_data
        if not has_data:
            if allow_missing_events:
                event_ok[sym] = True
            continue

        event_ok[sym] = True
        edates = earnings.get(sym, pd.DatetimeIndex([]))
        if edates is None or len(edates) == 0:
            continue

        blocked = np.zeros(n, dtype=bool)
        for raw in edates:
            event_day = pd.Timestamp(raw).normalize()
            idx = int(index.searchsorted(event_day))
            if idx >= n:
                continue
            for offset in range(1, forward_sessions + 1):
                t_idx = idx - offset
                if t_idx >= 0:
                    blocked[t_idx] = True
        event_ok[sym] = ~blocked

    return event_ok, data_available


def _first_failing_gate(gates: Dict[str, pd.DataFrame], order: List[str]) -> pd.DataFrame:
    reason = pd.DataFrame("PASS", index=gates[order[0]].index, columns=gates[order[0]].columns)
    assigned = pd.DataFrame(False, index=reason.index, columns=reason.columns)
    for name in order:
        fail = ~gates[name].fillna(False)
        take = fail & ~assigned
        reason = reason.mask(take, name)
        assigned = assigned | take
    return reason


def generate_signals(
    dataset: MRSDataset,
    config: Optional[MRSBreakoutConfig] = None,
) -> SignalPanel:
    """Evaluate every Section 2 gate on the aligned universe panel."""
    cfg = config or MRSBreakoutConfig()
    close, high, low, volume = dataset.close, dataset.high, dataset.low, dataset.volume
    bench = dataset.bench_close.reindex(close.index)

    rsd = compute_rsd(close, bench)
    mrs, mrs_valid = compute_mrs(rsd, period=cfg.rsd_sma_period)
    ema20 = compute_ema(close, period=cfg.ema_period)
    base_high, base_low, base_median, base_width_pct = compute_base_metrics(
        high, low, lookback=cfg.base_lookback
    )
    rs6m_rating, rs12m_rating = compute_rs_ratings(
        close, bench, lookback_6m=cfg.rs_lookback_6m, lookback_12m=cfg.rs_lookback_12m
    )
    rs_leading = compute_rs_leading_high(
        rsd,
        new_high_lookback=cfg.rs_new_high_lookback,
        leading_window=cfg.rs_leading_window,
    )
    sector_mrs, sector_mapped = compute_sector_mrs(
        dataset.sector_close,
        bench,
        close.columns,
        dataset.symbol_to_sector,
        period=cfg.rsd_sma_period,
    )
    event_ok, event_data_available = compute_event_ok(
        close.index,
        close.columns,
        dataset.earnings,
        dataset.symbols_with_event_data,
        forward_sessions=cfg.earnings_forward_sessions,
        allow_missing_events=cfg.allow_missing_events,
    )

    bench_ret_15 = bench / bench.shift(cfg.base_lookback) - 1.0
    quiet_market = bench_ret_15.le(cfg.bench_ret_15_max).fillna(False)
    vol_sma = volume.rolling(window=cfg.vol_sma_period, min_periods=cfg.vol_sma_period).mean()

    enough_history = close.notna()
    if len(enough_history) > MIN_HISTORY_BARS:
        enough_history.iloc[:MIN_HISTORY_BARS] = False
    else:
        enough_history.loc[:, :] = False

    gate_rs = (rs6m_rating > cfg.rs_percentile_gate) & (rs12m_rating > cfg.rs_percentile_gate)
    gate_consol = base_high.notna().mul(quiet_market, axis=0).astype(bool)
    gate_width = base_width_pct <= cfg.base_width_max_pct
    gate_breakout = close > base_high
    gate_rs_lead = rs_leading.fillna(False)
    gate_volume = volume >= (cfg.vol_mult * vol_sma)
    if cfg.allow_missing_sectors:
        gate_sector = sector_mrs.gt(0) | ~sector_mapped
    else:
        gate_sector = sector_mapped & sector_mrs.gt(0)
    gate_event = event_ok.copy()
    if not cfg.allow_missing_events:
        gate_event = gate_event & event_data_available

    gates = {
        "enough_history": enough_history,
        "rs_percentile": gate_rs.fillna(False),
        "consolidation_maturity": gate_consol.fillna(False),
        "base_width": gate_width.fillna(False),
        "breakout": gate_breakout.fillna(False),
        "rs_leading_high": gate_rs_lead,
        "volume": gate_volume.fillna(False),
        "sector_alignment": gate_sector.fillna(False),
        "corporate_event": gate_event.fillna(False),
        "event_data_available": event_data_available,
    }

    buy = enough_history.copy()
    for key in (
        "rs_percentile",
        "consolidation_maturity",
        "base_width",
        "breakout",
        "rs_leading_high",
        "volume",
        "sector_alignment",
        "corporate_event",
    ):
        buy = buy & gates[key]

    reject_reason = _first_failing_gate(
        gates,
        [
            "enough_history",
            "rs_percentile",
            "consolidation_maturity",
            "base_width",
            "breakout",
            "rs_leading_high",
            "volume",
            "sector_alignment",
            "corporate_event",
        ],
    )
    reject_reason = reject_reason.mask(buy, "PASS")
    reject_reason = reject_reason.mask(
        (~gates["corporate_event"])
        & (~gates["event_data_available"])
        & (reject_reason == "corporate_event"),
        "EVENT_DATA_UNAVAILABLE",
    )

    return SignalPanel(
        buy=buy,
        rsd=rsd,
        mrs=mrs,
        mrs_valid=mrs_valid,
        ema20=ema20,
        rs6m_rating=rs6m_rating,
        rs12m_rating=rs12m_rating,
        base_high=base_high,
        base_low=base_low,
        base_median=base_median,
        base_width_pct=base_width_pct,
        sector_mrs=sector_mrs,
        gates=gates,
        reject_reason=reject_reason,
    )


def gate_funnel(panel: SignalPanel) -> pd.DataFrame:
    """Successive-AND waterfall over every bar that has a close print."""
    live = panel.gates["enough_history"]
    rows = []
    remaining = live.copy()
    order = [
        "enough_history",
        "rs_percentile",
        "consolidation_maturity",
        "base_width",
        "breakout",
        "rs_leading_high",
        "volume",
        "sector_alignment",
        "corporate_event",
    ]
    total = int(live.sum().sum())
    for name in order:
        if name != "enough_history":
            remaining = remaining & panel.gates[name]
        count = int(remaining.sum().sum())
        rows.append(
            {
                "gate": name,
                "bars_passing": count,
                "pct_of_history": round(100.0 * count / total, 4) if total else 0.0,
            }
        )
    return pd.DataFrame(rows)


def latest_buy_candidates(panel: SignalPanel, date: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """Rows that fire a BUY on `date` (default: last session in the panel)."""
    if date is None:
        date = panel.buy.index[-1]
    date = pd.Timestamp(date).normalize()
    if date not in panel.buy.index:
        raise KeyError(f"{date.date()} is not in the signal calendar")
    flags = panel.buy.loc[date]
    symbols = flags[flags].index.tolist()
    rows = []
    for sym in symbols:
        rows.append(
            {
                "date": date,
                "symbol": sym,
                "rs6m_rating": panel.rs6m_rating.loc[date, sym],
                "rs12m_rating": panel.rs12m_rating.loc[date, sym],
                "mrs": panel.mrs.loc[date, sym],
                "sector_mrs": panel.sector_mrs.loc[date, sym],
                "base_high": panel.base_high.loc[date, sym],
                "base_low": panel.base_low.loc[date, sym],
                "base_width_pct": panel.base_width_pct.loc[date, sym],
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["rs12m_rating", "rs6m_rating"], ascending=False).reset_index(drop=True)
