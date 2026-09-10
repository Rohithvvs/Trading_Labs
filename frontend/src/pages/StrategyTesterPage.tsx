import React, { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  exportStrategyRun,
  fetchFilterAnalytics,
  fetchSavedStrategies,
  fetchStrategyCatalog,
  fetchStrategyHistory,
  fetchStrategyResults,
  fetchStrategyRun,
  saveStrategyDefinition,
  startStrategyTest,
  updateStrategyDefinition,
  type FilterStat,
  type FunnelStep,
  type HistoryRow,
  type SavedStrategyItem,
  type StrategyCatalog,
  type StrategyConfigPayload,
  type StrategyResultRow,
  type StrategyRunStatus,
} from "../api_strategy_tester";
import { buildStrategyPayload, mapRawFilterToModalFilter } from "../utils/strategyFilterPayload";
import { AllStockResultsTable } from "../components/strategy_tester/AllStockResultsTable";
import { ColumnsConfigModal } from "../components/strategy_tester/ColumnsConfigModal";
import { FilterAnalyticsCard } from "../components/strategy_tester/FilterAnalyticsCard";
import { FilterFunnelCard } from "../components/strategy_tester/FilterFunnelCard";
import { ImportStrategyModal } from "../components/strategy_tester/ImportStrategyModal";
import { RunStatusRow } from "../components/strategy_tester/RunStatusRow";
import { SaveStrategyModal } from "../components/strategy_tester/SaveStrategyModal";
import { SignalDistributionCard } from "../components/strategy_tester/SignalDistributionCard";
import {
  StrategyBuilderCard,
  type StrategyBuilderRule,
} from "../components/strategy_tester/StrategyBuilderCard";
import {
  StrategyBuilderModal,
  type ModalBuilderFilter,
} from "../components/strategy_tester/StrategyBuilderModal";
import { StrategyConfigurationPanel } from "../components/strategy_tester/StrategyConfigurationPanel";
import { StrategyTesterHeader } from "../components/strategy_tester/StrategyTesterHeader";
import { TopReturnsCard } from "../components/strategy_tester/TopReturnsCard";
import { navigateToStock } from "../utils/stockNavigation";
import { DEFAULT_PINE_TEMPLATE } from "../utils/pineParser";
import { IndicatorScreenerPanel } from "../components/strategy_tester/IndicatorScreenerPanel";
import type { SavedIndicator } from "../api_indicator_scanner";
import { useToast } from "../design-system";
import { isoDateIST } from "../utils/tradingHours";
import {
  resolveSelectedStrategyId,
  strategySelectOptions,
  uniqueStrategiesByIdAndName,
} from "../utils/strategyTesterState";
import "./strategyTester.css";

/** Pine Screener always evaluates the last 1D bar. A leftover window end scans a different tape. */
function pineScreenerEndDate(endDate: string | null | undefined): string {
  const today = isoDateIST();
  if (!endDate || endDate < today) return today;
  return endDate;
}

const DEFAULT_FILTERS: ModalBuilderFilter[] = [
  { id: "f1", field: "CLOSE", operator: ">", rightKind: "indicator", literal: "", indicator: "SMA", indicatorPeriod: "50", low: "", high: "" },
  { id: "f2", field: "SMA", period: "50", operator: ">", rightKind: "indicator", literal: "", indicator: "SMA", indicatorPeriod: "200", low: "", high: "" },
  { id: "f3", field: "RSI", period: "14", operator: ">", rightKind: "literal", literal: "55", indicator: "SMA", indicatorPeriod: "20", low: "", high: "" },
  { id: "f4", field: "VOLUME", operator: ">", rightKind: "indicator", literal: "", indicator: "AVG_VOLUME", indicatorPeriod: "20", low: "", high: "" },
];

