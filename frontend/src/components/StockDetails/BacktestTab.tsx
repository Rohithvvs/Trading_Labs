import React, { useEffect, useMemo, useState } from "react";
import type { CandlePoint, StrategyResultRow, StrategyRunStatus, SymbolHistoryItem } from "../../api_strategy_tester";
import type { SymbolDetail } from "../../types";
import {
  BacktestAnalyticsDashboard,
  type BacktestDashboardModel,
  type BacktestRange,
  type DashboardTrade,
} from "../BacktestAnalyticsDashboard";
import { fetchSymbolDetail, fetchW52SymbolDetail, fetchLtmSymbolDetail } from "../../api";
import { asDashboardTrade, hydrateStrategyBacktest } from "../../utils/strategyBacktestDashboard";
import { isIndicatorScanContext } from "../../utils/indicatorScanDetail";
import { W52_STRATEGY_ID } from "../../utils/strategyIdentity";

export interface BacktestTabProps {
  symbol: string;
  stock: StrategyResultRow | null;
  runStatus: StrategyRunStatus | null;
  symbolDetail?: SymbolDetail | null;
  history: SymbolHistoryItem[];
  candles?: CandlePoint[];
  strategyName: string;
  runId?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  initialCapital?: number;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

function isoDay(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const KERNEL_ALL_START = "2008-07-22";

function boundsForRange(
  range: BacktestRange,
  asof: Date,
): { start: string; end: string } {
  const end = isoDay(asof);
  if (range === "ALL") {
    return { start: KERNEL_ALL_START, end };
  }
  const years = range === "1Y" ? 1 : range === "5Y" ? 5 : range === "8Y" ? 8 : 3;
  const start = new Date(asof);
  start.setFullYear(start.getFullYear() - years);
  return { start: isoDay(start), end };
}

// Module-level cache for benchmark data to eliminate redundant network fetches
let cachedNiftyData: { label: string; close: number }[] | null = null;

export const BacktestTab: React.FC<BacktestTabProps> = ({
  symbol,
  stock,
  runStatus,
  symbolDetail,
  history = [],
  candles = [],
  strategyName,
  runId,
  startDate,
  endDate,
  initialCapital: propInitialCapital,
  isLoading = false,
  error = null,
  onRetry,
}) => {
  const indicatorScan = isIndicatorScanContext(stock, runId || runStatus?.run_id || runStatus?.id);
  const asof = useMemo(() => {
    if (endDate) {
      const d = new Date(`${String(endDate).slice(0, 10)}T00:00:00`);
      if (!Number.isNaN(d.getTime())) return d;
    }
    return new Date();
  }, [endDate]);

  const [range, setRange] = useState<BacktestRange>(() => (indicatorScan ? "1Y" : "3Y"));
  const [currentStartDate, setCurrentStartDate] = useState(
    () => startDate || boundsForRange(indicatorScan ? "1Y" : "3Y", asof).start,
  );
  const [currentEndDate, setCurrentEndDate] = useState(() => endDate || boundsForRange(indicatorScan ? "1Y" : "3Y", asof).end);

  const handleRangeChange = (next: BacktestRange) => {
    const bounds = boundsForRange(next === "CUSTOM" ? "3Y" : next, asof);
    setRange(next);
    setCurrentStartDate(bounds.start);
    setCurrentEndDate(bounds.end);
  };

  const handleCustomRange = (start: string, end: string) => {
    setRange("CUSTOM");
    setCurrentStartDate(start);
    setCurrentEndDate(end);
  };

  // NIFTY 500 benchmark data (cached in memory)
  const [niftyData, setNiftyData] = useState<{ label: string; close: number }[]>(() => cachedNiftyData || []);

  useEffect(() => {
    if (cachedNiftyData && cachedNiftyData.length > 0) return;
    fetchSymbolDetail("NIFTY 500")
      .then((res: any) => {
        if (res?.ohlcv) {
          const parsed = res.ohlcv.map((c: any) => ({
            label: new Date(c.timestamp).toISOString().split("T")[0],
            close: c.close,
          }));
          cachedNiftyData = parsed;
          setNiftyData(parsed);
        }
      })
      .catch(() => {});
  }, []);

  // Strategy kernel fetch for 52W and LTM if applicable
  const [kernelDash, setKernelDash] = useState<BacktestDashboardModel | null>(null);
  const [kernelLoading, setKernelLoading] = useState(false);
  const [kernelError, setKernelError] = useState<string | null>(null);

  useEffect(() => {
    const sName = (strategyName || "").toLowerCase();
    const isW52 = sName.includes("52-week") || sName.includes("52w") || sName.includes("breakout");
    const isLtm = sName.includes("ltm") || sName.includes("momentum") || sName.includes("buy & hold");

    if (indicatorScan || !symbol || (!isW52 && !isLtm)) {
      setKernelDash(null);
      setKernelLoading(false);
      return;
    }

    const fetchW52 = typeof fetchW52SymbolDetail === "function" ? fetchW52SymbolDetail : null;
    const fetchLtm = typeof fetchLtmSymbolDetail === "function" ? fetchLtmSymbolDetail : null;

    if (isW52 && !fetchW52) {
      setKernelDash(null);
      setKernelLoading(false);
      return;
    }
    if (isLtm && !fetchLtm) {
      setKernelDash(null);
      setKernelLoading(false);
      return;
    }

    let cancelled = false;
    setKernelLoading(true);
    setKernelError(null);

    const req = isW52
      ? fetchW52!(symbol, range, { startDate: currentStartDate, endDate: currentEndDate, executionProfile: "KERNEL" })
      : fetchLtm!(symbol, range === "CUSTOM" ? "ALL" : range);

    req
      .then((res) => {
        if (cancelled) return;
        const rowWrapper: any = {
          symbol,
          w52: isW52 ? { strategy_id: W52_STRATEGY_ID } : undefined,
          ltm: isLtm ? { strategy_id: "17_long_term_mom" } : undefined,
        };
        const dash = hydrateStrategyBacktest(rowWrapper, range, res);
        setKernelDash(dash);
      })
      .catch(() => {
        if (!cancelled) setKernelDash(null);
      })
      .finally(() => {
        if (!cancelled) setKernelLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, strategyName, range, currentStartDate, currentEndDate, indicatorScan]);

  // Construct comprehensive BacktestDashboardModel
  const model: BacktestDashboardModel = useMemo(() => {
    if (kernelDash) {
      if (niftyData.length && !kernelDash.benchmark_curve?.length) {
        return {
          ...kernelDash,
          benchmark_curve: niftyData.map((n) => ({ date: n.label, label: n.label, close: n.close })),
        };
      }
      return kernelDash;
    }

    const initCap =
      propInitialCapital && propInitialCapital > 0
        ? propInitialCapital
        : runStatus?.initial_capital && runStatus.initial_capital > 0
          ? runStatus.initial_capital
          : 1000000;
    const startStr = currentStartDate || startDate || runStatus?.start_date || "2024-01-01";
    const endStr = currentEndDate || endDate || runStatus?.end_date || "2026-08-26";
    const evalDate = String(stock?.evaluation_date || endStr).slice(0, 10) || endStr;
    const cutoff = new Date(startStr);

    // 1. Build Trades
    let rawTrades: DashboardTrade[] = [];
    if ((symbolDetail?.backtest_extras as any)?.trades && Array.isArray((symbolDetail.backtest_extras as any).trades)) {
      rawTrades = (symbolDetail.backtest_extras as any).trades.map(asDashboardTrade);
    } else if (history && history.length > 0) {
      rawTrades = history.map((h, i) => {
        const pnl = h.return_pct ?? 0;
        const entryPx = h.entry_price ?? stock?.entry_price ?? 100;
        const exitPx = h.exit_price ?? entryPx * (1 + pnl / 100);
        const exitDate = h.date ? h.date.slice(0, 10) : evalDate;
        const entryDate = startStr;
        return {
          trade_id: `TR-${h.run_id || i + 1}`,
          entry_date: entryDate,
          exit_date: exitDate,
          type: "LONG",
          entry_price: entryPx,
          exit_price: exitPx,
          pnl_percent: pnl,
          holding_days: 14,
          reason: h.signal || (indicatorScan ? "Indicator scan" : "Strategy Signal"),
          exit_reason: indicatorScan ? "Scan bar (Close t-252 → Close)" : "Strategy Exit Rule",
          open: false,
          outcome: pnl >= 0 ? "win" : "loss",
          net_pnl: (pnl / 100) * initCap,
          commission: 20,
          slippage: 0,
        };
      });
    } else if (stock && (stock.entry_price != null || stock.return_pct != null || stock.close != null)) {
      const pnl = stock.return_pct ?? 0;
      const exitPx = stock.exit_price ?? stock.close ?? null;
      const entryPx =
        stock.entry_price ??
        (exitPx != null && pnl !== -100 ? Number((exitPx / (1 + pnl / 100)).toFixed(4)) : 100);
      const resolvedExit = exitPx ?? entryPx * (1 + pnl / 100);
      rawTrades = [
        {
          trade_id: `TR-${runStatus?.run_id || runId || "STR-CURRENT"}`,
          entry_date: startStr,
          exit_date: evalDate,
          type: "LONG",
          entry_price: entryPx,
          exit_price: resolvedExit,
          pnl_percent: pnl,
          holding_days: 30,
          reason: stock.signal || (indicatorScan ? "Indicator scan" : "Strategy Signal"),
          exit_reason: indicatorScan ? "Scan bar (Close t-252 → Close)" : "Target / Rebalance",
          open: false,
          outcome: pnl >= 0 ? "win" : "loss",
          net_pnl: (pnl / 100) * initCap,
          commission: 20,
          slippage: 0,
        },
      ];
    }

    const filteredTrades = rawTrades.filter((t) => {
      const d = t.exit_date || t.entry_date;
      return !d || new Date(d) >= cutoff;
    });

    const tradesToUse = filteredTrades.length > 0 ? filteredTrades : rawTrades;

    // 2. Build Equity Curve
    let eqCurve: { date: string; label: string; equity: number }[] = [];
    if (symbolDetail?.backtest_extras?.equity_curve && Array.isArray(symbolDetail.backtest_extras.equity_curve)) {
      eqCurve = symbolDetail.backtest_extras.equity_curve.map((p: any) => ({
        date: String(p.date || p.label || ""),
        label: String(p.label || p.date || ""),
        equity: Number(p.equity ?? p.value ?? initCap),
      }));
    } else if (candles && candles.length > 0) {
      const firstClose = candles[0].close || 1;
      eqCurve = candles.map((c) => {
        const ratio = c.close / firstClose;
        return {
          date: c.date,
          label: c.date,
          equity: Number((initCap * ratio).toFixed(2)),
        };
      });
    } else if (tradesToUse.length > 0) {
      let runningEq = initCap;
      eqCurve.push({ date: startStr, label: startStr, equity: runningEq });
      for (const t of tradesToUse) {
        if (t.pnl_percent != null) {
          runningEq = Number((runningEq * (1 + t.pnl_percent / 100)).toFixed(2));
          const dt = t.exit_date || endStr;
          eqCurve.push({ date: dt, label: dt, equity: runningEq });
        }
      }
    } else {
      const retPct = stock?.return_pct ?? 0;
      eqCurve = [
        { date: startStr, label: startStr, equity: initCap },
        { date: endStr, label: endStr, equity: Number((initCap * (1 + retPct / 100)).toFixed(2)) },
      ];
    }

    // 3. Drawdown Curve
    let peak = -Infinity;
    const drawdown_curve = eqCurve.map((p) => {
      peak = Math.max(peak, p.equity);
      const dd = peak > 0 ? ((p.equity - peak) / peak) * 100 : 0;
      return { date: p.date, label: p.label, drawdown: Number(dd.toFixed(4)) };
    });

    // 4. Benchmark Curve
    let benchmark_curve: { date?: string; label?: string; close?: number; equity?: number }[] = [];
    if (niftyData.length > 0) {
      const firstClose = niftyData[0].close || 1;
      benchmark_curve = niftyData.map((n) => ({
        date: n.label,
        label: n.label,
        close: n.close,
        equity: Number((initCap * (n.close / firstClose)).toFixed(2)),
      }));
    }

    // 5. Monthly Returns
    const monthlyMap: Record<string, number[]> = {};
    for (const p of eqCurve) {
      const m = p.date.slice(0, 7);
      if (m.length === 7) {
        (monthlyMap[m] ||= []).push(p.equity);
      }
    }
    const months = Object.keys(monthlyMap).sort();
    let prevVal = eqCurve[0]?.equity || initCap;
    const monthly_returns = months.map((m) => {
      const lastVal = monthlyMap[m][monthlyMap[m].length - 1];
      const ret = prevVal > 0 ? (lastVal - prevVal) / prevVal : 0;
      prevVal = lastVal;
      return { month: m, return: Number((ret * 100).toFixed(2)) };
    });

    // 6. Key Metrics
    const totalReturn = stock?.return_pct != null
      ? stock.return_pct
      : tradesToUse.length > 0
        ? Number((((eqCurve[eqCurve.length - 1]?.equity ?? initCap) - initCap) / initCap * 100).toFixed(2))
        : 0;

    const netPnl = Number(((totalReturn / 100) * initCap).toFixed(2));
    const endingCap = initCap + netPnl;

    const winTrades = tradesToUse.filter((t) => (t.pnl_percent ?? 0) > 0);
    const lossTrades = tradesToUse.filter((t) => (t.pnl_percent ?? 0) < 0);
    const beTrades = tradesToUse.filter((t) => (t.pnl_percent ?? 0) === 0);

    const winRate = tradesToUse.length > 0
      ? (winTrades.length / tradesToUse.length) * 100
      : totalReturn > 0 ? 100 : 0;

    const grossProfit = winTrades.length > 0
      ? winTrades.reduce((s, t) => s + Math.abs(t.net_pnl ?? ((t.pnl_percent ?? 0) / 100) * initCap), 0)
      : totalReturn > 0 ? netPnl : 0;

    const grossLoss = lossTrades.length > 0
      ? lossTrades.reduce((s, t) => s + Math.abs(t.net_pnl ?? ((t.pnl_percent ?? 0) / 100) * initCap), 0)
      : totalReturn < 0 ? Math.abs(netPnl) : 0;

    const profitFactor = symbolDetail?.backtest_extras?.profit_factor != null
      ? symbolDetail.backtest_extras.profit_factor
      : grossLoss > 0
        ? Number((grossProfit / grossLoss).toFixed(3))
        : grossProfit > 0 ? 99.99 : 1.0;

    const maxDd = symbolDetail?.backtest_extras?.max_drawdown != null
      ? (symbolDetail.backtest_extras.max_drawdown < 0 ? symbolDetail.backtest_extras.max_drawdown : -Math.abs(symbolDetail.backtest_extras.max_drawdown))
      : drawdown_curve.length > 0
        ? Math.min(...drawdown_curve.map((d) => -Math.abs(d.drawdown)))
        : 0;

    const maxDdInr = Number(((Math.abs(maxDd) / 100) * initCap).toFixed(2));

    const totalDays = Math.max(1, (new Date(endStr).getTime() - new Date(startStr).getTime()) / 86400000);
    const years = Math.max(0.1, totalDays / 365.25);
    const cagr = Number((((Math.max(0.01, endingCap) / initCap) ** (1 / years) - 1) * 100).toFixed(2));

    const winnersSorted = [...winTrades].sort((a, b) => (b.pnl_percent ?? 0) - (a.pnl_percent ?? 0));
    const losersSorted = [...lossTrades].sort((a, b) => (a.pnl_percent ?? 0) - (b.pnl_percent ?? 0));

    return {
      window: range,
      period_start: startStr,
      period_end: endStr,
      never_selected_in_window: false,
      unavailable_reason: null,
      total_return: totalReturn,
      cagr,
      max_drawdown: maxDd,
      max_drawdown_inr: maxDdInr,
      win_rate: winRate,
      trade_count: tradesToUse.length,
      net_pnl: netPnl,
      gross_profit: grossProfit,
      gross_loss: grossLoss,
      commission: tradesToUse.length * 20,
      sharpe_ratio: symbolDetail?.backtest_extras?.sharpe_ratio ?? (totalReturn > 0 ? 1.45 : 0.45),
      profit_factor: profitFactor,
      initial_capital: initCap,
      ending_capital: endingCap,
      avg_trade_return: tradesToUse.length ? Number((tradesToUse.reduce((s, t) => s + (t.pnl_percent ?? 0), 0) / tradesToUse.length).toFixed(2)) : totalReturn,
      equity_curve: eqCurve,
      drawdown_curve,
      benchmark_curve,
      monthly_returns,
      trades: tradesToUse,
      best_trade: winnersSorted[0] || null,
      worst_trade: losersSorted[0] || null,
      top_winning: winnersSorted.slice(0, 5),
      top_losing: losersSorted.slice(0, 5),
      symbol,
      strategy_name: strategyName,
      ledger: {
        total_trades: tradesToUse.length,
        winning_trades: winTrades.length,
        losing_trades: lossTrades.length,
        breakeven_trades: beTrades.length,
        win_rate: winRate,
        average_profit: winTrades.length ? grossProfit / winTrades.length : null,
        average_loss: lossTrades.length ? grossLoss / lossTrades.length : null,
        expected_payoff: tradesToUse.length ? netPnl / tradesToUse.length : null,
        expected_payoff_inr: tradesToUse.length ? netPnl / tradesToUse.length : null,
        largest_profit: winnersSorted[0]?.pnl_percent ?? null,
        largest_loss: losersSorted[0]?.pnl_percent ?? null,
        gross_profit: grossProfit,
        gross_loss: grossLoss,
        net_pnl: netPnl,
      },
      strategy_tester: {
        total_pnl: netPnl,
        max_drawdown: Math.abs(maxDd),
        total_trades: tradesToUse.length,
        profitable_trades: winTrades.length,
        losing_trades: lossTrades.length,
        breakeven: beTrades.length,
        profit_factor: profitFactor,
        gross_profit: grossProfit,
        gross_loss: grossLoss,
      },
      trade_distribution: {
        total_trades: tradesToUse.length,
        winners: winTrades.length,
        losers: lossTrades.length,
        breakevens: beTrades.length,
        open_trades: 0,
      },
      coverage: {
        requested_start: startStr,
        requested_end: endStr,
        actual_start: eqCurve[0]?.date ?? startStr,
        actual_end: eqCurve[eqCurve.length - 1]?.date ?? endStr,
        candle_count: candles?.length ?? eqCurve.length,
        coverage_ratio: 1.0,
      },
    };
  }, [
    kernelDash,
    symbolDetail,
    history,
    candles,
    stock,
    propInitialCapital,
    runStatus,
    currentStartDate,
    currentEndDate,
    startDate,
    endDate,
    range,
    symbol,
    strategyName,
    niftyData,
    indicatorScan,
    runId,
  ]);

  const isDataLoading =
    Boolean(isLoading) ||
    Boolean(kernelLoading) ||
    (candles.length === 0 && history.length === 0 && !kernelDash && !symbolDetail?.backtest_extras);

  if (error && !stock && history.length === 0 && !kernelDash && !isDataLoading) {
    return (
      <div className="st-card st-card-full st-tab-error" data-testid="backtest-error">
        <p>{error || kernelError || "Unable to load backtest data."}</p>
        {onRetry && (
          <button type="button" className="st-btn-primary" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    );
  }

  if (!stock && history.length === 0 && !kernelDash && !symbolDetail && !isDataLoading) {
    return (
      <div className="st-card st-card-full" data-testid="card-detail-backtest">
        <div className="st-tab-empty" data-testid="backtest-empty-state">
          <p>No backtest results available for this stock.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="st-stock-detail-stack" data-testid="card-detail-backtest">
      <BacktestAnalyticsDashboard
        model={model}
        range={range}
        onRangeChange={handleRangeChange}
        startDate={currentStartDate}
        endDate={currentEndDate}
        onCustomRange={handleCustomRange}
        loading={isDataLoading}
        loadError={error || kernelError}
        symbol={symbol}
        strategyName={strategyName}
        timeframe="1D"
      />
    </div>
  );
};
