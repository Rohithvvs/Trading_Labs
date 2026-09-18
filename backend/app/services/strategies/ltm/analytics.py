"""Windowed backtest dashboard from the existing LTM blotter and equity curve.

Does not change selection, gates, or fills. Reuses calculate_cagr from the
production backtest service.
"""

from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any

from ...backtest_service import calculate_cagr
from .attribution import window_start
from .book_engine import Trade

WINDOW_YEARS = {"1Y": 1, "3Y": 3, "5Y": 5, "ALL": 100}


def parse_window(raw: str | None) -> str:
    key = (raw or "3Y").upper()
    return key if key in WINDOW_YEARS else "3Y"


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, type):
        return value
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def trade_from_dict(raw: dict[str, Any]) -> Trade:
    entry = _as_date(raw.get("entry_date")) or date.min
    exit_d = _as_date(raw.get("exit_date"))
    return Trade(
        symbol=str(raw.get("symbol") or ""),
        entry_date=entry,
        exit_date=exit_d,
        entry_price=float(raw.get("entry_price") or 0),
        exit_price=float(raw["exit_price"]) if raw.get("exit_price") is not None else None,
        shares=float(raw.get("shares") or 0),
        pnl_pct=float(raw["pnl_pct"]) if raw.get("pnl_pct") is not None else None,
        reason=str(raw.get("reason") or ""),
        open=bool(raw.get("open")),
    )


def _filter_trades(trades: list[Trade], start: date, end: date, symbol: str | None) -> list[Trade]:
    out: list[Trade] = []
    for tr in trades:
        if symbol and tr.symbol.upper() != symbol.upper():
            continue
        exit_d = tr.exit_date or end
        if tr.entry_date <= end and exit_d >= start:
            out.append(tr)
    return out


