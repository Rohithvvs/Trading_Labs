import type { IndicatorFilter, IndicatorScanRow, IndicatorScanStatus, SavedIndicator } from "../api_indicator_scanner";

export const INDICATOR_SCANNER_STATE_KEY = "indicator_scanner_state_v1";
export const INDICATOR_SCANNER_LAST_SCAN_ID_KEY = "indicator_scanner_last_scan_id";

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
};

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

export function loadIndicatorScannerState(): IndicatorScannerPersistedState | null {
  try {
    const raw = localStorage.getItem(INDICATOR_SCANNER_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const scan = asObject<IndicatorScanStatus>(parsed.scan);
    const applied = asObject<SavedIndicator>(parsed.appliedIndicator);
    return {
      selectedId: typeof parsed.selectedId === "string" ? parsed.selectedId : "",
      appliedIndicator: applied?.id ? applied : null,
      indicators: uniqueIndicatorsByIdAndName(Array.isArray(parsed.indicators) ? parsed.indicators : []),
      timeframe: typeof parsed.timeframe === "string" && parsed.timeframe ? parsed.timeframe : "1D",
      scanDate: typeof parsed.scanDate === "string" ? parsed.scanDate : "",
      filters: Array.isArray(parsed.filters) ? parsed.filters : [],
      scan,
      results: Array.isArray(parsed.results) ? parsed.results : [],
      total: typeof parsed.total === "number" ? parsed.total : 0,
      page: typeof parsed.page === "number" && parsed.page > 0 ? parsed.page : 1,
      sortField: typeof parsed.sortField === "string" && parsed.sortField ? parsed.sortField : "symbol",
      sortDir: parsed.sortDir === "desc" ? "desc" : "asc",
      search: typeof parsed.search === "string" ? parsed.search : "",
      matchedOnly: parsed.matchedOnly !== false,
      diagnostics: asObject<Record<string, unknown>>(parsed.diagnostics),
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
  const payload: IndicatorScannerPersistedState = {
    ...state,
    indicators: uniqueIndicatorsByIdAndName(state.indicators),
    appliedIndicator: state.appliedIndicator?.id ? state.appliedIndicator : null,
  };
  try {
    localStorage.setItem(INDICATOR_SCANNER_STATE_KEY, JSON.stringify(payload));
    const scanId = payload.scan?.scan_id || payload.scan?.id;
    if (scanId) localStorage.setItem(INDICATOR_SCANNER_LAST_SCAN_ID_KEY, scanId);
  } catch {
    try {
      const slim: IndicatorScannerPersistedState = {
        ...payload,
        results: [],
        diagnostics: null,
        indicators: payload.indicators.slice(0, 30),
      };
      localStorage.setItem(INDICATOR_SCANNER_STATE_KEY, JSON.stringify(slim));
    } catch {
      /* quota / private mode */
    }
  }
}
