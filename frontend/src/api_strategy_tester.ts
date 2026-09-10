import { apiUrl } from "./config";

async function fetchWithAuthResponse(path: string, init: RequestInit | undefined, _label: string): Promise<Response> {
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

export type OperandValue = number | { indicator?: string; field?: string; period?: number; std?: number; value?: number };

export type StrategyFilterInput = {
  id?: string;
  field: string;
  operator: string;
  left?: OperandValue | string;
  value?: OperandValue;
  low?: number;
  high?: number;
  label?: string;
};

export type StrategyConfigPayload = {
  name: string;
  description?: string;
  universe?: string;
  timeframe?: string;
  side?: "LONG" | "SHORT";
  filters?: StrategyFilterInput[];
  root?: Record<string, unknown>;
  position_rules?: { side?: string; return_method?: string };
  signal_rules?: { buy_requires_all?: boolean; watch_min_passed?: number; watch_min_pass_ratio?: number };
  initial_capital?: number;
  preset_id?: string;
  start_date?: string;
  end_date?: string;
  strategy_id?: string;
  source?: { type: "builder" | "pine"; pine_code?: string; pineCode?: string };
};

export type StrategyRunStatus = {
  id: string;
  run_id: string;
  strategy_name: string;
  strategy_version?: number;
  strategy_snapshot?: Record<string, unknown>;
  universe: string;
  universe_size: number;
  universe_label?: string;
  timeframe: string;
  start_date: string | null;
  end_date: string | null;
  initial_capital: number;
  calculation_version?: string;
  data_timestamp?: string | null;
  status: string;
  stage?: string | null;
  progress_pct: number;
  processed_count: number;
  total_count: number;
  buy: number;
  watch: number;
  reject: number;
  current_symbol?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  elapsed_seconds?: number | null;
  duration_seconds?: number | null;
  error_code?: string | null;
  error_detail?: string | null;
  error?: string | null;
  progress?: { processed_stocks?: number; total_stocks?: number; percent?: number };
  summary?: StrategyRunSummary | null;
};

export type RankedReturn = {
  rank: number;
  symbol: string;
  company?: string | null;
  entry_price: number | null;
  exit_price: number | null;
  return_pct: number | null;
  signal: string | null;
  key_filters?: string[];
  failed_filters?: string[];
  passed_filters?: string[];
};

export type FilterStat = {
  filter_id: string;
  label: string;
  filter_name?: string;
  passed: number;
  failed: number;
  skipped?: number;
  pass_pct: number | null;
  fail_pct: number | null;
  pass_rate?: number | null;
  fail_rate?: number | null;
};

export type FunnelStep = {
  step: number;
  filter_id: string | null;
  label: string;
  remaining: number;
  drop?: number;
  retention_pct?: number;
};

export type StrategyRunSummary = {
  universe_size: number;
  stocks_scanned: number;
  evaluated: number;
  insufficient_data: number;
  failed_validation: number;
  errors: number;
  buy: number;
  watch: number;
  reject: number;
  positive_returns: number;
  negative_returns: number;
  flat_returns: number;
  average_return?: number | null;
  error_count?: number;
  top_return?: number | null;
  worst_return?: number | null;
  top_positive?: RankedReturn[];
  top_negative?: RankedReturn[];
  filter_analytics?: FilterStat[];
  filter_funnel?: FunnelStep[];
  data_source?: string | null;
  scan_as_of?: string | null;
  scan_date_counts?: Record<string, number>;
  scan_date_mismatch?: boolean;
  scan_bar_note?: string | null;
};

export type StrategyResultRow = {
  rank: number | null;
  symbol: string;
  company?: string | null;
  status: string;
  signal: string | null;
  entry_price: number | null;
  exit_price: number | null;
  return_pct: number | null;
  return_bucket?: string | null;
  return_formula?: string | null;
  rsi?: number | null;
  sma_20?: number | null;
  sma_50?: number | null;
  sma_200?: number | null;
  volume?: number | null;
  avg_volume?: number | null;
  close?: number | null;
  high_252?: number | null;
  nifty500_close?: number | null;
  nifty500_sma_50?: number | null;
  evaluation_date?: string | null;
  indicators?: Record<string, number | string | null>;
  filters_passed: number;
  filters_failed: number;
  pass_count?: number;
  fail_count?: number;
  passed_filters: string[];
  failed_filters: string[];
  filter_details?: Array<{
    filter_id: string;
    label: string;
    passed: boolean | null;
    left_value: number | null;
    right_value: number | null;
    operator: string;
    reason?: string | null;
  }>;
  filter_results?: Array<{ name: string; passed: boolean }>;
  primary_failure_reason?: string | null;
  primary_failure?: string | null;
  error_detail?: string | null;
  source?: string;
  strategy_name?: string;
};

export type HistoryRow = {
  id: string;
  run_id: string;
  strategy: string;
  strategy_name: string;
  run_date: string | null;
  stocks: number;
  buy: number;
  watch: number;
  reject: number;
  top_return: number | null;
  worst_return: number | null;
  status: string;
};

export type SavedStrategyItem = {
  id: string;
  name: string;
  description?: string;
  config?: StrategyConfigPayload;
  version?: number;
  is_preset?: boolean;
  preset_id?: string | null;
  updated_at?: string | null;
};

export type StrategyCatalog = {
  universe_count: number;
  universe_label: string;
  universe_symbols?: { symbol: string; company?: string | null }[];
  operators: { code: string; label: string }[];
  fields: { code: string; label: string; group: string; periods?: number[] }[];
  presets: Array<StrategyConfigPayload & { preset_id: string; name: string; description: string }>;
  sides: string[];
  lookahead?: string;
  saved?: SavedStrategyItem[];
};

function asList<T>(value: unknown, keys: string[]): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    for (const key of keys) {
      if (Array.isArray(obj[key])) return obj[key] as T[];
    }
  }
  return [];
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => ({}));
  const detail = body?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const msg = detail.message || detail.error || detail.msg;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  if (Array.isArray(detail) && detail.length) {
    const parts = detail
      .map((item: { msg?: string; message?: string; loc?: unknown[] }) => {
        const loc = Array.isArray(item?.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
        const msg = item?.msg || item?.message;
        if (!msg) return "";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return body?.message || fallback;
}

export async function fetchStrategyCatalog(): Promise<StrategyCatalog> {
  const response = await fetchWithAuthResponse("/strategy-tests/catalog", { method: "GET" }, "Strategy tester catalog");
  if (!response.ok) throw new Error(await parseError(response, "Unable to load strategy catalog."));
  return response.json();
}

export async function fetchStrategyHistory(): Promise<HistoryRow[]> {
  const response = await fetchWithAuthResponse("/strategy-tests/history", { method: "GET" }, "Strategy tester history");
  if (!response.ok) throw new Error(await parseError(response, "Unable to load strategy history."));
  return asList<HistoryRow>(await response.json(), ["runs"]);
}

export async function saveStrategyDefinition(payload: StrategyConfigPayload): Promise<{ id: string; name: string; version: number }> {
  const response = await fetchWithAuthResponse(
    "/strategy-tests/strategies",
    { method: "POST", body: JSON.stringify(payload) },
    "Save strategy",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to save strategy."));
  return response.json();
}

export async function updateStrategyDefinition(
  id: string,
  payload: StrategyConfigPayload,
): Promise<{ id: string; name: string; version: number }> {
  const response = await fetchWithAuthResponse(
    `/strategy-tests/strategies/${encodeURIComponent(id)}`,
    { method: "PUT", body: JSON.stringify(payload) },
    "Update strategy",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to update strategy."));
  return response.json();
}

export async function fetchSavedStrategies(): Promise<SavedStrategyItem[]> {
  const response = await fetchWithAuthResponse("/strategy-tests/strategies", { method: "GET" }, "List saved strategies");
  if (!response.ok) throw new Error(await parseError(response, "Unable to load saved strategies."));
  return asList<SavedStrategyItem>(await response.json(), ["strategies"]);
}

export async function startStrategyTest(payload: StrategyConfigPayload): Promise<StrategyRunStatus> {
  const response = await fetchWithAuthResponse(
    "/strategy-tests",
    { method: "POST", body: JSON.stringify(payload) },
    "Start strategy test",
  );
  if (response.status === 409) {
    const body = await response.json().catch(() => ({}));
    const err: Error & { runId?: string } = new Error(body?.detail?.message || "A strategy test is already running");
    err.runId = body?.detail?.run_id || body?.run_id;
    throw err;
  }
  if (!response.ok) throw new Error(await parseError(response, "Unable to start strategy test."));
  return response.json();
}

export async function fetchStrategyRun(runId: string): Promise<StrategyRunStatus> {
  const response = await fetchWithAuthResponse(`/strategy-tests/${encodeURIComponent(runId)}`, { method: "GET" }, "Strategy test run");
  if (!response.ok) throw new Error(await parseError(response, "Unable to load strategy run."));
  return response.json();
}

export async function fetchStrategyResults(
  runId: string,
  params: {
    signal?: string;
    return_bucket?: string;
    returnBucket?: string;
    search?: string;
    sort?: string;
    direction?: string;
    page?: number;
    page_size?: number;
    pageSize?: number;
  },
): Promise<{ total: number; page: number; page_size: number; results: StrategyResultRow[] }> {
  const mapped: Record<string, string | number | undefined> = {
    signal: params.signal,
    return_bucket: params.return_bucket ?? params.returnBucket,
    search: params.search,
    sort: params.sort,
    direction: params.direction,
    page: params.page,
    page_size: params.page_size ?? params.pageSize,
  };
  const qs = new URLSearchParams();
  Object.entries(mapped).forEach(([key, value]) => {
    if (value != null && value !== "" && value !== "ALL") qs.set(key, String(value));
  });
  const response = await fetchWithAuthResponse(
    `/strategy-tests/${encodeURIComponent(runId)}/results?${qs.toString()}`,
    { method: "GET" },
    "Strategy test results",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load results."));
  return response.json();
}

export async function fetchStrategyResultDetail(runId: string, symbol: string): Promise<StrategyResultRow> {
  const response = await fetchWithAuthResponse(
    `/strategy-tests/${encodeURIComponent(runId)}/results/${encodeURIComponent(symbol)}`,
    { method: "GET" },
    "Strategy test result detail",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load stock detail."));
  return response.json();
}

export async function fetchFilterAnalytics(runId: string): Promise<{ independent: FilterStat[]; funnel: FunnelStep[] }> {
  const response = await fetchWithAuthResponse(
    `/strategy-tests/${encodeURIComponent(runId)}/filter-analytics`,
    { method: "GET" },
    "Strategy filter analytics",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load filter analytics."));
  return response.json();
}

export async function cancelStrategyRun(runId: string): Promise<void> {
  const response = await fetchWithAuthResponse(
    `/strategy-tests/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
    "Cancel strategy test",
  );
  if (!response.ok && response.status !== 409) throw new Error(await parseError(response, "Unable to cancel scan."));
}

export async function exportStrategyRun(runId: string, format: "csv" | "xlsx"): Promise<void> {
  const response = await fetchWithAuthResponse(
    `/strategy-tests/${encodeURIComponent(runId)}/export?format=${format}`,
    { method: "GET" },
    "Export strategy test",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to export run."));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `strategy-test-${runId}.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}

export type CandlePoint = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma_20?: number | null;
  sma_50?: number | null;
  sma_200?: number | null;
  rsi?: number | null;
};

export type SymbolHistoryItem = {
  run_id: string;
  strategy_name: string;
  date: string | null;
  signal: string | null;
  entry_price: number | null;
  exit_price: number | null;
  return_pct: number | null;
  status: string;
};

export async function fetchStrategyResultCandles(
  runId: string,
  symbol: string,
): Promise<{ symbol: string; start_date: string; end_date: string; candles: CandlePoint[] }> {
  const response = await fetchWithAuthResponse(
    `/strategy-tests/${encodeURIComponent(runId)}/results/${encodeURIComponent(symbol)}/candles`,
    { method: "GET" },
    "Strategy test stock candles",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load stock candles."));
  return response.json();
}

export async function fetchStrategyResultHistory(
  runId: string,
  symbol: string,
): Promise<{ symbol: string; history: SymbolHistoryItem[] }> {
  const response = await fetchWithAuthResponse(
    `/strategy-tests/${encodeURIComponent(runId)}/results/${encodeURIComponent(symbol)}/history`,
    { method: "GET" },
    "Strategy test stock history",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load stock history."));
  return response.json();
}

// ---------------------------------------------------------------------------
// QuantConnect LEAN Backtesting Engine API Client
// ---------------------------------------------------------------------------

export type LeanTradeItem = {
  tradeId: number;
  symbol: string;
  entryDate: string;
  entryPrice: number;
  exitDate?: string | null;
  exitPrice?: number | null;
  quantity: number;
  direction: "LONG" | "SHORT";
  grossPnL: number;
  commission: number;
  slippage: number;
  netPnL: number;
  returnPct: number;
  holdingPeriod: number;
  entryReason: string;
  exitReason: string;
  isOpen: boolean;
};

export type LeanEquityPointItem = {
  date: string;
  equity: number;
  cash: number;
  investedCapital: number;
  drawdown: number;
  drawdownPct: number;
};

export type LeanBacktestSummaryItem = {
  initialCapital: number;
  finalEquity: number;
  netProfit: number;
  netProfitPct: number;
  cagr?: number | null;
  sharpeRatio: number;
  sortinoRatio: number;
  maximumDrawdown: number;
  maximumDrawdownPct: number;
  calmarRatio?: number | null;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  profitFactor: number;
  averageTrade: number;
  averageWinningTrade: number;
  averageLosingTrade: number;
  expectancy: number;
  totalCommission: number;
  totalSlippage: number;
  executionModel: string;
  dataSource: string;
  dataCoverageRatio: number;
  tradingDaysCount: number;
};

export type LeanBacktestResultPayload = {
  jobId: string;
  strategyId: string;
  strategyName: string;
  engine: string;
  status: string;
  startDate: string;
  endDate: string;
  symbols: string[];
  summary: LeanBacktestSummaryItem;
  trades: LeanTradeItem[];
  equityCurve: LeanEquityPointItem[];
  positions: Array<{
    date: string;
    symbol: string;
    quantity: number;
    averagePrice: number;
    marketValue: number;
    unrealizedPnL: number;
    realizedPnL: number;
  }>;
  debugTrace?: Array<Record<string, unknown>> | null;
  validationParity?: {
    symbol: string;
    strategy: string;
    startDate: string;
    endDate: string;
    totalBars: number;
    signalMatches: number;
    signalMismatches: number;
    tradeMatches: number;
    metricsComparison: Record<string, Record<string, unknown>>;
    mismatchDetails: Array<Record<string, unknown>>;
    verdict: string;
  } | null;
};

export type LeanJobItem = {
  jobId: string;
  strategyId: string;
  strategyName: string;
  userId?: string | null;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  progressPct: number;
  stage: string;
  error?: string | null;
  request: {
    strategyId: string;
    strategyName: string;
    symbols: string[];
    startDate: string;
    endDate: string;
    initialCapital: number;
    commission?: number;
    slippage?: number;
    positionSizing?: string;
    positionSizingValue?: number;
    maxPositions?: number;
    benchmark?: string | null;
    timeframe?: string;
    dataSource?: string;
    executionMode?: string;
  };
  result?: LeanBacktestResultPayload | null;
};

export async function fetchLeanEngines(): Promise<{
  engines: Array<{ id: string; name: string; description: string; is_default: boolean; supports_portfolio: boolean }>;
  default_engine: string;
}> {
  const response = await fetchWithAuthResponse("/backtests/engines", { method: "GET" }, "LEAN engines");
  if (!response.ok) return { engines: [{ id: "LEAN", name: "QuantConnect LEAN Engine", description: "Professional event-driven backtesting engine", is_default: true, supports_portfolio: true }], default_engine: "LEAN" };
  return response.json();
}

export async function createLeanBacktest(payload: Record<string, unknown>): Promise<LeanJobItem> {
  const response = await fetchWithAuthResponse(
    "/backtests",
    { method: "POST", body: JSON.stringify(payload) },
    "Create LEAN backtest",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to create LEAN backtest job."));
  return response.json();
}

export async function fetchLeanJob(jobId: string): Promise<LeanJobItem> {
  const response = await fetchWithAuthResponse(
    `/backtests/${encodeURIComponent(jobId)}`,
    { method: "GET" },
    "LEAN job status",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load LEAN job status."));
  return response.json();
}

export async function fetchLeanJobResults(jobId: string): Promise<LeanBacktestResultPayload> {
  const response = await fetchWithAuthResponse(
    `/backtests/${encodeURIComponent(jobId)}/results`,
    { method: "GET" },
    "LEAN job results",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load LEAN results."));
  return response.json();
}

export async function cancelLeanJob(jobId: string): Promise<{ job_id: string; status: string }> {
  const response = await fetchWithAuthResponse(
    `/backtests/${encodeURIComponent(jobId)}/cancel`,
    { method: "POST" },
    "Cancel LEAN job",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to cancel LEAN job."));
  return response.json();
}

export async function validateLeanAgainstTv(
  symbol = "RELIANCE",
  startDate?: string,
  endDate?: string,
  strategyId = "09_52w_breakout",
): Promise<any> {
  const params = new URLSearchParams({ symbol, strategy_id: strategyId });
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const response = await fetchWithAuthResponse(
    `/backtests/validate-tv?${params.toString()}`,
    { method: "POST" },
    "Validate LEAN against TV",
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to validate LEAN against TradingView."));
  return response.json();
}

