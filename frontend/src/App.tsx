import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Route, Routes, useNavigate, useSearchParams } from "react-router-dom";

import {
  cacheLatestScanFromScreenerResponse,
  fetchUniverses,
  invalidateLatestScanCaches,
  loadScannerResultsByEngine,
  runPresetScreener,
  saveScannerPreset,
  type ScannerEngineId,
} from "./api";

const AllAnalyzedStocksTable = lazy(() =>
  import("./components/AllAnalyzedStocksTable").then((m) => ({ default: m.AllAnalyzedStocksTable })),
);
const CandidateTable = lazy(() =>
  import("./components/CandidateTable").then((m) => ({ default: m.CandidateTable })),
);
import type {
  CandidateRow,
  DashboardFilters,
  RankingItem,
  RecommendationPrefillRequest,
  ScanHistoryItem,
  ScreenerConditionResult,
  ScreenerResponse,
  SortKey,
  StockAnalysisResult,
} from "./types";

import { useAuth } from "./hooks/useAuth";
import { useTheme } from "./hooks/useTheme";
import { prefetchAppData } from "./utils/prefetchAppData";
import { ChartSkeleton, PanelSkeleton } from "./components/Skeleton";
import { AppShell } from "./layout/AppShell";
import { EmptyState, useToast } from "./design-system";
import { ScannerProgress } from "./components/ScannerProgress";
import { StatusCards } from "./components/StatusCards";
import { AdminRoute } from "./components/AdminRoute";
import FyersCallback from "./components/FyersCallback";
import { PaperOrderProvider } from "./contexts/PaperOrderContext";
import { navigateToPaperOrder } from "./utils/paperOrderNavigation";
import { FeaturePermissionsProvider } from "./contexts/FeaturePermissionsContext";
import { FeatureGuard } from "./components/FeatureGuard";
import { AccessDenied } from "./components/AccessDenied";

/** Code-split heavy modules — shell/nav paint first */
const PaperTradingPage = lazy(() =>
  import("./components/PaperTradingPage").then((m) => ({ default: m.PaperTradingPage })),
);
const PaperOrderPage = lazy(() =>
  import("./pages/PaperOrderPage").then((m) => ({ default: m.PaperOrderPage })),
);
const UserProfilePage = lazy(() =>
  import("./components/profile/UserProfilePage").then((m) => ({ default: m.UserProfilePage })),
);
const SystemLogs = lazy(() =>
  import("./pages/SystemLogs").then((m) => ({ default: m.SystemLogs })),
);
const CentralCommand = lazy(() =>
  import("./components/CentralCommand").then((m) => ({ default: m.CentralCommand })),
);
const StockDetailPanel = lazy(() =>
  import("./components/StockDetailPanel").then((m) => ({ default: m.StockDetailPanel })),
);
const MarketsPage = lazy(() =>
  import("./pages/MarketsPage").then((m) => ({ default: m.MarketsPage })),
);
const PerformancePage = lazy(() =>
  import("./pages/PerformancePage").then((m) => ({ default: m.PerformancePage })),
);
const RecommendationLabPage = lazy(() => import("./pages/RecommendationLabPage"));
const DiagnosticsPage = lazy(() =>
  import("./pages/Diagnostics").then((m) => ({ default: m.DiagnosticsPage })),
);
const AdminPanelPage = lazy(() =>
  import("./components/admin/AdminPanelPage").then((m) => ({ default: m.AdminPanelPage })),
);

function ViewFallback() {
  return (
    <div className="page-container" style={{ padding: 16 }} aria-busy="true">
      <PanelSkeleton title="Loading">
        <ChartSkeleton height={120} />
      </PanelSkeleton>
    </div>
  );
}

const DEFAULT_FILTERS: DashboardFilters = {
  signal: "ALL",
  search: "",
  scoreRange: [0, 100],
  sortBy: "rank",
  onlyHighConfidence: false,
};

const SCANNER_ENGINES: ScannerEngineId[] = ["Production", "RE-001", "RE-002"];

/** Parse `?engine=` query into a canonical ScannerEngineId (case-insensitive). */
function parseScannerEngineParam(raw: string | null | undefined): ScannerEngineId | null {
  if (!raw) return null;
  const upper = raw.trim().toUpperCase();
  if (upper === "PRODUCTION" || upper === "PROD" || upper === "BASELINE") return "Production";
  if (upper === "RE-001" || upper === "RE001") return "RE-001";
  if (upper === "RE-002" || upper === "RE002") return "RE-002";
  return null;
}

/** Build /scanner path preserving recommendation-engine context (and optional symbol). */
function buildScannerPath(opts: {
  engine?: ScannerEngineId | null;
  symbol?: string | null;
}): string {
  const qs = new URLSearchParams();
  if (opts.engine) qs.set("engine", opts.engine);
  if (opts.symbol) qs.set("symbol", opts.symbol);
  const s = qs.toString();
  return s ? `/scanner?${s}` : "/scanner";
}

type ScannerEngineSlice = {
  filters: DashboardFilters;
  screenerResult: ScreenerResponse | null;
  showAllAnalyzedStocks: boolean;
  selectedSymbol: string | null;
  error: string | null;
  lastScanDuration: number | null;
  loaded: boolean;
};

function emptyEngineSlice(): ScannerEngineSlice {
  return {
    filters: { ...DEFAULT_FILTERS },
    screenerResult: null,
    showAllAnalyzedStocks: false,
    selectedSymbol: null,
    error: null,
    lastScanDuration: null,
    loaded: false,
  };
}

