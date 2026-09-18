/**
 * Pure calculation and transformation utility for TradingView-style Trades Analysis.
 * Computes distribution metrics, return histogram bins, trade breakdown,
 * streaks, and comprehensive trade analysis details from closed trade records.
 */

import type { DashboardTrade } from "../components/BacktestAnalyticsDashboard";

export interface TradeDistributionStats {
  totalTrades: number;
  winCount: number;
  winPct: number;
  lossCount: number;
  lossPct: number;
  breakEvenCount: number;
  breakEvenPct: number;
}

export interface HistogramBin {
  label: string;
  min: number;
  max: number;
  count: number;
  isPositive: boolean;
}

export interface ReturnsDistributionStats {
  bins: HistogramBin[];
  avgWinPct: number | null;
  avgLossPct: number | null;
  minReturn: number;
  maxReturn: number;
  avgWinBinLabel: string | null;
  avgLossBinLabel: string | null;
}

export interface StreaksStats {
  currentWinStreak: number;
  maxWinStreak: number;
  currentLossStreak: number;
  maxLossStreak: number;
  currentBreakevenStreak: number;
  maxBreakevenStreak: number;
  avgWinStreak: number;
  avgLossStreak: number;
  winStreakCount: number;
  lossStreakCount: number;
  maxConsecutiveProfitInr: number | null;
  maxConsecutiveLossInr: number | null;
  maxConsecutiveProfitPct: number | null;
  maxConsecutiveLossPct: number | null;
}

export interface TopLevelMetrics {
  expectedPayoffInr: number | null;
  expectedPayoffPct: number | null;
  outliersPnlInr: number | null;
  outliersPnlPct: number | null;
  outlierTradesCount: number;
  largestProfitInr: number | null;
  largestProfitPct: number | null;
  largestLossInr: number | null;
  largestLossPct: number | null;
}

export interface TradeAnalysisDetails {
  totalTrades: number;
  winCount: number;
  lossCount: number;
  breakEvenCount: number;
  winRate: number | null;
  lossRate: number | null;
  breakEvenRate: number | null;
  grossProfitInr: number | null;
  grossProfitPct: number | null;
  grossLossInr: number | null;
  grossLossPct: number | null;
  netProfitInr: number | null;
  netProfitPct: number | null;
  profitFactor: number | null;
  profitFactorInfinite: boolean;
  expectedPayoffInr: number | null;
  expectedPayoffPct: number | null;
  avgTradeInr: number | null;
  avgTradePct: number | null;
  avgWinInr: number | null;
  avgWinPct: number | null;
  avgLossInr: number | null;
  avgLossPct: number | null;
  winLossRatio: number | null;
  largestProfitInr: number | null;
  largestProfitPct: number | null;
  largestLossInr: number | null;
  largestLossPct: number | null;
  outlierPnlInr: number | null;
  outlierPnlPct: number | null;
  outlierTradesCount: number;
  avgHoldingDays: number | null;
  avgWinHoldingDays: number | null;
  avgLossHoldingDays: number | null;
  medianHoldingDays: number | null;
  commissionInr: number | null;
}

export interface TradesAnalysisModel {
  topMetrics: TopLevelMetrics;
  returnsDistribution: ReturnsDistributionStats;
  tradesDistribution: TradeDistributionStats;
  streaks: StreaksStats;
  details: TradeAnalysisDetails;
}

export interface CalculatorOptions {
  trades?: DashboardTrade[];
  ledger?: Record<string, any> | null;
  strategyTester?: Record<string, any> | null;
  initialCapital?: number | null;
  totalReturn?: number | null;
}

/** Helper: Calculate median of numbers */
function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Helper: Classify trade outcome */
export function classifyTradeOutcome(t: DashboardTrade): "winner" | "loser" | "breakeven" {
  if (t.outcome === "winner" || t.outcome === "WINNER") return "winner";
  if (t.outcome === "loser" || t.outcome === "LOSER") return "loser";
  if (t.outcome === "breakeven" || t.outcome === "BREAKEVEN") return "breakeven";

  const pnlPct = t.pnl_percent != null ? Number(t.pnl_percent) : null;
  const netPnl = t.net_pnl != null ? Number(t.net_pnl) : null;

  if (netPnl != null) {
    if (netPnl > 0.0001) return "winner";
    if (netPnl < -0.0001) return "loser";
    return "breakeven";
  }

  if (pnlPct != null) {
    if (pnlPct > 0.0001) return "winner";
    if (pnlPct < -0.0001) return "loser";
    return "breakeven";
  }

  if (t.entry_price != null && t.exit_price != null) {
    const diff = Number(t.exit_price) - Number(t.entry_price);
    if (diff > 0.0001) return "winner";
    if (diff < -0.0001) return "loser";
    return "breakeven";
  }

  return "breakeven";
}

