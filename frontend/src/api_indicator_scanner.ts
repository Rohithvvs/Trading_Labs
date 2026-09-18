import { apiUrl } from "./config";

async function fetchWithAuth(path: string, init: RequestInit | undefined = undefined): Promise<Response> {
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

export type IndicatorIssue = {
  line: number;
  column: number;
  message: string;
  severity?: string;
  code?: string | null;
};

export type IndicatorInputDef = {
  name: string;
  title: string;
  kind: string;
  default: string | number | boolean | null;
  minval?: number | null;
  maxval?: number | null;
  step?: number | null;
};

export type IndicatorOutputDef = {
  name: string;
  kind: string;
  source_line?: number;
};

export type IndicatorValidation = {
  ok: boolean;
  status: string;
  errors: IndicatorIssue[];
  warnings: IndicatorIssue[];
  title?: string;
  inputs: IndicatorInputDef[];
  outputs: IndicatorOutputDef[];
  required_bars: number;
  required_symbols: string[];
  language_mode?: string;
  script_version?: number;
  timeframe?: string;
  timeframe_supported?: boolean;
  parsed_definition?: Record<string, unknown>;
  entry_conditions?: Array<{ id?: string; name: string }>;
  supported_syntax?: string[];
  disclaimer?: string;
  source_code?: string;
  name?: string;
  description?: string;
};

export type SavedIndicator = {
  id: string;
  name: string;
  description: string;
  source_code: string;
  script_version: number;
  language_mode: string;
  timeframe: string;
  parsed_definition?: Record<string, unknown> | null;
  entry_conditions?: Array<{ id?: string; name: string }>;
  validation_status: string;
  validation_errors?: IndicatorIssue[];
  required_bars: number;
  created_at?: string | null;
  updated_at?: string | null;
  last_used_at?: string | null;
  is_archived?: boolean;
};

export type SignalCondition =
  | "above"
  | "above_or_equal"
  | "below"
  | "below_or_equal"
  | "crosses"
  | "crosses_up"
  | "crosses_down"
  | "between"
  | "outside"
  | "equal";

export type IndicatorFilter = {
  field: string;
  operator: string;
  value?: string | number | boolean | null;
  low?: number | null;
  high?: number | null;
  condition?: SignalCondition;
  source?: string;
  setup_type?: "signal" | "pulse";
  compare_field?: string | null;
};

export type IndicatorScanStatus = {
  id: string;
  scan_id: string;
  indicator_id?: string | null;
  indicator_name: string;
  universe: string;
  universe_size: number;
  universe_label?: string;
  timeframe: string;
  status: string;
  stage?: string | null;
  progress_pct: number;
  processed_count: number;
  total_count: number;
  success_count?: number;
  failed_count?: number;
  skipped_count?: number;
  matched_count?: number;
  as_of?: string | null;
  benchmark_symbol?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  elapsed_seconds?: number | null;
  error_code?: string | null;
  error_detail?: string | null;
  summary?: Record<string, unknown> | null;
  outputs?: IndicatorOutputDef[];
  filters?: IndicatorFilter[];
  entry_conditions?: Array<{ id?: string; name: string }>;
};

export type IndicatorScanRow = {
  symbol: string;
  display_name?: string | null;
  exchange?: string;
  timeframe?: string;
  as_of?: string | null;
  status: string;
  matched: boolean;
  outputs: Record<string, number | boolean | string | null>;
  ohlcv?: Record<string, number | null>;
  error_detail?: string | null;
  bar_count?: number | null;
  return_pct?: number | null;
  signal?: string;
  rank?: number;
  company?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
};

export async function validateIndicatorSource(sourceCode: string, timeframe = "1D"): Promise<IndicatorValidation> {
  const response = await fetchWithAuth("/indicators/validate", {
    method: "POST",
    body: JSON.stringify({ source_code: sourceCode, timeframe }),
  });
  if (!response.ok) throw new Error(await parseError(response, "Unable to validate indicator."));
  return response.json();
}

export async function fetchIndicatorTemplate(): Promise<IndicatorValidation> {
  const response = await fetchWithAuth("/indicators/template");
  if (!response.ok) throw new Error(await parseError(response, "Unable to load indicator template."));
  return response.json();
}

export type LabIndicatorTemplate = IndicatorValidation & {
  strategy_id: string;
  number?: string;
  rank?: string;
  pine_kind?: string;
};

export async function fetchIndicatorTemplates(): Promise<LabIndicatorTemplate[]> {
  const response = await fetchWithAuth("/indicators/templates");
  if (!response.ok) throw new Error(await parseError(response, "Unable to load research-lab templates."));
  const body = await response.json();
  return Array.isArray(body?.templates) ? body.templates : [];
}

export async function seedLabIndicators(): Promise<{
  created: string[];
  skipped: string[];
  count: number;
  indicators: SavedIndicator[];
}> {
  const response = await fetchWithAuth("/indicators/seed-lab", { method: "POST" });
  if (!response.ok) throw new Error(await parseError(response, "Unable to save research-lab strategies."));
  return response.json();
}

export async function createIndicator(payload: {
  name: string;
  description?: string;
  source_code: string;
  timeframe?: string;
}): Promise<SavedIndicator> {
  const response = await fetchWithAuth("/indicators", { method: "POST", body: JSON.stringify(payload) });
  if (!response.ok) throw new Error(await parseError(response, "Unable to save indicator."));
  return response.json();
}

export async function updateIndicator(
  id: string,
  payload: { name: string; description?: string; source_code: string; timeframe?: string },
): Promise<SavedIndicator> {
  const response = await fetchWithAuth(`/indicators/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await parseError(response, "Unable to update indicator."));
  return response.json();
}

export async function fetchIndicators(): Promise<SavedIndicator[]> {
  const response = await fetchWithAuth("/indicators");
  if (!response.ok) throw new Error(await parseError(response, "Unable to load indicators."));
  const body = await response.json();
  return Array.isArray(body?.indicators) ? body.indicators : [];
}

export async function fetchIndicator(id: string): Promise<SavedIndicator> {
  const response = await fetchWithAuth(`/indicators/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(await parseError(response, "Unable to load indicator."));
  return response.json();
}

export async function duplicateIndicator(id: string): Promise<SavedIndicator> {
  const response = await fetchWithAuth(`/indicators/${encodeURIComponent(id)}/duplicate`, { method: "POST" });
  if (!response.ok) throw new Error(await parseError(response, "Unable to duplicate indicator."));
  return response.json();
}

export async function archiveIndicator(id: string): Promise<void> {
  const response = await fetchWithAuth(`/indicators/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await parseError(response, "Unable to archive indicator."));
}

export async function startIndicatorScan(
  indicatorId: string,
  payload: {
    universe_id?: string;
    timeframe?: string;
    scan_date?: string | null;
    input_overrides?: Record<string, unknown>;
    filters?: IndicatorFilter[];
    sort?: { field: string; direction: string };
  },
): Promise<IndicatorScanStatus> {
  const response = await fetchWithAuth(`/indicators/${encodeURIComponent(indicatorId)}/scans`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (response.status === 409) {
    const body = await response.json().catch(() => ({}));
    const detail = body?.detail && typeof body.detail === "object" ? body.detail : body;
    if (detail?.scan_id) {
      return {
        id: String(detail.id || detail.scan_id),
        scan_id: String(detail.scan_id),
        status: String(detail.status || "running"),
        universe_size: Number(detail.universe_size || 755),
        total_count: Number(detail.total_count || detail.universe_size || 755),
        processed_count: Number(detail.processed_count || 0),
        progress_pct: Number(detail.progress_pct || 0),
        indicator_name: String(detail.indicator_name || ""),
        universe: String(detail.universe || "nse-755"),
        timeframe: String(detail.timeframe || "1D"),
      };
    }
  }
  if (!response.ok) throw new Error(await parseError(response, "Unable to start indicator scan."));
  return response.json();
}

export async function fetchIndicatorScan(scanId: string): Promise<IndicatorScanStatus> {
  const response = await fetchWithAuth(`/indicator-scans/${encodeURIComponent(scanId)}`);
  if (!response.ok) throw new Error(await parseError(response, "Unable to load scan status."));
  return response.json();
}

export async function fetchIndicatorScanResult(
  scanId: string,
  symbol: string,
): Promise<
  IndicatorScanRow & {
    scan_id?: string;
    indicator_name?: string;
    filters?: IndicatorFilter[];
    filter_results?: Array<{ name: string; passed: boolean }>;
    signal?: string;
    company?: string | null;
    entry_price?: number | null;
    exit_price?: number | null;
    return_pct?: number | null;
    close?: number | null;
    evaluation_date?: string | null;
    source?: string;
  }
> {
  const response = await fetchWithAuth(
    `/indicator-scans/${encodeURIComponent(scanId)}/results/${encodeURIComponent(symbol)}`,
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load indicator scan result."));
  return response.json();
}

export async function fetchIndicatorScanResults(
  scanId: string,
  params: {
    page?: number;
    page_size?: number;
    search?: string;
    matched_only?: boolean;
    sort?: string;
    direction?: string;
    signal?: string;
    return_bucket?: string;
  } = {},
): Promise<{ total: number; page: number; page_size: number; outputs: string[]; results: IndicatorScanRow[]; matched_count?: number }> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.search) qs.set("search", params.search);
  if (params.matched_only === false) qs.set("matched_only", "false");
  if (params.sort) qs.set("sort", params.sort);
  if (params.direction) qs.set("direction", params.direction);
  if (params.signal) qs.set("signal", params.signal);
  if (params.return_bucket) qs.set("return_bucket", params.return_bucket);
  const response = await fetchWithAuth(`/indicator-scans/${encodeURIComponent(scanId)}/results?${qs.toString()}`);
  if (!response.ok) throw new Error(await parseError(response, "Unable to load scan results."));
  return response.json();
}

export async function fetchIndicatorScanDiagnostics(scanId: string): Promise<Record<string, unknown>> {
  const response = await fetchWithAuth(`/indicator-scans/${encodeURIComponent(scanId)}/diagnostics`);
  if (!response.ok) throw new Error(await parseError(response, "Unable to load diagnostics."));
  return response.json();
}

export async function exportIndicatorScanCsv(scanId: string): Promise<void> {
  const response = await fetchWithAuth(`/indicator-scans/${encodeURIComponent(scanId)}/results/export`);
  if (!response.ok) throw new Error(await parseError(response, "Unable to export CSV."));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${scanId}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function cancelIndicatorScan(scanId: string): Promise<void> {
  const response = await fetchWithAuth(`/indicator-scans/${encodeURIComponent(scanId)}/cancel`, { method: "POST" });
  if (!response.ok) throw new Error(await parseError(response, "Unable to cancel scan."));
}

export type IndicatorBacktestOptions = {
  start_date?: string;
  end_date?: string;
  initial_capital?: number;
  universe_id?: string;
  engine?: "LEAN" | "EXISTING";
  symbols?: string[];
  max_positions?: number;
  parameters?: Record<string, unknown>;
};

export type LeanJobStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type LeanTrade = {
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

export type LeanEquityPoint = {
  date: string;
  equity: number;
  cash: number;
  investedCapital: number;
  drawdown: number;
  drawdownPct: number;
};

export type LeanPositionHistory = {
  date: string;
  symbol: string;
  quantity: number;
  averagePrice: number;
  marketValue: number;
  unrealizedPnL: number;
  realizedPnL: number;
};

export type LeanBacktestSummary = {
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

export type LeanBacktestResult = {
  jobId: string;
  strategyId: string;
  strategyName: string;
  engine: string;
  status: LeanJobStatus;
  startDate: string;
  endDate: string;
  symbols: string[];
  summary: LeanBacktestSummary;
  trades: LeanTrade[];
  equityCurve: LeanEquityPoint[];
  positions: LeanPositionHistory[];
  debugTrace?: unknown[] | null;
  runtimeMetrics: Record<string, unknown>;
  validationParity?: Record<string, unknown> | null;
};

export type IndicatorBacktestJob = {
  jobId: string;
  strategyId: string;
  strategyName: string;
  userId?: string | null;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  status: LeanJobStatus;
  progressPct: number;
  stage: string;
  error?: string | null;
  request: Record<string, unknown>;
  result?: LeanBacktestResult | null;
};

export async function startIndicatorBacktest(
  indicatorId: string,
  options: IndicatorBacktestOptions = {},
): Promise<IndicatorBacktestJob> {
  const response = await fetchWithAuth(`/indicators/${encodeURIComponent(indicatorId)}/backtest`, {
    method: "POST",
    body: JSON.stringify({
      start_date: options.start_date || undefined,
      end_date: options.end_date || undefined,
      initial_capital: options.initial_capital ?? 100000.0,
      universe_id: options.universe_id || "nse-755",
      engine: options.engine || "LEAN",
      symbols: options.symbols || undefined,
      max_positions: options.max_positions ?? 10,
      parameters: options.parameters || {},
    }),
  });
  if (!response.ok) throw new Error(await parseError(response, "Unable to start LEAN backtest."));
  return response.json();
}

export async function fetchIndicatorBacktest(
  indicatorId: string,
  jobId: string,
): Promise<IndicatorBacktestJob> {
  const response = await fetchWithAuth(
    `/indicators/${encodeURIComponent(indicatorId)}/backtests/${encodeURIComponent(jobId)}`,
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load backtest status."));
  return response.json();
}

export async function fetchIndicatorBacktestResults(
  indicatorId: string,
  jobId: string,
): Promise<LeanBacktestResult> {
  const response = await fetchWithAuth(
    `/indicators/${encodeURIComponent(indicatorId)}/backtests/${encodeURIComponent(jobId)}/results`,
  );
  if (!response.ok) throw new Error(await parseError(response, "Unable to load backtest results."));
  return response.json();
}

