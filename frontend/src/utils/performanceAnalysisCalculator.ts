/**
 * Performance Analysis Calculation Engine.
 * Computes Breakdown, Periodical, Benchmarking, Margin Usage, and Growth & Decline
 * metrics and series from backtest trade logs, equity curves, and benchmark curves.
 */

import type { BacktestDashboardModel, DashboardTrade } from "../components/BacktestAnalyticsDashboard";

export interface BreakdownMetrics {
  grossProfitInr: number;
  grossProfitPct: number;
  grossLossInr: number;
  grossLossPct: number;
  profitFactor: number | null;
  profitFactorInfinite: boolean;
  commissionLoadPct: number;
  netPnlInr: number;
}

export interface SignalBreakdownRow {
  name: string;
  grossProfit: number;
  grossLoss: number;
  netPnl: number;
  tradeCount: number;
  winCount: number;
  lossCount: number;
}

export interface SideBreakdownRow {
  side: string;
  grossProfit: number;
  grossLoss: number;
  netPnl: number;
  tradeCount: number;
  winCount: number;
  lossCount: number;
}

export interface PeriodicalMetrics {
  cagr: number | null;
  totalReturn: number | null;
  sharpeRatio: number | null;
  sortinoRatio: number | null;
}

export interface PeriodicalBar {
  periodKey: string;
  label: string;
  realizedProfit: number;
  realizedLoss: number;
  favorableExcursion: number;
  adverseExcursion: number;
  netPnl: number;
  date: string;
}

export interface BenchmarkingMetrics {
  strategyReturn: number | null;
  buyAndHoldReturn: number | null;
  outperformance: number | null;
  correlation: number | null;
}

export interface BenchmarkBar {
  periodKey: string;
  label: string;
  strategyPnl: number;
  benchmarkPnl: number;
  date: string;
}

export interface MarginUsageMetrics {
  marginEfficiency: number | null;
  avgMarginUsed: number | null;
  marginCalls: number;
  totalLiquidatedVolume: number;
}

export interface MarginPoint {
  date: string;
  label: string;
  utilizationPct: number;
}

export interface GrowthDeclineMetrics {
  avgRunUpDurationDays: number | null;
  avgDrawdownDurationDays: number | null;
  maxDrawdownInr: number | null;
  maxDrawdownPct: number | null;
  maxDrawdownCapPct: number | null;
}

export interface AlternatingPeriodBar {
  id: string;
  label: string;
  type: "run_up" | "drawdown" | "current_run_up";
  valuePct: number;
  durationDays: number;
  startDate: string;
  endDate: string;
}

export interface GrowthDeclineComparison {
  runUp: {
    maximumPct: number;
    averagePct: number;
    currentPct: number;
  };
  drawdown: {
    maximumPct: number;
    averagePct: number;
  };
}

export interface PerformanceAnalysisModel {
  breakdown: {
    metrics: BreakdownMetrics;
    bySignals: SignalBreakdownRow[];
    bySide: SideBreakdownRow[];
  };
  periodical: {
    metrics: PeriodicalMetrics;
    weekly: PeriodicalBar[];
    quarterly: PeriodicalBar[];
    yearly: PeriodicalBar[];
  };
  benchmarking: {
    metrics: BenchmarkingMetrics;
    weekly: BenchmarkBar[];
    quarterly: BenchmarkBar[];
    yearly: BenchmarkBar[];
  };
  marginUsage: {
    metrics: MarginUsageMetrics;
    series: MarginPoint[];
  };
  growthDecline: {
    metrics: GrowthDeclineMetrics;
    alternating: AlternatingPeriodBar[];
    comparison: GrowthDeclineComparison;
  };
}

export interface PerformanceCalculatorOptions {
  model: BacktestDashboardModel | null;
  initialCapital?: number;
}

/** Helper: Parse ISO date string to Date safely */
function parseDate(d?: string | null): Date | null {
  if (!d) return null;
  const dt = new Date(d);
  return Number.isNaN(dt.getTime()) ? null : dt;
}

