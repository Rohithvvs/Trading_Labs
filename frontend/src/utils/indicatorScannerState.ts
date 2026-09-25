import type { IndicatorFilter, IndicatorScanRow, IndicatorScanStatus, SavedIndicator } from "../api_indicator_scanner";

export const INDICATOR_SCANNER_STATE_KEY = "indicator_scanner_state_v1";
export const INDICATOR_SCANNER_LAST_SCAN_ID_KEY = "indicator_scanner_last_scan_id";

/** Last completed (or in-progress) scan kept for one indicator strategy. */
export type IndicatorScanCacheEntry = {
  scan: IndicatorScanStatus;
  results: IndicatorScanRow[];
  total: number;
  page: number;
  scanDate: string;
  filters: IndicatorFilter[];
  diagnostics: Record<string, unknown> | null;
};

export type IndicatorScannerPersistedState = {
  selectedId: string;
  appliedIndicator: SavedIndicator | null;
  indicators: SavedIndicator[];
  timeframe: string;
  scanDate: string;
  filters: IndicatorFilter[];
  scan: IndicatorScanStatus | null;
  results: IndicatorScanRow[];
  total: number;
  page: number;
  sortField: string;
  sortDir: "asc" | "desc";
  search: string;
  matchedOnly: boolean;
  diagnostics: Record<string, unknown> | null;
  /** Prior scans keyed by indicator id, so switching strategies restores the last run. */
  scansByIndicator?: Record<string, IndicatorScanCacheEntry>;
};

const MAX_CACHED_STRATEGIES = 24;
const MAX_CACHED_ROWS = 100;

function indicatorTimestamp(item: SavedIndicator): string {
  return item.updated_at || item.last_used_at || item.created_at || "";
}

/** Keep one record per indicator id. Later/newer rows win when ids collide. */
export function uniqueIndicatorsById(list: SavedIndicator[] | null | undefined): SavedIndicator[] {
  const byId = new Map<string, SavedIndicator>();
  for (const item of list || []) {
    const id = String(item?.id ?? "").trim();
    if (!id) continue;
    const prev = byId.get(id);
    if (!prev || indicatorTimestamp(item) >= indicatorTimestamp(prev)) {
      byId.set(id, item);
    }
  }
  return Array.from(byId.values());
}

/**
 * Unique by id, then collapse identical names so the dropdown never lists
 * "52-Week High Breakout [SCAN]" twice. Later/newer rows win.
 */
export function uniqueIndicatorsByIdAndName(list: SavedIndicator[] | null | undefined): SavedIndicator[] {
  const unique = uniqueIndicatorsById(list);
  const byName = new Map<string, SavedIndicator>();
  const unnamed: SavedIndicator[] = [];
  for (const item of unique) {
    const key = (item.name || "").trim().toLowerCase();
    if (!key) {
      unnamed.push(item);
      continue;
    }
    const prev = byName.get(key);
    if (!prev || indicatorTimestamp(item) >= indicatorTimestamp(prev)) {
      byName.set(key, item);
    }
  }
  return [...byName.values(), ...unnamed];
}

function asObject<T>(value: unknown): T | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as T;
}

function cacheRank(entry: IndicatorScanCacheEntry): number {
  const raw = entry.scan.completed_at || entry.scan.started_at || "";
  const ms = Date.parse(raw);
  return Number.isFinite(ms) ? ms : 0;
}

export function trimIndicatorScanCache(
  cache: Record<string, IndicatorScanCacheEntry> | null | undefined,
  keepId = "",
): Record<string, IndicatorScanCacheEntry> {
  const source = cache || {};
  const entries = Object.entries(source).filter(([, entry]) => Boolean(entry?.scan?.scan_id));
  entries.sort((a, b) => cacheRank(b[1]) - cacheRank(a[1]));
  const kept = entries.slice(0, MAX_CACHED_STRATEGIES);
  if (keepId && source[keepId]?.scan?.scan_id && !kept.some(([id]) => id === keepId)) {
    if (kept.length >= MAX_CACHED_STRATEGIES) kept.pop();
    kept.push([keepId, source[keepId]]);
  }
  return Object.fromEntries(
    kept.map(([id, entry]) => [id, { ...entry, results: (entry.results || []).slice(0, MAX_CACHED_ROWS) }]),
  );
}