/** Helper: Get trade PnL in INR */
function getTradeNetPnl(t: DashboardTrade, initialCapital: number): number | null {
  if (t.net_pnl != null && Number.isFinite(Number(t.net_pnl))) {
    return Number(t.net_pnl);
  }
  if (t.pnl_percent != null && Number.isFinite(Number(t.pnl_percent))) {
    return (Number(t.pnl_percent) / 100) * initialCapital;
  }
  if (t.entry_price != null && t.exit_price != null) {
    return Number(t.exit_price) - Number(t.entry_price);
  }
  return null;
}

/**
 * Outlier calculation using 3-sigma (three standard deviations from the population mean).
 * Deterministic and matches TradingView Strategy Tester.
 */
export function calculateOutliers(
  pnls: number[],
  pcts: number[],
): { outlierPnlInr: number; outlierPnlPct: number; outlierCount: number } {
  if (pnls.length < 2) {
    return { outlierPnlInr: 0, outlierPnlPct: 0, outlierCount: 0 };
  }

  const mean = pnls.reduce((acc, v) => acc + v, 0) / pnls.length;
  const variance = pnls.reduce((acc, v) => acc + Math.pow(v - mean, 2), 0) / pnls.length;
  const stdDev = Math.sqrt(variance);

  if (stdDev === 0) {
    return { outlierPnlInr: 0, outlierPnlPct: 0, outlierCount: 0 };
  }

  let outlierPnlInr = 0;
  let outlierPnlPct = 0;
  let outlierCount = 0;

  for (let i = 0; i < pnls.length; i++) {
    const pnl = pnls[i];
    if (Math.abs(pnl - mean) > 3.0 * stdDev) {
      outlierPnlInr += pnl;
      outlierPnlPct += pcts[i] || 0;
      outlierCount++;
    }
  }

  return { outlierPnlInr, outlierPnlPct, outlierCount };
}

/**
 * Generates dynamic histogram bins centered at 0% with sensible integer or fractional steps.
 */
export function generateReturnsHistogramBins(
  returnPercentages: number[],
): { bins: HistogramBin[]; minReturn: number; maxReturn: number } {
  if (!returnPercentages.length) {
    const defaultBins: HistogramBin[] = [
      { label: "-4%", min: -4, max: -3, count: 0, isPositive: false },
      { label: "-3%", min: -3, max: -2, count: 0, isPositive: false },
      { label: "-2%", min: -2, max: -1, count: 0, isPositive: false },
      { label: "-1%", min: -1, max: 0, count: 0, isPositive: false },
      { label: "0%", min: 0, max: 1, count: 0, isPositive: true },
      { label: "1%", min: 1, max: 2, count: 0, isPositive: true },
      { label: "2%", min: 2, max: 3, count: 0, isPositive: true },
      { label: "3%", min: 3, max: 4, count: 0, isPositive: true },
      { label: "4%", min: 4, max: 5, count: 0, isPositive: true },
      { label: "5%", min: 5, max: 6, count: 0, isPositive: true },
      { label: "6%", min: 6, max: 7, count: 0, isPositive: true },
    ];
    return { bins: defaultBins, minReturn: 0, maxReturn: 0 };
  }

  const minReturn = Math.min(...returnPercentages);
  const maxReturn = Math.max(...returnPercentages);
  const span = Math.max(Math.abs(minReturn), Math.abs(maxReturn), 4);

  let step = 1;
  if (span > 50) step = 10;
  else if (span > 25) step = 5;
  else if (span > 12) step = 2;
  else if (span <= 2) step = 0.5;

  const minBinVal = Math.min(Math.floor(minReturn / step) * step, -step * 3);
  const maxBinVal = Math.max(Math.ceil(maxReturn / step) * step, step * 4);

  const bins: HistogramBin[] = [];

  for (let val = minBinVal; val <= maxBinVal; val += step) {
    const nextVal = val + step;
    const isPositive = val >= 0;
    const label = step < 1 ? `${val.toFixed(1)}%` : `${Math.round(val)}%`;
    bins.push({
      label,
      min: val,
      max: nextVal,
      count: 0,
      isPositive,
    });
  }

  returnPercentages.forEach((ret) => {
    for (let i = 0; i < bins.length; i++) {
      const b = bins[i];
      const isLast = i === bins.length - 1;
      if ((ret >= b.min && ret < b.max) || (isLast && ret >= b.min)) {
        b.count++;
        break;
      }
    }
  });

  return { bins, minReturn, maxReturn };
}

