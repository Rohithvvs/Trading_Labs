"""Persist and serve per-symbol 52W Strategy Tester metrics.

Replay the closed-trade book once over stored daily history, then store
TradingView-style tester fields in PostgreSQL so opening a name does not
recompute or assume win/loss counts.

Does not change selection, trail, or fill rules.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import select

from ....db.session import AsyncSessionLocal
from ....models.w52_strategy import W52SymbolPerformance
from ....utils import get_logger
from .analytics import build_symbol_dashboard, parse_window
from .execution import KERNEL_EXECUTION, parse_execution_profile
from .identity import DEFAULT_CAPITAL, HISTORICAL_PERIOD, STRATEGY_ID
from .period import PeriodRequestError

logger = get_logger("app.w52.performance_store")

DEFAULT_WINDOWS: tuple[str, ...] = ("1Y", "3Y", "5Y", "8Y", HISTORICAL_PERIOD, "ALL")
TESTER_FIELDS: tuple[str, ...] = (
    "total_pnl",
    "max_drawdown",
    "total_trades",
    "profitable_trades",
    "losing_trades",
    "breakeven",
    "profit_factor",
    "gross_profit",
    "gross_loss",
    "commission",
    "expected_payoff",
    "largest_profit",
    "largest_loss",
    "average_winning_trade",
    "average_losing_trade",
    "outlier_pnl",
)


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    return n


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _trade_net(trade: dict[str, Any]) -> float | None:
    return _as_float(trade.get("net_pnl"))


def strategy_tester_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    """Exact Strategy Tester fields requested for stock-detail lookup."""
    return {key: metrics.get(key) for key in TESTER_FIELDS}


def metrics_from_dashboard(dash: dict[str, Any]) -> dict[str, Any]:
    """Map a symbol-replay dashboard onto stored tester columns."""
    ledger = dash.get("ledger") if isinstance(dash.get("ledger"), dict) else {}
    dist = dash.get("trade_distribution") if isinstance(dash.get("trade_distribution"), dict) else {}
    coverage = dash.get("coverage") if isinstance(dash.get("coverage"), dict) else {}
    trades = list(dash.get("trades") or [])
    closed = [t for t in trades if isinstance(t, dict) and not t.get("open")]
    winners = [t for t in closed if t.get("outcome") == "winner"]
    losers = [t for t in closed if t.get("outcome") == "loser"]
    win_inr = [p for p in (_trade_net(t) for t in winners) if p is not None]
    loss_inr = [p for p in (_trade_net(t) for t in losers) if p is not None]

    reason = dash.get("unavailable_reason")
    status = "ok"
    if reason == "insufficient_history":
        status = "insufficient_history"
    elif reason == "backtest_failed" or dash.get("backtest_failed"):
        status = "failed"
    elif _as_int(dist.get("total_trades") or dash.get("trade_count")) == 0:
        status = "never_selected"

    total_trades = _as_int(dist.get("total_trades") or ledger.get("total_trades") or dash.get("trade_count"))
    profitable = _as_int(dist.get("winners") or ledger.get("winning_trades") or dash.get("winning_trades"))
    losing = _as_int(dist.get("losers") or ledger.get("losing_trades") or dash.get("losing_trades"))
    breakeven = _as_int(dist.get("breakevens") or ledger.get("breakeven_trades") or dash.get("breakeven_trades"))
    execution = dash.get("execution") if isinstance(dash.get("execution"), dict) else {}

    payload = {
        "strategy_id": dash.get("strategy_id") or STRATEGY_ID,
        "symbol": str(dash.get("symbol") or "").upper(),
        "window": str(dash.get("window") or "ALL").upper(),
        "execution_profile": str(execution.get("profile") or KERNEL_EXECUTION.profile),
        "period_start": _as_date(dash.get("period_start") or dash.get("window_start") or coverage.get("actual_start")),
        "period_end": _as_date(dash.get("period_end") or dash.get("window_end") or coverage.get("actual_end")),
        "evaluation_date": _as_date(dash.get("requested_end") or dash.get("window_end") or dash.get("period_end")),
        "status": status,
        "unavailable_reason": reason,
        "data_hash": dash.get("data_hash"),
        "candle_count": _as_int(coverage.get("candle_count"), default=0) or None,
        "coverage_ratio": _as_float(coverage.get("coverage_ratio")),
        "total_pnl": _as_float(ledger.get("net_pnl") if ledger.get("net_pnl") is not None else dash.get("net_pnl")),
        "max_drawdown": _as_float(dash.get("max_drawdown")),
        "max_drawdown_inr": _as_float(dash.get("max_drawdown_inr")),
        "total_trades": total_trades,
        "profitable_trades": profitable,
        "losing_trades": losing,
        "breakeven": breakeven,
        "profit_factor": _as_float(dash.get("profit_factor") if dash.get("profit_factor") is not None else ledger.get("profit_factor")),
        "profit_factor_infinite": bool(dash.get("profit_factor_infinite") or ledger.get("profit_factor_infinite")),
        "gross_profit": _as_float(ledger.get("gross_profit") if ledger.get("gross_profit") is not None else dash.get("gross_profit")),
        "gross_loss": _as_float(ledger.get("gross_loss") if ledger.get("gross_loss") is not None else dash.get("gross_loss")),
        "commission": _as_float(ledger.get("commission") if ledger.get("commission") is not None else dash.get("commission")),
        "expected_payoff": _as_float(ledger.get("expected_payoff") if ledger.get("expected_payoff") is not None else dash.get("expected_payoff")),
        "expected_payoff_inr": _as_float(ledger.get("expected_payoff_inr") if ledger.get("expected_payoff_inr") is not None else dash.get("expected_payoff_inr")),
        "largest_profit": _as_float(ledger.get("largest_profit") if ledger.get("largest_profit") is not None else dash.get("largest_profit")),
        "largest_loss": _as_float(ledger.get("largest_loss") if ledger.get("largest_loss") is not None else dash.get("largest_loss")),
        "largest_profit_inr": _as_float(ledger.get("largest_profit_inr")),
        "largest_loss_inr": _as_float(ledger.get("largest_loss_inr")),
        "average_winning_trade": _as_float(ledger.get("average_profit") if ledger.get("average_profit") is not None else dash.get("average_profit")),
        "average_losing_trade": _as_float(ledger.get("average_loss") if ledger.get("average_loss") is not None else dash.get("average_loss")),
        "average_winning_trade_inr": _mean(win_inr),
        "average_losing_trade_inr": _mean(loss_inr),
        "outlier_pnl": _as_float(ledger.get("outlier_pnl") if ledger.get("outlier_pnl") is not None else dash.get("outlier_pnl")),
        "outlier_trades": _as_int(ledger.get("outlier_trades")),
        "win_rate": _as_float(dash.get("win_rate") if dash.get("win_rate") is not None else ledger.get("win_rate")),
        "total_return": _as_float(dash.get("total_return")),
        "cagr": _as_float(dash.get("cagr")),
        "initial_capital": _as_float(dash.get("initial_capital")),
        "ending_capital": _as_float(dash.get("ending_capital")),
        "source": "closed_trade_ledger",
        "error_detail": dash.get("error_detail"),
        "trades": trades,
        "ledger": ledger or None,
        "coverage": coverage or None,
        "strategy_tester": None,
    }
    payload["strategy_tester"] = strategy_tester_payload(payload)
    return payload


def apply_stored_metrics(dash: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """Overwrite tester fields with the persisted closed-trade ledger."""
    out = dict(dash)
    ledger = dict(out.get("ledger") or {})
    dist = dict(out.get("trade_distribution") or {})
    out["net_pnl"] = stored.get("total_pnl")
    out["max_drawdown"] = stored.get("max_drawdown")
    out["max_drawdown_inr"] = stored.get("max_drawdown_inr")
    out["trade_count"] = stored.get("total_trades")
    out["winning_trades"] = stored.get("profitable_trades")
    out["losing_trades"] = stored.get("losing_trades")
    out["breakeven_trades"] = stored.get("breakeven")
    out["profit_factor"] = stored.get("profit_factor")
    out["profit_factor_infinite"] = bool(stored.get("profit_factor_infinite"))
    out["gross_profit"] = stored.get("gross_profit")
    out["gross_loss"] = stored.get("gross_loss")
    out["commission"] = stored.get("commission")
    out["expected_payoff"] = stored.get("expected_payoff")
    out["expected_payoff_inr"] = stored.get("expected_payoff_inr")
    out["average_profit"] = stored.get("average_winning_trade")
    out["average_loss"] = stored.get("average_losing_trade")
    out["outlier_pnl"] = stored.get("outlier_pnl")
    out["win_rate"] = stored.get("win_rate")
    out["total_return"] = stored.get("total_return")
    out["cagr"] = stored.get("cagr")
    out["persisted"] = True
    out["strategy_tester"] = strategy_tester_payload(stored)
    ledger.update(
        {
            "total_trades": stored.get("total_trades"),
            "winning_trades": stored.get("profitable_trades"),
            "losing_trades": stored.get("losing_trades"),
            "breakeven_trades": stored.get("breakeven"),
            "win_rate": stored.get("win_rate"),
            "average_profit": stored.get("average_winning_trade"),
            "average_loss": stored.get("average_losing_trade"),
            "expected_payoff": stored.get("expected_payoff"),
            "expected_payoff_inr": stored.get("expected_payoff_inr"),
            "gross_profit": stored.get("gross_profit"),
            "gross_loss": stored.get("gross_loss"),
            "profit_factor": stored.get("profit_factor"),
            "profit_factor_infinite": stored.get("profit_factor_infinite"),
            "net_pnl": stored.get("total_pnl"),
            "largest_profit": stored.get("largest_profit"),
            "largest_loss": stored.get("largest_loss"),
            "largest_profit_inr": stored.get("largest_profit_inr"),
            "largest_loss_inr": stored.get("largest_loss_inr"),
            "outlier_pnl": stored.get("outlier_pnl"),
            "outlier_trades": stored.get("outlier_trades"),
            "commission": stored.get("commission"),
            "source": "closed_trade_ledger",
        }
    )
    dist.update(
        {
            "total_trades": stored.get("total_trades") or 0,
            "winners": stored.get("profitable_trades") or 0,
            "losers": stored.get("losing_trades") or 0,
            "breakevens": stored.get("breakeven") or 0,
            "source": "closed_trade_ledger",
        }
    )
    out["ledger"] = ledger
    out["trade_distribution"] = dist
    if stored.get("trades") is not None:
        out["trades"] = stored["trades"]
    if stored.get("data_hash"):
        out["data_hash"] = stored["data_hash"]
    return out


def row_to_dict(row: W52SymbolPerformance) -> dict[str, Any]:
    return {
        "strategy_id": row.strategy_id,
        "symbol": row.symbol,
        "window": row.window,
        "execution_profile": row.execution_profile,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "evaluation_date": row.evaluation_date.isoformat() if row.evaluation_date else None,
        "status": row.status,
        "unavailable_reason": row.unavailable_reason,
        "data_hash": row.data_hash,
        "candle_count": row.candle_count,
        "coverage_ratio": row.coverage_ratio,
        "total_pnl": row.total_pnl,
        "max_drawdown": row.max_drawdown,
        "max_drawdown_inr": row.max_drawdown_inr,
        "total_trades": row.total_trades,
        "profitable_trades": row.profitable_trades,
        "losing_trades": row.losing_trades,
        "breakeven": row.breakeven,
        "profit_factor": row.profit_factor,
        "profit_factor_infinite": row.profit_factor_infinite,
        "gross_profit": row.gross_profit,
        "gross_loss": row.gross_loss,
        "commission": row.commission,
        "expected_payoff": row.expected_payoff,
        "expected_payoff_inr": row.expected_payoff_inr,
        "largest_profit": row.largest_profit,
        "largest_loss": row.largest_loss,
        "largest_profit_inr": row.largest_profit_inr,
        "largest_loss_inr": row.largest_loss_inr,
        "average_winning_trade": row.average_winning_trade,
        "average_losing_trade": row.average_losing_trade,
        "average_winning_trade_inr": row.average_winning_trade_inr,
        "average_losing_trade_inr": row.average_losing_trade_inr,
        "outlier_pnl": row.outlier_pnl,
        "outlier_trades": row.outlier_trades,
        "win_rate": row.win_rate,
        "total_return": row.total_return,
        "cagr": row.cagr,
        "initial_capital": row.initial_capital,
        "ending_capital": row.ending_capital,
        "source": row.source,
        "error_detail": row.error_detail,
        "trades": row.trades,
        "ledger": row.ledger,
        "coverage": row.coverage,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
        "strategy_tester": strategy_tester_payload(
            {
                "total_pnl": row.total_pnl,
                "max_drawdown": row.max_drawdown,
                "total_trades": row.total_trades,
                "profitable_trades": row.profitable_trades,
                "losing_trades": row.losing_trades,
                "breakeven": row.breakeven,
                "profit_factor": row.profit_factor,
                "gross_profit": row.gross_profit,
                "gross_loss": row.gross_loss,
                "commission": row.commission,
                "expected_payoff": row.expected_payoff,
                "largest_profit": row.largest_profit,
                "largest_loss": row.largest_loss,
                "average_winning_trade": row.average_winning_trade,
                "average_losing_trade": row.average_losing_trade,
                "outlier_pnl": row.outlier_pnl,
            }
        ),
    }


def dashboard_from_stored(
    stored: dict[str, Any],
    *,
    signal: str | None = None,
    technicals: dict[str, Any] | None = None,
    asof: date | None = None,
) -> dict[str, Any]:
    """Rebuild the stock-detail dashboard from stored trades + tester columns."""
    symbol = str(stored.get("symbol") or "")
    window = str(stored.get("window") or "ALL")
    eval_date = asof or _as_date(stored.get("evaluation_date")) or date.today()
    start = _as_date(stored.get("period_start"))
    end = _as_date(stored.get("period_end"))
    dash = build_symbol_dashboard(
        {
            "strategy_id": stored.get("strategy_id") or STRATEGY_ID,
            "evaluation_date": eval_date.isoformat(),
            "recommendations": [{"symbol": symbol, "signal": signal, "technicals": technicals}],
        },
        symbol,
        window,
        blotter=list(stored.get("trades") or []),
        asof=eval_date,
        initial_capital=float(stored.get("initial_capital") or DEFAULT_CAPITAL),
        symbol_replay=True,
        coverage=stored.get("coverage") if isinstance(stored.get("coverage"), dict) else None,
        unavailable_reason=stored.get("unavailable_reason"),
        window_start=start,
        window_end=end,
    )
    dash = apply_stored_metrics(dash, stored)
    dash["replay_kind"] = "symbol_window"
    dash["symbol"] = symbol
    dash["window"] = window
    profile = str(stored.get("execution_profile") or KERNEL_EXECUTION.profile)
    dash["execution"] = parse_execution_profile(profile).as_public_dict()
    return dash


def windows_from_all_dashboard(
    all_dash: dict[str, Any],
    windows: Sequence[str],
    *,
    asof: date,
    signal: str | None = None,
    technicals: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Slice 1Y/3Y/5Y/8Y/18Y metrics from a single ALL-history replay."""
    symbol = str(all_dash.get("symbol") or "")
    blotter = list(all_dash.get("trades") or [])
    equity = list(all_dash.get("equity_curve") or [])
    index_curve = list(all_dash.get("benchmark_curve") or all_dash.get("index_curve") or [])
    initial = float(all_dash.get("initial_capital") or DEFAULT_CAPITAL)
    out: list[dict[str, Any]] = []
    for raw in windows:
        key = parse_window(raw) if raw not in DEFAULT_WINDOWS and raw != "CUSTOM" else str(raw).upper()
        if key == "ALL":
            dash = dict(all_dash)
        else:
            dash = build_symbol_dashboard(
                {
                    "strategy_id": all_dash.get("strategy_id") or STRATEGY_ID,
                    "evaluation_date": asof.isoformat(),
                    "recommendations": [{"symbol": symbol, "signal": signal, "technicals": technicals}],
                },
                symbol,
                key,
                blotter=blotter,
                equity_curve=equity,
                index_curve=index_curve,
                asof=asof,
                initial_capital=initial,
                symbol_replay=True,
                coverage=all_dash.get("coverage") if key in {"ALL", HISTORICAL_PERIOD} else None,
            )
            dash["data_hash"] = all_dash.get("data_hash")
            dash["replay_kind"] = "symbol_window"
            dash["execution"] = all_dash.get("execution")
        dash["symbol"] = symbol
        out.append(metrics_from_dashboard(dash))
    return out


