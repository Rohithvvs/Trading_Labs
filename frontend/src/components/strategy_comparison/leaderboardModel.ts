import type { ComparisonPayload, ComparisonSlot } from "../../api_strategy_comparison";

export type LeaderboardGrade = "A" | "B" | "C" | "D" | "F";

export type LeaderboardRow = {
  slot: ComparisonSlot;
  slotIndex: number;
  rank: number;
  score: number | null;
  grade: LeaderboardGrade | null;
  trades: number | null;
  winRate: number | null;
  profitFactor: number | null;
  avgTrade: number | null;
  avgTradeUnit: string | null;
  cagr: number | null;
  totalReturn: number | null;
  maxDd: number | null;
  calmar: number | null;
  avgCash: number | null;
  avgExposure: number | null;
  bestTrade: string;
  worstTrade: string;
};

export function gradeFromScore(score: number | null): LeaderboardGrade | null {
  if (score == null || Number.isNaN(score)) return null;
  if (score >= 80) return "A";
  if (score >= 65) return "B";
  if (score >= 50) return "C";
  if (score >= 35) return "D";
  return "F";
}

export function scoreFromRadar(slotId: string, radar: ComparisonPayload["radar"]): number | null {
  const series = radar.series.find((item) => item.slot_id === slotId);
  if (!series) return null;
  const values = Object.values(series.values).filter((value): value is number => value != null && !Number.isNaN(value));
  if (!values.length) return null;
  return Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 10) / 10;
}

function calmarOf(slot: ComparisonSlot): number | null {
  if (slot.metrics.calmar_ratio != null && !Number.isNaN(slot.metrics.calmar_ratio)) {
    return slot.metrics.calmar_ratio;
  }
  const cagr = slot.metrics.cagr;
  const dd = slot.metrics.max_drawdown_pct;
  if (cagr == null || dd == null || Math.abs(dd) < 1e-9) return null;
  return cagr / Math.abs(dd);
}

function avgCashOf(slot: ComparisonSlot): number | null {
  if (slot.metrics.avg_cash != null) return slot.metrics.avg_cash;
  const cashes = (slot.equity_curve || []).map((p) => p.cash).filter((v): v is number => v != null);
  if (!cashes.length) return null;
  return cashes.reduce((sum, v) => sum + v, 0) / cashes.length;
}

function avgExposureOf(slot: ComparisonSlot): number | null {
  if (slot.metrics.avg_exposure_pct != null) return slot.metrics.avg_exposure_pct;
  const initial = slot.metrics.initial_capital || slot.config.initial_capital;
  const invested = (slot.equity_curve || []).map((p) => p.invested).filter((v): v is number => v != null);
  if (!invested.length || !initial) return null;
  return invested.reduce((sum, v) => sum + (v / initial) * 100, 0) / invested.length;
}

function tradeLabel(trade: ComparisonSlot["metrics"]["best_trade"]): string {
  if (!trade) return "—";
  const name = trade.symbol || "—";
  if (trade.return_pct != null) {
    const sign = trade.return_pct > 0 ? "+" : "";
    return `${name} ${sign}${trade.return_pct.toFixed(2)}%`;
  }
  if (trade.net_pnl != null) {
    const sign = trade.net_pnl > 0 ? "+" : trade.net_pnl < 0 ? "−" : "";
    return `${name} ${sign}₹${Math.abs(trade.net_pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
  }
  return name;
}

export function buildLeaderboard(comparison: ComparisonPayload): LeaderboardRow[] {
  const rows: LeaderboardRow[] = comparison.slots.map((slot, slotIndex) => ({
    slot,
    slotIndex,
    rank: 0,
    score: scoreFromRadar(slot.slot_id, comparison.radar),
    grade: null,
    trades: slot.metrics.total_trades,
    winRate: slot.metrics.win_rate,
    profitFactor: slot.metrics.profit_factor,
    avgTrade: slot.metrics.average_trade,
    avgTradeUnit: slot.metrics.average_trade_unit,
    cagr: slot.metrics.cagr,
    totalReturn: slot.metrics.total_return_pct,
    maxDd: slot.metrics.max_drawdown_pct ?? slot.metrics.max_drawdown,
    calmar: calmarOf(slot),
    avgCash: avgCashOf(slot),
    avgExposure: avgExposureOf(slot),
    bestTrade: tradeLabel(slot.metrics.best_trade),
    worstTrade: tradeLabel(slot.metrics.worst_trade),
  }));
  rows.forEach((row) => {
    row.grade = gradeFromScore(row.score);
  });
  rows.sort((a, b) => {
    if (a.score == null && b.score == null) {
      return (b.totalReturn ?? -Infinity) - (a.totalReturn ?? -Infinity);
    }
    if (a.score == null) return 1;
    if (b.score == null) return -1;
    if (b.score !== a.score) return b.score - a.score;
    return (b.totalReturn ?? -Infinity) - (a.totalReturn ?? -Infinity);
  });
  rows.forEach((row, index) => {
    row.rank = index + 1;
  });
  return rows;
}

export const LEADERBOARD_COLUMNS = [
  "Rank",
  "Strategy",
  "Score",
  "Grade",
  "Trades",
  "Win Rate",
  "PF",
  "Avg Trade",
  "CAGR",
  "Total Return",
  "Max DD",
  "Calmar",
  "Avg Cash",
  "Avg Exposure",
  "Best Trade",
  "Worst Trade",
] as const;

export const LEADERBOARD_NOTE =
  "Score is the average of this page’s radar display-scale metrics (0–100). Grade maps that score (A≥80, B≥65, C≥50, D≥35, F below). Rank orders by Score, then Total Return. Missing metrics stay blank — they are not estimated. This is not a trading recommendation.";