export default function App() {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const toast = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const symbolParam = searchParams.get("symbol");
  const engineParam = searchParams.get("engine");
  /** Deep-link / refresh: restore engine from URL so context survives navigation. */
  const urlEngine = parseScannerEngineParam(engineParam) ?? "Production";

  const [timeframe, setTimeframe] = useState("1d");
  const [lookback, setLookback] = useState(180);
  const [topN, setTopN] = useState(20);
  const [selectedUniverse, setSelectedUniverse] = useState("NIFTY500");
  const [universes, setUniverses] = useState<{ name: string; symbols: string[]; count: number }[]>([]);
  const [savedScanName, setSavedScanName] = useState("");
  /** Active recommendation engine for Scanner view (independent result sets). */
  const [scannerEngine, setScannerEngine] = useState<ScannerEngineId>(urlEngine);
  const scannerEngineRef = useRef<ScannerEngineId>(urlEngine);
  /** One-shot: keep detail open when landing via ?symbol= after results restore. */
  const deepLinkSymbolRef = useRef<string | null>(
    symbolParam ? symbolParam.toUpperCase() : null,
  );
  useEffect(() => {
    scannerEngineRef.current = scannerEngine;
  }, [scannerEngine]);
  const [engineSlices, setEngineSlices] = useState<Record<ScannerEngineId, ScannerEngineSlice>>(() => ({
    Production: emptyEngineSlice(),
    "RE-001": emptyEngineSlice(),
    "RE-002": emptyEngineSlice(),
  }));
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS);
  const [screenerResult, setScreenerResult] = useState<ScreenerResponse | null>(null);
  const [scanHistory, setScanHistory] = useState<ScanHistoryItem[]>(() => loadScanHistory());
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [detailViewOpen, setDetailViewOpen] = useState(false);
  const [paperTradingPrefill, setPaperTradingPrefill] = useState<RecommendationPrefillRequest | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAllAnalyzedStocks, setShowAllAnalyzedStocks] = useState(false);

  const [progressData, setProgressData] = useState({
    stage: "Initializing...",
    progress: 0,
    current_symbol: "",
    worker_id: undefined as number | undefined,
    done: 0,
    remaining: 0,
    eta_sec: 0,
  });
  const [scanStartTime, setScanStartTime] = useState<number | null>(null);
  const [lastScanDuration, setLastScanDuration] = useState<number | null>(null);

  const applyEngineSlice = useCallback((slice: ScannerEngineSlice) => {
    setFilters(slice.filters);
    setScreenerResult(slice.screenerResult);
    setShowAllAnalyzedStocks(slice.showAllAnalyzedStocks);
    setSelectedSymbol(slice.selectedSymbol);
    setError(slice.error);
    setLastScanDuration(slice.lastScanDuration);
  }, []);

  const universesMapped = useMemo(
    () => universes.map(({ name, count }) => ({ name, count })),
    [universes],
  );

  const handleSearchChange = useCallback(
    (value: string) => setFilters((current) => ({ ...current, search: value })),
    [],
  );

  const loadEngineResults = useCallback(
    async (engine: ScannerEngineId, force = true) => {
      try {
        const data = await loadScannerResultsByEngine(engine, { force });
        if (!data || data.available === false) {
          setEngineSlices((prev) => ({
            ...prev,
            [engine]: {
              ...prev[engine],
              screenerResult: null,
              loaded: true,
              error: null,
            },
          }));
          if (scannerEngineRef.current === engine) {
            setScreenerResult(null);
            setError(null);
          }
          return;
        }
        const response = data as ScreenerResponse;
        response.shortlisted_symbols = response.shortlisted_symbols || [];
        response.buy_candidate_symbols = response.buy_candidate_symbols || [];
        response.watch_candidate_symbols = response.watch_candidate_symbols || [];
        const completedAt =
          response.last_scan_completed_at ??
          response.scanned_at ??
          response.analysis?.generated_at ??
          null;
        if (completedAt) {
          response.last_scan_completed_at = completedAt;
          response.scanned_at = response.scanned_at ?? completedAt;
        }
        const nextSymbol =
          response.shortlisted_symbols[0] ??
          response.buy_candidate_symbols[0] ??
          response.watch_candidate_symbols[0] ??
          null;
        setEngineSlices((prev) => ({
          ...prev,
          [engine]: {
            ...prev[engine],
            screenerResult: response,
            selectedSymbol: nextSymbol,
            loaded: true,
            error: null,
          },
        }));
        if (scannerEngineRef.current === engine) {
          setScreenerResult(response);
          setError(null);
          setSelectedSymbol(nextSymbol);
        }
        if (engine === "Production") {
          setScanHistory((current) => saveScanHistory(response, current));
        }
      } catch (err) {
        console.warn(`[scanner] failed to load ${engine} results`, err);
        setEngineSlices((prev) => ({
          ...prev,
          [engine]: { ...prev[engine], loaded: true },
        }));
      }
    },
    [],
  );

  const handleScannerEngineChange = useCallback(
    (next: ScannerEngineId) => {
      if (next === scannerEngine) return;

      const savedCurrent: ScannerEngineSlice = {
        ...engineSlices[scannerEngine],
        filters: { ...filters },
        screenerResult,
        showAllAnalyzedStocks,
        selectedSymbol,
        error,
        lastScanDuration,
        loaded: engineSlices[scannerEngine].loaded || screenerResult != null,
      };
      const target = engineSlices[next] ?? emptyEngineSlice();

      setEngineSlices((prev) => ({ ...prev, [scannerEngine]: savedCurrent }));
      setScannerEngine(next);
      setDetailViewOpen(false);
      // Preserve engine in URL so refresh / direct navigation keep the active tab.
      navigate(buildScannerPath({ engine: next }), { replace: true });

      if (target.loaded || target.screenerResult) {
        applyEngineSlice(target);
      } else {
        applyEngineSlice(emptyEngineSlice());
        void loadEngineResults(next, true);
      }
      // Lab engines: land on Scan Results so BUY+WATCH+REJECT (full Lab cohort) is visible by default.
      // Production keeps Favorites as the default shortlist view.
      if (next !== "Production") {
        setShowAllAnalyzedStocks(true);
      }
    },
    [
      scannerEngine,
      engineSlices,
      filters,
      screenerResult,
      showAllAnalyzedStocks,
      selectedSymbol,
      error,
      lastScanDuration,
      applyEngineSlice,
      loadEngineResults,
      navigate,
    ],
  );

  const handleSelectSymbol = useCallback(
    (symbol: string) => {
      setSelectedSymbol(symbol);
      setDetailViewOpen(true);
      // Carry active recommendation engine so Stock Detail / refresh keep origin context.
      navigate(
        buildScannerPath({ engine: scannerEngineRef.current, symbol }),
        { replace: true },
      );
      import("./utils/researchPrefetcher").then(({ markPrefetched }) => markPrefetched(symbol));
    },
    [navigate],
  );

  const handleDetailBack = useCallback(() => {
    setDetailViewOpen(false);
    // Return to the same engine tab that opened Stock Detail.
    navigate(buildScannerPath({ engine: scannerEngineRef.current }), { replace: true });
  }, [navigate]);

  // Warm app cache after login
  useEffect(() => {
    if (user?.id) prefetchAppData();
  }, [user?.id]);

  useEffect(() => {
    function loadAndApply(force = true) {
      // Restore the engine from URL (default Production) so refresh keeps context.
      const eng = scannerEngineRef.current;
      void loadScannerResultsByEngine(eng, { force }).then((saved) => {
        if (!saved || saved.available === false) return;
        const response = saved as ScreenerResponse;
        response.shortlisted_symbols = response.shortlisted_symbols || [];
        response.buy_candidate_symbols = response.buy_candidate_symbols || [];
        response.watch_candidate_symbols = response.watch_candidate_symbols || [];
        const completedAt =
          response.last_scan_completed_at ??
          response.scanned_at ??
          response.analysis?.generated_at ??
          null;
        if (completedAt) {
          response.last_scan_completed_at = completedAt;
          response.scanned_at = response.scanned_at ?? completedAt;
        }
        const nextSymbol =
          response.shortlisted_symbols[0] ??
          response.buy_candidate_symbols[0] ??
          response.watch_candidate_symbols[0] ??
          null;
        const deepSymbol = deepLinkSymbolRef.current;
        setEngineSlices((prev) => ({
          ...prev,
          [eng]: {
            ...prev[eng],
            screenerResult: response,
            selectedSymbol: deepSymbol ?? nextSymbol,
            loaded: true,
            error: null,
          },
        }));
        if (scannerEngineRef.current === eng) {
          setScreenerResult(response);
          setError(null);
          if (deepSymbol) {
            // Preserve deep-link / refresh into Stock Detail for this symbol.
            setSelectedSymbol(deepSymbol);
            setDetailViewOpen(true);
            deepLinkSymbolRef.current = null;
          } else {
            setSelectedSymbol(nextSymbol);
            setDetailViewOpen(false);
          }
        }
        if (eng === "Production") {
          setScanHistory((current) => saveScanHistory(response, current));
        }
      });
      // Warm Production slice for Markets widgets when URL engine is a lab engine.
      if (eng !== "Production") {
        void loadScannerResultsByEngine("Production", { force }).then((saved) => {
          if (!saved || saved.available === false) return;
          setEngineSlices((prev) => ({
            ...prev,
            Production: {
              ...prev.Production,
              screenerResult: saved as ScreenerResponse,
              loaded: true,
            },
          }));
        });
      }
    }

    loadAndApply(true);

    const intervalId = setInterval(() => {
      console.info("[scanner] 30-min auto-polling new cached scan...");
      // Refresh the active engine only so other engines keep their cached slices
      void loadEngineResults(scannerEngineRef.current, true);
    }, 30 * 60 * 1000);

    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount once; interval uses latest via ref
  }, []);

  // When engine changes, keep interval-safe: nothing extra — load handled in switcher.

  useEffect(() => {
    void fetchUniverses().then(setUniverses).catch((err) => console.warn("Failed to load universes", err));
  }, []);

  // Deep-link: /scanner?symbol=RELIANCE&engine=RE-001 opens stock detail (only on initial load)
  const initialLoad = useRef(true);
  useEffect(() => {
    if (initialLoad.current && symbolParam) {
      initialLoad.current = false;
      const sym = symbolParam.toUpperCase();
      deepLinkSymbolRef.current = sym;
      setSelectedSymbol(sym);
      setDetailViewOpen(true);
    }
  }, [symbolParam]);

  // Lab engines default to Scan Results view (same rule as handleScannerEngineChange).
  useEffect(() => {
    if (urlEngine !== "Production") {
      setShowAllAnalyzedStocks(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only on initial URL engine
  }, []);

  /** Markets / portfolio widgets always reflect Production, not the Scanner engine tab. */
  const productionScreenerResult = useMemo(
    () =>
      scannerEngine === "Production"
        ? screenerResult
        : engineSlices.Production.screenerResult,
    [scannerEngine, screenerResult, engineSlices.Production.screenerResult],
  );

  const analysisItems = screenerResult?.analysis?.items ?? [];
  const shortlistRows = useMemo(() => buildCandidateRows(screenerResult), [screenerResult]);
  /** Paper desk candidates stay Production-based (existing behavior). */
  const productionShortlistRows = useMemo(
    () => buildCandidateRows(productionScreenerResult),
    [productionScreenerResult],
  );

  const filteredRows = useMemo(() => {
    const searchTerm = filters.search.trim().toUpperCase();
    return shortlistRows
      .filter((row) => {
        if (filters.signal === "ALL") return true;
        const sig = (row.signal || "").toLowerCase().trim();
        if (filters.signal === "BUY") return sig === "buy" || sig === "bullish";
        if (filters.signal === "WATCH") return sig === "watch" || sig === "neutral" || sig === "sideways";
        if (filters.signal === "REJECT") return sig === "reject" || sig === "bearish" || sig === "sell";
        return true;
      })
      .filter((row) => {
        // Keep analysis-failed rows visible under REJECT; do not invent Score=100.
        if (row.score === null || row.score === undefined) {
          return filters.signal === "REJECT" || filters.signal === "ALL";
        }
        return row.score >= filters.scoreRange[0] && row.score <= filters.scoreRange[1];
      })
      .filter((row) => (filters.onlyHighConfidence ? (row.confidence ?? 0) >= 0.7 : true))
      .filter((row) => (searchTerm ? row.symbol.includes(searchTerm) : true))
      .sort((left, right) => compareRows(left, right, filters.sortBy));
  }, [filters, shortlistRows]);

  const selectedRow = useMemo(() => {
    if (!filteredRows.length) return null;
    return filteredRows.find((row) => row.symbol === selectedSymbol) ?? filteredRows[0];
  }, [filteredRows, selectedSymbol]);

  const summaryMetrics = useMemo(() => {
    const src = productionScreenerResult;
    const favoritesCount = src?.shortlisted_symbols.length ?? 0;
    const buyCount = src?.buy_candidate_symbols.length ?? 0;
    const watchCount = src?.watch_candidate_symbols.length ?? 0;
    const rejectedCount = Math.max(favoritesCount - buyCount - watchCount, 0);

    return [
      { label: "Total scanned", value: src?.scanned_symbols ?? "--", helper: "Stocks checked in the universe." },
      { label: "Data valid", value: src?.data_valid_symbols?.length ?? "--", helper: "Names with enough clean OHLCV history." },
      { label: "Trend matched", value: src?.eligible_symbols?.length ?? "--", helper: "Names passing the broad trend gate.", tone: "positive" as const },
      { label: "Favorites", value: favoritesCount || "--", helper: "Top set moved into deeper analysis." },
      { label: "BUY ideas", value: buyCount || "--", helper: "Actionable swing ideas right now.", tone: "positive" as const },
      { label: "WATCH ideas", value: watchCount || "--", helper: "Promising names needing confirmation.", tone: "warning" as const },
      { label: "Rejected", value: rejectedCount || "--", helper: "Names that failed final recommendation.", tone: "negative" as const },
    ];
  }, [productionScreenerResult]);

  const applyScanResult = useCallback(
    (response: ScreenerResponse, _source: "fresh" | "restored", engine: ScannerEngineId = "Production") => {
      response.shortlisted_symbols = response.shortlisted_symbols || [];
      response.buy_candidate_symbols = response.buy_candidate_symbols || [];
      response.watch_candidate_symbols = response.watch_candidate_symbols || [];
      // Keep timestamp card and table aligned even if one field is missing.
      const completedAt =
        response.last_scan_completed_at ??
        response.scanned_at ??
        response.analysis?.generated_at ??
        null;
      if (completedAt) {
        response.last_scan_completed_at = completedAt;
        response.scanned_at = response.scanned_at ?? completedAt;
      }

      const nextSymbol =
        response.shortlisted_symbols[0] ??
        response.buy_candidate_symbols[0] ??
        response.watch_candidate_symbols[0] ??
        null;

      // Always stash into the target engine slice
      setEngineSlices((prev) => ({
        ...prev,
        [engine]: {
          ...prev[engine],
          screenerResult: response,
          selectedSymbol: nextSymbol,
          loaded: true,
          error: null,
        },
      }));

      // Only paint the table when this engine is currently selected
      if (scannerEngineRef.current === engine) {
        setScreenerResult(response);
        setSelectedSymbol(nextSymbol);
        setError(null);
      }

      if (engine === "Production") {
        setScanHistory((current) => saveScanHistory(response, current));
      }
      setDetailViewOpen(false);
    },
    [],
  );

  const handleRunScanner = useCallback(async () => {
    const activeEngine = scannerEngine;
    setIsLoading(true);
    setError(null);
    setProgressData({
      stage:
        activeEngine === "Production"
          ? "Connecting data feed..."
          : `Running ${activeEngine} via swing scanner...`,
      progress: 0,
      current_symbol: "",
      worker_id: undefined,
      done: 0,
      remaining: 0,
      eta_sec: 0,
    });
    const startedAt = Date.now();
    setScanStartTime(startedAt);

    try {
      // Universe scan is shared infrastructure. Lab engines (RE-001/RE-002) evaluate
      // fail-open during the same production analysis path; we then reload that engine's view.
      const response = await runPresetScreener(
        "swing",
        {
          intraday: "5m",
          swing: timeframe,
          lookback_window: lookback,
        },
        selectedUniverse === "NIFTY500" ? [] : universes.find((item) => item.name === selectedUniverse)?.symbols ?? [],
        topN,
        (update) => {
          if (typeof update === "object") {
            setProgressData((prev) => ({
              ...prev,
              stage: update.stage || prev.stage,
              progress: update.progress ?? prev.progress,
              current_symbol: update.current_symbol ?? prev.current_symbol,
              worker_id: update.worker_id ?? prev.worker_id,
              done: update.done ?? prev.done,
              remaining: update.remaining ?? prev.remaining,
              eta_sec: update.eta_sec ?? prev.eta_sec,
            }));
          } else {
            setProgressData((prev) => ({ ...prev, stage: String(update), progress: 0 }));
          }
        },
      );

      const durationSec = Math.round((Date.now() - startedAt) / 1000);
      setLastScanDuration(durationSec);
      invalidateLatestScanCaches();
      cacheLatestScanFromScreenerResponse(response);
      // Always refresh Production slice with the raw screener payload
      applyScanResult(response, "fresh", "Production");

      if (activeEngine === "Production") {
        toast.success(
          "Production scan complete",
          `${response.buy_candidate_symbols?.length ?? 0} BUY · ${response.watch_candidate_symbols?.length ?? 0} WATCH`,
        );
      } else {
        // Reload RE engine projection after the shared scan produced new lab decisions
        await loadEngineResults(activeEngine, true);
        setLastScanDuration(durationSec);
        toast.success(
          `${activeEngine} scan complete`,
          "Showing lab decisions for this engine only.",
        );
      }
    } catch (requestError: any) {
      if (requestError?.scanInProgress) {
        toast.info("Scanner is already running. Please wait for it to complete.");
        return;
      }
      console.error("[scanner] scanner request failed", requestError);
      const detail = requestError?.response?.data?.detail || requestError?.detail || null;

      let errorMessage = "Scanner failed. Please try again.";

      if (detail?.error_type === "FYERS_TOKEN_EXPIRED") {
        errorMessage = "Broker session expired — reconnect your broker and try again.";
      } else if (detail?.error_type === "FYERS_TOKEN_INVALID") {
        errorMessage = "Broker credentials invalid — check your connection settings.";
      } else if (detail?.error_type === "FYERS_RATE_LIMIT") {
        errorMessage = "Rate limit hit — wait about 60 seconds and try again.";
      } else if (detail?.error_type === "FYERS_API_ERROR") {
        errorMessage = `Broker error — ${detail.message}`;
      } else if (detail?.message) {
        errorMessage = detail.message;
      } else if (typeof requestError?.message === "string") {
        errorMessage = requestError.message;
      }

      setError(errorMessage);
      toast.error("Scan failed", errorMessage);
      setScanStartTime(null);
    } finally {
      setIsLoading(false);
      setScanStartTime(null);
    }
  }, [timeframe, lookback, selectedUniverse, universes, topN, toast, applyScanResult, scannerEngine, loadEngineResults]);

  async function handleSaveCurrentScan() {
    const name = savedScanName.trim() || `${selectedUniverse} ${timeframe} scan`;
    try {
      await saveScannerPreset({
        name,
        mode: "swing",
        timeframe,
        lookback_window: lookback,
        top_n: topN,
        universe: selectedUniverse,
        symbols: selectedUniverse === "NIFTY500" ? [] : universes.find((item) => item.name === selectedUniverse)?.symbols ?? [],
        filters,
      });
      setSavedScanName("");
      toast.success("Scan saved", name);
    } catch (e: any) {
      toast.error("Could not save scan", e?.message);
    }
  }

  function loadSavedScan(scan: any) {
    setSelectedUniverse(scan.universe ?? "NIFTY500");
    setTimeframe(scan.timeframe ?? "1d");
    setLookback(scan.lookback_window ?? 180);
    setTopN(scan.top_n ?? 20);
    navigate("/scanner");
  }

  const sendRowToPaperTrading = useCallback((row: CandidateRow, suggestedEntry?: number | null) => {
    const prefill = buildPaperTradingPrefill(row, "BUY");
    const rec = row.analysisItem?.recommendation as
      | {
          recommendation_id?: string | null;
          source_engine_id?: string | null;
          source_engine_version?: string | null;
          experiment_id?: string | null;
        }
      | undefined;
    // Prefer explicit lab provenance from decision payload; never hardcode Production for lab engines
    const engineId =
      (rec?.source_engine_id && String(rec.source_engine_id)) ||
      scannerEngine ||
      "Production";
    const entry =
      (suggestedEntry != null && suggestedEntry > 0 ? suggestedEntry : null) ??
      (prefill.suggested_entry != null && prefill.suggested_entry > 0
        ? prefill.suggested_entry
        : null);
    const stop =
      prefill.suggested_stop != null && prefill.suggested_stop > 0
        ? prefill.suggested_stop
        : null;
    const targets = (prefill.suggested_targets || []).filter((t) => typeof t === "number" && t > 0);
    const updatedPrefill = {
      ...prefill,
      suggested_entry: entry,
      suggested_stop: stop,
      suggested_targets: targets,
      source_engine_id: engineId,
      source_engine_version:
        rec?.source_engine_version ||
        (engineId === "Production" ? "production" : rec?.source_engine_version) ||
        undefined,
      source_recommendation_id: rec?.recommendation_id ?? prefill.source_recommendation_id ?? null,
      experiment_id: rec?.experiment_id ?? prefill.experiment_id ?? null,
    };

    // Dedicated full-page order ticket — never open a drawer on Scanner
    navigateToPaperOrder(navigate, {
      symbol: row.symbol,
      side: "BUY",
      prefill: updatedPrefill,
      currentPrice: entry,
      signal: String(row.signal ?? "BUY"),
      score: row.score ?? null,
      confidence: row.confidence ?? null,
      riskReward: row.riskReward ?? null,
      returnTo: `${window.location.pathname}${window.location.search || ""}`,
    });
  }, [navigate, scannerEngine]);

  const scannerListView = useMemo(() => (
    <div className="scanner-center">
      {/* Row 1: Title (left) + CTA & status chips (right) — trading-desk header */}
      <header className="scanner-page-header" data-testid="scanner-page-header">
        <div className="scanner-page-header__left">
          <p className="ds-label">Scanner</p>
          <h1 className="ds-display">Scanner</h1>
          <p className="ds-muted">
            Favorites and scan results · engine: <strong>{scannerEngine}</strong>
          </p>
        </div>

        <div className="scanner-page-header__right">
          <div className="scanner-page-header__cta">
            <button
              type="button"
              className="button ghost-button scanner-page-header__run-btn"
              onClick={() => navigate("/markets")}
              data-testid="scanner-run-from-markets"
            >
              Run from Markets
            </button>
          </div>
          <StatusCards
            compact
            className="scanner-page-header__status"
            lastScanAt={
              screenerResult?.last_scan_completed_at ??
              screenerResult?.scanned_at ??
              screenerResult?.analysis?.generated_at ??
              null
            }
            isLoading={isLoading}
            scannedSymbols={screenerResult?.scanned_symbols ?? null}
            durationSec={lastScanDuration}
          />
        </div>
      </header>

      {/* Row 2: Result view tabs
          Favorites count = existing business rule (BUY+WATCH for lab engines; shortlist size for Production).
          Scan Results count = full analyzed cohort (must include REJECT for RE-001/RE-002).
      */}
      <div className="scanner-result-tabs" role="tablist" aria-label="Result views">
        <button
          type="button"
          role="tab"
          aria-selected={!showAllAnalyzedStocks}
          className={`button ${!showAllAnalyzedStocks ? "primary-button" : "ghost-button"}`}
          onClick={() => setShowAllAnalyzedStocks(false)}
        >
          Favorites (
          {scannerEngine === "Production"
            ? (screenerResult?.shortlisted_symbols.length ?? 0)
            : (screenerResult?.buy_candidate_symbols?.length ?? 0) +
              (screenerResult?.watch_candidate_symbols?.length ?? 0)}
          )
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={showAllAnalyzedStocks}
          className={`button ${showAllAnalyzedStocks ? "primary-button" : "ghost-button"}`}
          onClick={() => setShowAllAnalyzedStocks(true)}
          data-testid="scanner-scan-results-tab"
        >
          Scan results (
          {screenerResult?.all_analyzed_stocks?.length ??
            screenerResult?.shortlisted_symbols?.length ??
            0}
          {screenerResult && scannerEngine !== "Production"
            ? ` · ${(screenerResult as { buy_count?: number }).buy_count ?? screenerResult.buy_candidate_symbols?.length ?? 0}B / ${(screenerResult as { watch_count?: number }).watch_count ?? screenerResult.watch_candidate_symbols?.length ?? 0}W / ${(screenerResult as { reject_count?: number }).reject_count ?? Math.max((screenerResult.shortlisted_symbols?.length ?? 0) - (screenerResult.buy_candidate_symbols?.length ?? 0) - (screenerResult.watch_candidate_symbols?.length ?? 0), 0)}R`
            : ""}
          )
        </button>
      </div>

      {/* Row 3: Recommendation engine selector — independent result sets */}
      <div
        className="scanner-engine-tabs"
        role="tablist"
        aria-label="Recommendation engine"
        data-testid="scanner-engine-tabs"
      >
        {SCANNER_ENGINES.map((eng) => (
          <button
            key={eng}
            type="button"
            role="tab"
            aria-selected={scannerEngine === eng}
            data-testid={`scanner-engine-${eng}`}
            className={`button ${scannerEngine === eng ? "primary-button" : "ghost-button"}`}
            onClick={() => handleScannerEngineChange(eng)}
          >
            {eng}
          </button>
        ))}
      </div>

      {isLoading ? (
        <ScannerProgress
          data={progressData}
          error={error}
          startTime={scanStartTime}
          onRetry={handleRunScanner}
        />
      ) : null}

      {error ? (
        <section className="panel error-state" role="alert">
          <h2 className="ds-title">Scan failed</h2>
          <p>{error}</p>
          <button type="button" className="button primary-button" onClick={handleRunScanner} style={{ marginTop: 12 }}>
            Retry scan
          </button>
        </section>
      ) : null}

      {!isLoading && !error ? (
        showAllAnalyzedStocks && scannerEngine === "Production" ? (
          // Production: full-universe screener breakdown
          <AllAnalyzedStocksTable stocks={screenerResult?.all_analyzed_stocks ?? []} />
        ) : (() => {
          // Lab engines: shortlisted_symbols is the full Recommendation Lab cohort (BUY+WATCH+REJECT).
          // Scan Results → full filtered cohort (row count must match Lab).
          // Favorites → BUY+WATCH only (existing favorites business rule).
          const tableRows =
            scannerEngine !== "Production" && !showAllAnalyzedStocks
              ? filteredRows.filter((r) => r.signal === "BUY" || r.signal === "WATCH")
              : filteredRows;
          return tableRows.length ? (
            <CandidateTable
              rows={tableRows}
              selectedSymbol={selectedRow?.symbol ?? null}
              onSelect={handleSelectSymbol}
              onBuy={sendRowToPaperTrading}
              exportFilePrefix={`scan_${scannerEngine.replace(/-/g, "").toLowerCase()}`}
            />
          ) : screenerResult ? (
            <EmptyState
              title="No matches for these filters"
              description="Adjust signal, score range, or search from Markets to refine results."
              primaryAction={{ label: "Open Markets", onClick: () => navigate("/markets"), variant: "secondary" }}
            />
          ) : null;
        })()
      ) : null}

      {!screenerResult && !isLoading && !error ? (
        <EmptyState
          title={`No ${scannerEngine} scan results yet`}
          description={
            scannerEngine === "Production"
              ? "Configure and run the swing scanner from Markets. Results will appear here automatically."
              : `Run a scan with ${scannerEngine} selected (or complete a full swing scan so lab decisions are stored), then open this tab.`
          }
          primaryAction={{ label: "Go to Markets", onClick: () => navigate("/markets"), variant: "trade" }}
        />
      ) : null}

      {screenerResult ? (
        <section className="panel footer-note">
          <p>
            <strong>{screenerResult.screener_name}</strong> is advisory only. You make the final trading decision.
          </p>
          <p>
            Sample rows: {analysisItems.length} analyzed · {filteredRows.length} visible after filters.
          </p>
        </section>
      ) : null}
    </div>
  ), [
    handleRunScanner, handleSelectSymbol, navigate,
    screenerResult, isLoading, error, showAllAnalyzedStocks,
    analysisItems, filteredRows, shortlistRows, selectedRow?.symbol,
    progressData, scanStartTime, lastScanDuration,
    scannerEngine, handleScannerEngineChange, sendRowToPaperTrading,
  ]);

  const scannerView = (
    <main className="page-container" key="scanner-view">
      <div style={{ display: detailViewOpen && selectedRow ? "block" : "none" }}>
        <Suspense fallback={<ViewFallback />}>
          {selectedRow && (
            <StockDetailPanel
              row={selectedRow}
              onBack={handleDetailBack}
              onSendToPaperTrading={sendRowToPaperTrading}
              originEngine={scannerEngine}
            />
          )}
        </Suspense>
      </div>
      <div style={{ display: detailViewOpen && selectedRow ? "none" : "block" }}>
        {scannerListView}
      </div>
    </main>
  );

  const paperDeskView = useMemo(() => (
    <div className="page-container page-container--wide" key="paper-desk">
      <Suspense fallback={<ViewFallback />}>
        <PaperTradingPage
          recommendationPrefill={paperTradingPrefill}
          onPrefillConsumed={() => setPaperTradingPrefill(null)}
          scannerCandidates={productionShortlistRows}
          lastScanAt={productionScreenerResult?.analysis?.generated_at ?? null}
          retailMode
        />
      </Suspense>
    </div>
  ), [paperTradingPrefill, productionShortlistRows, productionScreenerResult?.analysis?.generated_at]);

  const profileView = useMemo(() => (
    <Suspense fallback={<ViewFallback />} key="profile">
      <UserProfilePage
        retailMode
        onNavigate={(view) => {
          if (view === "scanner") navigate("/scanner");
          else if (view === "paper-trading") navigate("/paper");
          else navigate("/markets");
        }}
      />
    </Suspense>
  ), [navigate]);

  return (
    <FeaturePermissionsProvider>
      <PaperOrderProvider>
        <AppShell>
          <Suspense fallback={<ViewFallback />}>
            <Routes>
              {/* Ungated core landing (audit M-4) — avoid defaulting into a gated route */}
              <Route path="/" element={<Navigate to="/markets" replace />} />
              <Route path="/home" element={<Navigate to="/markets" replace />} />
              <Route
                path="/markets"
                element={
                  <Suspense fallback={<ViewFallback />}>
                    <MarketsPage
                      onLoadSavedScan={loadSavedScan}
                      screenerResult={productionScreenerResult}
                      isLoading={isLoading && scannerEngine === "Production"}
                      scanError={scannerEngine === "Production" ? error : null}
                      selectedUniverse={selectedUniverse}
                      timeframe={timeframe}
                      summaryMetrics={summaryMetrics}
                      onRunScanner={handleRunScanner}
                      search={filters.search}
                      onSearchChange={handleSearchChange}
                      topN={topN}
                      lookback={lookback}
                      universe={selectedUniverse}
                      universes={universesMapped}
                      onTopNChange={setTopN}
                      onLookbackChange={setLookback}
                      onTimeframeChange={setTimeframe}
                      onUniverseChange={setSelectedUniverse}
                      theme={theme}
                      onThemeToggle={toggleTheme}
                      progressData={progressData}
                      scanStartTime={scanStartTime}
                    />
                  </Suspense>
                }
              />
              <Route
                path="/scanner"
                element={
                  <FeatureGuard feature="advanced_scanner" fallback={<AccessDenied />}>
                    {scannerView}
                  </FeatureGuard>
                }
              />
              <Route path="/watchlist" element={<Navigate to="/paper?tab=watchlist" replace />} />
              <Route path="/paper" element={paperDeskView} />
              <Route path="/paper/:section" element={paperDeskView} />
              <Route
                path="/paper-order"
                element={
                  <Suspense fallback={<ViewFallback />}>
                    <PaperOrderPage />
                  </Suspense>
                }
              />
              <Route
                path="/performance"
                element={
                  <FeatureGuard feature="portfolio_analytics" fallback={<AccessDenied />}>
                    <Suspense fallback={<ViewFallback />}>
                      <PerformancePage />
                    </Suspense>
                  </FeatureGuard>
                }
              />
              <Route
                path="/recommendation-lab"
                element={
                  <FeatureGuard feature="recommendation_lab" fallback={<AccessDenied />}>
                    <Suspense fallback={<ViewFallback />}>
                      <RecommendationLabPage />
                    </Suspense>
                  </FeatureGuard>
                }
              />
              <Route
                path="/diagnostics"
                element={
                  <Suspense fallback={<ViewFallback />}>
                    <DiagnosticsPage />
                  </Suspense>
                }
              />
              <Route path="/profile" element={profileView} />
              <Route path="/logs" element={<Navigate to="/admin/logs" replace />} />
              <Route
                path="/admin"
                element={
                  <AdminRoute>
                    <Suspense fallback={<ViewFallback />}>
                      <AdminPanelPage />
                    </Suspense>
                  </AdminRoute>
                }
              />
              <Route
                path="/admin/logs"
                element={
                  <AdminRoute>
                    <FeatureGuard feature="system_logs" fallback={<AccessDenied />}>
                      <Suspense fallback={<ViewFallback />}>
                        <SystemLogs />
                      </Suspense>
                    </FeatureGuard>
                  </AdminRoute>
                }
              />
              <Route
                path="/admin/command"
                element={
                  <AdminRoute>
                    <FeatureGuard feature="central_command" fallback={<AccessDenied />}>
                      <Suspense fallback={<ViewFallback />}>
                        <CentralCommand />
                      </Suspense>
                    </FeatureGuard>
                  </AdminRoute>
                }
              />
              <Route path="/fyers/callback" element={<FyersCallback />} />
              <Route path="*" element={<Navigate to="/markets" replace />} />
            </Routes>
          </Suspense>
        </AppShell>
        {/* Global BUY/SELL bus → dedicated /paper-order page (no drawer) */}
        <PaperOrderRouteBridge />
      </PaperOrderProvider>
    </FeaturePermissionsProvider>
  );
}

/** Listens for paper:open-order and navigates to the full-page order ticket. */
function PaperOrderRouteBridge() {
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (ev: Event) => {
      const detail = (ev as CustomEvent).detail || {};
      navigateToPaperOrder(navigate, {
        symbol: detail.symbol,
        side: detail.side ?? "BUY",
        prefill: detail.prefill ?? null,
        orderId: detail.orderId ?? null,
        returnTo: detail.returnTo,
        currentPrice: detail.currentPrice ?? null,
        signal: detail.signal ?? null,
        score: detail.score ?? null,
        confidence: detail.confidence ?? null,
        riskReward: detail.riskReward ?? null,
      });
    };
    window.addEventListener("paper:open-order", handler);
    return () => window.removeEventListener("paper:open-order", handler);
  }, [navigate]);

  return null;
}