/** Helper: Format week identifier e.g. "2024-W05" and display label "Feb 1" */
function getWeekKey(dateStr: string): { key: string; label: string } {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return { key: dateStr, label: dateStr };
  // Thursday in current week decides the year
  const target = new Date(d.valueOf());
  const dayNr = (d.getDay() + 6) % 7;
  target.setDate(target.getDate() - dayNr + 3);
  const firstThursday = target.valueOf();
  target.setMonth(0, 1);
  if (target.getDay() !== 4) {
    target.setMonth(0, 1 + ((4 - target.getDay() + 7) % 7));
  }
  const weekNum = 1 + Math.ceil((firstThursday - target.valueOf()) / 604800000);
  const year = d.getFullYear();
  const monthName = d.toLocaleString("default", { month: "short" });
  const day = d.getDate();
  return {
    key: `${year}-W${String(weekNum).padStart(2, "0")}`,
    label: `${monthName} ${day}`,
  };
}

/** Helper: Format quarter identifier e.g. "2024-Q1" and display label "Q1 '24" */
function getQuarterKey(dateStr: string): { key: string; label: string } {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return { key: dateStr, label: dateStr };
  const q = Math.floor(d.getMonth() / 3) + 1;
  const yr = String(d.getFullYear()).slice(2);
  return {
    key: `${d.getFullYear()}-Q${q}`,
    label: `Q${q} '${yr}`,
  };
}

/** Helper: Format year identifier e.g. "2024" */
function getYearKey(dateStr: string): { key: string; label: string } {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return { key: dateStr, label: dateStr };
  return {
    key: `${d.getFullYear()}`,
    label: `${d.getFullYear()}`,
  };
}

/** Helper: Pearson correlation between two numeric arrays */
export function calculateCorrelation(x: number[], y: number[]): number | null {
  if (x.length !== y.length || x.length < 3) return null;
  const n = x.length;
  const meanX = x.reduce((a, b) => a + b, 0) / n;
  const meanY = y.reduce((a, b) => a + b, 0) / n;

  let num = 0;
  let denX = 0;
  let denY = 0;

  for (let i = 0; i < n; i++) {
    const dx = x[i] - meanX;
    const dy = y[i] - meanY;
    num += dx * dy;
    denX += dx * dx;
    denY += dy * dy;
  }

  const den = Math.sqrt(denX * denY);
  if (den === 0 || !Number.isFinite(den)) return null;
  const r = num / den;
  return Number.isFinite(r) ? Number(r.toFixed(3)) : null;
}

/**
 * 1. Calculate Breakdown Metrics & Groupings
 */
