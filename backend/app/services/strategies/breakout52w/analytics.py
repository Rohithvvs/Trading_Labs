"""Windowed backtest dashboard from the 52W blotter and equity curve.

Does not change selection, gates, or fills. Reuses calculate_cagr from the
production backtest service. Default window is 3Y.
"""

from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any

from ...backtest_service import calculate_cagr
from .attribution import trade_from_payload, window_start
from .book_engine import Trade
from .execution import ExecutionConfig, KERNEL_EXECUTION
from .identity import ATTRIBUTION_PERIODS, ATTRIBUTION_WINDOW, STRATEGY_ID
from .ledger import aggregate_closed_trades, ledger_payload
from .period import expected_sessions_for_period, resolve_period_bounds, trade_in_requested_period

WINDOW_YEARS = {"1Y": 1, "3Y": 3, "5Y": 5, "8Y": 8, "ALL": 100}


def parse_window(raw: str | None) -> str:
    key = (raw or ATTRIBUTION_WINDOW).upper()
    if key in WINDOW_YEARS or key in ATTRIBUTION_PERIODS or key == "CUSTOM":
        return key
    return ATTRIBUTION_WINDOW


def resolve_window_bounds(
    asof: date,
    window: str | None,
    *,
    start: date | None = None,
    end: date | None = None,
) -> tuple[str, date, date]:
    if start is not None and end is not None:
        if start > end:
            start, end = end, start
        raw = (window or "CUSTOM").upper()
        key = raw if raw in WINDOW_YEARS or raw in ATTRIBUTION_PERIODS or raw == "CUSTOM" else "CUSTOM"
        return key, start, end
    key = parse_window(window)
    if key == "ALL":
        return key, date(1970, 1, 1), asof
    if key in ATTRIBUTION_PERIODS:
        return resolve_period_bounds(asof, key)
    years = WINDOW_YEARS.get(key)
    if years is None:
        return resolve_period_bounds(asof, ATTRIBUTION_WINDOW)
    resolved_start = window_start(asof, years=years)
    return key, resolved_start, asof


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
    return trade_from_payload(raw)


def _filter_trades(trades: list[Trade], start: date, end: date, symbol: str | None) -> list[Trade]:
    out: list[Trade] = []
    for tr in trades:
        if symbol and tr.symbol.upper() != symbol.upper():
            continue
        if trade_in_requested_period(tr, start, end):
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


