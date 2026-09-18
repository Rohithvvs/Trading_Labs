import { apiUrl } from "./config";

async function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };
  if (method !== "GET" && method !== "HEAD" && !headers["Content-Type"] && !headers["content-type"]) {
    headers["Content-Type"] = "application/json";
  }
  return fetch(apiUrl(path), { ...init, credentials: "include", headers });
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({}));
  const detail = body?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const msg = detail.message || detail.error || detail.msg;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  return body?.message || fallback;
}

export type ComparisonSource = "strategy_tester" | "lean";

export type ComparisonCatalogStrategy = {
  id: string;
  name: string;
  description?: string | null;
  version?: number;
  updated_at?: string | null;
  completed_run_count: number;
  completed_lean_count: number;
  latest_run?: ComparisonRunPreview | null;
  has_pine?: boolean;
};

export type ComparisonRunPreview = {
  run_id: string;
  source: ComparisonSource;
  status: string;
  strategy_name: string;
  start_date: string | null;
  end_date: string | null;
  universe: string | null;
  universe_size?: number | null;
  timeframe: string | null;
  initial_capital?: number | null;
  completed_at: string | null;
  buy?: number | null;
  watch?: number | null;
  reject?: number | null;
  label: string;
};

export type ComparisonSuggestion = {
  title: string;
  subtitle: string;
  strategy_ids: string[];
  names: string[];
};

export type ComparisonCatalog = {
  strategies: ComparisonCatalogStrategy[];
  suggestions?: ComparisonSuggestion[];
  min_slots: number;
  max_slots: number;
  strategy_count: number;
};

export type ComparisonSlotInput = {
  strategy_id: string;
  run_id: string;
  source?: ComparisonSource;
};

export type ComparisonMetrics = {
  net_profit: number | null;
  total_return_pct: number | null;
  cagr: number | null;
  win_rate: number | null;
  total_trades: number | null;
  profit_factor: number | null;
  average_trade: number | null;
  average_trade_unit: string | null;
  max_drawdown: number | null;
  max_drawdown_pct: number | null;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  calmar_ratio?: number | null;
  avg_cash?: number | null;
  avg_exposure_pct?: number | null;
  long_trades: number | null;
  short_trades: number | null;
  best_trade: { symbol?: string | null; net_pnl?: number | null; return_pct?: number | null } | null;
  worst_trade: { symbol?: string | null; net_pnl?: number | null; return_pct?: number | null } | null;
  final_equity: number | null;
  initial_capital: number | null;
  metrics_source: ComparisonSource | null;
  metrics_note: string | null;
};

export type ComparisonLogic = {
  source_type: string;
  pine_code: string | null;
  entry_conditions: string[];
  exit_conditions: string[];
  indicators: string[];
  filters: string[];
  stop_loss: string | null;
  take_profit: string | null;
  trailing_stop: string | null;
  position_type: string;
  time_exit_bars: number | null;
};

export type ComparisonConfig = {
  start_date: string | null;
  end_date: string | null;
  universe: string | null;
  universe_size: number | null;
  timeframe: string | null;
  initial_capital: number | null;
  commission: number | null;
  slippage: number | null;
  position_type: string | null;
  source: ComparisonSource;
};

export type ComparisonTrade = {
  symbol: string;
  entry_date?: string | null;
  exit_date?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  quantity?: number | null;
  direction?: string | null;
  net_pnl?: number | null;
  return_pct?: number | null;
  holding_period?: number | null;
  holding_window?: string | null;
  exit_reason?: string | null;
  entry_reason?: string | null;
};

export type ComparisonSlot = {
  slot_id: string;
  strategy_id: string;
  strategy_name: string;
  description?: string | null;
  run_id: string;
  source: ComparisonSource;
  status: string;
  logic: ComparisonLogic;
  metrics: ComparisonMetrics;
  config: ComparisonConfig;
  signals: Array<{ symbol: string; signal: string | null; return_pct: number | null }>;
  trades: ComparisonTrade[];
  equity_curve: Array<{ date: string; equity: number | null; cash?: number | null; invested?: number | null; drawdown?: number | null; drawdown_pct?: number | null }>;
  drawdown_curve: Array<{ date: string; drawdown: number | null; drawdown_pct: number | null }>;
  monthly_returns: Array<{ period: string; return_pct: number | null }>;
  yearly_returns: Array<{ period: string; return_pct: number | null }>;
  trade_distribution: Array<{ bucket: string; label: string; count: number }>;
  scan_summary?: { buy: number; watch: number; reject: number; universe_size: number } | null;
};

export type ComparisonPayload = {
  slot_count: number;
  aligned_config: boolean;
  config_warnings: Array<{ field: string; label: string; message: string; values: unknown[] }>;
  slots: ComparisonSlot[];
  radar: {
    axes: Array<{ key: string; label: string; higher_is_better: boolean }>;
    series: Array<{
      slot_id: string;
      name: string;
      values: Record<string, number | null>;
      raw: Record<string, number | null>;
    }>;
    note: string;
  };
  signals: {
    available: boolean;
    unavailable_reason: string | null;
    pairwise: Array<{
      left_slot_id: string;
      right_slot_id: string;
      shared_buy: string[];
      left_only_buy: string[];
      right_only_buy: string[];
      shared_count: number;
      overlap_pct: number | null;
    }>;
    overlap_pct: number | null;
    symbols: Array<{ symbol: string; signals: Record<string, string | null> }>;
    symbol_count: number;
  };
  trades: {
    symbols: Array<{ symbol: string; by_slot: Record<string, ComparisonTrade | null> }>;
    symbol_count: number;
  };
  has_equity: boolean;
  has_pine: boolean;
};

export async function fetchComparisonCatalog(): Promise<ComparisonCatalog> {
  const response = await fetchWithAuth("/strategy-comparison/catalog");
  if (!response.ok) throw new Error(await parseError(response, "Unable to load strategies."));
  return response.json();
}

export async function fetchComparisonRuns(strategyId: string): Promise<{ strategy_id: string; strategy_name: string; runs: ComparisonRunPreview[] }> {
  const response = await fetchWithAuth(`/strategy-comparison/strategies/${encodeURIComponent(strategyId)}/runs`);
  if (!response.ok) throw new Error(await parseError(response, "Unable to load completed runs."));
  return response.json();
}

export async function compareStrategies(slots: ComparisonSlotInput[]): Promise<ComparisonPayload> {
  const response = await fetchWithAuth("/strategy-comparison", {
    method: "POST",
    body: JSON.stringify({ slots }),
  });
  if (!response.ok) throw new Error(await parseError(response, "Unable to compare strategies."));
  return response.json();
}