export function calculateBreakdown(
  trades: DashboardTrade[],
  initialCapital: number,
  ledger?: Record<string, any> | null,
  strategyTester?: Record<string, any> | null,
  commissionVal?: number | null,
): {
  metrics: BreakdownMetrics;
  bySignals: SignalBreakdownRow[];
  bySide: SideBreakdownRow[];
} {
  const closed = trades.filter((t) => !t.open);

  let grossProfitInr = 0;
  let grossLossInr = 0;
  let netPnlInr = 0;
  let totalCommissionInr = commissionVal ?? 0;

  const signalMap = new Map<string, SignalBreakdownRow>();
  const sideMap = new Map<string, SideBreakdownRow>();

  for (const tr of closed) {
    const pnlInr =
      tr.net_pnl != null && Number.isFinite(Number(tr.net_pnl))
        ? Number(tr.net_pnl)
        : tr.pnl_percent != null
          ? (Number(tr.pnl_percent) / 100) * initialCapital
          : 0;

    if (pnlInr > 0) grossProfitInr += pnlInr;
    else if (pnlInr < 0) grossLossInr += Math.abs(pnlInr);
    netPnlInr += pnlInr;

    if (tr.commission) totalCommissionInr += Number(tr.commission);

    // Group By Signals
    const signalName = tr.reason || tr.exit_reason || "All signals";
    const sigKey = signalName.trim() || "Default Signal";
    const sigRow = signalMap.get(sigKey) || {
      name: sigKey,
      grossProfit: 0,
      grossLoss: 0,
      netPnl: 0,
      tradeCount: 0,
      winCount: 0,
      lossCount: 0,
    };
    sigRow.tradeCount++;
    sigRow.netPnl += pnlInr;
    if (pnlInr > 0) {
      sigRow.grossProfit += pnlInr;
      sigRow.winCount++;
    } else if (pnlInr < 0) {
      sigRow.grossLoss += Math.abs(pnlInr);
      sigRow.lossCount++;
    }
    signalMap.set(sigKey, sigRow);

    // Group By Side (Long vs Short)
    const side = (tr.type || "LONG").toUpperCase();
    const sideKey = side === "SHORT" ? "Short" : "Long";
    const sideRow = sideMap.get(sideKey) || {
      side: sideKey,
      grossProfit: 0,
      grossLoss: 0,
      netPnl: 0,
      tradeCount: 0,
      winCount: 0,
      lossCount: 0,
    };
    sideRow.tradeCount++;
    sideRow.netPnl += pnlInr;
    if (pnlInr > 0) {
      sideRow.grossProfit += pnlInr;
      sideRow.winCount++;
    } else if (pnlInr < 0) {
      sideRow.grossLoss += Math.abs(pnlInr);
      sideRow.lossCount++;
    }
    sideMap.set(sideKey, sideRow);
  }

  // Override with ledger / strategy_tester if available for exact engine match
  if (strategyTester?.gross_profit != null) grossProfitInr = Number(strategyTester.gross_profit);
  else if (ledger?.gross_profit != null) grossProfitInr = Number(ledger.gross_profit);

  if (strategyTester?.gross_loss != null) grossLossInr = Math.abs(Number(strategyTester.gross_loss));
  else if (ledger?.gross_loss != null) grossLossInr = Math.abs(Number(ledger.gross_loss));

  if (strategyTester?.total_pnl != null) netPnlInr = Number(strategyTester.total_pnl);
  else if (ledger?.net_pnl != null) netPnlInr = Number(ledger.net_pnl);

  if (strategyTester?.commission != null) totalCommissionInr = Number(strategyTester.commission);
  else if (ledger?.commission != null) totalCommissionInr = Number(ledger.commission);

  const grossProfitPct = initialCapital > 0 ? (grossProfitInr / initialCapital) * 100 : 0;
  const grossLossPct = initialCapital > 0 ? (grossLossInr / initialCapital) * 100 : 0;

  let profitFactor: number | null = null;
  let profitFactorInfinite = false;

  if (strategyTester?.profit_factor != null) {
    profitFactor = Number(strategyTester.profit_factor);
  } else if (ledger?.profit_factor != null) {
    profitFactor = Number(ledger.profit_factor);
    profitFactorInfinite = Boolean(ledger?.profit_factor_infinite);
  } else if (grossLossInr > 0) {
    profitFactor = Number((grossProfitInr / grossLossInr).toFixed(3));
  } else if (grossProfitInr > 0 && grossLossInr === 0) {
    profitFactorInfinite = true;
  }

  const commissionLoadPct = initialCapital > 0 ? (totalCommissionInr / initialCapital) * 100 : 0;

  // Signal rows: build "All signals" row plus individual signals
  const allSignalsRow: SignalBreakdownRow = {
    name: "All signals",
    grossProfit: grossProfitInr,
    grossLoss: grossLossInr,
    netPnl: netPnlInr,
    tradeCount: closed.length,
    winCount: closed.filter((t) => (t.pnl_percent ?? 0) > 0).length,
    lossCount: closed.filter((t) => (t.pnl_percent ?? 0) < 0).length,
  };

  const bySignals: SignalBreakdownRow[] = [allSignalsRow];
  signalMap.forEach((row) => {
    if (signalMap.size > 1 || row.name !== "All signals") {
      bySignals.push(row);
    }
  });

  // If only 1 signal exists, ensure standard rows exist
  if (bySignals.length === 1 && closed.length > 0) {
    bySignals.push({
      name: "Primary Strategy",
      grossProfit: grossProfitInr,
      grossLoss: grossLossInr,
      netPnl: netPnlInr,
      tradeCount: closed.length,
      winCount: allSignalsRow.winCount,
      lossCount: allSignalsRow.lossCount,
    });
  }

  // Side rows: ensure Long and Short exist
  const bySide: SideBreakdownRow[] = [];
  const longRow = sideMap.get("Long") || {
    side: "Long",
    grossProfit: 0,
    grossLoss: 0,
    netPnl: 0,
    tradeCount: 0,
    winCount: 0,
    lossCount: 0,
  };
  const shortRow = sideMap.get("Short") || {
    side: "Short",
    grossProfit: 0,
    grossLoss: 0,
    netPnl: 0,
    tradeCount: 0,
    winCount: 0,
    lossCount: 0,
  };
  bySide.push(longRow, shortRow);

  return {
    metrics: {
      grossProfitInr,
      grossProfitPct,
      grossLossInr,
      grossLossPct,
      profitFactor,
      profitFactorInfinite,
      commissionLoadPct,
      netPnlInr,
    },
    bySignals,
    bySide,
  };
}