def _filter_curve(curve: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pt in curve:
        d = _as_date(pt.get("date") or pt.get("label"))
        if d is None or d < start or d > end:
            continue
        eq = pt.get("equity")
        if eq is None:
            continue
        rows.append({"date": d.isoformat(), "label": d.isoformat(), "equity": float(eq), "cash": pt.get("cash")})
    return rows


def _monthly_from_equity(curve: list[dict[str, Any]], initial: float) -> list[dict[str, Any]]:
    month_to_equities: dict[str, list[float]] = {}
    for pt in curve:
        key = str(pt["date"])[:7]
        month_to_equities.setdefault(key, []).append(float(pt["equity"]))
    monthly: list[dict[str, Any]] = []
    prev = initial
    for month in sorted(month_to_equities):
        end_eq = month_to_equities[month][-1]
        ret = (end_eq / prev - 1.0) if prev > 0 else None
        monthly.append({"month": month, "return": None if ret is None else round(ret, 6)})
        prev = end_eq
    return monthly


def _drawdown_series(curve: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float | None]:
    peak = None
    max_dd = None
    series: list[dict[str, Any]] = []
    for pt in curve:
        eq = float(pt["equity"])
        peak = eq if peak is None else max(peak, eq)
        dd = (eq / peak - 1.0) if peak else 0.0
        max_dd = dd if max_dd is None else min(max_dd, dd)
        series.append({"date": pt["date"], "label": pt["date"], "drawdown": round(dd * 100, 4)})
    return series, max_dd


def _max_consec_losses(pnls: list[float]) -> int:
    best = cur = 0
    for p in pnls:
        if p < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _trade_payload(tr: Trade) -> dict[str, Any]:
    hold = None
    if tr.exit_date:
        hold = (tr.exit_date - tr.entry_date).days
    pnl_pct = tr.pnl_pct
    return {
        "entry_date": tr.entry_date.isoformat(),
        "exit_date": tr.exit_date.isoformat() if tr.exit_date else None,
        "type": "LONG",
        "entry_price": tr.entry_price,
        "exit_price": tr.exit_price,
        "pnl_percent": None if pnl_pct is None else round(pnl_pct * 100, 4),
        "holding_days": hold,
        "reason": tr.reason,
        "open": tr.open,
        "symbol": tr.symbol,
    }


def build_symbol_dashboard(
    *,
    symbol: str,
    blotter: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    index_curve: list[dict[str, Any]] | None,
    asof: date,
    window: str = "3Y",
    initial_capital: float = 100_000.0,
) -> dict[str, Any]:
    key = parse_window(window)
    years = WINDOW_YEARS[key]
    start = window_start(asof, years=years) if key != "ALL" else date(1970, 1, 1)
    trades_all = [trade_from_dict(r) for r in blotter]
    trades = _filter_trades(trades_all, start, asof, symbol)
    curve = _filter_curve(equity_curve, start, asof)
    if curve:
        initial = float(curve[0]["equity"])
        ending = float(curve[-1]["equity"])
    else:
        initial = float(initial_capital)
        ending = initial
    days = 1
    if curve:
        d0 = _as_date(curve[0]["date"])
        d1 = _as_date(curve[-1]["date"])
        if d0 and d1:
            days = max((d1 - d0).days, 1)

    pnls = [t.pnl_pct for t in trades if t.pnl_pct is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    trade_count = len(trades)
    win_rate = (len(wins) / trade_count * 100.0) if trade_count else None
    profit_factor = None
    if losses and wins:
        profit_factor = abs(sum(wins) / sum(losses)) if sum(losses) else None
    elif wins and not losses:
        profit_factor = None  # infinite — surface as null + flag
    pf_infinite = bool(wins) and not losses and trade_count > 0

    name_net = 1.0
    for p in pnls:
        name_net *= 1.0 + p
    name_return = (name_net - 1.0) * 100.0 if pnls else None
    book_return = ((ending / initial) - 1.0) * 100.0 if initial else None
    cagr = calculate_cagr(initial, ending, days)
    dd_series, max_dd = _drawdown_series(curve)
    sharpe = None
    if trade_count > 1:
        try:
            mean_ret = statistics.mean([p * 100 for p in pnls])
            stdev = statistics.stdev([p * 100 for p in pnls])
            if stdev > 0:
                sharpe = round((mean_ret / stdev) * math.sqrt(trade_count), 3)
        except statistics.StatisticsError:
            sharpe = None

    payloads = [_trade_payload(t) for t in trades]
    payloads.sort(key=lambda t: t["entry_date"] or "", reverse=True)
    best = max(payloads, key=lambda t: t["pnl_percent"] if t["pnl_percent"] is not None else -1e18, default=None)
    worst = min(payloads, key=lambda t: t["pnl_percent"] if t["pnl_percent"] is not None else 1e18, default=None)
    winners = [t for t in payloads if t["pnl_percent"] is not None and t["pnl_percent"] > 0]
    losers = [t for t in payloads if t["pnl_percent"] is not None and t["pnl_percent"] < 0]
    winners.sort(key=lambda t: t["pnl_percent"], reverse=True)
    losers.sort(key=lambda t: t["pnl_percent"])

    bench = []
    for pt in index_curve or []:
        d = _as_date(pt.get("date") or pt.get("label"))
        if d is None or d < start or d > asof:
            continue
        close = pt.get("close") or pt.get("value") or pt.get("equity")
        if close is None:
            continue
        bench.append({"date": d.isoformat(), "label": d.isoformat(), "close": float(close)})

    period_start = curve[0]["date"] if curve else start.isoformat()
    period_end = curve[-1]["date"] if curve else asof.isoformat()
    verdict = None
    if trade_count:
        tr = name_return if name_return is not None else 0
        wr = win_rate or 0
        pf = profit_factor or (2 if pf_infinite else 0)
        verdict = "favorable" if tr > 0 and wr >= 45 and pf >= 1 else "mixed"

    return {
        "window": key,
        "period_start": period_start,
        "period_end": period_end,
        "total_return": None if book_return is None else round(book_return, 4),
        "symbol_return": None if name_return is None else round(name_return, 4),
        "cagr": None if cagr is None else round(cagr, 4),
        "max_drawdown": None if max_dd is None else round(max_dd * 100, 4),
        "win_rate": None if win_rate is None else round(win_rate, 4),
        "trade_count": trade_count,
        "sharpe_ratio": sharpe,
        "profit_factor": None if profit_factor is None else round(profit_factor, 4),
        "profit_factor_infinite": pf_infinite,
        "initial_capital": round(initial, 2),
        "ending_capital": round(ending, 2),
        "avg_trade_return": None if not pnls else round((sum(pnls) / len(pnls)) * 100, 4),
        "max_consecutive_losses": _max_consec_losses(pnls),
        "verdict": verdict,
        "equity_curve": curve,
        "drawdown_curve": dd_series,
        "benchmark_curve": bench,
        "monthly_returns": _monthly_from_equity(curve, initial),
        "trades": payloads,
        "best_trade": best,
        "worst_trade": worst,
        "top_winning": winners[:5],
        "top_losing": losers[:5],
        "never_selected_in_window": trade_count == 0,
    }
