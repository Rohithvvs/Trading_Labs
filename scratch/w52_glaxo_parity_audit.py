"""GLAXO 52W parity diagnostic — read-only. Does not change strategy rules.

Prints:
  - stored OHLCV span
  - actual Trading Labs replay trades
  - daily signal counts under alternative entry/exit hypotheses
  - first few breakout-state days vs first Labs trade
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from app.services.market_data_ingestion.repository import fetch_equity_history, fetch_index_history
from app.services.strategies.breakout52w.book_engine import replay_book
from app.services.strategies.breakout52w.identity import DEFAULT_CAPITAL
from app.services.strategies.breakout52w.indicators import (
    atr14,
    market_ok,
    prior_high_252,
    true_range,
    vol_sma20,
    wilder_atr14,
)
from app.services.strategies.breakout52w.trail import initial_tsl, should_exit, update_trail


SYMBOL = "GLAXO-EQ"
START = date(2023, 8, 19)
END = date(2026, 8, 19)
OUT = ROOT / "scratch" / "glaxo_w52_parity_daily.csv"


def _as_date(v):
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def simulate_state_hold(days, highs, closes, volumes, index, *, use_volume, use_market, exit_mode, atr_mult=3.0, atr_kind="sma"):
    """Single-name sequential sim. No pyramid, no same-bar rebuy.

    exit_mode:
      atr_close       — close < TSL (Labs)
      atr_intrabar    — low < TSL (TV-like stop fill)
      leave_breakout  — close < prior 252 high
      pct_1_28        — close < entry * (1 - 0.0128)
      next_bar        — always exit next session
    """
    n = len(days)
    held = False
    entry_i = None
    entry_px = None
    hwm = tsl = None
    trades = []
    for t in range(n):
        if days[t] < START or days[t] > END:
            continue
        ph = prior_high_252(highs, t)
        vs = vol_sma20(volumes, t)
        mok = market_ok(index, t)
        c = closes[t]
        h = highs[t]
        v = volumes[t]
        low = None  # filled by caller via lows
        breakout = ph is not None and c is not None and c >= ph
        vol_ok = (not use_volume) or (vs is not None and v is not None and v > vs)
        m_ok = (not use_market) or (mok is True)
        if held:
            # update / exit
            if exit_mode == "leave_breakout":
                if not breakout:
                    trades.append((days[entry_i], days[t], entry_px, c, (c / entry_px - 1) * 100, "leave_breakout"))
                    held = False
            elif exit_mode == "next_bar":
                trades.append((days[entry_i], days[t], entry_px, c, (c / entry_px - 1) * 100, "next_bar"))
                held = False
            elif exit_mode == "pct_1_28":
                if c < entry_px * (1 - 0.0128) or not breakout:
                    reason = "pct_stop" if c < entry_px * (1 - 0.0128) else "leave_breakout"
                    trades.append((days[entry_i], days[t], entry_px, c, (c / entry_px - 1) * 100, reason))
                    held = False
            else:
                atr = (wilder_atr14 if atr_kind == "wilder" else atr14)(highs, lows_global, closes, t)
                is_entry = t == entry_i
                hwm, tsl = update_trail(hwm=hwm, tsl=tsl, close=c, atr=atr, is_entry_bar=is_entry)
                hit = False
                if not is_entry:
                    if exit_mode == "atr_close":
                        hit = c < tsl
                    elif exit_mode == "atr_intrabar":
                        hit = lows_global[t] is not None and lows_global[t] < tsl
                    if atr_mult != 3.0 and not is_entry:
                        # rebuild TSL with custom mult from current HWM
                        pass
                if hit:
                    px = tsl if exit_mode == "atr_intrabar" else c
                    trades.append((days[entry_i], days[t], entry_px, px, (px / entry_px - 1) * 100, exit_mode))
                    held = False
        if not held:
            if breakout and vol_ok and m_ok and t >= 252:
                held = True
                entry_i = t
                entry_px = c
                atr = (wilder_atr14 if atr_kind == "wilder" else atr14)(highs, lows_global, closes, t)
                hwm = c
                tsl = (c - atr_mult * atr) if atr is not None else c * 0.90
    if held:
        t = n - 1
        trades.append((days[entry_i], days[t], entry_px, closes[t], (closes[t] / entry_px - 1) * 100, "eod"))
    return trades


lows_global: list = []


def count_days(days, highs, closes, volumes, index, lows):
    n = len(days)
    stats = {
        "bars_in_window": 0,
        "close_ge_prior252": 0,
        "close_gt_prior252": 0,
        "high_ge_prior252": 0,
        "close_ge_and_vol": 0,
        "close_ge_vol_market": 0,
        "new_high_cross": 0,  # first day of a close>=prior streak
        "tv_always_true_high_in_window": 0,  # high >= max(high[t-251:t+1]) always
    }
    prev_break = False
    for t in range(n):
        if days[t] < START or days[t] > END:
            continue
        stats["bars_in_window"] += 1
        ph = prior_high_252(highs, t)
        vs = vol_sma20(volumes, t)
        mok = market_ok(index, t)
        c, h, v = closes[t], highs[t], volumes[t]
        if ph is None:
            prev_break = False
            continue
        ge = c >= ph
        gt = c > ph
        hg = h >= ph
        if ge:
            stats["close_ge_prior252"] += 1
        if gt:
            stats["close_gt_prior252"] += 1
        if hg:
            stats["high_ge_prior252"] += 1
        if ge and vs is not None and v is not None and v > vs:
            stats["close_ge_and_vol"] += 1
            if mok is True:
                stats["close_ge_vol_market"] += 1
        if ge and not prev_break:
            stats["new_high_cross"] += 1
        prev_break = ge
        # TradingView ta.highest(high, 252) includes current bar
        if t >= 251:
            window = highs[t - 251 : t + 1]
            if h is not None and all(x is not None for x in window) and h >= max(window):
                stats["tv_always_true_high_in_window"] += 1
    return stats


async def main():
    global lows_global
    eq = await fetch_equity_history(SYMBOL)
    idx = await fetch_index_history("NIFTY500")
    if not eq:
        print("NO_DATA", SYMBOL)
        return
    days = [_as_date(r["trade_date"]) for r in eq]
    opens = [float(r["open"]) for r in eq]
    highs = [float(r["high"]) for r in eq]
    lows = [float(r["low"]) for r in eq]
    closes = [float(r["close"]) for r in eq]
    volumes = [float(r.get("volume") or 0) for r in eq]
    lows_global = lows
    idx_map = {_as_date(r["trade_date"]): float(r["close"]) for r in idx}
    index = [idx_map.get(d) for d in days]

    print("=== DATA ===")
    print("symbol", SYMBOL)
    print("first", days[0], "last", days[-1], "bars", len(days))
    print("first_close", closes[0], "last_close", closes[-1])
    win = [(d, o, h, l, c, v) for d, o, h, l, c, v in zip(days, opens, highs, lows, closes, volumes) if START <= d <= END]
    print("window_bars", len(win), "window_first", win[0][0] if win else None, "window_last", win[-1][0] if win else None)
    print("index_bars", len(idx_map), "index_first", min(idx_map) if idx_map else None, "index_last", max(idx_map) if idx_map else None)

    high_m = {SYMBOL: {d: h for d, h in zip(days, highs)}}
    low_m = {SYMBOL: {d: l for d, l in zip(days, lows)}}
    close_m = {SYMBOL: {d: c for d, c in zip(days, closes)}}
    vol_m = {SYMBOL: {d: v for d, v in zip(days, volumes)}}
    replay = replay_book(days, high_m, low_m, close_m, vol_m, idx_map, {SYMBOL}, initial_capital=DEFAULT_CAPITAL)
    trades = replay["trades"]
    print("\n=== TRADING LABS replay_book (single-name Mode B) ===")
    print("trade_count", len(trades))
    for tr in trades:
        print(
            tr.entry_date,
            "->",
            tr.exit_date,
            "entry",
            round(tr.entry_price, 2),
            "exit",
            None if tr.exit_price is None else round(tr.exit_price, 2),
            "pnl%",
            None if tr.pnl_pct is None else round(tr.pnl_pct * 100, 2),
            tr.reason,
        )
    curve = replay["equity_curve"]
    if curve:
        print("equity_first", curve[0]["date"], round(curve[0]["equity"], 2))
        print("equity_last", curve[-1]["date"], round(curve[-1]["equity"], 2))

    stats = count_days(days, highs, closes, volumes, index, lows)
    print("\n=== DAY COUNTS in", START, "->", END, "===")
    for k, v in stats.items():
        print(f"{k}: {v}")

    scenarios = [
        ("labs_filters_atr_close", True, True, "atr_close", 3.0, "sma"),
        ("no_vol_no_mkt_atr_close", False, False, "atr_close", 3.0, "sma"),
        ("no_vol_no_mkt_atr_intrabar", False, False, "atr_intrabar", 3.0, "sma"),
        ("no_vol_no_mkt_wilder_intrabar", False, False, "atr_intrabar", 3.0, "wilder"),
        ("no_vol_no_mkt_atr1_intrabar", False, False, "atr_intrabar", 1.0, "sma"),
        ("no_vol_no_mkt_leave_breakout", False, False, "leave_breakout", 3.0, "sma"),
        ("labs_filters_leave_breakout", True, True, "leave_breakout", 3.0, "sma"),
        ("no_vol_no_mkt_next_bar", False, False, "next_bar", 3.0, "sma"),
        ("labs_filters_next_bar", True, True, "next_bar", 3.0, "sma"),
        ("no_vol_no_mkt_pct_1_28", False, False, "pct_1_28", 3.0, "sma"),
    ]
    print("\n=== COUNTERFACTUAL TRADE COUNTS ===")
    for name, uv, um, em, am, ak in scenarios:
        tlist = simulate_state_hold(days, highs, closes, volumes, index, use_volume=uv, use_market=um, exit_mode=em, atr_mult=am, atr_kind=ak)
        wins = sum(1 for t in tlist if t[4] > 0)
        print(f"{name}: trades={len(tlist)} winners={wins} first={tlist[0][:2] if tlist else None}")

    # Daily diagnostic CSV for the test window
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "prior_252_high",
                "breakout_close_ge",
                "vol_sma20",
                "volume_ok",
                "atr14_sma",
                "atr14_wilder",
                "nifty_close",
                "market_ok",
                "labs_buy_signal",
            ]
        )
        n = len(days)
        for t in range(n):
            if days[t] < START or days[t] > END:
                continue
            ph = prior_high_252(highs, t)
            vs = vol_sma20(volumes, t)
            mok = market_ok(index, t)
            atr_s = atr14(highs, lows, closes, t)
            atr_w = wilder_atr14(highs, lows, closes, t)
            ge = ph is not None and closes[t] >= ph
            vok = vs is not None and volumes[t] > vs
            buy = ge and vok and mok is True
            w.writerow(
                [
                    days[t].isoformat(),
                    opens[t],
                    highs[t],
                    lows[t],
                    closes[t],
                    volumes[t],
                    ph,
                    int(ge),
                    vs,
                    int(bool(vok)),
                    atr_s,
                    atr_w,
                    index[t],
                    mok,
                    int(buy),
                ]
            )
    print("\nWrote", OUT)


if __name__ == "__main__":
    asyncio.run(main())
