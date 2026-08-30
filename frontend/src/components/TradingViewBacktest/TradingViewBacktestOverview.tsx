import React, { useState, useMemo } from "react";
import type { BacktestDashboardModel, BacktestRange, DashboardTrade } from "../BacktestAnalyticsDashboard";
import type { TvViewMode, TvDetailization, TvScriptStatus, TvKeyStatsData, TvPerformancePoint } from "./types";
import { TvToolbar } from "./TvToolbar";
import { TvKeyStats } from "./TvKeyStats";
import { TvPerformanceChart } from "./TvPerformanceChart";
import { TvListOfTrades } from "./TvListOfTrades";

interface TradingViewBacktestOverviewProps {
  model: BacktestDashboardModel | null;
  range: BacktestRange;
  onRangeChange: (next: BacktestRange) => void;
  startDate?: string;
  endDate?: string;
  onCustomRange?: (start: string, end: string) => void;
  loading?: boolean;
  symbol?: string;
  strategyName?: string;
  currency?: string;
  onOpenConfigModal?: () => void;
}

export const TradingViewBacktestOverview: React.FC<TradingViewBacktestOverviewProps> = ({
  model,
  range,
  onRangeChange,
  startDate,
  endDate,
  onCustomRange,
  loading = false,
  symbol = "STOCK",
  strategyName = "52-Week High Breakout",
  currency = "INR",
  onOpenConfigModal,
}) => {
  const [viewMode, setViewMode] = useState<TvViewMode>("chart");
  const [detailization, setDetailization] = useState<TvDetailization>("default");

  const initialCapital = model?.initial_capital ?? 100000;
  const rawTrades: DashboardTrade[] = useMemo(() => model?.trades || [], [model]);
  const closedTrades = useMemo(() => rawTrades.filter((t) => !t.open), [rawTrades]);

  // Compute Key Stats
  const keyStats: TvKeyStatsData = useMemo(() => {
    const totalTrades = model?.strategy_tester?.total_trades ?? model?.ledger?.total_trades ?? closedTrades.length;
    const winTrades = model?.strategy_tester?.profitable_trades ?? model?.ledger?.winning_trades ?? closedTrades.filter((t) => (t.pnl_percent ?? 0) > 0).length;

    const netPnlInr = model?.strategy_tester?.total_pnl ?? model?.ledger?.net_pnl ?? model?.net_pnl ?? (model?.ending_capital != null ? model.ending_capital - initialCapital : null);
    const totalPnlPct = model?.total_return ?? (netPnlInr != null && initialCapital > 0 ? (netPnlInr / initialCapital) * 100 : null);

    const maxDdInr = model?.max_drawdown_inr ?? (model?.max_drawdown != null ? (Math.abs(model.max_drawdown) / 100) * initialCapital : null);
    const maxDrawdownPct = model?.max_drawdown != null ? Math.abs(model.max_drawdown) : null;

    const winRatePct = model?.ledger?.win_rate ?? (totalTrades > 0 ? (winTrades / totalTrades) * 100 : model?.win_rate ?? null);

    let profitFactor = model?.profit_factor ?? model?.strategy_tester?.profit_factor ?? null;
    let profitFactorInfinite = Boolean(model?.profit_factor_infinite);

    if (profitFactor == null && model?.ledger?.gross_loss != null && model?.ledger?.gross_profit != null) {
      if (Math.abs(model.ledger.gross_loss) === 0) {
        profitFactorInfinite = true;
        profitFactor = null;
      } else {
        profitFactor = model.ledger.gross_profit / Math.abs(model.ledger.gross_loss);
      }
    }

    return {
      totalPnlInr: netPnlInr,
      totalPnlPct,
      maxDrawdownInr: maxDdInr,
      maxDrawdownPct,
      winRatePct,
      winCount: winTrades,
      totalTrades,
      profitFactor,
      profitFactorInfinite,
    };
  }, [model, closedTrades, initialCapital]);

  // Compute Performance Chart Points (Cumulative PnL, Buy & Hold, Run-up / Drawdown)
  const performancePoints: TvPerformancePoint[] = useMemo(() => {
    const eqCurve = model?.equity_curve || [];
    const ddCurve = new Map((model?.drawdown_curve || []).map((p) => [p.date || p.label || "", p.drawdown]));
    const benchCurve = model?.benchmark_curve || [];

    const firstBench = benchCurve[0]?.close ?? benchCurve[0]?.equity;
    const benchMap = new Map(
      benchCurve.map((p) => {
        const key = p.date || p.label || "";
        const raw = p.close ?? p.equity;
        const pnl = firstBench && raw != null ? ((Number(raw) - Number(firstBench)) / Number(firstBench)) * initialCapital : null;
        const pct = firstBench && raw != null ? ((Number(raw) - Number(firstBench)) / Number(firstBench)) * 100 : null;
        return [key, { pnl, pct }];
      }),
    );

    let peak = initialCapital;

    return eqCurve.map((pt, idx) => {
      const dateKey = pt.date || pt.label || "";
      const currentEq = Number(pt.equity);
      const cumulativePnl = currentEq - initialCapital;
      const cumulativePnlPct = initialCapital > 0 ? (cumulativePnl / initialCapital) * 100 : 0;

      if (currentEq > peak) peak = currentEq;

      const ddInr = ddCurve.get(dateKey) != null ? (Math.abs(ddCurve.get(dateKey)!) / 100) * initialCapital : (peak > currentEq ? peak - currentEq : 0);
      const ddPct = ddCurve.get(dateKey) != null ? Math.abs(ddCurve.get(dateKey)!) : (peak > 0 ? ((peak - currentEq) / peak) * 100 : 0);

      const runUpInr = currentEq > initialCapital ? currentEq - initialCapital : 0;
      const runUpPct = initialCapital > 0 ? (runUpInr / initialCapital) * 100 : 0;

      const benchItem = benchMap.get(dateKey);

      // Check if winning interval
      const prevEq = idx > 0 ? Number(eqCurve[idx - 1].equity) : initialCapital;
      const isWinningInterval = currentEq >= prevEq;

      return {
        date: dateKey,
        label: dateKey,
        cumulativePnl,
        cumulativePnlPct,
        buyAndHoldPnl: benchItem?.pnl ?? null,
        buyAndHoldPct: benchItem?.pct ?? null,
        drawdownInr: ddInr,
        drawdownPct: ddPct,
        runUpInr,
        runUpPct,
        isWinningInterval,
      };
    });
  }, [model, initialCapital]);

  const scriptStatus: TvScriptStatus = loading
    ? "running"
    : model?.unavailable_reason
      ? "error"
      : "completed";

  return (
    <div className="tv-backtest-overview-container" data-testid="tv-backtest-overview">
      {/* 1. Top TradingView Toolbar */}
      <TvToolbar
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        startDate={model?.period_start || startDate}
        endDate={model?.period_end || endDate}
        range={range}
        onRangeChange={onRangeChange}
        onCustomRange={onCustomRange}
        initialCapital={initialCapital}
        currency={currency}
        detailization={detailization}
        onDetailizationChange={setDetailization}
        scriptStatus={scriptStatus}
        tradeCount={closedTrades.length}
        onOpenConfigModal={onOpenConfigModal}
        symbol={symbol}
        strategyName={strategyName}
      />

      {/* 2. Content depending on selected view */}
      <div
        className="tv-chart-view-stack"
        style={{ display: viewMode === "chart" ? "block" : "none" }}
        data-testid="tv-chart-view-stack"
      >
        {/* Key stats */}
        <TvKeyStats
          stats={keyStats}
          currency={currency}
          loading={loading}
        />

        {/* Performance chart */}
        <TvPerformanceChart
          points={performancePoints}
          currency={currency}
          loading={loading}
          onOpenSettings={onOpenConfigModal}
        />
      </div>

      <div
        className="tv-table-view-stack"
        style={{ display: viewMode === "table" ? "block" : "none" }}
        data-testid="tv-table-view-stack"
      >
        {/* List of trades */}
        <TvListOfTrades
          trades={rawTrades}
          initialCapital={initialCapital}
          currency={currency}
          symbol={symbol}
          loading={loading}
        />
      </div>
    </div>
  );
};