def _assign_row(row: W52SymbolPerformance, payload: dict[str, Any]) -> None:
    row.strategy_id = payload.get("strategy_id") or STRATEGY_ID
    row.symbol = str(payload.get("symbol") or "").upper()
    row.window = str(payload.get("window") or "ALL").upper()
    row.execution_profile = str(payload.get("execution_profile") or KERNEL_EXECUTION.profile)
    row.period_start = payload.get("period_start") if isinstance(payload.get("period_start"), date) else _as_date(payload.get("period_start"))
    row.period_end = payload.get("period_end") if isinstance(payload.get("period_end"), date) else _as_date(payload.get("period_end"))
    row.evaluation_date = payload.get("evaluation_date") if isinstance(payload.get("evaluation_date"), date) else _as_date(payload.get("evaluation_date"))
    row.status = str(payload.get("status") or "ok")
    row.unavailable_reason = payload.get("unavailable_reason")
    row.data_hash = payload.get("data_hash")
    row.candle_count = payload.get("candle_count")
    row.coverage_ratio = payload.get("coverage_ratio")
    row.total_pnl = payload.get("total_pnl")
    row.max_drawdown = payload.get("max_drawdown")
    row.max_drawdown_inr = payload.get("max_drawdown_inr")
    row.total_trades = _as_int(payload.get("total_trades"))
    row.profitable_trades = _as_int(payload.get("profitable_trades"))
    row.losing_trades = _as_int(payload.get("losing_trades"))
    row.breakeven = _as_int(payload.get("breakeven"))
    row.profit_factor = payload.get("profit_factor")
    row.profit_factor_infinite = bool(payload.get("profit_factor_infinite"))
    row.gross_profit = payload.get("gross_profit")
    row.gross_loss = payload.get("gross_loss")
    row.commission = payload.get("commission")
    row.expected_payoff = payload.get("expected_payoff")
    row.expected_payoff_inr = payload.get("expected_payoff_inr")
    row.largest_profit = payload.get("largest_profit")
    row.largest_loss = payload.get("largest_loss")
    row.largest_profit_inr = payload.get("largest_profit_inr")
    row.largest_loss_inr = payload.get("largest_loss_inr")
    row.average_winning_trade = payload.get("average_winning_trade")
    row.average_losing_trade = payload.get("average_losing_trade")
    row.average_winning_trade_inr = payload.get("average_winning_trade_inr")
    row.average_losing_trade_inr = payload.get("average_losing_trade_inr")
    row.outlier_pnl = payload.get("outlier_pnl")
    row.outlier_trades = _as_int(payload.get("outlier_trades"))
    row.win_rate = payload.get("win_rate")
    row.total_return = payload.get("total_return")
    row.cagr = payload.get("cagr")
    row.initial_capital = payload.get("initial_capital")
    row.ending_capital = payload.get("ending_capital")
    row.source = str(payload.get("source") or "closed_trade_ledger")
    row.error_detail = payload.get("error_detail")
    row.trades = payload.get("trades")
    row.ledger = payload.get("ledger")
    row.coverage = payload.get("coverage")
    row.computed_at = _utc()