function buildPaperTradingPrefill(row: CandidateRow, side?: "BUY" | "SELL"): RecommendationPrefillRequest {
  const plan =
    row.analysisItem?.recommendation.trade_plans.find((item) => item.mode === "swing") ??
    row.analysisItem?.recommendation.trade_plans[0];
  let suggested_stop: number | null = plan?.stop_loss ?? row.stopLoss ?? null;
  let suggested_targets: number[] = [plan?.target_1, plan?.target_2].filter(
    (value): value is number => typeof value === "number",
  );
  if (plan && side) {
    const needsSwap =
      (side === "BUY" && plan.bias === "short") || (side === "SELL" && plan.bias === "long");
    if (needsSwap && plan.target_1 != null && plan.stop_loss != null) {
      suggested_stop = plan.target_1;
      suggested_targets = [plan.stop_loss, plan.target_2].filter(
        (value): value is number => typeof value === "number",
      );
    }
  }
  const pos = (n: number | null | undefined): number | null =>
    n != null && Number.isFinite(n) && Number(n) > 0 ? Number(n) : null;
  let suggested_entry: number | null = null;
  if (plan) {
    const mid =
      plan.entry_low != null && plan.entry_high != null
        ? (Number(plan.entry_low) + Number(plan.entry_high)) / 2
        : Number(plan.entry_high ?? plan.entry_low);
    suggested_entry = pos(mid);
  } else {
    suggested_entry = pos(row.entryLow);
  }
  const recAny = row.analysisItem?.recommendation as
    | { recommendation_id?: string; source_engine_id?: string; source_engine_version?: string; experiment_id?: string }
    | undefined;

  return {
    symbol: row.symbol,
    suggested_entry,
    suggested_stop: pos(suggested_stop),
    suggested_targets: suggested_targets.map((t) => pos(t)).filter((t): t is number => t != null),
    recommendation_meta: {
      signal: row.signal,
      score: row.score ?? 0,
      confidence: Math.round((row.confidence ?? 0) * 100) / 100,
    },
    source_recommendation_id: recAny?.recommendation_id ?? null,
    source_engine_id: recAny?.source_engine_id ?? null,
    source_engine_version: recAny?.source_engine_version ?? null,
    experiment_id: recAny?.experiment_id ?? null,
  };
}

