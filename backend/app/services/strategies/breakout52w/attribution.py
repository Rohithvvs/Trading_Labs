"""Per-name book-trade returns and Top 5 / Least 5 boards.

Default attribution window is 3 completed years. Strategy rules are unchanged.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .book_engine import Trade
from .identity import ATTRIBUTION_PERIODS, ATTRIBUTION_YEARS, STRATEGY_ID
from ....utils.symbol import canonical_symbol
from .period import (
    SIGNAL_SEMANTICS,
    backtest_cache_key,
    filter_period_trades,
    period_window_start,
    resolve_period_bounds,
    result_identity,
)


def _profit_factor(wins: list[float], losses: list[float]) -> float | None:
    """Gross-profit / gross-loss. Break-even (0) trades are neither wins nor losses.

    Infinite when there is profit and no gross loss. None when there is no
    closed PnL to score (empty or all break-even).
    """
    loss_abs = abs(sum(losses))
    if loss_abs:
        return (sum(wins) / loss_abs) if wins else 0.0
    if wins:
        return float("inf")
    return None


def window_start(end: date, *, years: int = ATTRIBUTION_YEARS) -> date:
    try:
        return end.replace(year=end.year - years)
    except ValueError:
        return end - timedelta(days=365 * years)


def _resolve_attribution_window(
    asof: date,
    *,
    years: int = ATTRIBUTION_YEARS,
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> tuple[str, date, date]:
    if start is not None and end is not None:
        key = (period or "CUSTOM").upper()
        if start > end:
            start, end = end, start
        return key, start, end
    if period:
        return resolve_period_bounds(asof, period, start=start, end=end)
    years_key = f"{int(years)}Y"
    if years_key in ATTRIBUTION_PERIODS:
        return years_key, period_window_start(asof, years_key), asof
    return f"{int(years)}Y", window_start(asof, years=years), asof


def per_name_backtests(
    trades: list[Trade],
    *,
    asof: date,
    years: int = ATTRIBUTION_YEARS,
    history_valid: set[str] | None = None,
    failed: set[str] | None = None,
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, dict[str, Any]]:
    key, start, end = _resolve_attribution_window(
        asof, years=years, period=period, start=start, end=end
    )
    skip_fail = set(failed or ())
    eligible = [
        tr
        for tr in trades
        if (history_valid is None or tr.symbol in history_valid) and tr.symbol not in skip_fail
    ]
    window_trades = filter_period_trades(eligible, start, end)
    by_sym: dict[str, list[Trade]] = {}
    for tr in window_trades:
        by_sym.setdefault(tr.symbol, []).append(tr)

    reports: dict[str, dict[str, Any]] = {}
    for sym, items in by_sym.items():
        rets = [t.pnl_pct for t in items if t.pnl_pct is not None]
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r < 0]
        net = 1.0
        for r in rets:
            net *= 1.0 + r
        net_return = net - 1.0
        win_rate = (len(wins) / len(rets)) if rets else 0.0
        profit_factor = _profit_factor(wins, losses)
        reports[sym] = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "period": key,
            "trade_count": len(items),
            "net_return": net_return,
            "win_rate": win_rate,
            "max_drawdown": min((r for r in rets if r < 0), default=0.0),
            "profit_factor": profit_factor,
            "never_selected_in_window": False,
            "failed": False,
            "trades": items,
        }
    return reports


def empty_backtest(
    asof: date,
    *,
    years: int = ATTRIBUTION_YEARS,
    failed: bool = False,
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    key, start, end = _resolve_attribution_window(
        asof, years=years, period=period, start=start, end=end
    )
    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "period": key,
        "trade_count": 0,
        "net_return": None,
        "win_rate": None,
        "max_drawdown": None,
        "profit_factor": None,
        "never_selected_in_window": not failed,
        "failed": failed,
        "trades": [],
    }


def build_boards(
    reports: dict[str, dict[str, Any]],
    signals: dict[str, str],
    *,
    top_n: int = 5,
    company_names: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    qualified = [
        (sym, rep)
        for sym, rep in reports.items()
        if not rep.get("never_selected_in_window")
        and not rep.get("failed")
        and rep.get("trade_count", 0) > 0
    ]

    def to_row(rank: int, sym: str, rep: dict[str, Any]) -> dict[str, Any]:
        pf = rep.get("profit_factor")
        canon_sym = canonical_symbol(sym)
        comp_name = (company_names.get(canon_sym) or company_names.get(sym)) if company_names else None
        return {
            "rank": rank,
            "symbol": canon_sym,
            "company_name": comp_name,
            "signal": signals.get(sym, signals.get(canon_sym, "REJECT")),
            "return": rep["net_return"],
            "trades": rep["trade_count"],
            "win_rate": rep["win_rate"],
            "max_dd": rep.get("max_drawdown"),
            "profit_factor": pf if pf != float("inf") else None,
            "profit_factor_infinite": pf == float("inf"),
            "window_start": rep.get("window_start"),
            "window_end": rep.get("window_end"),
            "signal_meaning": SIGNAL_SEMANTICS["meaning"],
        }

    positive = [(s, r) for s, r in qualified if (r.get("net_return") or 0) > 0]
    positive.sort(key=lambda item: (-(item[1]["net_return"] or 0), item[0]))
    top5 = [to_row(i + 1, s, r) for i, (s, r) in enumerate(positive[:top_n])]
    all_q = list(qualified)
    all_q.sort(key=lambda item: ((item[1]["net_return"] if item[1]["net_return"] is not None else 0), item[0]))
    least5 = [to_row(i + 1, s, r) for i, (s, r) in enumerate(all_q[:top_n])]
    return top5, least5


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


def _optional_float(raw: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if raw.get(key) is not None:
            try:
                return float(raw[key])
            except (TypeError, ValueError):
                return None
    return None


def trade_from_payload(raw: Trade | dict[str, Any]) -> Trade:
    if isinstance(raw, Trade):
        return raw
    entry = _as_date(raw.get("entry_date")) or date.min
    exit_d = _as_date(raw.get("exit_date"))
    pnl = raw.get("pnl_pct")
    if pnl is None and raw.get("pnl_percent") is not None:
        try:
            pct = float(raw["pnl_percent"])
            pnl = pct / 100.0 if abs(pct) > 2 or pct == 0 else pct
        except (TypeError, ValueError):
            pnl = None
    return Trade(
        symbol=str(raw.get("symbol") or ""),
        entry_date=entry,
        exit_date=exit_d,
        entry_price=float(raw.get("entry_price") or 0),
        exit_price=float(raw["exit_price"]) if raw.get("exit_price") is not None else None,
        shares=float(raw.get("shares") or raw.get("quantity") or 0),
        pnl_pct=float(pnl) if pnl is not None else None,
        reason=str(raw.get("reason") or raw.get("exit_reason") or ""),
        open=bool(raw.get("open")),
        trade_id=raw.get("trade_id"),
        strategy_id=str(raw.get("strategy_id") or STRATEGY_ID),
        direction=str(raw.get("direction") or raw.get("type") or "LONG"),
        signal_time=_as_date(raw.get("signal_time")),
        entry_order_time=_as_date(raw.get("entry_order_time")),
        entry_fill_time=_as_date(raw.get("entry_fill_time") or raw.get("entry_date")),
        exit_order_time=_as_date(raw.get("exit_order_time")),
        exit_fill_time=_as_date(raw.get("exit_fill_time") or raw.get("exit_date")),
        quantity=_optional_float(raw, "quantity", "shares"),
        gross_pnl=_optional_float(raw, "gross_pnl"),
        commission=_optional_float(raw, "commission"),
        slippage=_optional_float(raw, "slippage"),
        net_pnl=_optional_float(raw, "net_pnl"),
        return_pct=_optional_float(raw, "return_pct", "pnl_pct"),
        holding_period=int(raw["holding_days"]) if raw.get("holding_days") is not None else None,
        signal_price=_optional_float(raw, "signal_price"),
        order_price=_optional_float(raw, "order_price"),
        fill_price=_optional_float(raw, "fill_price"),
        fill_reason=raw.get("fill_reason"),
        outcome=raw.get("outcome"),
        exit_reason_canonical=raw.get("exit_reason") or raw.get("exit_reason_canonical"),
    )


def serialize_trade(tr: Trade | dict[str, Any]) -> dict[str, Any]:
    if isinstance(tr, dict):
        return tr
    return {
        "symbol": tr.symbol,
        "entry_date": tr.entry_date.isoformat(),
        "exit_date": tr.exit_date.isoformat() if tr.exit_date else None,
        "entry_price": tr.entry_price,
        "exit_price": tr.exit_price,
        "shares": tr.shares,
        "pnl_pct": tr.pnl_pct,
        "reason": tr.reason,
        "open": tr.open,
        "trade_id": tr.trade_id,
        "gross_pnl": tr.gross_pnl,
        "commission": tr.commission,
        "slippage": tr.slippage,
        "net_pnl": tr.net_pnl,
        "outcome": tr.outcome,
        "exit_reason": tr.exit_reason_canonical or tr.reason,
    }


def serialize_backtest(bt: dict[str, Any]) -> dict[str, Any]:
    pf = bt.get("profit_factor")
    return {
        "window_start": bt["window_start"],
        "window_end": bt["window_end"],
        "trade_count": bt["trade_count"],
        "net_return": bt["net_return"],
        "win_rate": bt["win_rate"],
        "max_drawdown": bt["max_drawdown"],
        "profit_factor": pf if pf != float("inf") else None,
        "profit_factor_infinite": pf == float("inf"),
        "never_selected_in_window": bt["never_selected_in_window"],
        "failed": bt.get("failed", False),
        "trades": [serialize_trade(t) for t in bt.get("trades") or []],
    }


def universe_average(
    recs: list[dict[str, Any]],
    *,
    asof: date,
    years: int = ATTRIBUTION_YEARS,
    strategy_id: str = STRATEGY_ID,
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Average of valid per-name net returns. Missing / failed names are not treated as 0."""
    key, start, end = _resolve_attribution_window(
        asof, years=years, period=period, start=start, end=end
    )
    valid: list[float] = []
    trade_count = 0
    for row in recs:
        bt = row.get("backtest_1y") or {}
        if bt.get("failed"):
            continue
        raw = bt.get("net_return")
        if raw is None:
            continue
        try:
            valid.append(float(raw))
        except (TypeError, ValueError):
            continue
        try:
            trade_count += int(bt.get("trade_count") or 0)
        except (TypeError, ValueError):
            pass
    universe = len(recs)
    valid_n = len(valid)
    return {
        "strategy_id": strategy_id,
        "window": key,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "universe_size": universe,
        "valid_backtests": valid_n,
        "unavailable": max(universe - valid_n, 0),
        "average_return": (sum(valid) / valid_n) if valid_n else None,
        "trade_count": trade_count,
    }


