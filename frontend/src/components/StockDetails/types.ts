import type { CandlePoint, StrategyResultRow, StrategyRunStatus, SymbolHistoryItem } from "../../api_strategy_tester";
import type { SymbolDetail } from "../../types";

export type StockDetailTabId =
  | "overview"
  | "chart"
  | "history"
  | "news"
  | "backtest"
  | "research";

export interface StockTabDefinition {
  id: StockDetailTabId;
  label: string;
  testId: string;
}

export const STOCK_DETAIL_TABS: StockTabDefinition[] = [
  { id: "overview", label: "Overview", testId: "tab-detail-overview" },
  { id: "chart", label: "Chart", testId: "tab-detail-chart" },
  { id: "history", label: "History", testId: "tab-detail-history" },
  { id: "news", label: "News", testId: "tab-detail-news" },
  { id: "backtest", label: "Backtest", testId: "tab-detail-backtest" },
  { id: "research", label: "Research", testId: "tab-detail-research" },
];

export interface FilterEvalItem {
  name: string;
  passed: boolean;
}

export interface StockContextData {
  symbol: string;
  companyName: string;
  exchange: string;
  runId: string;
  stock: StrategyResultRow | null;
  runStatus: StrategyRunStatus | null;
  symbolDetail: SymbolDetail | null;
  candles: CandlePoint[];
  history: SymbolHistoryItem[];
  filterResults: FilterEvalItem[];
  strategyName: string;
  startDate: string | null;
  endDate: string | null;
  initialCapital: number;
}