/**
 * 2. Calculate Periodical Metrics & Series (Weekly, Quarterly, Yearly)
 */
export function calculatePeriodical(
  equityCurve: { date?: string; label?: string; equity: number }[],
  trades: DashboardTrade[],
  initialCapital: number,
  totalReturnPct?: number | null,
  cagrPct?: number | null,
  sharpeVal?: number | null,
): {
  metrics: PeriodicalMetrics;
  weekly: PeriodicalBar[];
  quarterly: PeriodicalBar[];
  yearly: PeriodicalBar[];
} {
  const closed = trades.filter((t) => !t.open);

  // Derive Periodical Bars
  function aggregatePeriod(keyFn: (d: string) => { key: string; label: string }): PeriodicalBar[] {
    const map = new Map<string, PeriodicalBar>();

    for (const tr of closed) {
      const d = tr.exit_date || tr.entry_date;
      if (!d) continue;
      const { key, label } = keyFn(d);
      const pnl =
        tr.net_pnl != null && Number.isFinite(Number(tr.net_pnl))
          ? Number(tr.net_pnl)
          : tr.pnl_percent != null
            ? (Number(tr.pnl_percent) / 100) * initialCapital
            : 0;

      const bar = map.get(key) || {
        periodKey: key,
        label,
        realizedProfit: 0,
        realizedLoss: 0,
        favorableExcursion: 0,
        adverseExcursion: 0,
        netPnl: 0,
        date: d,
      };

      if (pnl > 0) {
        bar.realizedProfit += pnl;
        bar.favorableExcursion += pnl * 0.2; // Favorable excursion estimation
      } else if (pnl < 0) {
        bar.realizedLoss += Math.abs(pnl);
        bar.adverseExcursion += Math.abs(pnl) * 0.2; // Adverse excursion estimation
      }
      bar.netPnl += pnl;
      map.set(key, bar);
    }

    return Array.from(map.values()).sort((a, b) => a.periodKey.localeCompare(b.periodKey));
  }

  const weekly = aggregatePeriod(getWeekKey);
  const quarterly = aggregatePeriod(getQuarterKey);
  const yearly = aggregatePeriod(getYearKey);

  // Return Metrics
  const startEq = equityCurve[0]?.equity ?? initialCapital;
  const endEq = equityCurve[equityCurve.length - 1]?.equity ?? (startEq + closed.reduce((s, t) => s + (t.net_pnl ?? 0), 0));
  const calcTotalReturn = startEq > 0 ? ((endEq - startEq) / startEq) * 100 : 0;
  const finalTotalReturn = totalReturnPct != null ? totalReturnPct : calcTotalReturn;

  // Calculate CAGR
  let finalCagr = cagrPct ?? null;
  if (finalCagr == null && equityCurve.length > 1) {
    const d0 = parseDate(equityCurve[0].date || equityCurve[0].label);
    const d1 = parseDate(equityCurve[equityCurve.length - 1].date || equityCurve[equityCurve.length - 1].label);
    if (d0 && d1) {
      const years = Math.max((d1.getTime() - d0.getTime()) / (365.25 * 24 * 3600 * 1000), 0.1);
      if (startEq > 0 && endEq > 0) {
        finalCagr = (Math.pow(endEq / startEq, 1 / years) - 1) * 100;
      }
    }
  }

  // Calculate Sharpe & Sortino
  const returns: number[] = [];
  for (let i = 1; i < equityCurve.length; i++) {
    const prev = equityCurve[i - 1].equity;
    const curr = equityCurve[i].equity;
    if (prev > 0) returns.push((curr - prev) / prev);
  }

  let finalSharpe = sharpeVal ?? null;
  let finalSortino: number | null = null;

  if (returns.length >= 2) {
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
    const variance = returns.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / returns.length;
    const std = Math.sqrt(variance);

    if (finalSharpe == null && std > 0) {
      finalSharpe = Number(((mean / std) * Math.sqrt(252)).toFixed(3));
    }

    const downsideReturns = returns.filter((r) => r < 0);
    if (downsideReturns.length > 0) {
      const downsideVariance =
        downsideReturns.reduce((a, b) => a + Math.pow(b, 2), 0) / returns.length;
      const downsideStd = Math.sqrt(downsideVariance);
      if (downsideStd > 0) {
        finalSortino = Number(((mean / downsideStd) * Math.sqrt(252)).toFixed(3));
      }
    }
  }

  return {
    metrics: {
      cagr: finalCagr != null ? Number(finalCagr.toFixed(2)) : null,
      totalReturn: finalTotalReturn != null ? Number(finalTotalReturn.toFixed(2)) : null,
      sharpeRatio: finalSharpe != null ? Number(finalSharpe.toFixed(3)) : null,
      sortinoRatio: finalSortino != null ? Number(finalSortino.toFixed(3)) : null,
    },
    weekly,
    quarterly,
    yearly,
  };
}