function buildCandidateRows(screenerResult: ScreenerResponse | null): CandidateRow[] {
  if (!screenerResult) return [];

  const analysisBySymbol = new Map<string, StockAnalysisResult>();
  const matchBySymbol = new Map<string, ScreenerConditionResult>();
  const rankingBySymbol = new Map<string, RankingItem>();

  screenerResult.analysis?.items?.forEach((item) => {
    analysisBySymbol.set(String(item.symbol || "").toUpperCase(), item);
  });
  screenerResult.matches?.forEach((match) => {
    matchBySymbol.set(String(match.symbol || "").toUpperCase(), match);
  });
  screenerResult.analysis?.rankings?.rankings?.forEach((ranking) => {
    rankingBySymbol.set(String(ranking.symbol || "").toUpperCase(), ranking);
  });

  // Prefer full shortlist (lab cohort includes REJECT). Fall back to all_analyzed symbols.
  const symbolList =
    screenerResult.shortlisted_symbols?.length
      ? screenerResult.shortlisted_symbols
      : (screenerResult.all_analyzed_stocks ?? []).map((s) => s.symbol);

  return symbolList.map((rawSymbol) => {
    const symbol = String(rawSymbol || "").toUpperCase();
    const analysis = analysisBySymbol.get(symbol);
    const match = matchBySymbol.get(symbol);
    const ranking = rankingBySymbol.get(symbol);
    const plan =
      analysis?.recommendation.trade_plans.find((item) => item.mode === "swing") ??
      analysis?.recommendation.trade_plans[0];
    const technical = analysis?.technical.find((item) => item.mode === "swing") ?? analysis?.technical[0];

    const buySet = new Set((screenerResult.buy_candidate_symbols ?? []).map((s) => String(s).toUpperCase()));
    const watchSet = new Set((screenerResult.watch_candidate_symbols ?? []).map((s) => String(s).toUpperCase()));
    let signal: CandidateRow["signal"] = "REJECT";
    if (buySet.has(symbol)) {
      signal = "BUY";
    } else if (watchSet.has(symbol)) {
      signal = "WATCH";
    } else {
      // Explicit recommendation action (lab engines include REJECT in shortlist)
      const matchRec = (match as { recommendation?: string; tech_signal?: string } | undefined)?.recommendation
        ?? (match as { tech_signal?: string } | undefined)?.tech_signal;
      const action = String(analysis?.recommendation?.action ?? matchRec ?? "").toUpperCase();
      if (action === "BUY" || action === "WATCH" || action === "REJECT") {
        signal = action;
      }
    }

    const rec = analysis?.recommendation;
    const riskFactors = rec?.reasoning?.risk_factors ?? [];
    const hasPlans = Boolean(plan) || Boolean(rec?.trade_plans?.length);
    // Intentional REJECT is a valid lab outcome — do not treat as analysis failure
    const isExplicitReject = signal === "REJECT" && Boolean(rec);
    const analysisFailed =
      !isExplicitReject &&
      (!analysis ||
        riskFactors.some((r) => typeof r === "string" && r.toLowerCase().includes("analysis failed")) ||
        // Backend clears score/plans on true analysis failure (never invent Score=100).
        (Boolean(rec) && rec!.score === 0 && !hasPlans));

    // NEVER fall back to screener_score as the recommendation score.
    // Screener scores can hit 100 and look like a fake "perfect" composite.
    // Only use the real composite score from the completed analysis pipeline.
    const compositeScore = analysisFailed
      ? null
      : typeof rec?.score === "number"
        ? rec.score
        : null;

    return {
      rank: ranking?.rank ?? null,
      symbol,
      signal,
      score: compositeScore,
      confidence: analysisFailed ? null : rec?.confidence ?? null,
      entryLow: plan?.entry_low ?? null,
      entryHigh: plan?.entry_high ?? null,
      stopLoss: plan?.stop_loss ?? null,
      target1: plan?.target_1 ?? null,
      target2: plan?.target_2 ?? null,
      riskReward: plan?.risk_reward_ratio ?? null,
      analysisFailed: Boolean(analysisFailed),
      trend: formatTrend(technical, match),
      momentum: formatMomentum(technical, match),
      volume: formatVolume(technical, match),
      newsSentiment: analysis?.news_sentiment_label ?? "n/a",
      lastUpdated: screenerResult.analysis?.generated_at ?? null,
      tradeReadiness: analysis?.trade_readiness ?? (signal === "REJECT" ? "Avoid" : "Review manually"),
      recommendationSummary:
        analysis?.recommendation.summary ??
        (signal === "REJECT"
          ? "Rejected after the shortlist because the final recommendation layer did not confirm the setup."
          : "This stock passed the screener and is awaiting deeper analysis."),
      analysisItem: analysis,
      screenerMatch: match,
    };
  });
}