def expected_trading_sessions(
    window: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> int | None:
    key = (window or "").upper()
    if key == "ALL":
        return None
    expected = expected_sessions_for_period(key, start=start, end=end)
    if expected is not None:
        return expected
    if key == "CUSTOM" and start and end:
        days = max((end - start).days, 1)
        return max(2, int(round(days * 252 / 365.25)))
    if key in WINDOW_YEARS:
        return WINDOW_YEARS[key] * 252
    if start and end:
        days = max((end - start).days, 1)
        return max(2, int(round(days * 252 / 365.25)))
    parsed = parse_window(window)
    if parsed in WINDOW_YEARS:
        return WINDOW_YEARS[parsed] * 252
    return expected_sessions_for_period(parsed, start=start, end=end)


def assess_window_coverage(
    session_dates: list[date],
    *,
    start: date,
    end: date,
    window: str,
    min_ratio: float = 0.5,
) -> dict[str, Any]:
    """Compare requested window to the bars actually present."""
    in_window = sorted({d for d in session_dates if start <= d <= end})
    expected = expected_trading_sessions(window, start=start, end=end)
    actual = len(in_window)
    ratio = (actual / expected) if expected else (1.0 if actual >= 2 else 0.0)
    first = in_window[0] if in_window else None
    last = in_window[-1] if in_window else None
    min_bars = 1 if expected is not None and expected <= 1 else 2
    sufficient = actual >= min_bars and (expected is None or ratio >= float(min_ratio))
    return {
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "actual_start": first.isoformat() if first else None,
        "actual_end": last.isoformat() if last else None,
        "candle_count": actual,
        "expected_sessions": expected,
        "coverage_ratio": None if expected is None else round(ratio, 4),
        "sufficient": sufficient,
    }


def _calendar_dates(index_curve: list[dict[str, Any]] | None, start: date, end: date) -> list[date]:
    dates: list[date] = []
    for pt in index_curve or []:
        d = _as_date(pt.get("date") or pt.get("label"))
        if d is not None and start <= d <= end:
            dates.append(d)
    return sorted(set(dates))


def _equity_from_trades(
    trades: list[Trade],
    *,
    start: date,
    end: date,
    initial: float,
    calendar: list[date] | None = None,
) -> list[dict[str, Any]]:
    """Step equity for one name from its attributed book trades.

    The scan-level equity series is the 10-slot book. Reusing it on every
    stock-detail Backtest tab makes every BUY name look identical.
    """
    events: list[tuple[date, float]] = []
    for tr in trades:
        if tr.pnl_pct is None:
            continue
        events.append((tr.exit_date or end, float(tr.pnl_pct)))
    events.sort(key=lambda item: item[0])
    dates = [d for d in (calendar or []) if start <= d <= end]
    if not dates:
        dates = sorted({start, end, *(d for d, _ in events)})
        dates = [d for d in dates if start <= d <= end]
    if not dates:
        return []
    equity = float(initial)
    i = 0
    curve: list[dict[str, Any]] = []
    for d in dates:
        while i < len(events) and events[i][0] <= d:
            equity *= 1.0 + events[i][1]
            i += 1
        curve.append({"date": d.isoformat(), "label": d.isoformat(), "equity": round(equity, 4)})
    return curve


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


def _drawdown_series(curve: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float | None, float | None]:
    peak = None
    max_dd = None
    max_dd_inr = None
    series: list[dict[str, Any]] = []
    for pt in curve:
        eq = float(pt["equity"])
        peak = eq if peak is None else max(peak, eq)
        dd = (eq / peak - 1.0) if peak else 0.0
        dd_inr = eq - peak
        max_dd = dd if max_dd is None else min(max_dd, dd)
        max_dd_inr = dd_inr if max_dd_inr is None else min(max_dd_inr, dd_inr)
        series.append({"date": pt["date"], "label": pt["date"], "drawdown": round(dd * 100, 4)})
    return series, max_dd, max_dd_inr


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
    hold = tr.holding_period
    if hold is None and tr.exit_date:
        hold = (tr.exit_date - tr.entry_date).days
    pnl_pct = tr.pnl_pct
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)[:10]
    return {
        "trade_id": tr.trade_id,
        "symbol": tr.symbol,
        "strategy_id": tr.strategy_id,
        "direction": tr.direction or "LONG",
        "entry_date": tr.entry_date.isoformat(),
        "exit_date": tr.exit_date.isoformat() if tr.exit_date else None,
        "type": tr.direction or "LONG",
        "entry_price": tr.entry_price,
        "exit_price": tr.exit_price,
        "quantity": tr.quantity if tr.quantity is not None else tr.shares,
        "shares": tr.shares,
        "pnl_percent": None if pnl_pct is None else round(pnl_pct * 100, 4),
        "holding_days": hold,
        "reason": tr.reason,
        "exit_reason": tr.exit_reason_canonical or tr.reason,
        "open": tr.open,
        "signal_time": _iso(tr.signal_time),
        "entry_order_time": _iso(tr.entry_order_time),
        "entry_fill_time": _iso(tr.entry_fill_time),
        "exit_order_time": _iso(tr.exit_order_time),
        "exit_fill_time": _iso(tr.exit_fill_time),
        "signal_price": tr.signal_price,
        "order_price": tr.order_price,
        "fill_price": tr.fill_price,
        "fill_reason": tr.fill_reason or tr.reason,
        "gross_pnl": tr.gross_pnl,
        "commission": tr.commission,
        "slippage": tr.slippage,
        "net_pnl": tr.net_pnl,
        "return_pct": None if tr.return_pct is None else round(tr.return_pct * 100, 4),
        "outcome": tr.outcome,
        "pnl_pct": pnl_pct,
    }