/**
 * 3. Calculate Benchmarking Metrics & Series
 */
export function calculateBenchmarking(
  equityCurve: { date?: string; label?: string; equity: number }[],
  benchmarkCurve: { date?: string; label?: string; close?: number; equity?: number }[],
  trades: DashboardTrade[],
  initialCapital: number,
  strategyReturnPct?: number | null,
): {
  metrics: BenchmarkingMetrics;
  weekly: BenchmarkBar[];
  quarterly: BenchmarkBar[];
  yearly: BenchmarkBar[];
} {
  const startEq = equityCurve[0]?.equity ?? initialCapital;
  const endEq = equityCurve[equityCurve.length - 1]?.equity ?? startEq;
  const stratRet = strategyReturnPct != null ? strategyReturnPct : startEq > 0 ? ((endEq - startEq) / startEq) * 100 : 0;

  let buyAndHoldReturn: number | null = null;
  if (benchmarkCurve.length >= 2) {
    const firstBench = benchmarkCurve[0]?.close ?? benchmarkCurve[0]?.equity;
    const lastBench = benchmarkCurve[benchmarkCurve.length - 1]?.close ?? benchmarkCurve[benchmarkCurve.length - 1]?.equity;
    if (firstBench && lastBench && firstBench > 0) {
      buyAndHoldReturn = ((Number(lastBench) - Number(firstBench)) / Number(firstBench)) * 100;
    }
  }

  const outperformance =
    buyAndHoldReturn != null && stratRet != null ? stratRet - buyAndHoldReturn : null;

  // Correlation between strategy and benchmark
  const stratMap = new Map<string, number>();
  for (const eq of equityCurve) {
    if (eq.date || eq.label) stratMap.set(eq.date || eq.label!, eq.equity);
  }

  const alignedStrat: number[] = [];
  const alignedBench: number[] = [];

  for (let i = 1; i < benchmarkCurve.length; i++) {
    const d = benchmarkCurve[i].date || benchmarkCurve[i].label || "";
    const bCurr = Number(benchmarkCurve[i].close ?? benchmarkCurve[i].equity);
    const bPrev = Number(benchmarkCurve[i - 1].close ?? benchmarkCurve[i - 1].equity);
    const sCurr = stratMap.get(d);
    const dPrev = benchmarkCurve[i - 1].date || benchmarkCurve[i - 1].label || "";
    const sPrev = stratMap.get(dPrev);

    if (bCurr && bPrev && sCurr && sPrev && bPrev > 0 && sPrev > 0) {
      alignedBench.push((bCurr - bPrev) / bPrev);
      alignedStrat.push((sCurr - sPrev) / sPrev);
    }
  }

  const correlation = calculateCorrelation(alignedStrat, alignedBench);

  // Build comparison bars for Weekly, Quarterly, Yearly
  function buildBenchmarkPeriodBars(keyFn: (d: string) => { key: string; label: string }): BenchmarkBar[] {
    const map = new Map<string, BenchmarkBar>();

    // Strategy contribution from trades
    for (const tr of trades.filter((t) => !t.open)) {
      const d = tr.exit_date || tr.entry_date;
      if (!d) continue;
      const { key, label } = keyFn(d);
      const pnl =
        tr.net_pnl != null && Number.isFinite(Number(tr.net_pnl))
          ? Number(tr.net_pnl)
          : tr.pnl_percent != null
            ? (Number(tr.pnl_percent) / 100) * initialCapital
            : 0;

      const bar = map.get(key) || {
        periodKey: key,
        label,
        strategyPnl: 0,
        benchmarkPnl: 0,
        date: d,
      };
      bar.strategyPnl += pnl;
      map.set(key, bar);
    }

    // Benchmark contribution from benchmark curve
    if (benchmarkCurve.length >= 2) {
      const firstB = Number(benchmarkCurve[0].close ?? benchmarkCurve[0].equity ?? 1);
      for (let i = 1; i < benchmarkCurve.length; i++) {
        const d = benchmarkCurve[i].date || benchmarkCurve[i].label || "";
        const { key, label } = keyFn(d);
        const bCurr = Number(benchmarkCurve[i].close ?? benchmarkCurve[i].equity);
        const bPrev = Number(benchmarkCurve[i - 1].close ?? benchmarkCurve[i - 1].equity);
        if (!bCurr || !bPrev) continue;
        const bPnl = ((bCurr - bPrev) / firstB) * initialCapital;

        const bar = map.get(key) || {
          periodKey: key,
          label,
          strategyPnl: 0,
          benchmarkPnl: 0,
          date: d,
        };
        bar.benchmarkPnl += bPnl;
        map.set(key, bar);
      }
    }

    return Array.from(map.values()).sort((a, b) => a.periodKey.localeCompare(b.periodKey));
  }

  const weekly = buildBenchmarkPeriodBars(getWeekKey);
  const quarterly = buildBenchmarkPeriodBars(getQuarterKey);
  const yearly = buildBenchmarkPeriodBars(getYearKey);

  return {
    metrics: {
      strategyReturn: stratRet != null ? Number(stratRet.toFixed(2)) : null,
      buyAndHoldReturn: buyAndHoldReturn != null ? Number(buyAndHoldReturn.toFixed(2)) : null,
      outperformance: outperformance != null ? Number(outperformance.toFixed(2)) : null,
      correlation,
    },
    weekly,
    quarterly,
    yearly,
  };
}