function parseScanCache(value: unknown): Record<string, IndicatorScanCacheEntry> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const out: Record<string, IndicatorScanCacheEntry> = {};
  for (const [key, raw] of Object.entries(value as Record<string, unknown>)) {
    const entry = asObject<Record<string, unknown>>(raw);
    const scan = asObject<IndicatorScanStatus>(entry?.scan);
    const id = key.trim();
    if (!id || !scan?.scan_id) continue;
    out[id] = {
      scan: scan.indicator_id ? scan : { ...scan, indicator_id: id },
      results: Array.isArray(entry?.results) ? (entry.results as IndicatorScanRow[]) : [],
      total: typeof entry?.total === "number" ? entry.total : 0,
      page: typeof entry?.page === "number" && entry.page > 0 ? entry.page : 1,
      scanDate: typeof entry?.scanDate === "string" ? entry.scanDate : "",
      filters: Array.isArray(entry?.filters) ? (entry.filters as IndicatorFilter[]) : [],
      diagnostics: asObject<Record<string, unknown>>(entry?.diagnostics),
    };
  }
  return out;
}

export function loadIndicatorScannerState(): IndicatorScannerPersistedState | null {
  try {
    const raw = localStorage.getItem(INDICATOR_SCANNER_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const selectedId = typeof parsed.selectedId === "string" ? parsed.selectedId : "";
    let scan = asObject<IndicatorScanStatus>(parsed.scan);
    if (scan && !scan.indicator_id && selectedId) {
      scan = { ...scan, indicator_id: selectedId };
    }
    const applied = asObject<SavedIndicator>(parsed.appliedIndicator);
    const results = Array.isArray(parsed.results) ? parsed.results : [];
    const total = typeof parsed.total === "number" ? parsed.total : 0;
    const page = typeof parsed.page === "number" && parsed.page > 0 ? parsed.page : 1;
    const scanDate = typeof parsed.scanDate === "string" ? parsed.scanDate : "";
    const filters = Array.isArray(parsed.filters) ? parsed.filters : [];
    const diagnostics = asObject<Record<string, unknown>>(parsed.diagnostics);
    const scansByIndicator = parseScanCache(parsed.scansByIndicator);
    const owner = String(scan?.indicator_id || selectedId || "");
    if (scan?.scan_id && owner) {
      scansByIndicator[owner] = {
        scan,
        results,
        total,
        page,
        scanDate,
        filters,
        diagnostics,
      };
    }
    return {
      selectedId,
      appliedIndicator: applied?.id ? applied : null,
      indicators: uniqueIndicatorsByIdAndName(Array.isArray(parsed.indicators) ? parsed.indicators : []),
      timeframe: typeof parsed.timeframe === "string" && parsed.timeframe ? parsed.timeframe : "1D",
      scanDate,
      filters,
      scan,
      results,
      total,
      page,
      sortField: typeof parsed.sortField === "string" && parsed.sortField ? parsed.sortField : "symbol",
      sortDir: parsed.sortDir === "desc" ? "desc" : "asc",
      search: typeof parsed.search === "string" ? parsed.search : "",
      matchedOnly: parsed.matchedOnly !== false,
      diagnostics,
      scansByIndicator,
    };
  } catch {
    try {
      localStorage.removeItem(INDICATOR_SCANNER_STATE_KEY);
    } catch {
      /* ignore */
    }
    return null;
  }
}

export function saveIndicatorScannerState(state: IndicatorScannerPersistedState): void {
  const scansByIndicator = { ...(state.scansByIndicator || {}) };
  const owner = String(state.scan?.indicator_id || state.selectedId || "");
  if (state.scan?.scan_id && owner) {
    const scan = state.scan.indicator_id ? state.scan : { ...state.scan, indicator_id: owner };
    scansByIndicator[owner] = {
      scan,
      results: state.results || [],
      total: state.total || 0,
      page: state.page || 1,
      scanDate: state.scanDate || "",
      filters: state.filters || [],
      diagnostics: state.diagnostics || null,
    };
  }
  const payload: IndicatorScannerPersistedState = {
    ...state,
    scan: state.scan?.scan_id && owner ? scansByIndicator[owner].scan : state.scan,
    indicators: uniqueIndicatorsByIdAndName(state.indicators),
    appliedIndicator: state.appliedIndicator?.id ? state.appliedIndicator : null,
    scansByIndicator: trimIndicatorScanCache(scansByIndicator, owner),
  };
  try {
    localStorage.setItem(INDICATOR_SCANNER_STATE_KEY, JSON.stringify(payload));
    const scanId = payload.scan?.scan_id || payload.scan?.id;
    if (scanId) localStorage.setItem(INDICATOR_SCANNER_LAST_SCAN_ID_KEY, scanId);
  } catch {
    try {
      const slimScans: Record<string, IndicatorScanCacheEntry> = {};
      for (const [id, entry] of Object.entries(payload.scansByIndicator || {})) {
        slimScans[id] = { ...entry, results: [], diagnostics: null };
      }
      const slim: IndicatorScannerPersistedState = {
        ...payload,
        results: [],
        diagnostics: null,
        indicators: payload.indicators.slice(0, 30),
        scansByIndicator: slimScans,
      };
      localStorage.setItem(INDICATOR_SCANNER_STATE_KEY, JSON.stringify(slim));
    } catch {
      /* quota / private mode */
    }
  }
}
