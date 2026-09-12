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
  validation_status: string;
  validation_errors?: IndicatorIssue[];
  required_bars: number;
  created_at?: string | null;
  updated_at?: string | null;
  last_used_at?: string | null;
  is_archived?: boolean;
};

export type IndicatorFilter = {
  field: string;
  operator: string;
  value?: string | number | boolean | null;
  low?: number | null;
  high?: number | null;
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

export async function fetchIndicatorScanResults(
  scanId: string,
  params: {
    page?: number;
    page_size?: number;
    search?: string;
    matched_only?: boolean;
    sort?: string;
    direction?: string;
  } = {},
): Promise<{ total: number; page: number; page_size: number; outputs: string[]; results: IndicatorScanRow[]; matched_count?: number }> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.search) qs.set("search", params.search);
  if (params.matched_only === false) qs.set("matched_only", "false");
  if (params.sort) qs.set("sort", params.sort);
  if (params.direction) qs.set("direction", params.direction);
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