function toBuilderRule(f: ModalBuilderFilter): StrategyBuilderRule {
  if (f.label) {
    return { id: f.id, label: f.label, join: "AND" };
  }
  if (f.isBenchmark || f.field === "BENCHMARK_CLOSE") {
    const sym = f.benchmarkSymbol || "NIFTY 500";
    const ind = f.indicator || "SMA";
    const per = f.indicatorPeriod || "50";
    return { id: f.id, label: `${sym} Close > ${sym} ${ind} ${per}`, join: "AND" };
  }

  let leftLabel = f.field;
  if (f.field === "CLOSE") leftLabel = "Close Price";
  else if (f.field === "HIGH") leftLabel = "High";
  else if (f.field === "LOW") leftLabel = "Low";
  else if (f.field === "OPEN") leftLabel = "Open";
  else if (f.field === "VOLUME") leftLabel = "Volume";
  else if (f.field === "RSI") leftLabel = f.period ? `RSI ${f.period}` : "RSI";
  else if (f.period) leftLabel = `${f.field} ${f.period}`;

  let opLabel = f.operator;
  if (opLabel === "cross_above") opLabel = "Crosses Above";
  else if (opLabel === "cross_below") opLabel = "Crosses Below";

  let label = `${leftLabel}`;
  if (f.operator === "between") {
    label = `${label} between ${f.low} and ${f.high}`;
  } else if (f.operator === "outside") {
    label = `${label} outside ${f.low} to ${f.high}`;
  } else if (f.rightKind === "indicator" || f.indicator) {
    let indLabel = f.indicator;
    if (indLabel === "AVG_VOLUME") {
      indLabel = `Average Volume ${f.indicatorPeriod || 20}`;
    } else if (indLabel === "HIGH" && f.indicatorPeriod) {
      indLabel = f.indicatorPeriod === "252" ? "Previous 252-Session High" : `Previous ${f.indicatorPeriod}-Day High`;
    } else if (indLabel === "LOW" && f.indicatorPeriod) {
      indLabel = f.indicatorPeriod === "252" ? "Previous 252-Session Low" : `Previous ${f.indicatorPeriod}-Day Low`;
    } else if (f.indicatorPeriod) {
      indLabel = `${indLabel} ${f.indicatorPeriod}`;
    }
    label = `${label} ${opLabel} ${indLabel}`;
  } else {
    label = `${label} ${opLabel} ${f.literal}`;
  }
  return { id: f.id, label, join: "AND" };
}

function asRows<T>(value: unknown, key: string): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const nested = (value as Record<string, unknown>)[key];
    if (Array.isArray(nested)) return nested as T[];
  }
  return [];
}

class StrategyTesterErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="strategy-tester-container" data-testid="strategy-tester-error" style={{ padding: 24 }}>
          <h1 className="st-page-header-title">Strategy Tester</h1>
          <p className="st-page-header-subtitle">The page failed to render. {this.state.error.message}</p>
          <button
            type="button"
            className="st-btn-primary"
            style={{ marginTop: 16 }}
            onClick={() => {
              try {
                sessionStorage.removeItem("strategy_tester_state_v1");
              } catch {
                /* ignore */
              }
              window.location.reload();
            }}
          >
            Reset and reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export const StrategyTesterPageInner: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();
  const notify = useCallback(
    (opts: { title: string; message?: string; type?: "success" | "error" | "warning" | "info" }) => {
      const api = toast as typeof toast & { pushToast?: (o: typeof opts) => void };
      if (typeof api.pushToast === "function") {
        api.pushToast(opts);
        return;
      }
      const level = opts.type ?? "info";
      toast[level](opts.title, opts.message);
    },
    [toast],
  );

  const STORAGE_KEY = "strategy_tester_state_v1";
  const savedState = useMemo(() => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : null;
      if (!parsed || typeof parsed !== "object") return null;
      if (parsed.filters && !Array.isArray(parsed.filters)) parsed.filters = null;
      return parsed;
    } catch {
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
      return null;
    }
  }, []);

  // Strategy metadata
  const [catalog, setCatalog] = useState<StrategyCatalog | null>(null);
  const [savedStrategies, setSavedStrategies] = useState<SavedStrategyItem[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>(savedState?.selectedPresetId || "momentum");
  const [strategyName, setStrategyName] = useState<string>(savedState?.strategyName || "Momentum Strategy");
  const [strategyDesc, setStrategyDesc] = useState<string>(
    savedState?.strategyDesc || "Momentum based strategy using trend, momentum and volume filters."
  );
  const [strategySource, setStrategySource] = useState<"builder" | "pine">(savedState?.strategySource || "builder");
  const [pineCode, setPineCode] = useState<string>(savedState?.pineCode || DEFAULT_PINE_TEMPLATE);
  const [universe] = useState<string>("ALL_755");
  const [universeCount, setUniverseCount] = useState<number>(755);
  const [timeframe, setTimeframe] = useState<string>(savedState?.timeframe || "1 Day");
  const [startDate, setStartDate] = useState<string>(savedState?.startDate || "2024-01-01");
  const [endDate, setEndDate] = useState<string>(pineScreenerEndDate(savedState?.endDate));
  const [initialCapital, setInitialCapital] = useState<number>(
    typeof savedState?.initialCapital === "number" ? savedState.initialCapital : 1000000
  );
  const [positionSide, setPositionSide] = useState<"LONG" | "SHORT">(savedState?.positionSide || "LONG");
  const [logic, setLogic] = useState<"ALL" | "ANY">(savedState?.logic || "ALL");
  const [filters, setFilters] = useState<ModalBuilderFilter[]>(
    Array.isArray(savedState?.filters) && savedState.filters.length ? savedState.filters : DEFAULT_FILTERS,
  );

  // Run execution state
  const [activeRun, setActiveRun] = useState<StrategyRunStatus | null>(null);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [filterAnalytics, setFilterAnalytics] = useState<{
    independent: FilterStat[];
    funnel: FunnelStep[];
  } | null>(null);

  // Results table state
  const [results, setResults] = useState<StrategyResultRow[]>([]);
  const [totalResults, setTotalResults] = useState<number>(755);
  const [searchQuery, setSearchQuery] = useState<string>(savedState?.searchQuery || "");
  const [signalFilter, setSignalFilter] = useState<string>(savedState?.signalFilter || "ALL");
  const [returnFilter, setReturnFilter] = useState<string>(savedState?.returnFilter || "ALL");
  const [sortColumn, setSortColumn] = useState<string>(savedState?.sortColumn || "return_pct");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">(savedState?.sortDirection || "desc");
  const [currentPage, setCurrentPage] = useState<number>(savedState?.currentPage || 1);
  const [pageSize, setPageSize] = useState<number>(savedState?.pageSize || 25);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(savedState?.selectedSymbol || null);
  const [selectedEngine, setSelectedEngine] = useState<string>(savedState?.selectedEngine || "LEAN");

  // Modals state
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [isSaveModalOpen, setIsSaveModalOpen] = useState<boolean>(false);
  const [isBuilderModalOpen, setIsBuilderModalOpen] = useState<boolean>(false);
  const [isColumnsModalOpen, setIsColumnsModalOpen] = useState<boolean>(false);
  const [workspace, setWorkspace] = useState<"strategy" | "indicator">(
    savedState?.workspace === "indicator" ? "indicator" : "strategy",
  );
  const [builderTab, setBuilderTab] = useState<"builder" | "pine" | "indicator">("builder");
  const [appliedIndicator, setAppliedIndicator] = useState<SavedIndicator | null>(
    savedState?.appliedIndicator && savedState.appliedIndicator.id ? savedState.appliedIndicator : null,
  );
  const [editExistingIndicator, setEditExistingIndicator] = useState(false);

  // Visible columns
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => {
    const columns = new Set(
      savedState?.visibleColumns && Array.isArray(savedState.visibleColumns)
        ? savedState.visibleColumns
        : [
            "rank",
            "symbol",
            "company",
            "signal",
            "evaluation_date",
            "exit_price",
            "high_252",
            "volume",
            "avg_volume",
            "pass_count",
            "fail_count",
            "primary_failure",
          ],
    );
    columns.add("evaluation_date");
    columns.add("high_252");
    return columns;
  });

  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Sync state changes to sessionStorage to preserve Strategy Tester state
  useEffect(() => {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          selectedPresetId,
          strategyName,
          strategyDesc,
          strategySource,
          pineCode,
          timeframe,
          startDate,
          endDate,
          initialCapital,
          positionSide,
          logic,
          filters,
          searchQuery,
          signalFilter,
          returnFilter,
          sortColumn,
          sortDirection,
          currentPage,
          pageSize,
          visibleColumns: Array.from(visibleColumns),
          selectedSymbol,
          activeRunId: activeRun?.run_id,
          workspace,
          appliedIndicator,
        })
      );
      if (activeRun?.run_id) {
        localStorage.setItem("strategy_tester_last_run_id", activeRun.run_id);
      }
    } catch {
      // ignore
    }
  }, [
    selectedPresetId,
    strategyName,
    strategyDesc,
    strategySource,
    pineCode,
    timeframe,
    startDate,
    endDate,
    initialCapital,
    positionSide,
    logic,
    filters,
    searchQuery,
    signalFilter,
    returnFilter,
    sortColumn,
    sortDirection,
    currentPage,
    pageSize,
    visibleColumns,
    selectedSymbol,
    activeRun?.run_id,
    workspace,
    appliedIndicator,
  ]);

  // Load catalog on mount
  useEffect(() => {
    fetchStrategyCatalog()
      .then((cat) => {
        if (typeof cat.universe_count === "number" && cat.universe_count > 0) {
          setUniverseCount(cat.universe_count);
        }
        setCatalog((prev) => ({
          ...cat,
          saved:
            Array.isArray(prev?.saved) && prev.saved.length > 0
              ? uniqueStrategiesByIdAndName(prev.saved)
              : uniqueStrategiesByIdAndName(asRows<SavedStrategyItem>(cat.saved, "strategies")),
        }));
      })
      .catch((err) => console.error("Failed to load catalog:", err));

    fetchSavedStrategies()
      .then((saved) => {
        const list = uniqueStrategiesByIdAndName(asRows<SavedStrategyItem>(saved, "strategies"));
        setSavedStrategies(list);
        setCatalog((prev) => (prev ? { ...prev, saved: list } : prev));
      })
      .catch(() => {});

    // Check history for existing latest run
    fetchStrategyHistory()
      .then(async (history) => {
        const rows = asRows<HistoryRow>(history, "runs");
        if (rows.length > 0) {
          const latest = rows[0];
          try {
            const runData = await fetchStrategyRun(latest.run_id);
            setActiveRun(runData);
            if (typeof runData.universe_size === "number" && runData.universe_size > 0) {
              setUniverseCount(runData.universe_size);
            }
            localStorage.setItem("strategy_tester_last_run_id", latest.run_id);
            if (runData.status === "completed") {
              const [analytics, pageResults] = await Promise.all([
                fetchFilterAnalytics(latest.run_id).catch(() => null),
                fetchStrategyResults(latest.run_id, {
                  page: savedState?.currentPage || 1,
                  page_size: savedState?.pageSize || 25,
                  search: savedState?.searchQuery || undefined,
                  signal: savedState?.signalFilter && savedState.signalFilter !== "ALL" ? savedState.signalFilter : undefined,
                  return_bucket: savedState?.returnFilter && savedState.returnFilter !== "ALL" ? savedState.returnFilter : undefined,
                  sort: savedState?.sortColumn || "return_pct",
                  direction: savedState?.sortDirection || "desc",
                }).catch(() => null),
              ]);
              if (analytics) setFilterAnalytics(analytics);
              if (pageResults) {
                setResults(pageResults.results);
                setTotalResults(pageResults.total);
              }
            }
          } catch (e) {
            console.error("Failed to load latest run details:", e);
          }
        }
      })
      .catch(() => {});
  }, [savedState]);

  useEffect(() => {
    if (!catalog) return;
    const options = strategySelectOptions(catalog.presets, savedStrategies);
    setSelectedPresetId((current) => resolveSelectedStrategyId(current, options, catalog.presets, savedStrategies));
  }, [catalog, savedStrategies]);

  // Poll active run
  const pollRun = useCallback(
    (runId: string) => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);

      pollIntervalRef.current = setInterval(async () => {
        try {
          const status = await fetchStrategyRun(runId);
          setActiveRun(status);
          if (typeof status.universe_size === "number" && status.universe_size > 0) {
            setUniverseCount(status.universe_size);
          }
          localStorage.setItem("strategy_tester_last_run_id", runId);

          if (status.status === "completed" || status.status === "failed" || status.status === "cancelled") {
            if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
            setIsRunning(false);

            if (status.status === "completed") {
              const scanned = status.universe_size || status.total_count || 755;
              notify({ title: "Strategy test complete", message: `Scanned ${scanned} stocks successfully.`, type: "success" });

              const [analytics, pageResults] = await Promise.all([
                fetchFilterAnalytics(runId).catch(() => null),
                fetchStrategyResults(runId, {
                  page: 1,
                  page_size: pageSize,
                  sort: sortColumn,
                  direction: sortDirection,
                }).catch(() => null),
              ]);

              if (analytics) setFilterAnalytics(analytics);
              if (pageResults) {
                setResults(pageResults.results);
                setTotalResults(pageResults.total);
              }
            } else if (status.status === "failed") {
              notify({ title: "Strategy test failed", message: status.error || status.error_detail || "Execution error", type: "error" });
            }
          }
        } catch (err) {
          console.error("Polling error:", err);
        }
      }, 1200);
    },
    [pageSize, notify, sortColumn, sortDirection]
  );

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // Fetch results table data on parameter changes
  const loadResultsPage = useCallback(
    async (page: number, size: number, q: string, sig: string, ret: string, sort: string, dir: "asc" | "desc") => {
      if (!activeRun?.run_id) return;
      try {
        const data = await fetchStrategyResults(activeRun.run_id, {
          page,
          page_size: size,
          search: q || undefined,
          signal: sig !== "ALL" ? sig : undefined,
          return_bucket: ret !== "ALL" ? ret : undefined,
          sort,
          direction: dir,
        });
        setResults(data.results);
        setTotalResults(data.total);
      } catch (err) {
        console.error("Failed to load results page:", err);
      }
    },
    [activeRun?.run_id]
  );

  // Trigger results fetch on table filter/page changes
  useEffect(() => {
    if (activeRun?.run_id && activeRun.status === "completed") {
      loadResultsPage(currentPage, pageSize, searchQuery, signalFilter, returnFilter, sortColumn, sortDirection);
    }
  }, [activeRun?.run_id, activeRun?.status, currentPage, pageSize, searchQuery, signalFilter, returnFilter, sortColumn, sortDirection, loadResultsPage]);

  // Handle stock click: navigate to dedicated stock details page (/stock/:symbol)
  const handleStockSelect = useCallback(
    (symbol: string) => {
      setSelectedSymbol(symbol);
      const found = results.find((r) => r.symbol.toUpperCase() === symbol.toUpperCase());
      navigateToStock(navigate, symbol, {
        runId: activeRun?.run_id,
        returnTo: "/strategy-tester",
        state: {
          stock: found || null,
          runId: activeRun?.run_id,
        },
      });
    },
    [navigate, activeRun?.run_id, results]
  );

  // Run strategy handler
  const handleRunStrategy = async (overrideConfig?: {
    name?: string;
    description?: string;
    filters?: ModalBuilderFilter[];
    logic?: "ALL" | "ANY";
    side?: "LONG" | "SHORT";
    source?: { type: "builder" | "pine"; pine_code?: string };
  }) => {
    try {
      setIsRunning(true);
      // Clear stale results immediately so user sees fresh scanning state
      setResults([]);
      setFilterAnalytics(null);

      const effName = overrideConfig?.name ?? strategyName;
      const effDesc = overrideConfig?.description ?? strategyDesc;
      const effFilters = overrideConfig?.filters ?? filters;
      const effLogic = overrideConfig?.logic ?? logic;
      const effSide = overrideConfig?.side ?? positionSide;
      const effSource = overrideConfig?.source ?? { type: strategySource, pine_code: pineCode };

      const scanEnd = pineScreenerEndDate(endDate);
      if (scanEnd !== endDate) {
        setEndDate(scanEnd);
      }

      const payload: StrategyConfigPayload = buildStrategyPayload({
        name: effName,
        description: effDesc,
        universe,
        timeframe,
        side: effSide,
        startDate,
        endDate: scanEnd,
        initialCapital,
        filters: effFilters,
        logic: effLogic,
        source: effSource,
      });

      const startRes = await startStrategyTest(payload);
      if (typeof startRes.universe_size === "number" && startRes.universe_size > 0) {
        setUniverseCount(startRes.universe_size);
      }
      const runningCount = startRes.universe_size || universeCount;
      notify({
        title: "Strategy test started",
        message: `Run ID: ${startRes.run_id} running across ${runningCount} stocks.`,
        type: "info",
      });

      pollRun(startRes.run_id);
    } catch (err: any) {
      setIsRunning(false);
      notify({
        title: "Failed to start strategy test",
        message: err.message || "Unknown error",
        type: "error",
      });
    }
  };

  // Reset to default momentum configuration
  const handleReset = () => {
    setSelectedPresetId("momentum");
    setStrategyName("Momentum Strategy");
    setStrategyDesc("Momentum based strategy using trend, momentum and volume filters.");
    setStartDate("2024-01-01");
    setEndDate(isoDateIST());
    setInitialCapital(1000000);
    setPositionSide("LONG");
    setLogic("ALL");
    setFilters(DEFAULT_FILTERS);
    setTimeframe("1 Day");
    setStrategySource("builder");
    setPineCode(DEFAULT_PINE_TEMPLATE);
    notify({ title: "Reset complete", message: "Restored default Momentum Strategy parameters.", type: "info" });
  };

  // Preset switch
  const handlePresetChange = (presetId: string) => {
    setSelectedPresetId(presetId);
    const p = catalog?.presets?.find((item) => item.preset_id === presetId);
    if (p) {
      setStrategyName(p.name);
      setStrategyDesc(p.description);
      if (p.filters && Array.isArray(p.filters)) {
        setFilters(p.filters.map(mapRawFilterToModalFilter));
      }
      if (p.side) {
        setPositionSide(p.side);
      }
      if (p.signal_rules?.buy_requires_all !== undefined) {
        setLogic(p.signal_rules.buy_requires_all ? "ALL" : "ANY");
      }
    } else {
      const savedList = Array.isArray(savedStrategies)
        ? savedStrategies
        : asRows<SavedStrategyItem>(catalog?.saved, "strategies");
      const s = savedList.find((item) => item.id === presetId);
      if (s) {
        setStrategyName(s.name);
        setStrategyDesc(s.description || "");
        if (s.config?.filters && Array.isArray(s.config.filters)) {
          setFilters(s.config.filters.map(mapRawFilterToModalFilter));
        }
        if (s.config?.side) {
          setPositionSide(s.config.side);
        }
        if (s.config?.signal_rules?.buy_requires_all !== undefined) {
          setLogic(s.config.signal_rules.buy_requires_all ? "ALL" : "ANY");
        }
        if (s.config?.source) {
          setStrategySource(s.config.source.type || "builder");
          if (s.config.source.pine_code) {
            setPineCode(s.config.source.pine_code);
          }
        }
      }
    }
  };

  // Export CSV handler
  const handleExportCSV = async () => {
    if (!activeRun?.run_id) {
      notify({ title: "No run data", message: "Please run a strategy test first.", type: "warning" });
      return;
    }
    try {
      await exportStrategyRun(activeRun.run_id, "csv");
      notify({ title: "Export downloaded", message: "CSV file generated successfully.", type: "success" });
    } catch (err: any) {
      notify({ title: "Export failed", message: err.message || "Unable to export.", type: "error" });
    }
  };

  const persistCurrentStrategy = useCallback(
    async (payload: StrategyConfigPayload) => {
      const selectedSaved = savedStrategies.find((item) => item.id === selectedPresetId);
      if (selectedSaved?.id) {
        return updateStrategyDefinition(selectedSaved.id, payload);
      }
      const match = uniqueStrategiesByIdAndName(savedStrategies).find(
        (item) => item.name.trim().toLowerCase() === payload.name.trim().toLowerCase(),
      );
      if (match?.id) {
        return updateStrategyDefinition(match.id, payload);
      }
      return saveStrategyDefinition(payload);
    },
    [savedStrategies, selectedPresetId],
  );

  const refreshSavedStrategies = useCallback(async (preferId?: string) => {
    const saved = uniqueStrategiesByIdAndName(asRows<SavedStrategyItem>(await fetchSavedStrategies(), "strategies"));
    setSavedStrategies(saved);
    setCatalog((prev) => (prev ? { ...prev, saved } : prev));
    if (preferId && saved.some((row) => row.id === preferId)) {
      setSelectedPresetId(preferId);
    }
    return saved;
  }, []);

  // Import JSON handler
  const handleImportJSON = (jsonStr: string) => {
    try {
      const parsed = JSON.parse(jsonStr);
      if (parsed.name) setStrategyName(parsed.name);
      if (parsed.description) setStrategyDesc(parsed.description);
      if (parsed.side) setPositionSide(parsed.side);
      if (parsed.signal_rules?.buy_requires_all !== undefined) {
        setLogic(parsed.signal_rules.buy_requires_all ? "ALL" : "ANY");
      }
      if (parsed.filters && Array.isArray(parsed.filters)) {
        setFilters(parsed.filters.map(mapRawFilterToModalFilter));
      }
      notify({ title: "Strategy imported", message: "Imported strategy configuration successfully.", type: "success" });
    } catch (e: any) {
      notify({ title: "Import failed", message: e.message, type: "error" });
    }
  };

  // Save Strategy handler
  const handleSaveStrategy = async (name: string, description: string) => {
    try {
      const payload: StrategyConfigPayload = buildStrategyPayload({
        name,
        description,
        universe,
        timeframe,
        side: positionSide,
        startDate,
        endDate,
        initialCapital,
        filters,
        logic,
        source: { type: strategySource, pine_code: pineCode },
      });
      const savedRow = await persistCurrentStrategy(payload);
      setStrategyName(name);
      setStrategyDesc(description);
      await refreshSavedStrategies(savedRow.id);
      notify({ title: "Strategy saved", message: `Saved strategy "${name}".`, type: "success" });
    } catch (e: any) {
      notify({ title: "Save failed", message: e.message, type: "error" });
    }
  };

  // Strategy Builder Modal Save & Apply
  const handleBuilderApply = async (
    name: string,
    description: string,
    newFilters: ModalBuilderFilter[],
    newLogic: "ALL" | "ANY",
    newSide: "LONG" | "SHORT",
    source: "builder" | "pine" = "builder",
    newPineCode?: string
  ) => {
    setStrategyName(name);
    setStrategyDesc(description);
    setFilters(newFilters);
    setLogic(newLogic);
    setPositionSide(newSide);
    setStrategySource(source);
    if (newPineCode) {
      setPineCode(newPineCode);
    }

    let savePayload: StrategyConfigPayload;
    try {
      const scanEnd = pineScreenerEndDate(endDate);
      if (scanEnd !== endDate) {
        setEndDate(scanEnd);
      }
      savePayload = buildStrategyPayload({
        name,
        description,
        universe,
        timeframe,
        side: newSide,
        startDate,
        endDate: scanEnd,
        initialCapital,
        filters: newFilters,
        logic: newLogic,
        source: { type: source, pine_code: newPineCode || pineCode },
      });
    } catch (e: any) {
      notify({
        title: "Invalid strategy",
        message: e?.message || "Fix the filter conditions before applying.",
        type: "error",
      });
      return;
    }

    try {
      const savedRow = await persistCurrentStrategy(savePayload);
      await refreshSavedStrategies(savedRow.id);
    } catch (e: any) {
      notify({
        title: "Save failed",
        message: e?.message || "Unable to save strategy definition.",
        type: "error",
      });
    }

    await handleRunStrategy({
      name,
      description,
      filters: newFilters,
      logic: newLogic,
      side: newSide,
      source: { type: source, pine_code: newPineCode || pineCode },
    });
  };

  // Column toggle
  const handleToggleColumn = (colKey: string) => {
    const next = new Set(visibleColumns);
    if (next.has(colKey)) {
      if (next.size > 2) next.delete(colKey);
    } else {
      next.add(colKey);
    }
    setVisibleColumns(next);
  };

  const handleResetColumns = () => {
    setVisibleColumns(
      new Set([
        "rank",
        "symbol",
        "company",
        "signal",
        "evaluation_date",
        "exit_price",
        "high_252",
        "volume",
        "avg_volume",
        "pass_count",
        "fail_count",
        "primary_failure",
      ])
    );
  };

  const scrollToResultsTable = () => {
    const el = document.getElementById("all-results-section");
    if (el) el.scrollIntoView({ behavior: "smooth" });
  };

  // Convert builder filters to StrategyBuilderRules
  const builderRules = useMemo(
    () => (Array.isArray(filters) ? filters : DEFAULT_FILTERS).map(toBuilderRule),
    [filters],
  );

  const catalogView = useMemo(
    () => (catalog ? { ...catalog, saved: uniqueStrategiesByIdAndName(savedStrategies) } : catalog),
    [catalog, savedStrategies],
  );

  return (
    <div className="strategy-tester-container" data-testid="strategy-tester-page">
      {/* Main Content Column */}
      <main className="strategy-tester-main">
        {/* 1. Header */}
        <StrategyTesterHeader
          onImportClick={() => setIsImportModalOpen(true)}
          onSaveClick={() => setIsSaveModalOpen(true)}
          onNewClick={() => {
            setEditExistingIndicator(false);
            setBuilderTab(workspace === "indicator" ? "indicator" : "builder");
            setIsBuilderModalOpen(true);
          }}
          workspace={workspace}
          onWorkspaceChange={setWorkspace}
        />

        {workspace === "indicator" ? (
          <IndicatorScreenerPanel
            universeCount={universeCount}
            universeRows={catalog?.universe_symbols}
            appliedIndicator={appliedIndicator}
            navigate={navigate}
            onAddIndicator={() => {
              setEditExistingIndicator(false);
              setBuilderTab("indicator");
              setIsBuilderModalOpen(true);
            }}
            onEditIndicator={(indicator) => {
              setAppliedIndicator(indicator);
              setEditExistingIndicator(true);
              setBuilderTab("indicator");
              setIsBuilderModalOpen(true);
            }}
            notify={notify}
          />
        ) : (
          <>

        {/* 2. Strategy Configuration Panel */}
        <StrategyConfigurationPanel
          catalog={catalogView}
          selectedPresetId={selectedPresetId}
          selectedEngine={selectedEngine}
          strategyName={strategyName}
          strategyDescription={strategyDesc}
          universe={universe}
          universeCount={universeCount}
          timeframe={timeframe}
          startDate={startDate}
          endDate={endDate}
          initialCapital={initialCapital}
          isRunning={isRunning}
          onPresetChange={handlePresetChange}
          onEngineChange={setSelectedEngine}
          onEditStrategy={() => {
            setBuilderTab("builder");
            setIsBuilderModalOpen(true);
          }}
          onStartDateChange={setStartDate}
          onEndDateChange={setEndDate}
          onCapitalChange={setInitialCapital}
          onRunStrategy={handleRunStrategy}
          onReset={handleReset}
        />

        {/* 3. Run Status (3 Cards) */}
        <RunStatusRow run={activeRun} isRunning={isRunning} />

        {/* 4. Upper Analytics Grid: Strategy Builder (Left) | Stacked Top 5 Positive & Negative (Right) */}
        <section className="st-upper-analytics-grid" aria-label="Strategy overview analytics">
          {/* Left Column: Strategy Builder */}
          <div className="st-builder-col">
            <StrategyBuilderCard
              rules={builderRules}
              logicText={`Logic: ${logic} conditions must be true`}
              universeCount={universeCount}
              timeframe={timeframe}
              positionSide={positionSide === "LONG" ? "LONG ONLY" : "SHORT ONLY"}
              exitRule="EOD (End of Day)"
              capital={initialCapital}
              sourceType={strategySource}
              onEditClick={() => setIsBuilderModalOpen(true)}
            />
          </div>

          {/* Right Column: Top 5 Positive (top) + Top 5 Negative (bottom) STACKED */}
          <div className="st-top-returns-col">
            <TopReturnsCard
              type="positive"
              items={activeRun?.summary?.top_positive}
              totalCount={activeRun?.summary?.positive_returns ?? (activeRun?.summary?.buy ?? 42)}
              onStockClick={handleStockSelect}
              onViewAllClick={() => {
                setReturnFilter("POSITIVE");
                scrollToResultsTable();
              }}
            />
            <TopReturnsCard
              type="negative"
              items={activeRun?.summary?.top_negative}
              totalCount={activeRun?.summary?.negative_returns ?? (activeRun?.summary?.reject ?? 530)}
              onStockClick={handleStockSelect}
              onViewAllClick={() => {
                setReturnFilter("NEGATIVE");
                scrollToResultsTable();
              }}
            />
          </div>
        </section>

        {/* 5. Lower Analytics Grid: 3 Equal-Width Columns */}
        <section className="st-lower-analytics-grid" aria-label="Filter and signal analytics">
          {/* Column 1: Filter Analytics (Independent) */}
          <FilterAnalyticsCard
            stats={filterAnalytics?.independent}
            totalUniverse={universeCount}
          />

          {/* Column 2: Filter Funnel (Sequential) */}
          <FilterFunnelCard
            steps={filterAnalytics?.funnel}
            totalUniverse={universeCount}
            onStepClick={(step) => {
              if (step.step === 0) {
                setSignalFilter("ALL");
              } else if (step.filter_id === "final" || step.label?.toLowerCase().includes("buy")) {
                setSignalFilter("BUY");
              }
              scrollToResultsTable();
            }}
          />

          {/* Column 3: Signal Distribution Donut Chart */}
          <SignalDistributionCard
            buyCount={activeRun?.summary?.buy ?? activeRun?.buy ?? 42}
            watchCount={activeRun?.summary?.watch ?? activeRun?.watch ?? 183}
            rejectCount={activeRun?.summary?.reject ?? activeRun?.reject ?? 530}
            failedCount={
              (activeRun?.summary?.insufficient_data ?? 0) +
              (activeRun?.summary?.errors ?? 0) +
              (activeRun?.summary?.error_count ?? 0)
            }
            totalUniverse={universeCount}
            onSignalClick={(sig) => {
              setSignalFilter(sig);
              scrollToResultsTable();
            }}
          />
        </section>

        {/* 6. All Stock Results Table */}
        <AllStockResultsTable
          results={results}
          totalResults={totalResults}
          selectedSymbol={selectedSymbol}
          searchQuery={searchQuery}
          signalFilter={signalFilter}
          returnFilter={returnFilter}
          sortColumn={sortColumn}
          sortDirection={sortDirection}
          currentPage={currentPage}
          pageSize={pageSize}
          visibleColumns={visibleColumns}
          buyCount={activeRun?.summary?.buy ?? activeRun?.buy ?? 42}
          watchCount={activeRun?.summary?.watch ?? activeRun?.watch ?? 183}
          rejectCount={activeRun?.summary?.reject ?? activeRun?.reject ?? 530}
          failedCount={
            (activeRun?.summary?.insufficient_data ?? 0) +
            (activeRun?.summary?.errors ?? 0) +
            (activeRun?.summary?.error_count ?? 0)
          }
          onSearchChange={setSearchQuery}
          onSignalFilterChange={setSignalFilter}
          onReturnFilterChange={setReturnFilter}
          onSortChange={(col) => {
            if (sortColumn === col) {
              setSortDirection(sortDirection === "asc" ? "desc" : "asc");
            } else {
              setSortColumn(col);
              setSortDirection("desc");
            }
          }}
          onPageChange={setCurrentPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setCurrentPage(1);
          }}
          onStockSelect={handleStockSelect}
          onColumnsClick={() => setIsColumnsModalOpen(true)}
          onExportClick={handleExportCSV}
        />
          </>
        )}
      </main>

      {/* Modals */}
      <ImportStrategyModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onImport={handleImportJSON}
      />

      <SaveStrategyModal
        isOpen={isSaveModalOpen}
        initialName={strategyName}
        initialDescription={strategyDesc}
        onClose={() => setIsSaveModalOpen(false)}
        onSave={handleSaveStrategy}
      />

      <StrategyBuilderModal
        isOpen={isBuilderModalOpen}
        initialName={strategyName}
        initialDescription={strategyDesc}
        initialFilters={filters}
        initialLogic={logic}
        initialSide={positionSide}
        initialSource={strategySource}
        initialPineCode={pineCode}
        initialTab={builderTab}
        editingIndicator={builderTab === "indicator" && editExistingIndicator ? appliedIndicator : null}
        onClose={() => setIsBuilderModalOpen(false)}
        onApply={handleBuilderApply}
        onApplyIndicator={(indicator, applyToScreener = true) => {
          setAppliedIndicator(indicator);
          if (applyToScreener) {
            setWorkspace("indicator");
            setEditExistingIndicator(false);
          }
        }}
      />

      <ColumnsConfigModal
        isOpen={isColumnsModalOpen}
        visibleColumns={visibleColumns}
        onClose={() => setIsColumnsModalOpen(false)}
        onToggleColumn={handleToggleColumn}
        onResetColumns={handleResetColumns}
      />
    </div>
  );
};

export const StrategyTesterPage: React.FC = () => (
  <StrategyTesterErrorBoundary>
    <StrategyTesterPageInner />
  </StrategyTesterErrorBoundary>
);

export default StrategyTesterPage;
