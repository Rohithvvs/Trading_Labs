"""Canonical closed-trade ledger and aggregate metrics.

Statistics are computed only from simulated fills (closed trades), never from
signals. Classification uses net P&L against an explicit rupee tolerance, not
rounded display percentages.
"""

from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any, Iterable, Sequence

from .book_engine import Trade
from .execution import ExecutionConfig, KERNEL_EXECUTION
from .identity import STRATEGY_ID


def _finite(value: Any) -> bool:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(n)


def classify_outcome(net_pnl: float, *, tolerance: float = 0.0) -> str:
    if net_pnl > tolerance:
        return "winner"
    if net_pnl < -tolerance:
        return "loser"
    return "breakeven"


def trade_net_pnl(tr: Trade) -> float | None:
    if tr.net_pnl is not None and _finite(tr.net_pnl):
        return float(tr.net_pnl)
    if tr.entry_price and tr.exit_price is not None and tr.shares:
        gross = float(tr.shares) * (float(tr.exit_price) - float(tr.entry_price))
        commission = float(tr.commission or 0.0)
        slippage = float(tr.slippage or 0.0)
        return gross - commission - slippage
    if tr.pnl_pct is not None and _finite(tr.pnl_pct) and tr.entry_price and tr.shares:
        return float(tr.pnl_pct) * float(tr.entry_price) * float(tr.shares)
    return None


def trade_return_pct(tr: Trade) -> float | None:
    """Fraction, not percent. Prefer explicit return_pct, else price return."""
    if tr.return_pct is not None and _finite(tr.return_pct):
        return float(tr.return_pct)
    if tr.pnl_pct is not None and _finite(tr.pnl_pct):
        return float(tr.pnl_pct)
    if tr.entry_price and tr.exit_price is not None and float(tr.entry_price) != 0:
        return float(tr.exit_price) / float(tr.entry_price) - 1.0
    return None


def closed_trades(trades: Iterable[Trade]) -> list[Trade]:
    return [tr for tr in trades if not tr.open]


def annotate_outcomes(trades: Sequence[Trade], *, tolerance: float = 0.0) -> list[Trade]:
    for tr in trades:
        if tr.open:
            tr.outcome = None
            continue
        sized = bool(tr.shares or tr.quantity)
        pnl = trade_net_pnl(tr)
        if sized and pnl is not None:
            tr.outcome = classify_outcome(pnl, tolerance=tolerance)
            continue
        ret = trade_return_pct(tr)
        tr.outcome = classify_outcome(ret, tolerance=0.0) if ret is not None else None
    return list(trades)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def outlier_pnl(net_pnls: Sequence[float]) -> tuple[float | None, int]:
    """TradingView Strategy Tester: P&L of trades beyond 3 population stdevs."""
    values = [float(p) for p in net_pnls if _finite(p)]
    if not values:
        return None, 0
    if len(values) < 2:
        return 0.0, 0
    mean = statistics.mean(values)
    sd = statistics.pstdev(values)
    if sd == 0:
        return 0.0, 0
    outliers = [p for p in values if abs(p - mean) > 3.0 * sd]
    return (sum(outliers) if outliers else 0.0), len(outliers)