async def get_symbol_performance(
    symbol: str,
    window: str,
    *,
    strategy_id: str = STRATEGY_ID,
    execution_profile: str = "KERNEL",
) -> W52SymbolPerformance | None:
    symbol = symbol.upper()
    window = str(window or "ALL").upper()
    async with AsyncSessionLocal() as db:
        stmt = (
            select(W52SymbolPerformance)
            .where(
                W52SymbolPerformance.strategy_id == strategy_id,
                W52SymbolPerformance.symbol == symbol,
                W52SymbolPerformance.window == window,
                W52SymbolPerformance.execution_profile == execution_profile,
            )
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()


async def list_symbol_performance(
    symbol: str,
    *,
    strategy_id: str = STRATEGY_ID,
    execution_profile: str | None = None,
) -> list[W52SymbolPerformance]:
    symbol = symbol.upper()
    async with AsyncSessionLocal() as db:
        stmt = select(W52SymbolPerformance).where(
            W52SymbolPerformance.strategy_id == strategy_id,
            W52SymbolPerformance.symbol == symbol,
        )
        if execution_profile:
            stmt = stmt.where(W52SymbolPerformance.execution_profile == execution_profile)
        stmt = stmt.order_by(W52SymbolPerformance.window.asc())
        return list((await db.execute(stmt)).scalars().all())


async def upsert_symbol_performance(payload: dict[str, Any]) -> W52SymbolPerformance:
    symbol = str(payload.get("symbol") or "").upper()
    window = str(payload.get("window") or "ALL").upper()
    strategy_id = payload.get("strategy_id") or STRATEGY_ID
    profile = str(payload.get("execution_profile") or KERNEL_EXECUTION.profile)
    async with AsyncSessionLocal() as db:
        stmt = (
            select(W52SymbolPerformance)
            .where(
                W52SymbolPerformance.strategy_id == strategy_id,
                W52SymbolPerformance.symbol == symbol,
                W52SymbolPerformance.window == window,
                W52SymbolPerformance.execution_profile == profile,
            )
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = W52SymbolPerformance(strategy_id=strategy_id, symbol=symbol, window=window)
            db.add(row)
        _assign_row(row, payload)
        await db.commit()
        await db.refresh(row)
        return row


async def persist_dashboard(dash: dict[str, Any]) -> dict[str, Any]:
    payload = metrics_from_dashboard(dash)
    if not payload.get("symbol") or payload.get("window") == "CUSTOM":
        return payload
    await upsert_symbol_performance(payload)
    return payload


async def load_stored_dashboard(
    symbol: str,
    window: str,
    *,
    signal: str | None = None,
    technicals: dict[str, Any] | None = None,
    asof: date | None = None,
    execution_profile: str = "KERNEL",
) -> dict[str, Any] | None:
    row = await get_symbol_performance(symbol, window, execution_profile=execution_profile)
    if row is None:
        return None
    stored = row_to_dict(row)
    return dashboard_from_stored(stored, signal=signal, technicals=technicals, asof=asof)


async def resolve_evaluation_date() -> date:
    from ...market_data_ingestion.repository import fetch_index_history
    from ....config.settings import settings

    idx = await fetch_index_history(
        getattr(settings, "strategy_index_store_symbol", None) or "NIFTY500"
    )
    last: date | None = None
    for row in idx:
        d = _as_date(row.get("trade_date"))
        if d is not None and (last is None or d > last):
            last = d
    return last or date.today()


async def collect_symbol_performance(
    symbol: str,
    *,
    asof: date | None = None,
    windows: Sequence[str] | None = None,
    force: bool = False,
    initial_capital: float = DEFAULT_CAPITAL,
    execution_profile: str | None = None,
    historical_fill_mode: str | None = None,
    signal: str | None = None,
    technicals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay full history once, persist tester metrics for each window."""
    from .window_backtest import dataset_fingerprint, load_symbol_window_bars, run_symbol_window_backtest

    symbol = symbol.upper()
    asof = asof or await resolve_evaluation_date()
    wanted = tuple(str(w).upper() for w in (windows or DEFAULT_WINDOWS))
    cfg = parse_execution_profile(execution_profile, fill_mode=historical_fill_mode)
    profile_name = cfg.profile

    if not force:
        existing = await get_symbol_performance(symbol, "ALL", execution_profile=profile_name)
        if existing is not None and existing.data_hash:
            dates, _h, _l, close_m, _v, _idx, _o = await load_symbol_window_bars(
                symbol, start=date(1970, 1, 1), end=asof, window="ALL"
            )
            fp = dataset_fingerprint(symbol, close_m.get(symbol, {}), [d for d in dates if d in close_m.get(symbol, {})])
            if existing.data_hash == fp.get("data_hash"):
                stored = [row_to_dict(r) for r in await list_symbol_performance(symbol, execution_profile=profile_name)]
                logger.info("PERF_SKIP symbol=%s reason=data_hash_match windows=%s", symbol, len(stored))
                return {
                    "symbol": symbol,
                    "status": "skipped",
                    "reason": "data_hash_match",
                    "windows": stored,
                }

    try:
        all_dash = await run_symbol_window_backtest(
            symbol,
            "ALL",
            asof=asof,
            initial_capital=initial_capital,
            signal=signal,
            technicals=technicals,
            execution_profile=execution_profile,
            historical_fill_mode=historical_fill_mode,
        )
    except PeriodRequestError as exc:
        logger.info("PERF_FAILED symbol=%s reason=%s", symbol, exc)
        payload = {
            "strategy_id": STRATEGY_ID,
            "symbol": symbol,
            "window": "ALL",
            "execution_profile": profile_name,
            "status": "failed",
            "unavailable_reason": "backtest_failed",
            "error_detail": str(exc),
            "total_trades": 0,
            "profitable_trades": 0,
            "losing_trades": 0,
            "breakeven": 0,
            "evaluation_date": asof,
        }
        await upsert_symbol_performance(payload)
        return {"symbol": symbol, "status": "failed", "reason": str(exc), "windows": [payload]}

    rows = windows_from_all_dashboard(
        all_dash, wanted, asof=asof, signal=signal, technicals=technicals
    )
    stored = []
    for payload in rows:
        row = await upsert_symbol_performance(payload)
        stored.append(row_to_dict(row))
    dist = all_dash.get("trade_distribution") or {}
    logger.info(
        "PERF_STORED symbol=%s windows=%s closed=%s winners=%s losers=%s breakeven=%s",
        symbol,
        len(stored),
        dist.get("total_trades"),
        dist.get("winners"),
        dist.get("losers"),
        dist.get("breakevens"),
    )
    return {
        "symbol": symbol,
        "status": "stored",
        "evaluation_date": asof.isoformat(),
        "data_hash": all_dash.get("data_hash"),
        "windows": stored,
    }


async def collect_universe_performance(
    *,
    symbols: Iterable[str] | None = None,
    asof: date | None = None,
    windows: Sequence[str] | None = None,
    force: bool = False,
    concurrency: int = 4,
    limit: int | None = None,
) -> dict[str, Any]:
    """Collect tester metrics for the NIFTY 500 universe (or an explicit list)."""
    from ...universe_service import UniverseService

    asof = asof or await resolve_evaluation_date()
    if symbols is None:
        names = await UniverseService.get_active_nifty500_symbols()
    else:
        names = [str(s).upper() for s in symbols if str(s).strip()]
    if limit is not None:
        names = names[: int(limit)]
    sem = asyncio.Semaphore(max(1, int(concurrency)))
    processed = successful = failed = skipped = 0
    errors: list[dict[str, str]] = []

    async def _one(sym: str) -> dict[str, Any]:
        nonlocal processed, successful, failed, skipped
        async with sem:
            try:
                result = await collect_symbol_performance(
                    sym, asof=asof, windows=windows, force=force
                )
            except Exception as exc:  # pragma: no cover - per-name isolation
                logger.exception("PERF_SYMBOL_FAILED symbol=%s", sym)
                failed += 1
                processed += 1
                errors.append({"symbol": sym, "error": str(exc)})
                return {"symbol": sym, "status": "failed", "reason": str(exc)}
            processed += 1
            if result.get("status") == "skipped":
                skipped += 1
            elif result.get("status") == "failed":
                failed += 1
            else:
                successful += 1
            if processed % 25 == 0 or processed == len(names):
                logger.info(
                    "PERF_PROGRESS processed=%s/%s successful=%s skipped=%s failed=%s",
                    processed,
                    len(names),
                    successful,
                    skipped,
                    failed,
                )
            return result

    results = await asyncio.gather(*[_one(sym) for sym in names])
    return {
        "strategy_id": STRATEGY_ID,
        "evaluation_date": asof.isoformat(),
        "windows": list(windows or DEFAULT_WINDOWS),
        "total": len(names),
        "processed": processed,
        "successful": successful,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:50],
        "symbols": [r.get("symbol") for r in results],
    }
