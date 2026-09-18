"""Derived field helpers: delivery_pct, turnover, ADTV-20, weekly resample."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Sequence

import pandas as pd


def compute_turnover(close: float | Decimal | None, volume: int | float | None) -> Decimal | None:
    if close is None or volume is None:
        return None
    try:
        return (Decimal(str(close)) * Decimal(str(int(volume)))).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    except Exception:
        return None


def compute_delivery_pct(
    delivery_qty: int | float | None,
    traded_qty: int | float | None,
) -> Decimal | None:
    """delivery_pct = delivery_qty / traded_qty * 100.

    Never invents values. Returns None when inputs missing or traded_qty <= 0.
    Prefer NSE report traded_qty as denominator when available (not OHLCV volume).
    """
    if delivery_qty is None or traded_qty is None:
        return None
    try:
        tq = int(traded_qty)
        dq = int(delivery_qty)
    except (TypeError, ValueError):
        return None
    if tq <= 0:
        return None
    try:
        return (Decimal(dq) / Decimal(tq) * Decimal(100)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    except Exception:
        return None


def adtv_20(rows: Sequence[dict[str, Any]]) -> float | None:
    """Mean of last 20 sessions' turnover (or close*volume)."""
    if not rows:
        return None
    vals: list[float] = []
    for r in list(rows)[-20:]:
        t = r.get("turnover")
        if t is None:
            c, v = r.get("close"), r.get("volume")
            if c is None or v is None:
                continue
            t = float(c) * float(v)
        try:
            vals.append(float(t))
        except (TypeError, ValueError):
            continue
    if not vals:
        return None
    return sum(vals) / len(vals)


def _session_turnover(row: dict[str, Any]) -> float | None:
    t = row.get("turnover")
    if t is not None:
        try:
            return float(t)
        except (TypeError, ValueError):
            pass
    c, v = row.get("close"), row.get("volume")
    if c is None or v is None:
        return None
    try:
        return float(c) * float(v)
    except (TypeError, ValueError):
        return None


def attach_adtv_20_series(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Set ``adtv_20`` on each row: rolling mean of up to 20 sessions of close×volume.

    Rows should be sorted ascending by trade_date. Mutates and returns the list.
    Uses available history when fewer than 20 bars exist (same as ``adtv_20``).
    """
    ordered = list(rows)
    window: list[float] = []
    for r in ordered:
        turn = _session_turnover(r)
        if turn is not None:
            window.append(turn)
            if len(window) > 20:
                window = window[-20:]
            r["adtv_20"] = sum(window) / len(window)
        else:
            # Keep prior window; mark null for this bar if no turnover
            r["adtv_20"] = (sum(window) / len(window)) if window else None
    return ordered


def compute_adtv_20_for_bar(
    history_before: Sequence[dict[str, Any]],
    bar: dict[str, Any],
) -> float | None:
    """On-the-fly ADTV-20 for one bar given prior sessions (oldest→newest) + bar."""
    combined = list(history_before) + [bar]
    return adtv_20(combined[-20:])


def weekly_ohlcv(daily_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resample daily OHLCV to weekly bars (on-demand; not stored)."""
    if not daily_rows:
        return []
    df = pd.DataFrame(list(daily_rows))
    if df.empty or "trade_date" not in df.columns:
        return []
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date").sort_index()
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    cols = {k: v for k, v in agg.items() if k in df.columns}
    weekly = df.resample("W-FRI").agg(cols).dropna(how="all")
    out: list[dict[str, Any]] = []
    for idx, row in weekly.iterrows():
        item = {"trade_date": idx.date() if hasattr(idx, "date") else idx}
        for c in cols:
            val = row.get(c)
            if pd.isna(val):
                item[c] = None
            else:
                item[c] = float(val) if c != "volume" else int(val)
        out.append(item)
    return out
