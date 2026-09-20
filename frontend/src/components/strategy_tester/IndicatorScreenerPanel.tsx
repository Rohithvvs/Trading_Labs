import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  archiveIndicator,
  cancelIndicatorScan,
  duplicateIndicator,
  exportIndicatorScanCsv,
  fetchIndicatorBacktest,
  fetchIndicatorBacktestResults,
  fetchIndicatorScan,
  fetchIndicatorScanDiagnostics,
  fetchIndicatorScanResults,
  fetchIndicators,
  seedLabIndicators,
  startIndicatorBacktest,
  startIndicatorScan,
  type IndicatorBacktestJob,
  type IndicatorBacktestOptions,
  type IndicatorFilter,
  type IndicatorScanRow,
  type IndicatorScanStatus,
  type LeanBacktestResult,
  type SavedIndicator,
} from "../../api_indicator_scanner";
import { fetchStrategyCatalog } from "../../api_strategy_tester";
import { currentCashSessionIST } from "../../utils/tradingHours";
import { navigateToStock } from "../../utils/stockNavigation";
import {
  absorbFromParsedDefinition,
  absorbScreenFilters,
  defaultColumnFilter,
  isAggregateSignalFilter,
  isTvStyleSignalEqualsOneOnPricePlot,
  normalizePineScreenerFilters,
  preferredScreenerColumn,
} from "../../utils/indicatorAbsorb";
import {
  loadIndicatorScannerState,
  saveIndicatorScannerState,
  uniqueIndicatorsByIdAndName,
} from "../../utils/indicatorScannerState";
import { formatDateTime, formatDuration } from "./RunStatusRow";
import { StrategyBuilderCard } from "./StrategyBuilderCard";
import { TopReturnsCard } from "./TopReturnsCard";
import { FilterAnalyticsCard } from "./FilterAnalyticsCard";
import { FilterFunnelCard } from "./FilterFunnelCard";
import { SignalDistributionCard } from "./SignalDistributionCard";
import { AllStockResultsTable } from "./AllStockResultsTable";
import { ColumnsConfigModal } from "./ColumnsConfigModal";
import { IndicatorLeanBacktestModal } from "./IndicatorLeanBacktestModal";
import { IndicatorLeanBacktestView } from "./IndicatorLeanBacktestView";
import { mapIndicatorResultToStock } from "../../utils/indicatorScanDetail";
import { ScreenerColumnChip } from "./signalSetup/ScreenerColumnChip";
import { IndicatorCustomDropdown } from "./IndicatorCustomDropdown";
import type { FilterStat, FunnelStep, RankedReturn, StrategyResultRow } from "../../api_strategy_tester";
import type { NavigateFunction } from "react-router-dom";

const HEADER_SCAN_SLOT_ID = "ind-header-scan-slot";

export type UniverseRow = { symbol: string; company?: string | null };

export type IndicatorScreenerPanelProps = {
  universeCount: number;
  universeRows?: UniverseRow[];
  appliedIndicator: SavedIndicator | null;
  navigate: NavigateFunction;
  onAddIndicator: () => void;
  onEditIndicator: (indicator: SavedIndicator) => void;
  notify: (opts: { title: string; message?: string; type?: "success" | "error" | "warning" | "info" }) => void;
};

const SIGNAL_FIELD = "52W Breakout Signal";
const VALUELESS_OPS = new Set(["is_true", "is_false", "is_null", "is_not_null"]);

function absorbedFromIndicator(indicator: SavedIndicator | null | undefined) {
  return absorbFromParsedDefinition(indicator?.parsed_definition);
}

function upsertIndicator(list: SavedIndicator[], item: SavedIndicator | null | undefined): SavedIndicator[] {
  if (!item?.id) return uniqueIndicatorsByIdAndName(list);
  const idx = list.findIndex((row) => row.id === item.id);
  const next = idx === -1 ? [item, ...list] : list.map((row, i) => (i === idx ? item : row));
  return uniqueIndicatorsByIdAndName(next);
}

/** Today's NSE cash session from midnight IST; weekends/holidays use the last completed session. */
function currentScanSessionIST(): string {
  return currentCashSessionIST();
}

const FETCHING_DATA_STAGES = new Set([
  "preparing",
  "fetching_current_data",
  "loading_benchmark",
  "repairing_market_data",
  "loading_market_data",
]);

function isFetchingCurrentData(status: IndicatorScanStatus | null): boolean {
  if (!status) return false;
  if (status.status === "queued") return true;
  return FETCHING_DATA_STAGES.has(String(status.stage || ""));
}

function scanStatusText(status: IndicatorScanStatus | null, hasIndicator: boolean): string {
  if (!status) {
    return hasIndicator
      ? "Ready to scan. Click Scan to evaluate the universe."
      : "Add or apply an indicator, then click Scan.";
  }
  const total = status.total_count || status.universe_size || 755;
  if (status.status === "queued" || status.stage === "preparing") return "Preparing scan…";
  if (isFetchingCurrentData(status)) return "Fetching current market data…";
  if (status.status === "running" || status.stage === "scanning") {
    return `Scanning ${total} symbols: ${status.processed_count} / ${total}`;
  }
  if (status.stage === "applying_filters") return "Applying filters…";
  if (status.status === "completed") {
    const matched = status.matched_count ?? 0;
    if (matched === 0) {
      return "No symbols match your filters. Ease up on those filters or reset them.";
    }
    return `Scan complete: ${matched} stocks matched.`;
  }
  if (status.status === "failed") return status.error_detail || "Scan failed.";
  if (status.status === "cancelled") return "Scan cancelled.";
  return status.stage || status.status;
}

function cleanFilters(filters: IndicatorFilter[]): IndicatorFilter[] {
  return filters
    .filter((filter) => Boolean(filter.field))
    .map((filter) => {
      const cleaned: IndicatorFilter = { field: filter.field, operator: filter.operator || "=" };
      if (filter.condition) cleaned.condition = filter.condition;
      if (filter.source) cleaned.source = filter.source;
      if (filter.setup_type) cleaned.setup_type = filter.setup_type;
      if (filter.compare_field) cleaned.compare_field = filter.compare_field;
      if (filter.operator === "between" || filter.operator === "outside") {
        cleaned.low = filter.low;
        cleaned.high = filter.high;
      } else if (!VALUELESS_OPS.has(filter.operator) && !filter.compare_field) {
        cleaned.value = filter.value;
      }
      return cleaned;
    })
    .filter((filter) => {
      if (VALUELESS_OPS.has(filter.operator)) return true;
      if (filter.compare_field) return true;
      if (filter.operator === "between" || filter.operator === "outside") {
        return filter.low !== undefined && filter.low !== null && filter.high !== undefined && filter.high !== null;
      }
      return filter.value !== undefined && filter.value !== null && filter.value !== "";
    });
}

function isScanActive(status: IndicatorScanStatus | null): boolean {
  if (!status) return false;
  return status.status === "queued" || status.status === "running" || status.status === "cancelling";
}

const STALE_SCAN_MS = 10 * 60 * 1000;

function isFreshActiveScan(status: IndicatorScanStatus | null): boolean {
  if (!isScanActive(status)) return false;
  if (!status?.started_at) return true;
  const started = Date.parse(status.started_at);
  if (!Number.isFinite(started)) return true;
  return Date.now() - started < STALE_SCAN_MS;
}

function scanBarDate(scan: IndicatorScanStatus | null, fallback: string): string {
  const summary = scan?.summary && typeof scan.summary === "object" ? scan.summary : null;
  const fromSummary = summary && typeof summary.scan_as_of === "string" ? summary.scan_as_of : "";
  return fromSummary || scan?.as_of || fallback || "—";
}

