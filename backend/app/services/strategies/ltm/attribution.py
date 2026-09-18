"""Per-name book-trade returns and Top 5 / Least 5 boards.

Default attribution window is 3 completed years. Strategy rules are unchanged.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .book_engine import Trade
from .identity import ATTRIBUTION_YEARS, STRATEGY_ID
from ....utils.symbol import canonical_symbol


def window_start(end: date, *, years: int = ATTRIBUTION_YEARS) -> date:
    try:
        return end.replace(year=end.year - years)
    except ValueError:
        return end - timedelta(days=365 * years)


def _overlaps_window(tr: Trade, start: date, end: date) -> bool:
    entry = tr.entry_date
    exit_d = tr.exit_date or end
    return entry <= end and exit_d >= start


def per_name_backtests(
    trades: list[Trade],
    *,
    asof: date,
    years: int = ATTRIBUTION_YEARS,
    history_valid: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    start = window_start(asof, years=years)
    by_sym: dict[str, list[Trade]] = {}
    for tr in trades:
        if history_valid is not None and tr.symbol not in history_valid:
            continue
        if not _overlaps_window(tr, start, asof):
            continue
        by_sym.setdefault(tr.symbol, []).append(tr)

    reports: dict[str, dict[str, Any]] = {}
    for sym, items in by_sym.items():
        closed = [t for t in items if not t.open]
        marked = [t for t in items if t.open]
        all_t = closed + marked
        rets = [t.pnl_pct for t in all_t if t.pnl_pct is not None]
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r <= 0]
        net = 1.0
        for r in rets:
            net *= 1.0 + r
        net_return = net - 1.0
        win_rate = (len(wins) / len(rets)) if rets else 0.0
        profit_factor = None
        if losses:
            profit_factor = (sum(wins) / abs(sum(losses))) if wins else 0.0
        elif wins:
            profit_factor = float("inf")
        best = max(all_t, key=lambda t: t.pnl_pct or -999, default=None)
        worst = min(all_t, key=lambda t: t.pnl_pct or 999, default=None)
        reports[sym] = {
            "window_start": start.isoformat(),
            "window_end": asof.isoformat(),
            "trade_count": len(all_t),
            "net_return": net_return,
            "win_rate": win_rate,
            "max_drawdown": min((r for r in rets if r < 0), default=0.0),
            "profit_factor": profit_factor,
            "never_selected_in_window": False,
            "trades": all_t,
            "best_trade": best,
            "worst_trade": worst,
        }
    return reports


def empty_backtest(asof: date, *, years: int = ATTRIBUTION_YEARS) -> dict[str, Any]:
    return {
        "window_start": window_start(asof, years=years).isoformat(),
        "window_end": asof.isoformat(),
        "trade_count": 0,
        "net_return": None,
        "win_rate": None,
        "max_drawdown": None,
        "profit_factor": None,
        "never_selected_in_window": True,
        "trades": [],
        "best_trade": None,
        "worst_trade": None,
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
        if not rep.get("never_selected_in_window") and rep.get("trade_count", 0) > 0
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


def trade_from_payload(raw: Trade | dict[str, Any]) -> Trade:
    if isinstance(raw, Trade):
        return raw
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
) -> dict[str, Any]:
    """Average of valid per-name net returns. Missing / failed names are not treated as 0."""
    valid: list[float] = []
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
    universe = len(recs)
    valid_n = len(valid)
    return {
        "strategy_id": strategy_id,
        "window": f"{years}Y",
        "window_start": window_start(asof, years=years).isoformat(),
        "window_end": asof.isoformat(),
        "universe_size": universe,
        "valid_backtests": valid_n,
        "unavailable": max(universe - valid_n, 0),
        "average_return": (sum(valid) / valid_n) if valid_n else None,
    }


def apply_windowed_attribution(
    payload: dict[str, Any],
    *,
    years: int = ATTRIBUTION_YEARS,
) -> dict[str, Any]:
    """Recompute Top 5 / Least 5 / per-name windows from the persisted blotter."""
    asof = _as_date(payload.get("evaluation_date"))
    recs = [dict(r) for r in (payload.get("recommendations") or [])]
    if asof is None or not recs:
        return payload

    out = dict(payload)
    out["recommendations"] = recs
    history_valid = {
        str(r.get("symbol") or "")
        for r in recs
        if r.get("backtest_1y") is not None or r.get("first_failure") != "insufficient_history"
    }
    trades = [trade_from_payload(t) for t in (payload.get("blotter") or []) if t]
    reports = per_name_backtests(trades, asof=asof, years=years, history_valid=history_valid)
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
        if (prior or {}).get("failed") or row.get("first_failure") == "data_source_failure":
            bt = empty_backtest(asof, years=years)
            bt["failed"] = True
            bt["never_selected_in_window"] = False
            bt["net_return"] = None
        else:
            bt = reports.get(sym) or empty_backtest(asof, years=years)
        row["backtest_1y"] = serialize_backtest(bt)

    start = window_start(asof, years=years)
    out["top5_positive"] = top5
    out["least5"] = least5
    out["attribution_window"] = f"{years}Y"
    out["attribution_window_start"] = start.isoformat()
    out["attribution_window_end"] = asof.isoformat()
    out["universe_average"] = universe_average(
        recs,
        asof=asof,
        years=years,
        strategy_id=str(payload.get("strategy_id") or STRATEGY_ID),
    )
    coverage = out.get("data_coverage") if isinstance(out.get("data_coverage"), dict) else {}
    curve = payload.get("equity_curve") or []
    dates = [_as_date(p.get("date")) for p in curve if isinstance(p, dict)]
    dates = [d for d in dates if d is not None]
    ohlcv_start = min(dates).isoformat() if dates else coverage.get("ohlcv_start")
    ohlcv_end = max(dates).isoformat() if dates else coverage.get("ohlcv_end") or asof.isoformat()
    out["data_coverage"] = {
        "requested_start": start.isoformat(),
        "requested_end": asof.isoformat(),
        "ohlcv_start": ohlcv_start,
        "ohlcv_end": ohlcv_end,
        "sessions": len({d.isoformat() for d in dates}) if dates else coverage.get("sessions"),
        "complete_3y": bool(ohlcv_start and ohlcv_start <= start.isoformat()),
    }
    return out