/**
 * 4. Calculate Margin Usage Metrics & Series
 */
export function calculateMarginUsage(
  equityCurve: { date?: string; label?: string; equity: number }[],
  trades: DashboardTrade[],
  initialCapital: number,
): {
  metrics: MarginUsageMetrics;
  series: MarginPoint[];
} {
  const closed = trades.filter((t) => !t.open);
  const netPnl = closed.reduce((acc, t) => acc + (t.net_pnl ?? 0), 0);

  // Derive margin points based on open positions and capital allocation
  const series: MarginPoint[] = equityCurve.map((eq) => {
    const d = eq.date || eq.label || "";
    // Typical positional allocation utilization percentage
    const active = closed.filter((t) => (t.entry_date || "") <= d && (t.exit_date || "") >= d);
    const usedMargin = active.reduce((s, t) => s + (t.entry_price || 0), 0);
    const utilPct = eq.equity > 0 ? Math.min(100, (usedMargin / eq.equity) * 100) : 0;

    return {
      date: d,
      label: d,
      utilizationPct: Number(utilPct.toFixed(2)),
    };
  });

  const avgMarginUsed =
    closed.length > 0
      ? closed.reduce((s, t) => s + (t.entry_price || 0), 0) / closed.length
      : 0;

  const marginEfficiency = avgMarginUsed > 0 ? Number((netPnl / avgMarginUsed).toFixed(2)) : null;

  return {
    metrics: {
      marginEfficiency,
      avgMarginUsed: Number(avgMarginUsed.toFixed(2)),
      marginCalls: 0,
      totalLiquidatedVolume: 0,
    },
    series,
  };
}

/**
 * 5. Calculate Growth and Decline Analysis
 */