function scanDateMismatch(scan: IndicatorScanStatus | null): boolean {
  const summary = scan?.summary && typeof scan.summary === "object" ? scan.summary : null;
  const counts = summary?.scan_date_counts;
  if (!counts || typeof counts !== "object" || Array.isArray(counts)) return false;
  return Object.keys(counts).length > 1;
}

function IndicatorRunStatusCard({
  scan,
  scanning,
  fallbackAsOf,
  universeCount = 755,
}: {
  scan: IndicatorScanStatus | null;
  scanning: boolean;
  fallbackAsOf: string;
  universeCount?: number;
}) {
  const processed = scan?.processed_count || (scan?.status === "completed" ? (universeCount || 755) : 0);
  const total = scan?.total_count || scan?.universe_size || universeCount || 755;
  const pct = scan?.progress_pct ?? (total > 0 ? Math.round((processed / total) * 100) : scan?.status === "completed" ? 100 : 0);
  const matched = scan?.matched_count ?? 0;
  const failedCalc = scan?.failed_count ?? 0;
  const skipped = scan?.skipped_count ?? 0;
  const unmatched = Math.max(0, (scan?.success_count ?? 0) - matched);
  const failed = unmatched + failedCalc;
  const summary = (scan?.summary && typeof scan.summary === "object" ? scan.summary : {}) as Record<string, unknown>;
  const scannedCount = Number(summary.stocks_scanned ?? scan?.total_count ?? total);
  const posCount = Number(summary.positive_returns ?? 0);
  const negCount = Number(summary.negative_returns ?? 0);
  const flatCount = Number(summary.flat_returns ?? Math.max(0, scannedCount - posCount - negCount));
  const avgReturn = typeof summary.average_return === "number" ? summary.average_return : 0;
  const matchedPct = scannedCount > 0 ? ((matched / scannedCount) * 100).toFixed(1) : "0.0";
  const failedPct = scannedCount > 0 ? ((failed / scannedCount) * 100).toFixed(1) : "0.0";
  const skippedPct = scannedCount > 0 ? ((skipped / scannedCount) * 100).toFixed(1) : "0.0";
  const posPct = scannedCount > 0 ? ((posCount / scannedCount) * 100).toFixed(1) : "0.0";
  const negPct = scannedCount > 0 ? ((negCount / scannedCount) * 100).toFixed(1) : "0.0";
  const status = scanning
    ? "running"
    : !scan
      ? "idle"
      : scan.status === "failed" || scan.status === "cancelled"
        ? scan.status
        : scan.status === "completed"
          ? "completed"
          : scan.status;
  return (
    <div className="st-status-row" data-testid="indicator-scan-status">
      <div className="st-card" data-testid="card-run-info">
        <div className="st-card-title">
          <span className="st-run-id-text">RUN ID: {scan?.scan_id || scan?.id || "—"}</span>
          {status === "running" || status === "queued" || status === "cancelling" ? (
            <span className="st-status-badge st-status-badge--running">⏳ Running</span>
          ) : status === "failed" ? (
            <span className="st-status-badge st-status-badge--failed">✕ Failed</span>
          ) : status === "cancelled" ? (
            <span className="st-status-badge st-status-badge--failed">✕ Cancelled</span>
          ) : status === "completed" ? (
            <span className="st-status-badge st-status-badge--completed">✓ Completed</span>
          ) : (
            <span className="st-status-badge">Ready to scan</span>
          )}
        </div>
        <div className="st-run-meta-list">
          <div>
            <span>Started:</span>
            <span className="val">{scan ? formatDateTime(scan.started_at) : "—"}</span>
          </div>
          <div>
            <span>Completed:</span>
            <span className="val">{scanning || !scan ? "—" : formatDateTime(scan.completed_at)}</span>
          </div>
          <div>
            <span>Duration:</span>
            <span className="val">{scan ? formatDuration(scan.elapsed_seconds) : "00:00:00"}</span>
          </div>
          <div>
            <span>Scan Date:</span>
            <span className="val" data-testid="run-scan-as-of">
              {scan ? scanBarDate(scan, fallbackAsOf) : (fallbackAsOf || currentCashSessionIST())}
            </span>
          </div>
        </div>
        {scan && scanDateMismatch(scan) ? (
          <p className="st-scan-bar-warning" data-testid="scan-date-mismatch">
            Symbols were evaluated on different session dates. Re-run after market data is filled so every name uses the same last 1D bar as TradingView.
          </p>
        ) : null}
        {scan && typeof scan.summary?.scan_bar_note === "string" && scan.summary.scan_bar_note ? (
          <p className="st-scan-bar-note" data-testid="scan-bar-note">
            {String(scan.summary.scan_bar_note)}
          </p>
        ) : null}
        {scan && typeof scan.summary?.scan_bar_warning === "string" && scan.summary.scan_bar_warning ? (
          <p className="st-scan-bar-warning" data-testid="scan-bar-warning">
            {String(scan.summary.scan_bar_warning)}
          </p>
        ) : null}
        {scan?.status === "failed" && scan.error_detail ? (
          <p className="st-scan-bar-warning">{scan.error_detail}</p>
        ) : null}
      </div>
      <div className="st-card" data-testid="card-scan-progress">
        <div className="st-card-title">Scan Progress</div>
        <div className="st-progress-huge">{pct}%</div>
        <div className="st-progress-bar-wrap">
          <div className="st-progress-bar-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
        </div>
        <div className="st-progress-sub">
          {scanning && scan && isFetchingCurrentData(scan)
            ? "Fetching current market data…"
            : `${processed} / ${total} stocks processed`}
          {scanning && scan?.stage && scan.stage !== "scanning" && !isFetchingCurrentData(scan)
            ? ` · ${String(scan.stage).replace(/_/g, " ")}`
            : ""}
        </div>
        <div className="st-signal-chips">
          <div className="st-signal-chip">
            <span className="st-signal-chip-label buy">● MATCHED</span>
            <span className="st-signal-chip-val buy">{matched}</span>
          </div>
          <div className="st-signal-chip">
            <span className="st-signal-chip-label reject">○ REJECTED</span>
            <span className="st-signal-chip-val reject">{failed}</span>
          </div>
          <div className="st-signal-chip">
            <span className="st-signal-chip-label watch">★ SKIPPED</span>
            <span className="st-signal-chip-val watch">{skipped}</span>
          </div>
        </div>
      </div>
      <div className="st-card" data-testid="card-run-summary">
        <div className="st-card-title">Run Summary</div>
        <div className="st-summary-grid">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div className="st-summary-row">
              <span className="st-summary-label">Stocks Scanned:</span>
              <span className="st-summary-val">{scannedCount}</span>
            </div>
            <div className="st-summary-row">
              <span className="st-summary-label">Matched:</span>
              <span className="st-summary-val green">{matched} ({matchedPct}%)</span>
            </div>
            <div className="st-summary-row">
              <span className="st-summary-label">Rejected:</span>
              <span className="st-summary-val red">{failed} ({failedPct}%)</span>
            </div>
            <div className="st-summary-row">
              <span className="st-summary-label">Skipped:</span>
              <span className="st-summary-val yellow">{skipped} ({skippedPct}%)</span>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div className="st-summary-row">
              <span className="st-summary-label">Positive:</span>
              <span className="st-summary-val green">{posCount} ({posPct}%)</span>
            </div>
            <div className="st-summary-row">
              <span className="st-summary-label">Negative:</span>
              <span className="st-summary-val red">{negCount} ({negPct}%)</span>
            </div>
            <div className="st-summary-row">
              <span className="st-summary-label">Flat Returns:</span>
              <span className="st-summary-val" style={{ color: "#94a3b8" }}>{flatCount}</span>
            </div>
            <div className="st-summary-row">
              <span className="st-summary-label">Avg Return:</span>
              <span className={`st-summary-val ${avgReturn >= 0 ? "green" : "red"}`}>
                {avgReturn > 0 ? `+${avgReturn.toFixed(2)}%` : `${Number(avgReturn).toFixed(2)}%`}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function parseUniverseCsv(text: string): UniverseRow[] {
  const rows: UniverseRow[] = [];
  const seen = new Set<string>();
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || /^company name/i.test(line)) continue;
    const parts = line.split(",");
    const symbol = (parts[2] || "").trim().toUpperCase();
    const company = (parts[0] || "").trim();
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    rows.push({ symbol, company });
  }
  return rows;
}

