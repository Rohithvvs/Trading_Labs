import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  archiveIndicator,
  cancelIndicatorScan,
  duplicateIndicator,
  exportIndicatorScanCsv,
  fetchIndicatorScan,
  fetchIndicatorScanDiagnostics,
  fetchIndicatorScanResults,
  fetchIndicators,
  startIndicatorScan,
  type IndicatorFilter,
  type IndicatorScanRow,
  type IndicatorScanStatus,
  type SavedIndicator,
} from "../../api_indicator_scanner";
import { fetchStrategyCatalog } from "../../api_strategy_tester";
import { lastCompletedTradingDayIST } from "../../utils/tradingHours";
import { navigateToStock } from "../../utils/stockNavigation";
import { absorbFromParsedDefinition } from "../../utils/indicatorAbsorb";
import {
  loadIndicatorScannerState,
  saveIndicatorScannerState,
  uniqueIndicatorsByIdAndName,
} from "../../utils/indicatorScannerState";
import { formatDateTime, formatDuration } from "./RunStatusRow";
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

/** Last completed NSE session in IST — Pine Screener's 1D bar (weekends + holidays skipped). */
function lastCompletedSessionIST(): string {
  return lastCompletedTradingDayIST();
}

function formatValue(value: number | boolean | string | null | undefined, kind?: string): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") {
    return value ? "1.00" : "0.00";
  }
  if (typeof value === "number") {
    if (kind === "volume") {
      return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  return String(value);
}

function scanStatusText(status: IndicatorScanStatus | null, hasIndicator: boolean): string {
  if (!status) {
    return hasIndicator
      ? "Ready to scan. Click Scan to evaluate the universe."
      : "Add or apply an indicator, then click Scan.";
  }
  const total = status.total_count || status.universe_size || 755;
  if (status.status === "queued" || status.stage === "preparing") return "Preparing scan…";
  if (status.stage === "loading_benchmark" || status.stage === "loading_market_data") return "Loading market data…";
  if (status.status === "running" || status.stage === "scanning") {
    return `Scanning ${total} symbols: ${status.processed_count} / ${total}`;
  }
  if (status.stage === "applying_filters") return "Applying filters…";
  if (status.status === "completed") {
    const matched = status.matched_count ?? 0;
    if (matched === 0) return "No stocks matched the current indicator and filters.";
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
      if (filter.operator === "between") {
        cleaned.low = filter.low;
        cleaned.high = filter.high;
      } else if (!VALUELESS_OPS.has(filter.operator)) {
        cleaned.value = filter.value;
      }
      return cleaned;
    })
    .filter((filter) => {
      if (VALUELESS_OPS.has(filter.operator)) return true;
      if (filter.operator === "between") {
        return filter.low !== undefined && filter.low !== null && filter.high !== undefined && filter.high !== null;
      }
      return filter.value !== undefined && filter.value !== null && filter.value !== "";
    });
}