def aggregate_closed_trades(
    trades: Sequence[Trade],
    *,
    cfg: ExecutionConfig | None = None,
    initial_capital: float | None = None,
) -> dict[str, Any]:
    cfg = cfg or KERNEL_EXECUTION
    tolerance = float(cfg.breakeven_tolerance_inr)
    closed = closed_trades(trades)
    annotate_outcomes(closed, tolerance=tolerance)

    winners = [t for t in closed if t.outcome == "winner"]
    losers = [t for t in closed if t.outcome == "loser"]
    breakevens = [t for t in closed if t.outcome == "breakeven"]

    net_pnls = [trade_net_pnl(t) for t in closed]
    net_pnls_f = [p for p in net_pnls if p is not None]
    win_pnls = [trade_net_pnl(t) for t in winners]
    win_pnls_f = [p for p in win_pnls if p is not None]
    loss_pnls = [trade_net_pnl(t) for t in losers]
    loss_pnls_f = [p for p in loss_pnls if p is not None]

    rets = [trade_return_pct(t) for t in closed]
    rets_f = [r for r in rets if r is not None]
    win_rets = [trade_return_pct(t) for t in winners]
    win_rets_f = [r for r in win_rets if r is not None]
    loss_rets = [trade_return_pct(t) for t in losers]
    loss_rets_f = [r for r in loss_rets if r is not None]

    holds: list[int] = []
    for t in closed:
        if t.holding_period is not None:
            holds.append(int(t.holding_period))
        elif t.exit_date and t.entry_date:
            holds.append((t.exit_date - t.entry_date).days)

    gross_profit = sum(p for p in win_pnls_f if p > 0)
    gross_loss = sum(p for p in loss_pnls_f if p < 0)
    net_pnl = sum(net_pnls_f)
    profit_factor = None
    pf_infinite = False
    if gross_loss < 0 and gross_profit > 0:
        profit_factor = gross_profit / abs(gross_loss)
    elif gross_profit > 0 and not loss_pnls_f:
        pf_infinite = True

    total = len(closed)
    avg_profit_pct = (sum(win_rets_f) / len(win_rets_f)) if win_rets_f else None
    avg_loss_pct = (sum(loss_rets_f) / len(loss_rets_f)) if loss_rets_f else None
    expected_payoff_pct = (sum(rets_f) / len(rets_f)) if rets_f else None
    expected_payoff_inr = (sum(net_pnls_f) / len(net_pnls_f)) if net_pnls_f else None

    commissions = [float(t.commission or 0.0) for t in closed]
    slippages = [float(t.slippage or 0.0) for t in closed]
    grosses = []
    for t in closed:
        if t.gross_pnl is not None and _finite(t.gross_pnl):
            grosses.append(float(t.gross_pnl))
        elif t.entry_price and t.exit_price is not None and t.shares:
            grosses.append(float(t.shares) * (float(t.exit_price) - float(t.entry_price)))

    largest_profit = max(win_rets_f) if win_rets_f else None
    largest_loss = min(loss_rets_f) if loss_rets_f else None
    largest_profit_inr = max(win_pnls_f) if win_pnls_f else None
    largest_loss_inr = min(loss_pnls_f) if loss_pnls_f else None
    outlier_inr, outlier_trades = outlier_pnl(net_pnls_f)
    total_return = None
    if initial_capital and initial_capital > 0:
        total_return = net_pnl / float(initial_capital)

    return {
        "strategy_id": STRATEGY_ID,
        "total_trades": total,
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "breakeven_trades": len(breakevens),
        "win_rate": (len(winners) / total) if total else None,
        "average_profit": avg_profit_pct,
        "average_loss": avg_loss_pct,
        "expected_payoff": expected_payoff_pct,
        "expected_payoff_pct": expected_payoff_pct,
        "expected_payoff_inr": expected_payoff_inr,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "profit_factor_infinite": pf_infinite,
        "net_pnl": net_pnl,
        "total_return": total_return,
        "largest_profit": largest_profit,
        "largest_loss": largest_loss,
        "largest_profit_inr": largest_profit_inr,
        "largest_loss_inr": largest_loss_inr,
        "outlier_pnl": outlier_inr,
        "outlier_trades": outlier_trades,
        "average_holding_period": (sum(holds) / len(holds)) if holds else None,
        "median_holding_period": _median([float(h) for h in holds]),
        "commission": sum(commissions),
        "slippage": sum(slippages),
        "gross_pnl": sum(grosses) if grosses else None,
        "breakeven_tolerance_inr": tolerance,
        "source": "closed_trade_ledger",
    }


def ledger_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    """Frontend-facing copy: percentages scaled to display units where needed."""

    def pct(value: Any) -> float | None:
        if value is None:
            return None
        return round(float(value) * 100.0, 6)

    return {
        "total_trades": metrics.get("total_trades") or 0,
        "winning_trades": metrics.get("winning_trades") or 0,
        "losing_trades": metrics.get("losing_trades") or 0,
        "breakeven_trades": metrics.get("breakeven_trades") or 0,
        "win_rate": pct(metrics.get("win_rate")),
        "average_profit": pct(metrics.get("average_profit")),
        "average_loss": pct(metrics.get("average_loss")),
        "expected_payoff": pct(metrics.get("expected_payoff")),
        "expected_payoff_inr": None
        if metrics.get("expected_payoff_inr") is None
        else round(float(metrics["expected_payoff_inr"]), 6),
        "gross_profit": metrics.get("gross_profit"),
        "gross_loss": metrics.get("gross_loss"),
        "profit_factor": metrics.get("profit_factor"),
        "profit_factor_infinite": metrics.get("profit_factor_infinite"),
        "net_pnl": metrics.get("net_pnl"),
        "total_return": pct(metrics.get("total_return")),
        "largest_profit": pct(metrics.get("largest_profit")),
        "largest_loss": pct(metrics.get("largest_loss")),
        "largest_profit_inr": metrics.get("largest_profit_inr"),
        "largest_loss_inr": metrics.get("largest_loss_inr"),
        "outlier_pnl": metrics.get("outlier_pnl"),
        "outlier_trades": metrics.get("outlier_trades") or 0,
        "average_holding_period": metrics.get("average_holding_period"),
        "median_holding_period": metrics.get("median_holding_period"),
        "commission": metrics.get("commission"),
        "slippage": metrics.get("slippage"),
        "breakeven_tolerance_inr": metrics.get("breakeven_tolerance_inr"),
        "source": "closed_trade_ledger",
    }
