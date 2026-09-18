"""LeanResultParser: Normalizes LEAN algorithm execution results into Trading Labs standard models."""

from __future__ import annotations

import math
import statistics
from typing import Any

from ..models import (
    LeanBacktestResult,
    LeanBacktestSummary,
    LeanEquityPoint,
    LeanJobStatus,
    LeanPositionHistory,
    LeanTrade,
    LeanValidationReport,
)


class LeanResultParser:
    """Computes professional risk & performance metrics and normalizes backtest outputs."""

    @classmethod
    def parse(
        cls,
        *,
        job_id: str,
        strategy_id: str,
        strategy_name: str,
        start_date_str: str,
        end_date_str: str,
        initial_capital: float,
        equity_records: list[dict[str, Any]],
        closed_trades: list[dict[str, Any]],
        position_snapshots: list[dict[str, Any]],
        symbols: list[str],
        trading_days_count: int,
        execution_model_name: str = "LEAN NextBarOpen",
        data_source: str = "Trading Labs NSE Data",
        debug_trace: list[Any] | None = None,
        validation_report: LeanValidationReport | None = None,
    ) -> LeanBacktestResult:
        final_equity = equity_records[-1]["equity"] if equity_records else initial_capital
        net_profit = final_equity - initial_capital
        net_profit_pct = (net_profit / initial_capital * 100.0) if initial_capital > 0 else 0.0

        # Build equity curve & drawdowns
        equity_curve: list[LeanEquityPoint] = []
        peak_equity = initial_capital
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        daily_returns: list[float] = []
        prev_eq = initial_capital

        for rec in equity_records:
            eq = float(rec["equity"])
            cash = float(rec.get("cash", eq))
            inv = float(rec.get("invested", 0.0))
            d_str = str(rec["date"])

            if eq > peak_equity:
                peak_equity = eq
            dd = peak_equity - eq
            dd_pct = (dd / peak_equity * 100.0) if peak_equity > 0 else 0.0

            if dd > max_drawdown:
                max_drawdown = dd
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct

            if prev_eq > 0:
                day_ret = (eq - prev_eq) / prev_eq
                daily_returns.append(day_ret)
            prev_eq = eq

            equity_curve.append(
                LeanEquityPoint(
                    date=d_str,
                    equity=round(eq, 2),
                    cash=round(cash, 2),
                    investedCapital=round(inv, 2),
                    drawdown=round(dd, 2),
                    drawdownPct=round(dd_pct, 2),
                )
            )

        # CAGR Calculation
        cagr: float | None = None
        if trading_days_count > 1 and initial_capital > 0 and final_equity > 0:
            try:
                cagr = ((final_equity / initial_capital) ** (252.0 / trading_days_count) - 1.0) * 100.0
                if math.isnan(cagr) or math.isinf(cagr):
                    cagr = None
                else:
                    cagr = round(cagr, 2)
            except Exception:
                cagr = None

        # Sharpe & Sortino Ratios (Standard 252 annualization)
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        if len(daily_returns) > 1:
            mean_ret = statistics.mean(daily_returns)
            stdev = statistics.stdev(daily_returns)
            if stdev > 0:
                sharpe_ratio = round((mean_ret / stdev) * math.sqrt(252), 3)

            neg_returns = [r for r in daily_returns if r < 0]
            if neg_returns and len(neg_returns) > 1:
                downside_std = statistics.stdev(neg_returns)
                if downside_std > 0:
                    sortino_ratio = round((mean_ret / downside_std) * math.sqrt(252), 3)

        # Calmar Ratio
        calmar_ratio = round(cagr / max_drawdown_pct, 2) if (cagr is not None and max_drawdown_pct > 0) else None

        # Trade statistics
        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if float(t.get("net_pnl", 0)) > 0]
        losing_trades = [t for t in closed_trades if float(t.get("net_pnl", 0)) < 0]
        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        win_rate = round((win_count / total_trades * 100.0), 2) if total_trades > 0 else 0.0

        total_win_pnl = sum(float(t.get("net_pnl", 0)) for t in winning_trades)
        total_loss_pnl = abs(sum(float(t.get("net_pnl", 0)) for t in losing_trades))

        if total_loss_pnl > 0:
            profit_factor = round(total_win_pnl / total_loss_pnl, 2)
        elif total_win_pnl > 0:
            profit_factor = round(total_win_pnl, 2)
        else:
            profit_factor = 0.0

        returns = [float(t.get("return_pct", 0)) for t in closed_trades]
        win_returns = [float(t.get("return_pct", 0)) for t in winning_trades]
        loss_returns = [float(t.get("return_pct", 0)) for t in losing_trades]

        avg_trade = round(statistics.mean(returns), 2) if returns else 0.0
        avg_win = round(statistics.mean(win_returns), 2) if win_returns else 0.0
        avg_loss = round(statistics.mean(loss_returns), 2) if loss_returns else 0.0

        # Expectancy = (Win% * AvgWin) - (Loss% * |AvgLoss|)
        p_win = win_count / total_trades if total_trades > 0 else 0.0
        p_loss = loss_count / total_trades if total_trades > 0 else 0.0
        expectancy = round((p_win * avg_win) - (p_loss * abs(avg_loss)), 2)

        total_commission = sum(float(t.get("commission", 0)) for t in closed_trades)
        total_slippage = sum(float(t.get("slippage", 0)) for t in closed_trades)

        # Build trade models
        trades: list[LeanTrade] = []
        for t in closed_trades:
            trades.append(
                LeanTrade(
                    tradeId=int(t["trade_id"]),
                    symbol=str(t["symbol"]),
                    entryDate=str(t["entry_date"]),
                    entryPrice=float(t["entry_price"]),
                    exitDate=str(t.get("exit_date")),
                    exitPrice=float(t["exit_price"]) if t.get("exit_price") is not None else None,
                    quantity=int(t["quantity"]),
                    direction=str(t.get("direction", "LONG")),
                    grossPnL=float(t.get("gross_pnl", 0.0)),
                    commission=float(t.get("commission", 0.0)),
                    slippage=float(t.get("slippage", 0.0)),
                    netPnL=float(t.get("net_pnl", 0.0)),
                    returnPct=float(t.get("return_pct", 0.0)),
                    holdingPeriod=int(t.get("holding_period", 1)),
                    entryReason=str(t.get("entry_reason", "Signal")),
                    exitReason=str(t.get("exit_reason", "Exit Signal")),
                    isOpen=bool(t.get("is_open", False)),
                )
            )

        # Build position history models
        positions: list[LeanPositionHistory] = []
        for p in position_snapshots:
            positions.append(
                LeanPositionHistory(
                    date=str(p["date"]),
                    symbol=str(p["symbol"]),
                    quantity=int(p["quantity"]),
                    averagePrice=float(p["average_price"]),
                    marketValue=float(p["market_value"]),
                    unrealizedPnL=float(p.get("unrealized_pnl", 0.0)),
                    realizedPnL=float(p.get("realized_pnl", 0.0)),
                )
            )

        summary = LeanBacktestSummary(
            initialCapital=round(initial_capital, 2),
            finalEquity=round(final_equity, 2),
            netProfit=round(net_profit, 2),
            netProfitPct=round(net_profit_pct, 2),
            cagr=cagr,
            sharpeRatio=sharpe_ratio,
            sortinoRatio=sortino_ratio,
            maximumDrawdown=round(max_drawdown, 2),
            maximumDrawdownPct=round(max_drawdown_pct, 2),
            calmarRatio=calmar_ratio,
            totalTrades=total_trades,
            winningTrades=win_count,
            losingTrades=loss_count,
            winRate=win_rate,
            profitFactor=profit_factor,
            averageTrade=avg_trade,
            averageWinningTrade=avg_win,
            averageLosingTrade=avg_loss,
            expectancy=expectancy,
            totalCommission=round(total_commission, 2),
            totalSlippage=round(total_slippage, 2),
            executionModel=execution_model_name,
            dataSource=data_source,
            dataCoverageRatio=1.0,
            tradingDaysCount=trading_days_count,
        )

        return LeanBacktestResult(
            jobId=job_id,
            strategyId=strategy_id,
            strategyName=strategy_name,
            engine="LEAN",
            status=LeanJobStatus.COMPLETED,
            startDate=start_date_str,
            endDate=end_date_str,
            symbols=symbols,
            summary=summary,
            trades=trades,
            equityCurve=equity_curve,
            positions=positions,
            debugTrace=debug_trace,
            validationParity=validation_report,
        )