function isScanActive(status: IndicatorScanStatus | null): boolean {
  if (!status) return false;
  return status.status === "queued" || status.status === "running" || status.status === "cancelling";
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
}: {
  scan: IndicatorScanStatus;
  scanning: boolean;
  fallbackAsOf: string;
}) {
  const processed = scan.processed_count || 0;
  const total = scan.total_count || scan.universe_size || 755;
  const pct = scan.progress_pct ?? (total > 0 ? Math.round((processed / total) * 100) : 0);
  const matched = scan.matched_count ?? 0;
  const failed = scan.failed_count ?? 0;
  const skipped = scan.skipped_count ?? 0;
  const status = scanning
    ? "running"
    : scan.status === "failed" || scan.status === "cancelled"
      ? scan.status
      : scan.status === "completed"
        ? "completed"
        : scan.status;
  return (
    <div className="ind-status-row" data-testid="indicator-scan-status">
      <div className="st-card" data-testid="card-run-info">
        <div className="st-card-title">
          <span className="st-run-id-text">RUN ID: {scan.scan_id || scan.id || "—"}</span>
          {status === "running" || status === "queued" || status === "cancelling" ? (
            <span className="st-status-badge st-status-badge--running">⏳ Running</span>
          ) : status === "failed" ? (
            <span className="st-status-badge st-status-badge--failed">✕ Failed</span>
          ) : status === "cancelled" ? (
            <span className="st-status-badge st-status-badge--failed">✕ Cancelled</span>
          ) : (
            <span className="st-status-badge st-status-badge--completed">✓ Completed</span>
          )}
        </div>
        <div className="st-run-meta-list">
          <div>
            <span>Started:</span>
            <span className="val">{formatDateTime(scan.started_at)}</span>
          </div>
          <div>
            <span>Completed:</span>
            <span className="val">{scanning ? "—" : formatDateTime(scan.completed_at)}</span>
          </div>
          <div>
            <span>Duration:</span>
            <span className="val">{formatDuration(scan.elapsed_seconds)}</span>
          </div>
          <div>
            <span>Scan bar:</span>
            <span className="val" data-testid="run-scan-as-of">
              {scanBarDate(scan, fallbackAsOf)}
            </span>
          </div>
        </div>
        {scanDateMismatch(scan) ? (
          <p className="st-scan-bar-warning" data-testid="scan-date-mismatch">
            Symbols were evaluated on different session dates. Re-run after market data is filled so every name uses the same last 1D bar as TradingView.
          </p>
        ) : null}
        {scan.status === "failed" && scan.error_detail ? (
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
          {processed} / {total} stocks processed
          {scanning && scan.stage && scan.stage !== "scanning"
            ? ` · ${String(scan.stage).replace(/_/g, " ")}`
            : ""}
        </div>
        <div className="st-signal-chips">
          <div className="st-signal-chip">
            <span className="st-signal-chip-label buy">● MATCHED</span>
            <span className="st-signal-chip-val buy">{matched}</span>
          </div>
          <div className="st-signal-chip">
            <span className="st-signal-chip-label failed">○ FAILED</span>
            <span className="st-signal-chip-val failed">{failed}</span>
          </div>
          <div className="st-signal-chip">
            <span className="st-signal-chip-label watch">★ SKIPPED</span>
            <span className="st-signal-chip-val watch">{skipped}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function logoHue(symbol: string): string {
  let hue = 0;
  for (let i = 0; i < symbol.length; i += 1) hue = (hue * 33 + symbol.charCodeAt(i)) % 360;
  return `hsl(${hue} 62% 42%)`;
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
  const [scanDate, setScanDate] = useState(savedScanner?.scanDate || lastCompletedSessionIST());
  const [filters, setFilters] = useState<IndicatorFilter[]>(() =>
    savedScanner?.filters?.length ? savedScanner.filters : absorbedFromIndicator(appliedIndicator || savedScanner?.appliedIndicator).filters,
  );
  const [scan, setScan] = useState<IndicatorScanStatus | null>(savedScanner?.scan || null);
  const [results, setResults] = useState<IndicatorScanRow[]>(savedScanner?.results || []);
  const [total, setTotal] = useState(savedScanner?.total || 0);
  const [page, setPage] = useState(savedScanner?.page || 1);
  const [pageSize] = useState(50);
  const [sortField, setSortField] = useState(savedScanner?.sortField || "symbol");
  const [sortDir, setSortDir] = useState<"asc" | "desc">(savedScanner?.sortDir || "asc");
  const [search, setSearch] = useState(savedScanner?.search || "");
  const [matchedOnly, setMatchedOnly] = useState(savedScanner?.matchedOnly !== false);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown> | null>(savedScanner?.diagnostics || null);
  const [universeRows, setUniverseRows] = useState<UniverseRow[]>(universeRowsProp || []);
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

  const outputNames = useMemo(() => absorbedFromIndicator(selected).columns.map((col) => col.name), [selected]);

  const syncFiltersToOutputs = useCallback((indicator: SavedIndicator | null | undefined) => {
    const absorbed = absorbedFromIndicator(indicator);
    const outputs = absorbed.columns.map((col) => col.name);
    setFilters((prev) => {
      if (!outputs.length) return prev;
      const valid = prev.filter((item) => outputs.includes(item.field));
      const next = valid.length ? valid : absorbed.filters;
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
    fetchIndicators()
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

  const loadResults = useCallback(
    async (scanId: string, nextPage = page) => {
      const payload = await fetchIndicatorScanResults(scanId, {
        page: nextPage,
        page_size: pageSize,
        search: search || undefined,
        matched_only: matchedOnly,
        sort: sortField,
        direction: sortDir,
      });
      setResults(payload.results);
      setTotal(payload.total);
    },
    [page, pageSize, search, matchedOnly, sortField, sortDir],
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
        await loadResults(status.scan_id, 1);
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
    [loadResults, notify, stopPoll],
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
    if (isScanActive(scan)) {
      setBusy(true);
      poll(scanId);
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
        matchedOnly,
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
    matchedOnly,
    diagnostics,
  ]);

  useEffect(() => {
    if (scan?.scan_id && scan.status === "completed") {
      loadResults(scan.scan_id).catch(() => {});
    }
  }, [page, sortField, sortDir, search, matchedOnly, scan?.scan_id, scan?.status, loadResults]);

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
    setBusy(true);
    setResults([]);
    setTotal(0);
    setDiagnostics(null);
    setPage(1);
    try {
      const started = await startIndicatorScan(indicator.id, {
        universe_id: "nse-755",
        timeframe: "1D",
        scan_date: scanDate || lastCompletedSessionIST(),
        filters: cleanFilters(filters),
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

  const toggleSort = (field: string) => {
    if (sortField === field) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortField(field);
    setSortDir(field === "symbol" ? "asc" : "desc");
  };

  const scanning = busy || isScanActive(scan);
  const scanned = scan?.status === "completed";
  const displayRows: IndicatorScanRow[] = useMemo(() => {
    if (scanned) return results;
    const needle = search.trim().toUpperCase();
    return universeRows
      .filter(
        (row) =>
          !needle ||
          row.symbol.toUpperCase().includes(needle) ||
          (row.company || "").toUpperCase().includes(needle),
      )
      .map((row) => ({
        symbol: row.symbol,
        display_name: row.company || "",
        status: "pending",
        matched: false,
        outputs: {},
      }));
  }, [scanned, results, universeRows, search]);
  const listCount = scanned ? total : displayRows.length;
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
            Scanning…
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
        <label className="ind-pill" title="1D bar to evaluate (TradingView Pine Screener as-of)">
          <span className="ind-pill-prefix">As of</span>
          <input
            type="date"
            value={scanDate}
            max={lastCompletedSessionIST()}
            onChange={(e) => setScanDate(e.target.value || lastCompletedSessionIST())}
            data-testid="input-indicator-scan-date"
          />
        </label>
        {showScanChrome && (
          <label className="ind-pill ind-pill-grow">
            <select
              value={selected?.id || selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              data-testid="select-saved-indicator"
            >
              {!selected?.id && !selectedId && <option value="">Select indicator</option>}
              {visibleIndicators.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
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
        {outputNames.length > 0 && (
          <div className="ind-pill-wrap" data-testid="indicator-absorbed-columns">
            {outputNames.map((name) => (
              <button
                key={name}
                type="button"
                className="ind-pill"
                onClick={() => {
                  if (filters.some((item) => item.field === name)) return;
                  setFilters([...filters, { field: name, operator: "=", value: 1 }]);
                }}
              >
                {name}
              </button>
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
      </div>
      {scanSlot ? null : scanActions}
      </div>
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
          onClick={() => setFilters([...filters, { field: outputNames[0] || SIGNAL_FIELD, operator: "=", value: 1 }])}
          data-testid="btn-add-filter"
        >
          + Filter
        </button>
        <button type="button" className="st-btn-dark" onClick={() => setFilters([])} data-testid="btn-clear-filters">
          Clear Filters
        </button>
      </div>
      )}

      {scan && (
        <IndicatorRunStatusCard scan={scan} scanning={scanning} fallbackAsOf={scanDate} />
      )}
      {!scan && (
        <p className="ind-scan-strip" data-testid="indicator-scan-ready">
          {scanStatusText(null, Boolean(selected))}
        </p>
      )}

      <div className="ind-list-card">
        <div className="ind-results-header">
          <strong data-testid="indicator-result-count">
            Symbol {scanned ? total : listCount}
          </strong>
          <div className="ind-results-actions">
            <input
              className="st-search-box"
              placeholder="Search symbol"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              aria-label="Search results"
            />
            {showScanChrome && (
              <>
                <label className="ind-matched-toggle">
                  <input
                    type="checkbox"
                    checked={matchedOnly}
                    onChange={(e) => {
                      setMatchedOnly(e.target.checked);
                      setPage(1);
                    }}
                    data-testid="chk-matched-only"
                  />
                  Matched only
                </label>
                <button type="button" className="st-btn-dark" onClick={handleDiagnostics} disabled={!scan} data-testid="btn-indicator-diagnostics">
                  View Diagnostics
                </button>
                <button type="button" className="st-btn-dark" onClick={handleExport} disabled={!scan} data-testid="btn-export-indicator-csv">
                  Export CSV
                </button>
              </>
            )}
          </div>
        </div>

        <div className="ind-table-wrap">
          <table className="ind-results-table" data-testid="indicator-results-table">
            <thead>
              <tr>
                <th>
                  <button type="button" onClick={() => toggleSort("symbol")}>
                    Symbol {sortField === "symbol" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                  </button>
                </th>
                {outputNames.map((name) => (
                  <th key={name} className="is-numeric">
                    <button type="button" onClick={() => toggleSort(name)}>
                      {name} {sortField === name ? (sortDir === "asc" ? "↑" : "↓") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayRows.length === 0 ? (
                <tr>
                  <td colSpan={1 + outputNames.length} data-testid="indicator-empty-state">
                    {scan?.status === "completed"
                      ? "No stocks matched the current indicator and filters."
                      : "Loading universe…"}
                  </td>
                </tr>
              ) : (
                displayRows.map((row) => (
                  <tr
                    key={row.symbol}
                    tabIndex={0}
                    onClick={() => navigateToStock(navigate, row.symbol, { returnTo: "/strategy-tester" })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") navigateToStock(navigate, row.symbol, { returnTo: "/strategy-tester" });
                    }}
                    data-testid={`indicator-row-${row.symbol}`}
                  >
                    <td>
                      <div className="ind-symbol-cell">
                        <span className="ind-logo" style={{ background: logoHue(row.symbol) }} aria-hidden>
                          {row.symbol.slice(0, 1)}
                        </span>
                        <span className="ind-symbol-ticker">{row.symbol}</span>
                        <span className="ind-symbol-name">{row.display_name || ""}</span>
                      </div>
                    </td>
                    {outputNames.map((name) => {
                      const value = row.outputs?.[name];
                      const isSignal =
                        typeof value === "boolean" ||
                        name.toLowerCase().includes("signal") ||
                        name.toLowerCase().includes("breakout");
                      return (
                        <td key={name} className={`is-numeric ${isSignal && (value === 1 || value === true) ? "is-signal-on" : ""}`}>
                          {formatValue(value)}
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {total > pageSize && (
          <div className="ind-pagination">
            <button type="button" className="st-btn-dark" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span>
              Page {page} of {Math.ceil(total / pageSize)}
            </span>
            <button
              type="button"
              className="st-btn-dark"
              disabled={page >= Math.ceil(total / pageSize)}
              onClick={() => setPage(page + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>

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
    </section>
  );
};