async function loadUniverseRows(provided?: UniverseRow[]): Promise<UniverseRow[]> {
  if (provided && provided.length) return provided;
  try {
    const cat = await fetchStrategyCatalog();
    if (Array.isArray(cat.universe_symbols) && cat.universe_symbols.length) return cat.universe_symbols;
  } catch {
    /* fall through to bundled CSV */
  }
  const csv = await fetch("/nifty500.csv").then((res) => (res.ok ? res.text() : ""));
  return parseUniverseCsv(csv);
}

export const IndicatorScreenerPanel: React.FC<IndicatorScreenerPanelProps> = ({
  universeCount,
  universeRows: universeRowsProp,
  appliedIndicator,
  navigate,
  onAddIndicator,
  onEditIndicator,
  notify,
}) => {
  const savedScanner = useMemo(() => loadIndicatorScannerState(), []);
  const [indicators, setIndicators] = useState<SavedIndicator[]>(() =>
    upsertIndicator(savedScanner?.indicators || [], appliedIndicator || savedScanner?.appliedIndicator || null),
  );
  const [selectedId, setSelectedId] = useState<string>(
    savedScanner?.selectedId || appliedIndicator?.id || savedScanner?.appliedIndicator?.id || "",
  );
  const [timeframe, setTimeframe] = useState(savedScanner?.timeframe || "1D");
  const [scanDate, setScanDate] = useState(() => currentScanSessionIST());
  const [filters, setFilters] = useState<IndicatorFilter[]>(() =>
    savedScanner?.filters?.length ? savedScanner.filters : absorbedFromIndicator(appliedIndicator || savedScanner?.appliedIndicator).filters,
  );
  const [scan, setScan] = useState<IndicatorScanStatus | null>(savedScanner?.scan || null);
  const [results, setResults] = useState<IndicatorScanRow[]>(savedScanner?.results || []);
  const [total, setTotal] = useState(savedScanner?.total || 0);
  const [page, setPage] = useState(savedScanner?.page || 1);
  const [pageSize, setPageSize] = useState(25);
  const [sortField, setSortField] = useState("signal");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [search, setSearch] = useState(savedScanner?.search || "");
  const [matchedOnly, setMatchedOnly] = useState(false);
  const [signalFilter, setSignalFilter] = useState("ALL");
  const [returnFilter, setReturnFilter] = useState("ALL");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [topPositiveRows, setTopPositiveRows] = useState<RankedReturn[]>([]);
  const [topNegativeRows, setTopNegativeRows] = useState<RankedReturn[]>([]);
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(
    () => new Set(["rank", "symbol", "company", "signal", "entry_price", "exit_price", "return_pct", "evaluation_date", "pass_count", "primary_failure"]),
  );
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(savedScanner?.diagnostics || null);
  const [universeRows, setUniverseRows] = useState<UniverseRow[]>(universeRowsProp || []);
  const [backtestModalOpen, setBacktestModalOpen] = useState(false);
  const [leanJob, setLeanJob] = useState<IndicatorBacktestJob | null>(null);
  const [leanResult, setLeanResult] = useState<LeanBacktestResult | null>(null);
  const [leanLoading, setLeanLoading] = useState(false);
  const [showBacktestView, setShowBacktestView] = useState(false);
  const [openColumn, setOpenColumn] = useState<string | null>(null);
  const [hiddenColumns, setHiddenColumns] = useState<string[]>([]);
  const backtestPollRef = useRef<number | null>(null);
  const pollRef = useRef<number | null>(null);
  const scanIdRef = useRef<string | null>(savedScanner?.scan?.scan_id || null);
  const lastAppliedId = useRef<string | null>(appliedIndicator?.id || null);
  const [scanSlot, setScanSlot] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setScanSlot(document.getElementById(HEADER_SCAN_SLOT_ID));
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadUniverseRows(universeRowsProp)
      .then((rows) => {
        if (!cancelled && rows.length) setUniverseRows(rows);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [universeRowsProp]);

  const visibleIndicators = useMemo(() => uniqueIndicatorsByIdAndName(indicators), [indicators]);

  const selected = useMemo(() => {
    const byId = visibleIndicators.find((item) => item.id === selectedId);
    if (byId) return byId;
    const fromAll = indicators.find((item) => item.id === selectedId);
    if (fromAll) {
      const alias = visibleIndicators.find(
        (item) => item.name.trim().toLowerCase() === fromAll.name.trim().toLowerCase(),
      );
      if (alias) return alias;
    }
    if (appliedIndicator?.id) {
      const applied = visibleIndicators.find((item) => item.id === appliedIndicator.id);
      if (applied) return applied;
    }
    return visibleIndicators[0] || (appliedIndicator?.id === selectedId ? appliedIndicator : null);
  }, [visibleIndicators, indicators, selectedId, appliedIndicator]);

  const absorbedSelected = useMemo(() => absorbedFromIndicator(selected), [selected]);
  const visibleColumnsAbsorbed = useMemo(
    () => absorbedSelected.columns.filter((col) => !hiddenColumns.includes(col.name)),
    [absorbedSelected.columns, hiddenColumns],
  );
  const outputNames = absorbedSelected.columns.map((col) => col.name);
  const entryConditions = absorbedSelected.entryConditions;
  const screenerSignalColumn = preferredScreenerColumn(absorbedSelected.columns);
  const tvStylePriceEqualsOne = useMemo(
    () => filters.some((item) => isTvStyleSignalEqualsOneOnPricePlot(item, absorbedSelected.columns)),
    [filters, absorbedSelected.columns],
  );

  const syncFiltersToOutputs = useCallback((indicator: SavedIndicator | null | undefined) => {
    const absorbed = absorbedFromIndicator(indicator);
    const outputs = absorbed.columns.map((col) => col.name);
    setFilters((prev) => {
      const extra = normalizePineScreenerFilters(
        prev.filter((item) => outputs.includes(item.field) && !isAggregateSignalFilter(item)),
        absorbed.columns,
      );
      if (absorbed.entryConditions.length) {
        if (
          extra.length === prev.length &&
          extra.every((item, i) => item.field === prev[i]?.field && item.operator === prev[i]?.operator && item.value === prev[i]?.value)
        ) {
          return prev;
        }
        return extra;
      }
      if (!outputs.length) return prev;
      const next = extra.length ? extra : absorbed.filters;
      if (
        next.length === prev.length &&
        next.every((item, i) => item.field === prev[i]?.field && item.operator === prev[i]?.operator && item.value === prev[i]?.value)
      ) {
        return prev;
      }
      return next;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadLibrary = async () => {
      let rows = await fetchIndicators();
      const hasLab = rows.some((row) => /^\d{2}\s/.test(row.name) && row.name.includes("[SCAN]"));
      if (!hasLab) {
        try {
          const seeded = await seedLabIndicators();
          if (Array.isArray(seeded.indicators) && seeded.indicators.length) {
            rows = seeded.indicators;
          } else {
            rows = await fetchIndicators();
          }
        } catch {
          /* keep whatever the library already had */
        }
      }
      return rows;
    };
    loadLibrary()
      .then((rows) => {
        if (cancelled) return;
        setLoadError(null);
        const incoming = uniqueIndicatorsByIdAndName([
          ...rows,
          ...(appliedIndicator ? [appliedIndicator] : []),
        ]);
        setIndicators((prev) => (incoming.length ? incoming : uniqueIndicatorsByIdAndName(prev)));
        setSelectedId((current) => {
          if (!incoming.length) return current;
          if (current && incoming.some((row) => row.id === current)) return current;
          const currentRow = [...rows, ...(appliedIndicator ? [appliedIndicator] : [])].find((row) => row.id === current);
          if (currentRow) {
            const alias = incoming.find(
              (row) => row.name.trim().toLowerCase() === currentRow.name.trim().toLowerCase(),
            );
            if (alias) return alias.id;
          }
          if (appliedIndicator?.id && incoming.some((row) => row.id === appliedIndicator.id)) {
            return appliedIndicator.id;
          }
          return incoming[0]?.id || current || "";
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Unable to load indicators.");
      });
    return () => {
      cancelled = true;
    };
  }, [appliedIndicator?.id]);

  useEffect(() => {
    if (!appliedIndicator?.id) return;
    setIndicators((prev) => upsertIndicator(prev, appliedIndicator));
    if (lastAppliedId.current !== appliedIndicator.id) {
      lastAppliedId.current = appliedIndicator.id;
      setSelectedId(appliedIndicator.id);
    }
  }, [appliedIndicator]);

  useEffect(() => {
    syncFiltersToOutputs(selected);
  }, [selected, syncFiltersToOutputs]);

  useEffect(() => {
    setOpenColumn(null);
    setHiddenColumns([]);
  }, [selected?.id]);

  const mapTopRow = useCallback((row: IndicatorScanRow, rank: number): RankedReturn => {
    const stock = mapIndicatorResultToStock(row);
    return {
      rank,
      symbol: row.symbol,
      company: row.display_name || stock.company,
      entry_price: stock.entry_price,
      exit_price: stock.exit_price,
      return_pct: stock.return_pct,
      signal: stock.signal || (row.matched ? "MATCH" : "REJECT"),
      key_filters: stock.passed_filters?.slice(0, 3),
      passed_filters: stock.passed_filters,
      failed_filters: stock.failed_filters,
    };
  }, []);

  const loadTopReturns = useCallback(
    async (scanId: string) => {
      const [positive, negative] = await Promise.all([
        fetchIndicatorScanResults(scanId, {
          page: 1,
          page_size: 5,
          matched_only: false,
          return_bucket: "POSITIVE",
          sort: "return_pct",
          direction: "desc",
        }),
        fetchIndicatorScanResults(scanId, {
          page: 1,
          page_size: 5,
          matched_only: false,
          return_bucket: "NEGATIVE",
          sort: "return_pct",
          direction: "asc",
        }),
      ]);
      setTopPositiveRows((positive.results || []).map((row, index) => mapTopRow(row, index + 1)));
      setTopNegativeRows((negative.results || []).map((row, index) => mapTopRow(row, index + 1)));
    },
    [mapTopRow],
  );

  const loadResults = useCallback(
    async (scanId: string, nextPage = page) => {
      const payload = await fetchIndicatorScanResults(scanId, {
        page: nextPage,
        page_size: pageSize,
        search: search || undefined,
        matched_only: false,
        signal: signalFilter === "ALL" ? undefined : signalFilter,
        return_bucket: returnFilter === "ALL" ? undefined : returnFilter,
        sort: signalFilter === "ALL" ? "signal" : sortField,
        direction: sortDir,
      });
      setResults(payload.results);
      setTotal(payload.total);
    },
    [page, pageSize, search, signalFilter, returnFilter, sortField, sortDir],
  );

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const handleTerminalScan = useCallback(
    async (status: IndicatorScanStatus) => {
      stopPoll();
      setBusy(false);
      setScan(status);
      if (status.status === "completed") {
        try {
          const fresh = await fetchIndicatorScan(status.scan_id);
          setScan(fresh);
        } catch {
          /* keep polled status */
        }
        await Promise.all([loadResults(status.scan_id, 1), loadTopReturns(status.scan_id)]);
        setPage(1);
        const failed = status.failed_count || 0;
        if (failed > 0) {
          notify({
            title: "Some symbols could not be calculated. View diagnostics.",
            type: "warning",
          });
        }
      }
    },
    [loadResults, loadTopReturns, notify, stopPoll],
  );

  const poll = useCallback(
    (scanId: string) => {
      stopPoll();
      scanIdRef.current = scanId;
      const tick = async () => {
        try {
          const status = await fetchIndicatorScan(scanId);
          if (scanIdRef.current !== scanId) return;
          setScan(status);
          if (status.status === "completed" || status.status === "failed" || status.status === "cancelled") {
            await handleTerminalScan(status);
          }
        } catch {
          stopPoll();
          setBusy(false);
        }
      };
      void tick();
      pollRef.current = window.setInterval(() => {
        void tick();
      }, 1000);
    },
    [handleTerminalScan, stopPoll],
  );

  useEffect(() => () => stopPoll(), [stopPoll]);

  useEffect(() => {
    const scanId = scan?.scan_id;
    if (!scanId) return;
    if (isFreshActiveScan(scan)) {
      setBusy(true);
      poll(scanId);
    } else if (scan && isScanActive(scan)) {
      setScan({
        ...scan,
        status: "failed",
        error_detail: "Previous scan was interrupted. Start a new scan.",
      });
    } else if (scan?.status === "completed") {
      fetchIndicatorScan(scanId)
        .then((status) => {
          setScan(status);
          return loadTopReturns(scanId);
        })
        .catch(() => {});
    }
    // Restore a completed run from storage; never start a new scan on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    try {
      saveIndicatorScannerState({
        selectedId: selected?.id || selectedId,
        appliedIndicator: selected || appliedIndicator,
        indicators: visibleIndicators,
        timeframe,
        scanDate,
        filters,
        scan,
        results,
        total,
        page,
        sortField,
        sortDir,
        search,
        matchedOnly: signalFilter === "MATCH",
        diagnostics,
      });
    } catch {
      /* ignore */
    }
  }, [
    selected,
    selectedId,
    appliedIndicator,
    visibleIndicators,
    timeframe,
    scanDate,
    filters,
    scan,
    results,
    total,
    page,
    sortField,
    sortDir,
    search,
    signalFilter,
    diagnostics,
  ]);

  useEffect(() => {
    if (scan?.scan_id && scan.status === "completed") {
      loadResults(scan.scan_id).catch(() => {});
    }
  }, [page, sortField, sortDir, search, signalFilter, returnFilter, scan?.scan_id, scan?.status, loadResults]);

  useEffect(() => {
    if (scan?.scan_id && scan.status === "completed") {
      loadTopReturns(scan.scan_id).catch(() => {});
    }
  }, [scan?.scan_id, scan?.status, loadTopReturns]);

  const handleScan = async () => {
    const indicator = selected || indicators[0];
    if (!indicator?.id) {
      notify({ title: "Add an indicator before scanning.", type: "warning" });
      return;
    }
    if (!selected?.id) setSelectedId(indicator.id);
    if (timeframe !== "1D") {
      notify({
        title: "Weekly and monthly timeframes are not supported yet. Daily (1D) data is available.",
        type: "warning",
      });
      return;
    }
    const today = currentScanSessionIST();
    const effectiveScanDate = !scanDate || scanDate > today ? today : scanDate;
    if (effectiveScanDate !== scanDate) {
      setScanDate(effectiveScanDate);
    }
    setBusy(true);
    setResults([]);
    setTopPositiveRows([]);
    setTopNegativeRows([]);
    setTotal(0);
    setDiagnostics(null);
    setPage(1);
    try {
      const cleaned = cleanFilters(filters);
      const pineFilters = cleaned.length ? cleaned : absorbScreenFilters(absorbedSelected.columns);
      const started = await startIndicatorScan(indicator.id, {
        universe_id: "nse-755",
        timeframe: "1D",
        scan_date: effectiveScanDate,
        filters: pineFilters,
        sort: { field: sortField, direction: sortDir },
      });
      setScan(started);
      scanIdRef.current = started.scan_id || null;
      if (!started.scan_id) {
        setBusy(false);
        notify({ title: "Failed to start scan", message: "Scan did not return an id.", type: "error" });
        return;
      }
      if (started.status === "completed" || started.status === "failed" || started.status === "cancelled") {
        await handleTerminalScan(started);
        return;
      }
      poll(started.scan_id);
    } catch (err) {
      setBusy(false);
      notify({
        title: "Failed to start scan",
        message: err instanceof Error ? err.message : "Unknown error",
        type: "error",
      });
    }
  };

  const handleCancel = async () => {
    if (!scan?.scan_id) return;
    try {
      await cancelIndicatorScan(scan.scan_id);
      setScan((prev) => (prev ? { ...prev, status: "cancelling", stage: "cancelling" } : prev));
    } catch (err) {
      notify({ title: "Unable to cancel scan", message: err instanceof Error ? err.message : "", type: "error" });
    }
  };

  const stopBacktestPoll = useCallback(() => {
    if (backtestPollRef.current) {
      window.clearInterval(backtestPollRef.current);
      backtestPollRef.current = null;
    }
  }, []);

  const handleStartLeanBacktest = useCallback(
    async (options: IndicatorBacktestOptions) => {
      const indicator = selected || indicators[0];
      if (!indicator?.id) {
        notify({ title: "Select an indicator before starting backtest.", type: "warning" });
        return;
      }
      stopBacktestPoll();
      setLeanLoading(true);
      setLeanResult(null);
      setShowBacktestView(true);

      try {
        const job = await startIndicatorBacktest(indicator.id, options);
        setLeanJob(job);
        if (job.status === "COMPLETED" && job.result) {
          setLeanResult(job.result);
          setLeanLoading(false);
          notify({ title: "LEAN Backtest completed successfully!", type: "success" });
          return;
        }
        if (job.status === "FAILED") {
          setLeanLoading(false);
          notify({ title: "LEAN Backtest failed", message: job.error || "Execution error", type: "error" });
          return;
        }

        const jobId = job.jobId;
        const tick = async () => {
          try {
            const currentJob = await fetchIndicatorBacktest(indicator.id, jobId);
            setLeanJob(currentJob);
            if (currentJob.status === "COMPLETED") {
              stopBacktestPoll();
              setLeanLoading(false);
              const res = await fetchIndicatorBacktestResults(indicator.id, jobId);
              setLeanResult(res);
              notify({ title: "LEAN Backtest completed successfully!", type: "success" });
            } else if (currentJob.status === "FAILED" || currentJob.status === "CANCELLED") {
              stopBacktestPoll();
              setLeanLoading(false);
              notify({
                title: "LEAN Backtest finished with error",
                message: currentJob.error || currentJob.status,
                type: "error",
              });
            }
          } catch {
            stopBacktestPoll();
            setLeanLoading(false);
          }
        };

        backtestPollRef.current = window.setInterval(() => {
          void tick();
        }, 1500);
      } catch (err) {
        setLeanLoading(false);
        notify({
          title: "Failed to launch LEAN backtest",
          message: err instanceof Error ? err.message : "Unknown error",
          type: "error",
        });
      }
    },
    [selected, indicators, notify, stopBacktestPoll],
  );

  const handleCancelLeanBacktest = useCallback(() => {
    stopBacktestPoll();
    setLeanLoading(false);
    setLeanJob((prev) => (prev ? { ...prev, status: "CANCELLED" } : null));
    notify({ title: "LEAN Backtest cancelled", type: "info" });
  }, [stopBacktestPoll, notify]);

  useEffect(() => () => stopBacktestPoll(), [stopBacktestPoll]);

  const handleDiagnostics = async () => {
    if (!scan?.scan_id) return;
    try {
      setDiagnostics(await fetchIndicatorScanDiagnostics(scan.scan_id));
      setDiagnosticsOpen(true);
    } catch (err) {
      if (diagnostics) {
        setDiagnosticsOpen(true);
        return;
      }
      notify({ title: "Unable to load diagnostics", message: err instanceof Error ? err.message : "", type: "error" });
    }
  };

  const handleExport = async () => {
    if (!scan?.scan_id) {
      notify({ title: "Run a scan first.", type: "warning" });
      return;
    }
    try {
      await exportIndicatorScanCsv(scan.scan_id);
    } catch (err) {
      notify({ title: "Export failed", message: err instanceof Error ? err.message : "", type: "error" });
    }
  };

  const handleDuplicate = async () => {
    if (!selected?.id) return;
    try {
      const copy = await duplicateIndicator(selected.id);
      setIndicators((prev) => uniqueIndicatorsByIdAndName(upsertIndicator(prev, copy)));
      setSelectedId(copy.id);
      notify({ title: "Indicator duplicated", type: "success" });
    } catch (err) {
      notify({ title: "Unable to duplicate indicator", message: err instanceof Error ? err.message : "", type: "error" });
    }
  };

  const handleArchive = async () => {
    if (!selected?.id) return;
    try {
      await archiveIndicator(selected.id);
      const remaining = uniqueIndicatorsByIdAndName(indicators.filter((item) => item.id !== selected.id));
      setIndicators(remaining);
      setSelectedId(remaining[0]?.id || "");
      notify({ title: "Indicator archived", type: "success" });
    } catch (err) {
      notify({ title: "Unable to archive indicator", message: err instanceof Error ? err.message : "", type: "error" });
    }
  };

  const scanning = busy || isScanActive(scan);
  const fetchingData = scanning && (isFetchingCurrentData(scan) || !isScanActive(scan));
  const scanned = scan?.status === "completed";
  const scanSummary = (scan?.summary && typeof scan.summary === "object" ? scan.summary : {}) as Record<string, unknown>;
  const tableRows: StrategyResultRow[] = useMemo(() => {
    if (scanned) {
      return results.map((row, index) => ({
        ...mapIndicatorResultToStock(row, scan),
        rank: (row as IndicatorScanRow & { rank?: number }).rank ?? (page - 1) * pageSize + index + 1,
      }));
    }
    const needle = search.trim().toUpperCase();
    return universeRows
      .filter(
        (row) =>
          !needle ||
          row.symbol.toUpperCase().includes(needle) ||
          (row.company || "").toUpperCase().includes(needle),
      )
      .slice((page - 1) * pageSize, page * pageSize)
      .map((row, index) => ({
        rank: (page - 1) * pageSize + index + 1,
        symbol: row.symbol,
        company: row.company || "",
        status: "pending",
        signal: "",
        evaluation_date: null,
        entry_price: null,
        exit_price: null,
        return_pct: 0,
        close: null,
        volume: null,
        avg_volume: null,
        rsi: null,
        sma_20: null,
        sma_50: null,
        sma_200: null,
        high_252: null,
        filters_passed: 0,
        filters_failed: 0,
        passed_filters: [],
        failed_filters: [],
        primary_failure_reason: null,
      }));
  }, [scanned, results, scan, universeRows, search, page, pageSize]);
  const listCount = scanned ? total : universeRows.length;
  const matchedCount = scan?.matched_count ?? 0;
  const skippedCount = scan?.skipped_count ?? 0;
  const unmatchedCount = Math.max(0, (scan?.success_count ?? 0) - matchedCount) + (scan?.failed_count ?? 0);
  const builderRules = entryConditions.map((name, index) => ({
    id: `c${index + 1}`,
    label: name,
    join: "AND" as const,
  }));
  const filterStats = (Array.isArray(scanSummary.filter_analytics)
    ? scanSummary.filter_analytics
    : (entryConditions.length
        ? entryConditions
        : ["No entry conditions"]).map((name, index) => ({
        filter_id: `c${index + 1}`,
        label: name,
        passed: 0,
        failed: 0,
        pass_pct: 0,
        fail_pct: 0,
      }))) as FilterStat[];
  const funnelSteps = (Array.isArray(scanSummary.filter_funnel)
    ? scanSummary.filter_funnel
    : [
        { step: 0, filter_id: null, label: "Start Universe", remaining: universeCount || 755, drop: 0, retention_pct: 100 },
        ...entryConditions.map((name, index) => ({
          step: index + 1,
          filter_id: `c${index + 1}`,
          label: name,
          remaining: universeCount || 755,
          drop: 0,
          retention_pct: 100,
        })),
        { step: entryConditions.length + 1, filter_id: "final", label: "Final MATCHED Signals", remaining: matchedCount, drop: 0, retention_pct: 0 },
      ]) as FunnelStep[];
  const topPositive = (
    topPositiveRows.length
      ? topPositiveRows
      : Array.isArray(scanSummary.top_positive)
        ? scanSummary.top_positive
        : []
  ) as RankedReturn[];
  const topNegative = (
    topNegativeRows.length
      ? topNegativeRows
      : Array.isArray(scanSummary.top_negative)
        ? scanSummary.top_negative
        : []
  ) as RankedReturn[];
  const showScanChrome = Boolean(selected);
  const scanActions = (
    <div className="ind-scan-actions">
      <button
        type="button"
        className="st-btn-run"
        onClick={() => void handleScan()}
        disabled={scanning && (scan?.processed_count || 0) > 0}
        data-testid="btn-scan-indicator"
      >
        {scanning ? (
          <>
            <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12" />
            </svg>
            {fetchingData ? "Fetching data…" : "Scanning…"}
          </>
        ) : (
          <>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            Scan
          </>
        )}
      </button>
      <button
        type="button"
        className="st-btn-dark"
        onClick={() => setBacktestModalOpen(true)}
        disabled={!selected || leanLoading}
        data-testid="btn-open-lean-backtest"
        style={{
          background: "linear-gradient(135deg, #1e3a8a, #2563eb)",
          color: "#ffffff",
          borderColor: "#3b82f6",
          fontWeight: 600,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 6,
          padding: "6px 12px",
        }}
        title="Run multi-asset historical portfolio backtest with LEAN"
      >
        <span>⚡</span>
        <span>Portfolio backtest</span>
      </button>
      {scanning && scan?.scan_id && (
        <button type="button" className="st-btn-reset" onClick={handleCancel} data-testid="btn-cancel-indicator-scan">
          Cancel
        </button>
      )}
    </div>
  );
  return (
    <section className="ind-screener ind-screener-tv" data-testid="indicator-screener">
      {scanSlot ? createPortal(scanActions, scanSlot) : null}
      <div className="ind-top-row">
      <div className="ind-pill-bar" role="toolbar" aria-label="Indicator screener controls">
        <label className="ind-pill" data-testid="select-indicator-universe">
          <select value="nse-755" disabled>
            <option value="nse-755">{universeCount || 755} Stocks</option>
          </select>
        </label>
        <label className="ind-pill" title="As-of date in IST. The scan evaluates the last NSE 1D session on or before this date.">
          <span className="ind-pill-prefix">As of</span>
          <input
            type="date"
            value={scanDate}
            max={currentScanSessionIST()}
            onChange={(e) => setScanDate(e.target.value || currentScanSessionIST())}
            data-testid="input-indicator-scan-date"
          />
        </label>
        {showScanChrome && (
          <div className="ind-pill-grow" style={{ display: "inline-flex", position: "relative" }}>
            <IndicatorCustomDropdown
              selected={selected}
              indicators={visibleIndicators}
              onSelect={(id) => setSelectedId(id)}
            />
            <select
              value={selected?.id || selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              data-testid="select-saved-indicator"
              style={{ position: "absolute", opacity: 0, pointerEvents: "none", width: 0, height: 0 }}
              tabIndex={-1}
              aria-hidden="true"
            >
              {!selected?.id && !selectedId && <option value="">Select indicator</option>}
              {visibleIndicators.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
        )}
        {showScanChrome && (
          <label className="ind-pill">
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} data-testid="select-screener-timeframe">
              <option value="1D">1D</option>
              <option value="1W">1W</option>
              <option value="1M">1M</option>
            </select>
          </label>
        )}
        {visibleColumnsAbsorbed.length > 0 && (
          <div className="ind-pill-wrap" data-testid="indicator-absorbed-columns">
            {visibleColumnsAbsorbed.map((col) => (
              <ScreenerColumnChip
                key={col.name}
                column={col}
                columns={absorbedSelected.columns}
                filter={filters.find((item) => item.field === col.name) || null}
                open={openColumn === col.name}
                onToggle={() => setOpenColumn((current) => (current === col.name ? null : col.name))}
                onClose={() => setOpenColumn(null)}
                onApplyFilter={(next) => {
                  setFilters((prev) => {
                    const without = prev.filter((item) => item.field !== next.field);
                    return [...without, next];
                  });
                }}
                onRemoveColumn={(field) => {
                  setFilters((prev) => prev.filter((item) => item.field !== field));
                  setHiddenColumns((prev) => (prev.includes(field) ? prev : [...prev, field]));
                }}
              />
            ))}
          </div>
        )}
        <button type="button" className="ind-pill ind-pill-add" onClick={onAddIndicator} data-testid="btn-add-indicator">
          + Add indicator
        </button>
        {selected && (
          <>
            <button type="button" className="ind-pill" onClick={() => onEditIndicator(selected)} data-testid="btn-edit-indicator">
              Edit
            </button>
            <button type="button" className="ind-pill" onClick={handleDuplicate} data-testid="btn-duplicate-indicator">
              Duplicate
            </button>
            <button type="button" className="ind-pill" onClick={handleArchive} data-testid="btn-archive-indicator">
              Archive
            </button>
          </>
        )}
        {(leanJob || leanResult) && (
          <button
            type="button"
            className="ind-pill"
            onClick={() => setShowBacktestView((prev) => !prev)}
            data-testid="btn-toggle-lean-view"
            style={{
              background: showBacktestView ? "#2563eb" : "#0d1527",
              color: "#ffffff",
              border: "1px solid #3b82f6",
              fontWeight: 600,
            }}
          >
            ⚡ {showBacktestView ? "Hide LEAN Results" : "View LEAN Results"}
            {leanResult?.summary?.cagr !== null && leanResult?.summary?.cagr !== undefined
              ? ` (${(leanResult.summary.cagr * 100).toFixed(1)}% CAGR)`
              : leanLoading
                ? " (Running…)"
                : ""}
          </button>
        )}
      </div>
      {scanSlot ? null : scanActions}
      </div>

      {showBacktestView && (leanJob || leanResult) && (
        <IndicatorLeanBacktestView
          job={leanJob}
          result={leanResult}
          loading={leanLoading}
          onCancel={handleCancelLeanBacktest}
          onClose={() => setShowBacktestView(false)}
          onRerun={() => setBacktestModalOpen(true)}
        />
      )}
      {timeframe !== "1D" && showScanChrome && (
        <p className="st-pine-summary-warning" data-testid="screener-timeframe-warning">
          Weekly and monthly timeframes are not supported yet. Daily (1D) data is available.
        </p>
      )}
      {loadError && (
        <div className="st-pine-error-banner" data-testid="indicator-load-error">
          {loadError}
        </div>
      )}
      {!selected && (
        <span className="sr-only" data-testid="indicator-empty-library">
          Universe is {universeCount || 755} Stocks. Click Add indicator, Observe Pine, then Scan.
        </span>
      )}

      {showScanChrome && entryConditions.length > 0 && (
        <div className="st-card" data-testid="indicator-strategy-conditions">
          <h2 className="st-card-title">Strategy Conditions</h2>
          <p className="st-reject-not-a-trade">
            TradingView Pine Screener and this scan both evaluate the last 1D bar. MATCH requires every
            required entry condition on that bar, plus any column filters you set. ta.crossover is true
            only on that bar.
          </p>
          <div className="st-filter-eval-list">
            {entryConditions.map((name) => (
              <div key={name} className="st-filter-eval-item">
                <span className="st-filter-eval-name">{name}</span>
                <span className="st-filter-eval-status passed">✓ Required</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {showScanChrome && (
      <div className="ind-filter-row" data-testid="indicator-filter-row">
        {filters.map((filter, index) => (
          <div key={`${filter.field}-${index}`} className="ind-filter-chip">
            <select
              aria-label="Filter output"
              value={filter.field}
              onChange={(e) => {
                const next = [...filters];
                next[index] = { ...next[index], field: e.target.value };
                setFilters(next);
              }}
            >
              {(outputNames.length ? outputNames : [filter.field || SIGNAL_FIELD]).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter operator"
              value={filter.operator}
              onChange={(e) => {
                const next = [...filters];
                next[index] = { ...next[index], operator: e.target.value };
                setFilters(next);
              }}
            >
              <option value="=">=</option>
              <option value="!=">!=</option>
              <option value=">">&gt;</option>
              <option value=">=">&gt;=</option>
              <option value="<">&lt;</option>
              <option value="<=">&lt;=</option>
              <option value="between">between</option>
              <option value="is_true">is true</option>
              <option value="is_false">is false</option>
              <option value="is_null">is null</option>
              <option value="is_not_null">is not null</option>
            </select>
            {filter.operator === "between" ? (
              <>
                <input
                  aria-label="Filter low"
                  value={filter.low === undefined || filter.low === null ? "" : String(filter.low)}
                  onChange={(e) => {
                    const next = [...filters];
                    const raw = e.target.value;
                    next[index] = { ...next[index], low: raw === "" ? null : Number(raw) };
                    setFilters(next);
                  }}
                />
                <input
                  aria-label="Filter high"
                  value={filter.high === undefined || filter.high === null ? "" : String(filter.high)}
                  onChange={(e) => {
                    const next = [...filters];
                    const raw = e.target.value;
                    next[index] = { ...next[index], high: raw === "" ? null : Number(raw) };
                    setFilters(next);
                  }}
                />
              </>
            ) : VALUELESS_OPS.has(filter.operator) ? null : (
              <input
                aria-label="Filter value"
                value={filter.value === undefined || filter.value === null ? "" : String(filter.value)}
                onChange={(e) => {
                  const next = [...filters];
                  const raw = e.target.value;
                  next[index] = { ...next[index], value: raw === "" ? "" : Number.isNaN(Number(raw)) ? raw : Number(raw) };
                  setFilters(next);
                }}
              />
            )}
            <button
              type="button"
              className="st-btn-dark"
              aria-label="Remove filter"
              onClick={() => setFilters(filters.filter((_, i) => i !== index))}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className="st-btn-dark"
          onClick={() =>
            setFilters([
              ...filters,
              screenerSignalColumn
                ? defaultColumnFilter(screenerSignalColumn)
                : { field: SIGNAL_FIELD, operator: "=", value: 1 },
            ])
          }
          data-testid="btn-add-filter"
        >
          + Filter
        </button>
        <button type="button" className="st-btn-dark" onClick={() => setFilters([])} data-testid="btn-clear-filters">
          Clear Filters
        </button>
      </div>
      )}
      {showScanChrome && tvStylePriceEqualsOne && (
        <p className="st-pine-summary-warning" data-testid="pine-screener-filter-warning">
          TradingView Pine Screener filters plot columns on the last 1D bar. Setting{" "}
          {filters.find((item) => isTvStyleSignalEqualsOneOnPricePlot(item, absorbedSelected.columns))?.field || "EMA 20"}{" "}
          = 1 matches no symbols because that plot is a price, not a 0/1 signal. That is why TradingView
          showed “No symbols match your filters”. Filter {screenerSignalColumn?.name || "Momentum Signal"} is
          true, or add plot(buySignal ? 1 : 0, &quot;Signal&quot;) and filter Signal = 1 on both platforms.
          {screenerSignalColumn ? (
            <>
              {" "}
              <button
                type="button"
                className="st-btn-dark"
                data-testid="btn-use-screener-signal-filter"
                onClick={() => setFilters([defaultColumnFilter(screenerSignalColumn)])}
              >
                Use {screenerSignalColumn.name} is true
              </button>
            </>
          ) : null}
        </p>
      )}

      {/* 1. All Stock Results Table (Top) */}
      <div data-testid="indicator-results-table">
        <AllStockResultsTable
          title={`All ${scanned ? total : listCount} Stock Results`}
          results={tableRows}
          totalResults={scanned ? total : listCount}
          selectedSymbol={selectedSymbol}
          searchQuery={search}
          signalFilter={scanned ? signalFilter : "ALL"}
          returnFilter={returnFilter}
          sortColumn={sortField}
          sortDirection={sortDir}
          currentPage={page}
          pageSize={pageSize}
          visibleColumns={visibleColumns}
          buyCount={matchedCount}
          watchCount={skippedCount}
          rejectCount={unmatchedCount}
          failedCount={scan?.failed_count ?? 0}
          variant="scanner"
          caption={`MATCHED means every required strategy entry condition passed on the same last 1D bar TradingView Pine Screener uses, and every column filter passed. ta.crossover is true only on that bar — yesterday's crosses will not match today's screen. Filtering a price plot such as EMA 20 to 1 matches no symbols (TradingView empty result). Filter Momentum Signal is true to screen the pulse. REJECTED means at least one required condition or filter did not pass. SKIPPED means the name did not have enough history.${outputNames.length ? ` Indicator outputs: ${outputNames.join(", ")}.` : ""}`}
          onSearchChange={(q) => {
            setSearch(q);
            setPage(1);
          }}
          onSignalFilterChange={(sig) => {
            setSignalFilter(sig);
            setMatchedOnly(sig === "MATCH");
            if (sig === "ALL") setSortField("signal");
            setPage(1);
          }}
          onReturnFilterChange={(ret) => {
            setReturnFilter(ret);
            setPage(1);
          }}
          onSortChange={(col) => {
            if (sortField === col) {
              setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
            } else {
              setSortField(col);
              setSortDir(col === "symbol" ? "asc" : "desc");
            }
          }}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
          }}
          onStockSelect={(symbol) => {
            setSelectedSymbol(symbol);
            navigateToStock(navigate, symbol, {
              runId: scan?.scan_id,
              returnTo: "/strategy-tester",
              state: { strategyName: selected?.name || scan?.indicator_name || "Indicator Scanner" },
            });
          }}
          onColumnsClick={() => setColumnsOpen(true)}
          onExportClick={() => {
            if (scan) void handleExport();
          }}
        />
      </div>
      <span className="sr-only" data-testid="indicator-result-count">
        Symbol {scanned ? total : listCount}
      </span>
      <button type="button" className="sr-only" onClick={handleDiagnostics} disabled={!scan} data-testid="btn-indicator-diagnostics">
        View Diagnostics
      </button>

      {/* 2. Run Status Row (RUN ID | SCAN PROGRESS | RUN SUMMARY) */}
      <IndicatorRunStatusCard
        scan={scan}
        scanning={scanning}
        fallbackAsOf={scanDate}
        universeCount={universeCount}
      />
      {!scan && (
        <p className="ind-scan-strip" data-testid="indicator-scan-ready" style={{ display: "none" }}>
          {scanStatusText(null, Boolean(selected))}
        </p>
      )}

      {/* 3. Upper Analytics Grid (STRATEGY BUILDER | TOP 5 POSITIVE & NEGATIVE RETURNS) */}
      <section className="st-upper-analytics-grid" aria-label="Strategy overview analytics">
        <div className="st-builder-col">
          <StrategyBuilderCard
            strategyName={selected?.name || "Indicator Strategy"}
            rules={builderRules.length ? builderRules : [{ id: "1", label: selected?.name || "Scan indicator", join: "AND" }]}
            logicText="Logic: ALL conditions must be true"
            universeCount={universeCount || 755}
            timeframe={timeframe || "1 Day"}
            positionSide="LONG ONLY"
            exitRule="EOD (End of Day)"
            capital={1000000}
            sourceType="pine"
            onEditClick={() => (selected ? onEditIndicator(selected) : onAddIndicator())}
          />
        </div>
        <div className="st-top-returns-col">
          <TopReturnsCard
            type="positive"
            items={topPositive}
            totalCount={Number(scanSummary.positive_returns ?? 0)}
            onStockClick={(symbol) =>
              navigateToStock(navigate, symbol, {
                runId: scan?.scan_id,
                returnTo: "/strategy-tester",
                state: { strategyName: selected?.name || scan?.indicator_name || "Indicator Scanner" },
              })
            }
            onViewAllClick={() => {
              setReturnFilter("POSITIVE");
              setPage(1);
              document.getElementById("all-results-section")?.scrollIntoView({ behavior: "smooth" });
            }}
          />
          <TopReturnsCard
            type="negative"
            items={topNegative}
            totalCount={Number(scanSummary.negative_returns ?? 0)}
            onStockClick={(symbol) =>
              navigateToStock(navigate, symbol, {
                runId: scan?.scan_id,
                returnTo: "/strategy-tester",
                state: { strategyName: selected?.name || scan?.indicator_name || "Indicator Scanner" },
              })
            }
            onViewAllClick={() => {
              setReturnFilter("NEGATIVE");
              setPage(1);
              document.getElementById("all-results-section")?.scrollIntoView({ behavior: "smooth" });
            }}
          />
        </div>
      </section>

      {/* 4. Lower Analytics Grid (FILTER ANALYTICS | FILTER FUNNEL | SIGNAL DISTRIBUTION) */}
      <section className="st-lower-analytics-grid" aria-label="Filter and signal analytics">
        <FilterAnalyticsCard stats={filterStats} totalUniverse={universeCount || 755} />
        <FilterFunnelCard
          steps={funnelSteps}
          totalUniverse={universeCount || 755}
          onStepClick={(step) => {
            if (step.step === 0) setSignalFilter("ALL");
            if (step.filter_id === "final" || step.label?.toLowerCase().includes("matched")) setSignalFilter("MATCH");
            setPage(1);
            document.getElementById("all-results-section")?.scrollIntoView({ behavior: "smooth" });
          }}
        />
        <SignalDistributionCard
          buyCount={matchedCount}
          watchCount={skippedCount}
          rejectCount={unmatchedCount}
          failedCount={0}
          totalUniverse={universeCount || 755}
          labels={{ buy: "MATCHED", watch: "SKIPPED", reject: "REJECTED" }}
          onSignalClick={(sig) => {
            setSignalFilter(sig);
            setPage(1);
            document.getElementById("all-results-section")?.scrollIntoView({ behavior: "smooth" });
          }}
        />
      </section>

      <ColumnsConfigModal
        isOpen={columnsOpen}
        visibleColumns={visibleColumns}
        onClose={() => setColumnsOpen(false)}
        onToggleColumn={(colKey) => {
          setVisibleColumns((prev) => {
            const next = new Set(prev);
            if (next.has(colKey)) {
              if (next.size > 2) next.delete(colKey);
            } else {
              next.add(colKey);
            }
            return next;
          });
        }}
        onResetColumns={() =>
          setVisibleColumns(new Set(["rank", "symbol", "company", "signal", "entry_price", "exit_price", "return_pct", "evaluation_date", "pass_count", "primary_failure"]))
        }
      />

      {diagnosticsOpen && diagnostics && (
        <div className="st-modal-overlay" onClick={() => setDiagnosticsOpen(false)} data-testid="indicator-diagnostics">
          <div className="st-modal-card" style={{ maxWidth: 640 }} onClick={(e) => e.stopPropagation()}>
            <div className="st-modal-header">
              <h2>Scan diagnostics</h2>
              <button type="button" className="st-detail-close-btn" onClick={() => setDiagnosticsOpen(false)} aria-label="Close diagnostics">
                ✕
              </button>
            </div>
            <div className="st-modal-body">
              <p>Total symbols: {String(diagnostics.total_symbols ?? "")}</p>
              <p>Successful calculations: {String(diagnostics.successful ?? "")}</p>
              <p>Failed: {String(diagnostics.failed ?? "")}</p>
              <p>Skipped (insufficient history): {String(diagnostics.skipped ?? "")}</p>
              <p>Benchmark: {String(diagnostics.benchmark_symbol ?? "")}</p>
              <p>As of: {String(diagnostics.as_of ?? "")}</p>
              <ul>
                {Array.isArray(diagnostics.failures)
                  ? (diagnostics.failures as { symbol: string; error_detail?: string }[]).slice(0, 50).map((item) => (
                      <li key={item.symbol}>
                        {item.symbol}: {item.error_detail || "failed"}
                      </li>
                    ))
                  : null}
              </ul>
            </div>
          </div>
        </div>
      )}

      <IndicatorLeanBacktestModal
        isOpen={backtestModalOpen}
        onClose={() => setBacktestModalOpen(false)}
        indicatorName={selected?.name || "Indicator Strategy"}
        onStartBacktest={handleStartLeanBacktest}
        isStarting={leanLoading}
      />
    </section>
  );
};