def apply_windowed_attribution(
    payload: dict[str, Any],
    *,
    years: int = ATTRIBUTION_YEARS,
    period: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Recompute Top 5 / Least 5 / per-name windows from the persisted blotter."""
    asof = _as_date(payload.get("evaluation_date"))
    recs = [dict(r) for r in (payload.get("recommendations") or [])]
    if asof is None or not recs:
        return payload

    key, win_start, win_end = _resolve_attribution_window(
        asof, years=years, period=period, start=start, end=end
    )
    out = dict(payload)
    out["recommendations"] = recs
    history_valid = {
        str(r.get("symbol") or "")
        for r in recs
        if r.get("backtest_1y") is not None or r.get("first_failure") != "insufficient_history"
    }
    failed = {
        str(r.get("symbol") or "")
        for r in recs
        if (r.get("backtest_1y") or {}).get("failed") or r.get("first_failure") == "data_source_failure"
    }
    trades = [trade_from_payload(t) for t in (payload.get("blotter") or []) if t]
    reports = per_name_backtests(
        trades,
        asof=asof,
        years=years,
        period=key,
        start=win_start,
        end=win_end,
        history_valid=history_valid,
        failed=failed,
    )
    signals = {str(r.get("symbol") or ""): str(r.get("signal") or "REJECT") for r in recs}
    company_names = {
        canonical_symbol(str(r.get("symbol") or "")): r.get("company_name")
        for r in recs
        if r.get("company_name")
    }
    top5, least5 = build_boards(reports, signals, company_names=company_names)
    for row in recs:
        sym = str(row.get("symbol") or "")
        prior = row.get("backtest_1y")
        if prior is None and row.get("first_failure") == "insufficient_history":
            row["backtest_1y"] = None
            continue
        if prior and prior.get("failed") or sym in failed:
            bt = empty_backtest(asof, years=years, failed=True, period=key, start=win_start, end=win_end)
        else:
            bt = reports.get(sym) or empty_backtest(
                asof, years=years, period=key, start=win_start, end=win_end
            )
        row["backtest_1y"] = serialize_backtest(bt)

    period_trades = filter_period_trades(trades, win_start, win_end)
    identity = result_identity(start=win_start, end=win_end, trades=period_trades)
    cache_key = backtest_cache_key(
        start_date=win_start,
        end_date=win_end,
        universe_id=str(payload.get("scan_id") or payload.get("strategy_id") or STRATEGY_ID),
    )
    out["top5_positive"] = top5
    out["least5"] = least5
    out["attribution_window"] = key
    out["attribution_window_start"] = win_start.isoformat()
    out["attribution_window_end"] = win_end.isoformat()
    out["requested_start"] = win_start.isoformat()
    out["requested_end"] = win_end.isoformat()
    out["period_trade_count"] = len(period_trades)
    out["result_identity"] = identity
    out["cache_key"] = cache_key
    out["signal_semantics"] = SIGNAL_SEMANTICS
    out["universe_average"] = universe_average(
        recs,
        asof=asof,
        years=years,
        period=key,
        start=win_start,
        end=win_end,
        strategy_id=str(payload.get("strategy_id") or STRATEGY_ID),
    )
    coverage = out.get("data_coverage") if isinstance(out.get("data_coverage"), dict) else {}
    curve = payload.get("equity_curve") or []
    dates = [_as_date(p.get("date")) for p in curve if isinstance(p, dict)]
    dates = [d for d in dates if d is not None]
    ohlcv_start = min(dates).isoformat() if dates else coverage.get("ohlcv_start")
    ohlcv_end = max(dates).isoformat() if dates else coverage.get("ohlcv_end") or win_end.isoformat()
    out["data_coverage"] = {
        "requested_start": win_start.isoformat(),
        "requested_end": win_end.isoformat(),
        "ohlcv_start": ohlcv_start,
        "ohlcv_end": ohlcv_end,
        "sessions": len({d.isoformat() for d in dates}) if dates else coverage.get("sessions"),
        "complete_3y": bool(ohlcv_start and ohlcv_start <= win_start.isoformat()),
    }
    out["period_accounting"] = period_accounting(out)
    return out


def period_accounting(payload: dict[str, Any]) -> dict[str, Any]:
    """Explicit success/failure counts for a period-attributed scan payload."""
    recs = payload.get("recommendations") or []
    processed = len(recs)
    insufficient_history = 0
    failed = 0
    no_trades = 0
    with_trades = 0
    winning = 0
    losing = 0
    returns: list[float] = []
    for row in recs:
        bt = row.get("backtest_1y")
        first = row.get("first_failure")
        if first == "insufficient_history" and bt is None:
            insufficient_history += 1
            continue
        if (bt or {}).get("failed") or first == "data_source_failure":
            failed += 1
            continue
        count = int((bt or {}).get("trade_count") or 0)
        if count <= 0:
            no_trades += 1
            continue
        with_trades += 1
        raw = (bt or {}).get("net_return")
        try:
            ret = float(raw)
        except (TypeError, ValueError):
            continue
        returns.append(ret)
        if ret > 0:
            winning += 1
        elif ret < 0:
            losing += 1
    skipped = insufficient_history
    successful = with_trades
    avg = (sum(returns) / len(returns)) if returns else None
    ordered = sorted(returns)
    median = None
    if ordered:
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "processed": processed,
        "successful": successful,
        "failed": failed,
        "skipped": skipped,
        "insufficient_history": insufficient_history,
        "no_trades": no_trades,
        "stocks_with_trades": with_trades,
        "winning_names": winning,
        "losing_names": losing,
        "trade_count": int(payload.get("period_trade_count") or 0),
        "average_return": avg,
        "median_return": median,
    }