export function calculateGrowthDecline(
  equityCurve: { date?: string; label?: string; equity: number }[],
  initialCapital: number,
  maxDrawdownInrVal?: number | null,
  maxDrawdownPctVal?: number | null,
): {
  metrics: GrowthDeclineMetrics;
  alternating: AlternatingPeriodBar[];
  comparison: GrowthDeclineComparison;
} {
  if (equityCurve.length < 2) {
    return {
      metrics: {
        avgRunUpDurationDays: null,
        avgDrawdownDurationDays: null,
        maxDrawdownInr: maxDrawdownInrVal ?? null,
        maxDrawdownPct: maxDrawdownPctVal ?? null,
        maxDrawdownCapPct: null,
      },
      alternating: [],
      comparison: {
        runUp: { maximumPct: 0, averagePct: 0, currentPct: 0 },
        drawdown: { maximumPct: 0, averagePct: 0 },
      },
    };
  }

  let peak = equityCurve[0].equity;
  let trough = equityCurve[0].equity;
  let peakDate = equityCurve[0].date || equityCurve[0].label || "";
  let troughDate = peakDate;

  let maxDdInr = 0;
  let maxDdPct = 0;

  const runUps: { pct: number; duration: number }[] = [];
  const drawdowns: { pct: number; duration: number }[] = [];
  const alternating: AlternatingPeriodBar[] = [];

  let inDrawdown = false;
  let periodStart = peakDate;
  let periodStartVal = peak;

  for (let i = 0; i < equityCurve.length; i++) {
    const pt = equityCurve[i];
    const eq = pt.equity;
    const curDate = pt.date || pt.label || "";

    if (eq > peak) {
      if (inDrawdown) {
        // Drawdown ended
        const ddPct = peak > 0 ? ((peak - trough) / peak) * 100 : 0;
        const d0 = parseDate(periodStart);
        const d1 = parseDate(curDate);
        const days = d0 && d1 ? Math.max(1, Math.round((d1.getTime() - d0.getTime()) / (24 * 3600 * 1000))) : 1;
        drawdowns.push({ pct: ddPct, duration: days });
        alternating.push({
          id: `dd-${alternating.length}`,
          label: `DD ${alternating.length + 1}`,
          type: "drawdown",
          valuePct: Number(ddPct.toFixed(2)),
          durationDays: days,
          startDate: periodStart,
          endDate: curDate,
        });

        // Start new run-up
        inDrawdown = false;
        periodStart = troughDate;
        periodStartVal = trough;
      }
      peak = eq;
      peakDate = curDate;
      trough = eq;
      troughDate = curDate;
    } else {
      const curDd = peak - eq;
      const curDdPct = peak > 0 ? (curDd / peak) * 100 : 0;
      maxDdInr = Math.max(maxDdInr, curDd);
      maxDdPct = Math.max(maxDdPct, curDdPct);

      if (!inDrawdown && curDdPct > 0.001) {
        // Run-up ended
        const ruPct = periodStartVal > 0 ? ((peak - periodStartVal) / periodStartVal) * 100 : 0;
        const d0 = parseDate(periodStart);
        const d1 = parseDate(peakDate);
        const days = d0 && d1 ? Math.max(1, Math.round((d1.getTime() - d0.getTime()) / (24 * 3600 * 1000))) : 1;
        runUps.push({ pct: ruPct, duration: days });
        alternating.push({
          id: `ru-${alternating.length}`,
          label: `RU ${alternating.length + 1}`,
          type: "run_up",
          valuePct: Number(ruPct.toFixed(2)),
          durationDays: days,
          startDate: periodStart,
          endDate: peakDate,
        });

        inDrawdown = true;
        periodStart = peakDate;
        periodStartVal = peak;
      }

      if (eq < trough) {
        trough = eq;
        troughDate = curDate;
      }
    }
  }

  // Add final active period as current run-up or current drawdown
  const lastDate = equityCurve[equityCurve.length - 1].date || equityCurve[equityCurve.length - 1].label || "";
  const lastEq = equityCurve[equityCurve.length - 1].equity;
  const d0 = parseDate(periodStart);
  const d1 = parseDate(lastDate);
  const finalDays = d0 && d1 ? Math.max(1, Math.round((d1.getTime() - d0.getTime()) / (24 * 3600 * 1000))) : 1;

  if (inDrawdown) {
    const finalDdPct = peak > 0 ? ((peak - lastEq) / peak) * 100 : 0;
    drawdowns.push({ pct: finalDdPct, duration: finalDays });
    alternating.push({
      id: `dd-${alternating.length}`,
      label: `Current DD`,
      type: "drawdown",
      valuePct: Number(finalDdPct.toFixed(2)),
      durationDays: finalDays,
      startDate: periodStart,
      endDate: lastDate,
    });
  } else {
    const finalRuPct = periodStartVal > 0 ? ((lastEq - periodStartVal) / periodStartVal) * 100 : 0;
    runUps.push({ pct: finalRuPct, duration: finalDays });
    alternating.push({
      id: `cur-ru-${alternating.length}`,
      label: `Current RU`,
      type: "current_run_up",
      valuePct: Number(finalRuPct.toFixed(2)),
      durationDays: finalDays,
      startDate: periodStart,
      endDate: lastDate,
    });
  }

  const avgRunUpDays =
    runUps.length > 0
      ? Math.round(runUps.reduce((s, r) => s + r.duration, 0) / runUps.length)
      : null;
  const avgDrawdownDays =
    drawdowns.length > 0
      ? Math.round(drawdowns.reduce((s, r) => s + r.duration, 0) / drawdowns.length)
      : null;

  const maxRunUpPct = runUps.length > 0 ? Math.max(...runUps.map((r) => r.pct)) : 0;
  const avgRunUpPct = runUps.length > 0 ? runUps.reduce((s, r) => s + r.pct, 0) / runUps.length : 0;
  const curRunUpPct = runUps.length > 0 ? runUps[runUps.length - 1].pct : 0;

  const maxDrawdownPctCalc = drawdowns.length > 0 ? Math.max(...drawdowns.map((d) => d.pct)) : maxDdPct;
  const avgDrawdownPct =
    drawdowns.length > 0 ? drawdowns.reduce((s, d) => s + d.pct, 0) / drawdowns.length : 0;

  const finalMaxDdInr = maxDrawdownInrVal != null ? Math.abs(maxDrawdownInrVal) : maxDdInr;
  const finalMaxDdPct = maxDrawdownPctVal != null ? Math.abs(maxDrawdownPctVal) : maxDrawdownPctCalc;
  const maxDdCapPct = initialCapital > 0 ? (finalMaxDdInr / initialCapital) * 100 : finalMaxDdPct;

  return {
    metrics: {
      avgRunUpDurationDays: avgRunUpDays,
      avgDrawdownDurationDays: avgDrawdownDays,
      maxDrawdownInr: Number(finalMaxDdInr.toFixed(2)),
      maxDrawdownPct: Number(finalMaxDdPct.toFixed(2)),
      maxDrawdownCapPct: Number(maxDdCapPct.toFixed(2)),
    },
    alternating,
    comparison: {
      runUp: {
        maximumPct: Number(maxRunUpPct.toFixed(2)),
        averagePct: Number(avgRunUpPct.toFixed(2)),
        currentPct: Number(curRunUpPct.toFixed(2)),
      },
      drawdown: {
        maximumPct: Number(maxDrawdownPctCalc.toFixed(2)),
        averagePct: Number(avgDrawdownPct.toFixed(2)),
      },
    },
  };
}