/** Find closest bin label for a given return value */
function findClosestBinLabel(bins: HistogramBin[], value: number | null): string | null {
  if (value == null || !bins.length) return null;
  for (let i = 0; i < bins.length; i++) {
    const b = bins[i];
    const isLast = i === bins.length - 1;
    if ((value >= b.min && value < b.max) || (isLast && value >= b.min)) {
      return b.label;
    }
  }
  return bins[0]?.label ?? null;
}

/**
 * Computes streaks from chronological trades.
 */
export function calculateStreaks(trades: DashboardTrade[], initialCapital: number): StreaksStats {
  const sorted = [...trades].sort((a, b) => {
    const dateA = a.exit_date || a.entry_date || "";
    const dateB = b.exit_date || b.entry_date || "";
    return dateA.localeCompare(dateB);
  });

  const winStreaks: number[] = [];
  const lossStreaks: number[] = [];
  const beStreaks: number[] = [];

  let currentStreakType: "winner" | "loser" | "breakeven" | null = null;
  let currentStreakLen = 0;

  let consecutiveProfitInr = 0;
  let maxConsecutiveProfitInr = 0;
  let consecutiveLossInr = 0;
  let maxConsecutiveLossInr = 0;

  let consecutiveProfitPct = 0;
  let maxConsecutiveProfitPct = 0;
  let consecutiveLossPct = 0;
  let maxConsecutiveLossPct = 0;

  for (const tr of sorted) {
    const outcome = classifyTradeOutcome(tr);
    const pnlInr = getTradeNetPnl(tr, initialCapital) || 0;
    const pnlPct = tr.pnl_percent != null ? Number(tr.pnl_percent) : 0;

    if (outcome === currentStreakType) {
      currentStreakLen++;
      if (outcome === "winner") {
        consecutiveProfitInr += pnlInr;
        consecutiveProfitPct += pnlPct;
        maxConsecutiveProfitInr = Math.max(maxConsecutiveProfitInr, consecutiveProfitInr);
        maxConsecutiveProfitPct = Math.max(maxConsecutiveProfitPct, consecutiveProfitPct);
      } else if (outcome === "loser") {
        consecutiveLossInr += pnlInr;
        consecutiveLossPct += pnlPct;
        maxConsecutiveLossInr = Math.min(maxConsecutiveLossInr, consecutiveLossInr);
        maxConsecutiveLossPct = Math.min(maxConsecutiveLossPct, consecutiveLossPct);
      }
    } else {
      if (currentStreakType === "winner") {
        winStreaks.push(currentStreakLen);
      } else if (currentStreakType === "loser") {
        lossStreaks.push(currentStreakLen);
      } else if (currentStreakType === "breakeven") {
        beStreaks.push(currentStreakLen);
      }

      currentStreakType = outcome;
      currentStreakLen = 1;

      if (outcome === "winner") {
        consecutiveProfitInr = pnlInr;
        consecutiveProfitPct = pnlPct;
        maxConsecutiveProfitInr = Math.max(maxConsecutiveProfitInr, consecutiveProfitInr);
        maxConsecutiveProfitPct = Math.max(maxConsecutiveProfitPct, consecutiveProfitPct);
        consecutiveLossInr = 0;
        consecutiveLossPct = 0;
      } else if (outcome === "loser") {
        consecutiveLossInr = pnlInr;
        consecutiveLossPct = pnlPct;
        maxConsecutiveLossInr = Math.min(maxConsecutiveLossInr, consecutiveLossInr);
        maxConsecutiveLossPct = Math.min(maxConsecutiveLossPct, consecutiveLossPct);
        consecutiveProfitInr = 0;
        consecutiveProfitPct = 0;
      } else {
        consecutiveProfitInr = 0;
        consecutiveProfitPct = 0;
        consecutiveLossInr = 0;
        consecutiveLossPct = 0;
      }
    }
  }

  if (currentStreakType === "winner") {
    winStreaks.push(currentStreakLen);
  } else if (currentStreakType === "loser") {
    lossStreaks.push(currentStreakLen);
  } else if (currentStreakType === "breakeven") {
    beStreaks.push(currentStreakLen);
  }

  const maxWinStreak = winStreaks.length ? Math.max(...winStreaks) : 0;
  const currentWinStreak = currentStreakType === "winner" ? currentStreakLen : 0;
  const avgWinStreak = winStreaks.length ? winStreaks.reduce((a, b) => a + b, 0) / winStreaks.length : 0;

  const maxLossStreak = lossStreaks.length ? Math.max(...lossStreaks) : 0;
  const currentLossStreak = currentStreakType === "loser" ? currentStreakLen : 0;
  const avgLossStreak = lossStreaks.length ? lossStreaks.reduce((a, b) => a + b, 0) / lossStreaks.length : 0;

  const maxBreakevenStreak = beStreaks.length ? Math.max(...beStreaks) : 0;
  const currentBreakevenStreak = currentStreakType === "breakeven" ? currentStreakLen : 0;

  return {
    currentWinStreak,
    maxWinStreak,
    currentLossStreak,
    maxLossStreak,
    currentBreakevenStreak,
    maxBreakevenStreak,
    avgWinStreak: Number(avgWinStreak.toFixed(1)),
    avgLossStreak: Number(avgLossStreak.toFixed(1)),
    winStreakCount: winStreaks.length,
    lossStreakCount: lossStreaks.length,
    maxConsecutiveProfitInr: maxConsecutiveProfitInr || null,
    maxConsecutiveLossInr: maxConsecutiveLossInr || null,
    maxConsecutiveProfitPct: maxConsecutiveProfitPct || null,
    maxConsecutiveLossPct: maxConsecutiveLossPct || null,
  };
}