def build_symbol_dashboard(
    payload: dict[str, Any] | None = None,
    symbol: str = "",
    window: str = ATTRIBUTION_WINDOW,
    *,
    blotter: list[dict[str, Any]] | None = None,
    equity_curve: list[dict[str, Any]] | None = None,
    index_curve: list[dict[str, Any]] | None = None,
    asof: date | None = None,
    initial_capital: float = 100_000.0,
    symbol_replay: bool = False,
    coverage: dict[str, Any] | None = None,
    unavailable_reason: str | None = None,
    window_start: date | None = None,
    window_end: date | None = None,
    execution_config: ExecutionConfig | None = None,
) -> dict[str, Any]:
    """Stock-detail dashboard for the selected window.

    Accepts either the persisted scan payload (scanner route) or explicit
    blotter/curve arguments (tests / LTM-compatible call).

    ``symbol_replay=True`` means ``equity_curve`` is this name's own replay
    (daily marks), not the 10-slot scan book.
    """
    src = payload or {}
    symbol = (symbol or src.get("symbol") or "").upper()
    asof = asof or _as_date(src.get("evaluation_date")) or date.today()
    key, start, end = resolve_window_bounds(
        asof,
        window,
        start=window_start,
        end=window_end,
    )
    blotter = blotter if blotter is not None else list(src.get("blotter") or [])
    equity_curve = equity_curve if equity_curve is not None else list(src.get("equity_curve") or [])
    if index_curve is None:
        index_curve = list(src.get("index_curve") or [])
    metrics = src.get("book_metrics") if isinstance(src.get("book_metrics"), dict) else {}
    initial_capital = float(src.get("initial_capital") or metrics.get("initial_capital") or initial_capital)

    recs = src.get("recommendations") or []
    match = next((r for r in recs if str(r.get("symbol", "")).upper() == symbol), None)
    trades_all = [trade_from_payload(r) for r in blotter]
    trades = _filter_trades(trades_all, start, end, symbol)
    trades.sort(key=lambda t: (t.exit_date or end, t.entry_date, t.symbol))
    initial = float(initial_capital)
    calendar = _calendar_dates(index_curve, start, end) or _calendar_dates(equity_curve, start, end)
    if symbol_replay:
        curve = _filter_curve(equity_curve, start, end)
        if not curve and calendar:
            curve = _equity_from_trades(trades, start=start, end=end, initial=initial, calendar=calendar)
        if curve:
            initial = float(curve[0]["equity"])
    else:
        curve = _equity_from_trades(trades, start=start, end=end, initial=initial, calendar=calendar) if trades else []
    if curve:
        ending = float(curve[-1]["equity"])
    else:
        ending = initial
    days = max((end - start).days, 1)

    closed = [t for t in trades if not t.open]
    execution_cfg = execution_config or src.get("execution_config")
    if not isinstance(execution_cfg, ExecutionConfig):
        execution_cfg = KERNEL_EXECUTION
    ledger = aggregate_closed_trades(closed, cfg=execution_cfg, initial_capital=initial)
    ledger_ui = ledger_payload(ledger)
    pnls = [t.pnl_pct for t in closed if t.pnl_pct is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    trade_count = int(ledger.get("total_trades") or len(closed))
    win_rate = None if ledger.get("win_rate") is None else float(ledger["win_rate"]) * 100.0
    profit_factor = None
    if losses and wins:
        profit_factor = abs(sum(wins) / sum(losses)) if sum(losses) else None
    elif wins and not losses:
        profit_factor = None
    pf_infinite = bool(wins) and not losses and trade_count > 0

    name_net = 1.0
    for p in pnls:
        name_net *= 1.0 + p
    name_return = (name_net - 1.0) * 100.0 if pnls else None
    if symbol_replay and curve and initial:
        name_return = (ending / initial - 1.0) * 100.0
    cagr = calculate_cagr(initial, ending, days) if (trade_count or (symbol_replay and curve)) else None
    dd_series, max_dd, max_dd_inr = _drawdown_series(curve)
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
    closed_payloads = [p for p in payloads if not p.get("open")]
    best = max(closed_payloads, key=lambda t: t["pnl_percent"] if t["pnl_percent"] is not None else -1e18, default=None)
    worst = min(closed_payloads, key=lambda t: t["pnl_percent"] if t["pnl_percent"] is not None else 1e18, default=None)
    winners = [t for t in closed_payloads if t.get("outcome") == "winner" or (not t.get("outcome") and t["pnl_percent"] is not None and t["pnl_percent"] > 0)]
    losers = [t for t in closed_payloads if t.get("outcome") == "loser" or (not t.get("outcome") and t["pnl_percent"] is not None and t["pnl_percent"] < 0)]
    winners.sort(key=lambda t: t["pnl_percent"], reverse=True)
    losers.sort(key=lambda t: t["pnl_percent"])

    bench = []
    for pt in index_curve or []:
        d = _as_date(pt.get("date") or pt.get("label"))
        if d is None or d < start or d > end:
            continue
        close = pt.get("close") or pt.get("value") or pt.get("equity")
        if close is None:
            continue
        bench.append({"date": d.isoformat(), "label": d.isoformat(), "close": float(close)})

    period_start = curve[0]["date"] if curve else start.isoformat()
    period_end = curve[-1]["date"] if curve else end.isoformat()
    verdict = None
    if trade_count:
        tr = name_return if name_return is not None else 0
        wr = win_rate or 0
        pf = profit_factor or (2 if pf_infinite else 0)
        verdict = "favorable" if tr > 0 and wr >= 45 and pf >= 1 else "mixed"

    failed = bool(((match or {}).get("backtest_1y") or {}).get("failed"))
    if unavailable_reason is None:
        if failed:
            unavailable_reason = "backtest_failed"
        elif coverage and coverage.get("sufficient") is False:
            unavailable_reason = "insufficient_history"
        elif trade_count == 0 and not symbol_replay:
            unavailable_reason = "never_selected_in_window"

    name_ret_pct = None if name_return is None else round(name_return, 4)
    if unavailable_reason == "insufficient_history":
        name_ret_pct = None
        cagr = None
        max_dd = None
        max_dd_inr = None
        win_rate = None
        trade_count = 0
        payloads = []
        best = None
        worst = None
        winners = []
        losers = []
        curve = []
        dd_series = []
        ending = None
        ledger = aggregate_closed_trades([], cfg=execution_cfg, initial_capital=initial)
        ledger_ui = ledger_payload(ledger)
    return {
        "strategy_id": src.get("strategy_id") or STRATEGY_ID,
        "symbol": symbol,
        "window": key,
        "period_start": period_start,
        "period_end": period_end,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "signal": (match or {}).get("signal"),
        "technicals": (match or {}).get("technicals"),
        "total_return": name_ret_pct,
        "symbol_return": name_ret_pct,
        "cagr": None if cagr is None else round(cagr, 4),
        "max_drawdown": None if max_dd is None else round(max_dd * 100, 4),
        "max_drawdown_inr": None if max_dd_inr is None else round(max_dd_inr, 2),
        "win_rate": None if win_rate is None else round(win_rate, 4),
        "trade_count": trade_count,
        "sharpe_ratio": sharpe,
        "profit_factor": None if profit_factor is None else round(profit_factor, 4),
        "profit_factor_infinite": pf_infinite,
        "initial_capital": round(initial, 2),
        "ending_capital": round(ending, 2) if trade_count else None,
        "avg_trade_return": None if not pnls else round((sum(pnls) / len(pnls)) * 100, 4),
        "max_consecutive_losses": _max_consec_losses(pnls),
        "verdict": verdict,
        "equity_curve": curve,
        "drawdown_curve": dd_series,
        "benchmark_curve": bench,
        "index_curve": bench,
        "monthly_returns": _monthly_from_equity(curve, initial) if curve else [],
        "trades": payloads,
        "best_trade": best,
        "worst_trade": worst,
        "top_winning": winners[:5],
        "top_losing": losers[:5],
        "never_selected_in_window": trade_count == 0 and unavailable_reason != "insufficient_history",
        "backtest_failed": failed,
        "unavailable_reason": unavailable_reason,
        "coverage": coverage,
        "replay_kind": "symbol_window" if symbol_replay else "scan_blotter",
        "book_metrics": None if symbol_replay else src.get("book_metrics"),
        "ledger": ledger_ui,
        "trade_distribution": {
            "total_trades": ledger_ui.get("total_trades") or 0,
            "winners": ledger_ui.get("winning_trades") or 0,
            "losers": ledger_ui.get("losing_trades") or 0,
            "breakevens": ledger_ui.get("breakeven_trades") or 0,
            "open_trades": sum(1 for t in payloads if t.get("open")),
            "source": "closed_trade_ledger",
        },
        "winning_trades": ledger_ui.get("winning_trades"),
        "losing_trades": ledger_ui.get("losing_trades"),
        "breakeven_trades": ledger_ui.get("breakeven_trades"),
        "expected_payoff": ledger_ui.get("expected_payoff"),
        "expected_payoff_inr": ledger_ui.get("expected_payoff_inr"),
        "average_profit": ledger_ui.get("average_profit"),
        "average_loss": ledger_ui.get("average_loss"),
        "net_pnl": ledger_ui.get("net_pnl"),
        "gross_profit": ledger_ui.get("gross_profit"),
        "gross_loss": ledger_ui.get("gross_loss"),
        "commission": ledger_ui.get("commission"),
        "outlier_pnl": ledger_ui.get("outlier_pnl"),
        "execution": execution_cfg.as_public_dict(),
    }