function loadScanHistory(): ScanHistoryItem[] {
  try {
    return JSON.parse(window.localStorage.getItem("scanHistory") ?? "[]") as ScanHistoryItem[];
  } catch {
    return [];
  }
}

function saveScanHistory(response: ScreenerResponse, current: ScanHistoryItem[]) {
  const shortlisted = response.shortlisted_symbols || [];
  const item: ScanHistoryItem = {
    id: `${response.analysis?.generated_at ?? new Date().toISOString()}-${shortlisted.join("-")}`,
    generated_at: response.analysis?.generated_at ?? new Date().toISOString(),
    screener_name: response.screener_name || "Unknown",
    scanned_symbols: response.scanned_symbols || 0,
    shortlisted_count: shortlisted.length,
    buy_symbols: response.buy_candidate_symbols || [],
    watch_symbols: response.watch_candidate_symbols || [],
    data_source: response.data_source || "unknown",
    data_warning: response.data_warning || null,
  };
  const next = [item, ...current.filter((entry) => entry.id !== item.id)].slice(0, 20);
  window.localStorage.setItem("scanHistory", JSON.stringify(next));
  return next;
}

function compareRows(left: CandidateRow, right: CandidateRow, sortBy: SortKey) {
  if (sortBy === "rank") return (left.rank ?? 999) - (right.rank ?? 999);
  if (sortBy === "confidence") return (right.confidence ?? -1) - (left.confidence ?? -1);
  if (sortBy === "riskReward") return (right.riskReward ?? -1) - (left.riskReward ?? -1);
  return (right.score ?? -1) - (left.score ?? -1);
}