/**
 * Main calculator function that returns all derived data for Trades Analysis.
 */
export function computeTradesAnalysis(options: CalculatorOptions): TradesAnalysisModel {
  const {
    trades: rawTrades = [],
    ledger,
    strategyTester,
    totalReturn = null,
  } = options;
  const initialCapital = options.initialCapital ?? 100000;

  // Use only closed trades for canonical calculations
  const closed = rawTrades.filter((t) => !t.open);

  const winners: DashboardTrade[] = [];
  const losers: DashboardTrade[] = [];
  const breakevens: DashboardTrade[] = [];

  const allPnlsInr: number[] = [];
  const allPnlsPct: number[] = [];
  const winPnlsInr: number[] = [];
  const winPnlsPct: number[] = [];
  const lossPnlsInr: number[] = [];
  const lossPnlsPct: number[] = [];
  const holdingDays: number[] = [];
  const winHoldingDays: number[] = [];
  const lossHoldingDays: number[] = [];

  for (const tr of closed) {
    const outcome = classifyTradeOutcome(tr);
    const pnlInr = getTradeNetPnl(tr, initialCapital);
    const pnlPct = tr.pnl_percent != null ? Number(tr.pnl_percent) : null;
    const hold = tr.holding_days != null ? Number(tr.holding_days) : null;

    if (hold != null) {
      holdingDays.push(hold);
    }

    if (pnlInr != null) allPnlsInr.push(pnlInr);
    if (pnlPct != null) allPnlsPct.push(pnlPct);

    if (outcome === "winner") {
      winners.push(tr);
      if (pnlInr != null) winPnlsInr.push(pnlInr);
      if (pnlPct != null) winPnlsPct.push(pnlPct);
      if (hold != null) winHoldingDays.push(hold);
    } else if (outcome === "loser") {
      losers.push(tr);
      if (pnlInr != null) lossPnlsInr.push(pnlInr);
      if (pnlPct != null) lossPnlsPct.push(pnlPct);
      if (hold != null) lossHoldingDays.push(hold);
    } else {
      breakevens.push(tr);
    }
  }

  // Basic trade counts
  const totalTrades =
    strategyTester?.total_trades ?? ledger?.total_trades ?? closed.length;
  const winCount =
    strategyTester?.profitable_trades ?? ledger?.winning_trades ?? winners.length;
  const lossCount =
    strategyTester?.losing_trades ?? ledger?.losing_trades ?? losers.length;
  const breakEvenCount =
    strategyTester?.breakeven ?? ledger?.breakeven_trades ?? breakevens.length;

  const winPct = totalTrades > 0 ? (winCount / totalTrades) * 100 : 0;
  const lossPct = totalTrades > 0 ? (lossCount / totalTrades) * 100 : 0;
  const breakEvenPct = totalTrades > 0 ? (breakEvenCount / totalTrades) * 100 : 0;

  // Averages
  const avgWinPct =
    strategyTester?.average_winning_trade ??
    ledger?.average_profit ??
    (winPnlsPct.length ? winPnlsPct.reduce((a, b) => a + b, 0) / winPnlsPct.length : null);

  const avgLossPct =
    strategyTester?.average_losing_trade ??
    ledger?.average_loss ??
    (lossPnlsPct.length ? lossPnlsPct.reduce((a, b) => a + b, 0) / lossPnlsPct.length : null);

  const avgWinInr = winPnlsInr.length ? winPnlsInr.reduce((a, b) => a + b, 0) / winPnlsInr.length : null;
  const avgLossInr = lossPnlsInr.length ? lossPnlsInr.reduce((a, b) => a + b, 0) / lossPnlsInr.length : null;

  // Financial totals
  const grossProfitInr =
    strategyTester?.gross_profit ??
    ledger?.gross_profit ??
    (winPnlsInr.length ? winPnlsInr.reduce((a, b) => a + Math.max(0, b), 0) : 0);

  const grossLossInr =
    strategyTester?.gross_loss ??
    ledger?.gross_loss ??
    (lossPnlsInr.length ? lossPnlsInr.reduce((a, b) => a + Math.min(0, b), 0) : 0);

  const netProfitInr =
    strategyTester?.total_pnl ??
    ledger?.net_pnl ??
    (allPnlsInr.length ? allPnlsInr.reduce((a, b) => a + b, 0) : 0);

  const grossProfitPct = winPnlsPct.length ? winPnlsPct.reduce((a, b) => a + Math.max(0, b), 0) : null;
  const grossLossPct = lossPnlsPct.length ? lossPnlsPct.reduce((a, b) => a + Math.min(0, b), 0) : null;
  const netProfitPct = totalReturn ?? (allPnlsPct.length ? allPnlsPct.reduce((a, b) => a + b, 0) : null);

  // Profit Factor
  let profitFactor: number | null = strategyTester?.profit_factor ?? ledger?.profit_factor ?? null;
  let profitFactorInfinite = Boolean(ledger?.profit_factor_infinite);

  if (profitFactor == null && !profitFactorInfinite) {
    const absLoss = Math.abs(grossLossInr || 0);
    if (grossProfitInr > 0 && absLoss > 0) {
      profitFactor = grossProfitInr / absLoss;
    } else if (grossProfitInr > 0 && absLoss === 0) {
      profitFactorInfinite = true;
    }
  }

  // Expected Payoff
  let expectedPayoffPct = strategyTester?.expected_payoff ?? ledger?.expected_payoff ?? null;
  let expectedPayoffInr = ledger?.expected_payoff_inr ?? null;

  if (expectedPayoffPct == null && totalTrades > 0) {
    if (avgWinPct != null && avgLossPct != null) {
      expectedPayoffPct = (winPct / 100) * avgWinPct + (lossPct / 100) * avgLossPct;
    } else if (allPnlsPct.length) {
      expectedPayoffPct = allPnlsPct.reduce((a, b) => a + b, 0) / totalTrades;
    }
  }

  if (expectedPayoffInr == null && totalTrades > 0) {
    if (allPnlsInr.length) {
      expectedPayoffInr = netProfitInr / totalTrades;
    } else if (expectedPayoffPct != null) {
      expectedPayoffInr = (expectedPayoffPct / 100) * initialCapital;
    }
  }

  // Largest profit & loss
  const largestProfitInr =
    ledger?.largest_profit_inr ??
    (winPnlsInr.length ? Math.max(...winPnlsInr) : null);

  const largestProfitPct =
    strategyTester?.largest_profit ??
    ledger?.largest_profit ??
    (winPnlsPct.length ? Math.max(...winPnlsPct) : null);

  const largestLossInr =
    ledger?.largest_loss_inr ??
    (lossPnlsInr.length ? Math.min(...lossPnlsInr) : null);

  const largestLossPct =
    strategyTester?.largest_loss ??
    ledger?.largest_loss ??
    (lossPnlsPct.length ? Math.min(...lossPnlsPct) : null);

  // Outliers
  const calculatedOutliers = calculateOutliers(allPnlsInr, allPnlsPct);
  const outliersPnlInr =
    ledger?.outlier_pnl ?? strategyTester?.outlier_pnl ?? calculatedOutliers.outlierPnlInr;
  const outlierTradesCount =
    ledger?.outlier_trades ?? calculatedOutliers.outlierCount;
  const outliersPnlPct =
    initialCapital > 0 && outliersPnlInr != null
      ? (outliersPnlInr / initialCapital) * 100
      : calculatedOutliers.outlierPnlPct;

  // Histogram
  const histResult = generateReturnsHistogramBins(allPnlsPct);
  const avgWinBinLabel = findClosestBinLabel(histResult.bins, avgWinPct);
  const avgLossBinLabel = findClosestBinLabel(histResult.bins, avgLossPct);

  // Streaks
  const streaks = calculateStreaks(closed, initialCapital);

  // Averages for Details
  const avgTradeInr = totalTrades > 0 ? netProfitInr / totalTrades : null;
  const avgTradePct = totalTrades > 0 && allPnlsPct.length ? allPnlsPct.reduce((a, b) => a + b, 0) / totalTrades : null;
  const winLossRatio =
    avgWinPct != null && avgLossPct != null && avgLossPct !== 0
      ? Math.abs(avgWinPct / avgLossPct)
      : null;

  const avgHoldingDays = holdingDays.length
    ? ledger?.average_holding_period ?? holdingDays.reduce((a, b) => a + b, 0) / holdingDays.length
    : null;
  const avgWinHoldingDays = winHoldingDays.length
    ? winHoldingDays.reduce((a, b) => a + b, 0) / winHoldingDays.length
    : null;
  const avgLossHoldingDays = lossHoldingDays.length
    ? lossHoldingDays.reduce((a, b) => a + b, 0) / lossHoldingDays.length
    : null;
  const medianHoldingDays = ledger?.median_holding_period ?? median(holdingDays);

  return {
    topMetrics: {
      expectedPayoffInr,
      expectedPayoffPct,
      outliersPnlInr,
      outliersPnlPct,
      outlierTradesCount,
      largestProfitInr,
      largestProfitPct,
      largestLossInr,
      largestLossPct,
    },
    returnsDistribution: {
      bins: histResult.bins,
      avgWinPct,
      avgLossPct,
      minReturn: histResult.minReturn,
      maxReturn: histResult.maxReturn,
      avgWinBinLabel,
      avgLossBinLabel,
    },
    tradesDistribution: {
      totalTrades,
      winCount,
      winPct,
      lossCount,
      lossPct,
      breakEvenCount,
      breakEvenPct,
    },
    streaks,
    details: {
      totalTrades,
      winCount,
      lossCount,
      breakEvenCount,
      winRate: winPct,
      lossRate: lossPct,
      breakEvenRate: breakEvenPct,
      grossProfitInr,
      grossProfitPct,
      grossLossInr,
      grossLossPct,
      netProfitInr,
      netProfitPct,
      profitFactor,
      profitFactorInfinite,
      expectedPayoffInr,
      expectedPayoffPct,
      avgTradeInr,
      avgTradePct,
      avgWinInr,
      avgWinPct,
      avgLossInr,
      avgLossPct,
      winLossRatio,
      largestProfitInr,
      largestProfitPct,
      largestLossInr,
      largestLossPct,
      outlierPnlInr: outliersPnlInr,
      outlierPnlPct: outliersPnlPct,
      outlierTradesCount,
      avgHoldingDays,
      avgWinHoldingDays,
      avgLossHoldingDays,
      medianHoldingDays,
      commissionInr: ledger?.commission ?? strategyTester?.commission ?? null,
    },
  };
}
