import type { DashboardTrade, BacktestRange } from "../BacktestAnalyticsDashboard";

export type TvViewMode = "chart" | "table";

export type TvChartLayer = "cumulative" | "buy_and_hold" | "excursions" | "runups_drawdowns";

export type TvColumnKey =
  | "trade_number"
  | "type"
  | "action"
  | "date_time"
  | "price"
  | "size"
  | "net_pnl"
  | "return";

export type TvDetailization = "default" | "trade_by_trade" | "bar_by_bar";

export type TvScriptStatus = "completed" | "running" | "pending" | "error";

export interface TvKeyStatsData {
  totalPnlInr: number | null;
  totalPnlPct: number | null;
  maxDrawdownInr: number | null;
  maxDrawdownPct: number | null;
  winRatePct: number | null;
  winCount: number;
  totalTrades: number;
  profitFactor: number | null;
  profitFactorInfinite: boolean;
}

export interface TvPerformancePoint {
  date: string;
  label: string;
  cumulativePnl: number;
  cumulativePnlPct: number;
  buyAndHoldPnl: number | null;
  buyAndHoldPct: number | null;
  drawdownInr: number | null;
  drawdownPct: number | null;
  runUpInr: number | null;
  runUpPct: number | null;
  isWinningInterval: boolean;
}

export interface TvTradeItem extends DashboardTrade {
  tradeNumber: number;
  notionalValue: number | null;
  quantity: number;
}