function formatTrend(
  technical: StockAnalysisResult["technical"][number] | undefined,
  match: ScreenerConditionResult | undefined,
) {
  if (technical?.indicators.higher_timeframe_trend) {
    return String(technical.indicators.higher_timeframe_trend);
  }
  if (match?.conditions.supertrend_positive && match.conditions.close_above_ema20) {
    return "uptrend";
  }
  return "mixed";
}

function formatMomentum(
  technical: StockAnalysisResult["technical"][number] | undefined,
  match: ScreenerConditionResult | undefined,
) {
  if (!technical && !match) return "n/a";
  const macdPositive = technical ? Boolean(technical.indicators.macd_positive) : Boolean(match?.conditions.macd_positive);
  const rsiSupportive = technical ? Boolean(technical.indicators.rsi_supportive) : true;
  return macdPositive && rsiSupportive ? "supported" : macdPositive ? "mixed" : "weak";
}

function formatVolume(
  technical: StockAnalysisResult["technical"][number] | undefined,
  match: ScreenerConditionResult | undefined,
) {
  if (technical) {
    const liquid = Boolean(technical.indicators.basic_liquidity_filter_pass);
    const expanding = Boolean(technical.indicators.volume_above_previous_day);
    return liquid && expanding ? "expanding" : liquid ? "adequate" : "thin";
  }
  if (!match) return "n/a";
  return match.conditions.volume_above_previous_day ? "expanding" : "adequate";
}


