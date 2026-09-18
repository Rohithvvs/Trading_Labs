"""Shared 10% × 10 book. Copied from Trading-main run_all_baseline.run_portfolio."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .catalog import ALLOC_PCT, INITIAL_CAPITAL, MAX_POSITIONS
from .costs import TransactionCosts
from .signals_types import MarketData, SignalBook


def run_portfolio(
    md: MarketData,
    book: SignalBook,
    start_date: Optional[pd.Timestamp] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    close = md.close
    dates = close.index
    if start_date is not None:
        dates = dates[dates >= pd.Timestamp(start_date)]
    costs = TransactionCosts()
    cash = INITIAL_CAPITAL
    holdings: Dict[str, dict] = {}
    trades: List[dict] = []
    equity_rows: List[dict] = []

    buy = book.buy
    sell = book.sell
    rank = book.rank
    atr = book.atr
    exit_below = book.exit_below
    initial_stop = book.initial_stop
    trail_stop = book.trail_stop

    def mtm(day: pd.Timestamp) -> float:
        value = cash
        px = close.loc[day]
        for sym, pos in holdings.items():
            price = px.get(sym)
            if price is not None and not pd.isna(price):
                value += pos["shares"] * float(price)
        return value

    def close_position(sym: str, day: pd.Timestamp, price: float, reason: str) -> None:
        nonlocal cash
        pos = holdings.pop(sym)
        turnover = pos["shares"] * price
        fee = costs.sell_cost(turnover)
        cash += turnover - fee
        ret_pct = (price / pos["entry_price"] - 1.0) * 100.0
        trades.append(
            {
                "symbol": sym,
                "entry_date": pos["entry_date"],
                "entry_price": pos["entry_price"],
                "exit_date": day,
                "exit_price": price,
                "return_pct": ret_pct,
                "exit_reason": reason,
                "status": "CLOSED",
                "hold_days": int((day - pos["entry_date"]).days),
            }
        )

    for day in dates:
        px = close.loc[day]

        to_close: List[Tuple[str, float, str]] = []
        for sym, pos in list(holdings.items()):
            if pos["entry_date"] == day:
                continue
            price = px.get(sym)
            if price is None or pd.isna(price):
                continue
            price = float(price)

            if sell is not None and bool(sell.loc[day, sym]):
                to_close.append((sym, price, "signal"))
                continue

            if book.hard_stop_pct is not None and price < pos["entry_price"] * (1.0 - book.hard_stop_pct):
                to_close.append((sym, price, "hard_stop"))
                continue

            if book.trail_atr_mult is not None and atr is not None:
                a = atr.loc[day, sym]
                if not pd.isna(a):
                    if price > pos["hwm"]:
                        pos["hwm"] = price
                        pos["tsl"] = max(pos.get("tsl", -np.inf), price - book.trail_atr_mult * float(a))
                if pos.get("tsl") is not None and price < pos["tsl"]:
                    to_close.append((sym, price, "atr_trail"))
                    continue

            if book.tsl_pct is not None:
                pos["hwm"] = max(pos.get("hwm", price), price)
                if price <= pos["hwm"] * (1.0 - book.tsl_pct):
                    to_close.append((sym, price, "tsl"))
                    continue

            if exit_below is not None:
                lvl = exit_below.loc[day, sym]
                if not pd.isna(lvl) and price < float(lvl):
                    to_close.append((sym, price, "exit_below"))
                    continue

            if book.entry_atr_stop_mult is not None and price < pos.get("atr_stop", -np.inf):
                to_close.append((sym, price, "atr_stop"))
                continue

            if book.take_profit_rr is not None and pos.get("tp", 0) > 0 and price >= pos["tp"]:
                to_close.append((sym, price, "take_profit"))
                continue

            if trail_stop is not None:
                trail = trail_stop.loc[day, sym]
                if not pd.isna(trail) and float(trail) > pos.get("stop", 0):
                    pos["stop"] = float(trail)
            if pos.get("stop") is not None and price < pos["stop"]:
                to_close.append((sym, price, "stop"))
                continue

            if initial_stop is not None and book.take_profit_rr is None and trail_stop is None:
                if price < pos.get("stop", -np.inf):
                    to_close.append((sym, price, "base_low"))
                    continue

        for sym, price, reason in to_close:
            if sym in holdings:
                close_position(sym, day, price, reason)

        equity = mtm(day)
        equity_rows.append(
            {
                "date": day,
                "equity": equity,
                "cash": cash,
                "n_positions": len(holdings),
            }
        )

        free = MAX_POSITIONS - len(holdings)
        if free <= 0:
            continue

        try:
            buys_today = buy.loc[day]
        except KeyError:
            continue
        candidates = [s for s, flag in buys_today.items() if flag and s not in holdings]
        if not book.allow_same_day_rebuy:
            sold_today = {t["symbol"] for t in trades if t["exit_date"] == day}
            candidates = [s for s in candidates if s not in sold_today]
        if not candidates:
            continue

        if rank is not None:
            scores = []
            for s in candidates:
                try:
                    val = rank.loc[day, s]
                except Exception:
                    val = np.nan
                scores.append(val if not pd.isna(val) else -np.inf)
            order = [s for _, s in sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)]
        else:
            order = candidates

        for sym in order[:free]:
            price = px.get(sym)
            if price is None or pd.isna(price) or float(price) <= 0:
                continue
            price = float(price)
            alloc = equity * ALLOC_PCT
            fee_est = costs.buy_cost(alloc)
            investable = min(cash - fee_est, alloc - fee_est)
            if investable <= 0:
                continue
            shares = investable / price
            turnover = shares * price
            fee = costs.buy_cost(turnover)
            if turnover + fee > cash + 1e-6:
                continue
            cash -= turnover + fee
            pos = {
                "shares": shares,
                "entry_date": day,
                "entry_price": price,
                "hwm": price,
            }
            if book.trail_atr_mult is not None and atr is not None:
                a = atr.loc[day, sym]
                pos["tsl"] = price - book.trail_atr_mult * float(a) if not pd.isna(a) else price * 0.9
            if book.entry_atr_stop_mult is not None and atr is not None:
                a = atr.loc[day, sym]
                pos["atr_stop"] = price - book.entry_atr_stop_mult * float(a) if not pd.isna(a) else price * 0.9
            if initial_stop is not None:
                stp = initial_stop.loc[day, sym]
                if not pd.isna(stp):
                    pos["stop"] = float(stp)
                    if book.take_profit_rr is not None:
                        risk = price - float(stp)
                        pos["tp"] = price + book.take_profit_rr * risk if risk > 0 else 0.0
            holdings[sym] = pos
            free -= 1
            if free <= 0:
                break

    last_day = dates[-1]
    for sym in list(holdings.keys()):
        hist = close[sym].loc[:last_day].dropna()
        if hist.empty:
            holdings.pop(sym)
            continue
        close_position(sym, hist.index[-1], float(hist.iloc[-1]), "eod_liquidation")

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_rows).set_index("date")
    return trades_df, equity_df