/**
 * Master Performance Analysis calculation entry point.
 */
export function computePerformanceAnalysis(options: PerformanceCalculatorOptions): PerformanceAnalysisModel {
  const { model, initialCapital = 100000 } = options;

  const trades = model?.trades || [];
  const equityCurve = model?.equity_curve || [];
  const benchmarkCurve = model?.benchmark_curve || [];
  const ledger = model?.ledger || null;
  const strategyTester = model?.strategy_tester || null;

  const breakdown = calculateBreakdown(
    trades,
    initialCapital,
    ledger,
    strategyTester,
    model?.commission,
  );

  const periodical = calculatePeriodical(
    equityCurve,
    trades,
    initialCapital,
    model?.total_return,
    model?.cagr,
    model?.sharpe_ratio,
  );

  const benchmarking = calculateBenchmarking(
    equityCurve,
    benchmarkCurve,
    trades,
    initialCapital,
    model?.total_return,
  );

  const marginUsage = calculateMarginUsage(equityCurve, trades, initialCapital);

  const growthDecline = calculateGrowthDecline(
    equityCurve,
    initialCapital,
    model?.max_drawdown_inr,
    model?.max_drawdown,
  );

  return {
    breakdown,
    periodical,
    benchmarking,
    marginUsage,
    growthDecline,
  };
}
