import { lazy, startTransition, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import {
  cacheLatestScanFromScreenerResponse,
  fetchLtmLatest,
  fetchLtmRun,
  fetchScannerStrategies,
  fetchUniverses,
  fetchUniverseInstruments,
  fetchW52Latest,
  fetchW52Run,
  invalidateLatestScanCaches,
  loadLatestScan,
  runPresetScreener,
  saveScannerPreset,
  startLtmScan,
  startW52Scan,
} from "./api";
import { LtmScanSummary } from "./components/LtmScanSummary";
import { LtmRejectionBreakdown } from "./components/LtmRejectionBreakdown";
import { LtmReturnBoards } from "./components/LtmReturnBoards";
import { W52ScanSummary } from "./components/W52ScanSummary";
import { W52RejectionBreakdown } from "./components/W52RejectionBreakdown";
import { W52ReturnBoards } from "./components/W52ReturnBoards";
import { W52OrderList } from "./components/W52OrderList";

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
import {
  buildLtmCandidateRows,
  buildPaperTradingPrefill,
  buildW52CandidateRows,
  preferredPaperEntry,
} from "./utils/scannerCandidates";
import { displayCanonicalSymbol } from "./utils/canonicalSymbol";
import {
  attachInstrumentMetadata,
  indexUniverseInstruments,
  type UniverseInstrument,
} from "./utils/universeInstruments";
import { FeaturePermissionsProvider } from "./contexts/FeaturePermissionsContext";
import { FeatureGuard } from "./components/FeatureGuard";
import { AccessDenied } from "./components/AccessDenied";
import {
  hasDisplayableStrategyResults,
  isCurrentScanCompleted,
  isCurrentScanFailed,
  isStrategyRunActive,
  isStrategyRunFailed,
  mapStrategyStage,
  readStoredScannerStrategy,
  startedAtMs,
  storeScannerStrategy,
} from "./utils/strategyScan";

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

/** Build /scanner path preserving optional symbol context. */
function buildScannerPath(opts: { symbol?: string | null }): string {
  const qs = new URLSearchParams();
  if (opts.symbol) qs.set("symbol", opts.symbol);
  const s = qs.toString();
  return s ? `/scanner?${s}` : "/scanner";
}

const POLL_LIMIT = 3600;
const POLL_MS = 1000;
const EMPTY_CANDIDATES: CandidateRow[] = [];

function progressFromPayload(payload: Record<string, any> | null | undefined) {
  return {
    stage: mapStrategyStage(payload?.stage || payload?.run_status || payload?.status),
    progress: Number(payload?.progress_pct) || 0,
    current_symbol: payload?.current_symbol ? String(payload.current_symbol) : "",
    processed_count: payload?.processed_count != null ? Number(payload.processed_count) : undefined,
    total_count: payload?.total_count != null ? Number(payload.total_count) : undefined,
  };
}

export default function App() {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const symbolParam = searchParams.get("symbol");
  const onScannerPage = location.pathname.startsWith("/scanner");

  const [timeframe, setTimeframe] = useState("1d");
  const [lookback, setLookback] = useState(180);
  const [topN, setTopN] = useState(20);
  const [selectedUniverse, setSelectedUniverse] = useState("NIFTY500");
  const [universes, setUniverses] = useState<{ name: string; symbols: string[]; count: number }[]>([]);
  const [universeInstruments, setUniverseInstruments] = useState<UniverseInstrument[]>([]);
  const [savedScanName, setSavedScanName] = useState("");
  /** One-shot: keep detail open when landing via ?symbol= after results restore. */
  const deepLinkSymbolRef = useRef<string | null>(
    symbolParam ? symbolParam.toUpperCase() : null,
  );
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
  const [scannerStrategy, setScannerStrategy] = useState<"production" | "17_long_term_mom" | "09_52w_breakout">(
    readStoredScannerStrategy,
  );
  const [ltmPayload, setLtmPayload] = useState<Record<string, any> | null>(null);
  const [w52Payload, setW52Payload] = useState<Record<string, any> | null>(null);
  const [ltmStrategies, setLtmStrategies] = useState<{ id: string; display_name: string }[]>([]);
  const [ltmRun, setLtmRun] = useState<{ running: boolean; error: string | null; durationSec: number | null }>({
    running: false,
    error: null,
    durationSec: null,
  });
  const [w52Run, setW52Run] = useState<{ running: boolean; error: string | null; durationSec: number | null }>({
    running: false,
    error: null,
    durationSec: null,
  });
  const [ltmProgress, setLtmProgress] = useState({
    stage: "Starting scan...",
    progress: 0,
    current_symbol: "",
    processed_count: undefined as number | undefined,
    total_count: undefined as number | undefined,
  });
  const [w52Progress, setW52Progress] = useState({
    stage: "Starting scan...",
    progress: 0,
    current_symbol: "",
    processed_count: undefined as number | undefined,
    total_count: undefined as number | undefined,
  });
  const [ltmStartTime, setLtmStartTime] = useState<number | null>(null);
  const [w52StartTime, setW52StartTime] = useState<number | null>(null);
  const [ltmHydrated, setLtmHydrated] = useState(false);
  const [w52Hydrated, setW52Hydrated] = useState(false);
  const ltmPollRef = useRef(false);
  const w52PollRef = useRef(false);
  const ltmScanIdRef = useRef<string | null>(null);
  const w52ScanIdRef = useRef<string | null>(null);
  const ltmFetchedRef = useRef(false);
  const w52FetchedRef = useRef(false);
  const ltmInFlight = ltmRun.running || isStrategyRunActive(ltmPayload);
  const w52InFlight = w52Run.running || isStrategyRunActive(w52Payload);

  const universesMapped = useMemo(
    () => (Array.isArray(universes) ? universes : []).map(({ name, count }) => ({ name, count })),
    [universes],
  );

  const handleSearchChange = useCallback(
    (value: string) => setFilters((current) => ({ ...current, search: value })),
    [],
  );

  const handleSelectSymbol = useCallback(
    (symbol: string) => {
      setSelectedSymbol(symbol);
      setDetailViewOpen(true);
      navigate(buildScannerPath({ symbol }), { replace: true });
      import("./utils/researchPrefetcher").then(({ markPrefetched }) => markPrefetched(symbol));
    },
    [navigate],
  );

  const handleDetailBack = useCallback(() => {
    setDetailViewOpen(false);
    navigate("/scanner", { replace: true });
  }, [navigate]);

  // Warm app cache after login
  useEffect(() => {
    if (user?.id) prefetchAppData();
  }, [user?.id]);

  useEffect(() => {
    function loadAndApply(force = true) {
      void loadLatestScan({ force }).then((response) => {
        if (!response) return;
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
        setScanHistory((current) => saveScanHistory(response, current));
      });
    }

    loadAndApply(true);

    const intervalId = setInterval(() => {
      console.info("[scanner] 30-min auto-polling new cached scan...");
      void loadLatestScan({ force: true }).then((response) => {
        if (!response) return;
        setScreenerResult(response);
        setError(null);
      });
    }, 30 * 60 * 1000);

    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount once; interval uses latest via ref
  }, []);

  useEffect(() => {
    void fetchUniverses()
      .then((data) => setUniverses(Array.isArray(data) ? data : []))
      .catch((err) => console.warn("Failed to load universes", err));
    void fetchUniverseInstruments()
      .then((data) => setUniverseInstruments(Array.isArray(data) ? data : []))
      .catch((err) => console.warn("Failed to load universe instruments", err));
  }, []);

  useEffect(() => {
    void fetchScannerStrategies()
      .then((res) => setLtmStrategies((res.strategies || []).filter((s: any) => s.id !== "production")))
      .catch(() =>
        setLtmStrategies([
          { id: "17_long_term_mom", display_name: "Long-Term Buy & Hold Momentum" },
          { id: "09_52w_breakout", display_name: "52-Week High Breakout" },
        ]),
      );
  }, []);

  useEffect(() => {
    if (!onScannerPage) return;
    let cancelled = false;
    if (scannerStrategy === "17_long_term_mom" && !ltmFetchedRef.current) {
      void fetchLtmLatest()
        .then((p) => {
          if (cancelled) return;
          startTransition(() => setLtmPayload(p));
        })
        .catch(() => {
          if (!cancelled) setLtmPayload(null);
        })
        .finally(() => {
          if (cancelled) return;
          ltmFetchedRef.current = true;
          setLtmHydrated(true);
        });
    } else if (scannerStrategy === "17_long_term_mom") {
      setLtmHydrated(true);
    }
    if (scannerStrategy === "09_52w_breakout" && !w52FetchedRef.current) {
      void fetchW52Latest()
        .then((p) => {
          if (cancelled) return;
          startTransition(() => setW52Payload(p));
        })
        .catch(() => {
          if (!cancelled) setW52Payload(null);
        })
        .finally(() => {
          if (cancelled) return;
          w52FetchedRef.current = true;
          setW52Hydrated(true);
        });
    } else if (scannerStrategy === "09_52w_breakout") {
      setW52Hydrated(true);
    }
    return () => {
      cancelled = true;
    };
  }, [onScannerPage, scannerStrategy]);

  useEffect(() => {
    storeScannerStrategy(scannerStrategy);
  }, [scannerStrategy]);

  // Deep-link: /scanner?symbol=RELIANCE opens stock detail
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

  /** Markets / portfolio widgets always reflect the latest completed scan. */
  const analysisItems = screenerResult?.analysis?.items ?? [];
  const instrumentIndex = useMemo(
    () => indexUniverseInstruments(universeInstruments),
    [universeInstruments],
  );
  const shortlistRows = useMemo(
    () => attachInstrumentMetadata(buildCandidateRows(screenerResult), instrumentIndex),
    [screenerResult, instrumentIndex],
  );

  const ltmCandidateRows = useMemo(
    () =>
      scannerStrategy === "17_long_term_mom"
        ? attachInstrumentMetadata(buildLtmCandidateRows(ltmPayload), instrumentIndex)
        : EMPTY_CANDIDATES,
    [scannerStrategy, ltmPayload, instrumentIndex],
  );
  const w52CandidateRows = useMemo(
    () =>
      scannerStrategy === "09_52w_breakout"
        ? attachInstrumentMetadata(buildW52CandidateRows(w52Payload), instrumentIndex)
        : EMPTY_CANDIDATES,
    [scannerStrategy, w52Payload, instrumentIndex],
  );
  const w52ScanResultRows = useMemo(
    () =>
      scannerStrategy === "09_52w_breakout"
        ? attachInstrumentMetadata(buildW52CandidateRows(w52Payload, { includeUniverseRejects: true }), instrumentIndex)
        : EMPTY_CANDIDATES,
    [scannerStrategy, w52Payload, instrumentIndex],
  );
  const w52VisibleRows = showAllAnalyzedStocks ? w52ScanResultRows : w52CandidateRows;

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
      .filter((row) => {
        if (!searchTerm) return true;
        const haystack = [
          row.symbol,
          displayCanonicalSymbol(row.symbol),
          row.companyName ?? "",
        ]
          .join(" ")
          .toUpperCase();
        return haystack.includes(searchTerm);
      })
      .sort((left, right) => compareRows(left, right, filters.sortBy));
  }, [filters, shortlistRows]);

  const selectedRow = useMemo(() => {
    const pool =
      scannerStrategy === "17_long_term_mom"
        ? ltmCandidateRows
        : scannerStrategy === "09_52w_breakout"
          ? w52ScanResultRows.length
            ? w52ScanResultRows
            : w52CandidateRows
          : filteredRows;
    if (!pool.length) return null;
    return pool.find((row) => row.symbol === selectedSymbol) ?? pool[0];
  }, [filteredRows, ltmCandidateRows, w52CandidateRows, w52ScanResultRows, scannerStrategy, selectedSymbol]);

  const summaryMetrics = useMemo(() => {
    const src = screenerResult;
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
  }, [screenerResult]);

  const applyScanResult = useCallback(
    (response: ScreenerResponse, _source: "fresh" | "restored") => {
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

      setScreenerResult(response);
      setSelectedSymbol(nextSymbol);
      setError(null);
      setScanHistory((current) => saveScanHistory(response, current));
      setDetailViewOpen(false);
    },
    [],
  );

  const handleRunScanner = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setProgressData({
      stage: "Connecting data feed...",
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
      applyScanResult(response, "fresh");
      toast.success(
        "Scan complete",
        `${response.buy_candidate_symbols?.length ?? 0} BUY · ${response.watch_candidate_symbols?.length ?? 0} WATCH`,
      );
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
  }, [timeframe, lookback, selectedUniverse, universes, topN, toast, applyScanResult]);

  const pollLtmUntilDone = useCallback(async (startedAt: number) => {
    if (ltmPollRef.current) return;
    ltmPollRef.current = true;
    try {
      let scanId: string | undefined = ltmScanIdRef.current || undefined;
      for (let i = 0; i < POLL_LIMIT; i += 1) {
        const expected = ltmScanIdRef.current;
        const latest = await fetchLtmLatest();
        if (latest) {
          setLtmProgress(progressFromPayload(latest));
          setLtmStartTime((t) => t ?? startedAtMs(latest) ?? startedAt);
          if (isCurrentScanCompleted(latest, expected, startedAt)) {
            const fresh = await fetchLtmLatest();
            startTransition(() => setLtmPayload(fresh || latest));
            setLtmHydrated(true);
            setLtmRun({ running: false, error: null, durationSec: Math.round((Date.now() - startedAt) / 1000) });
            ltmScanIdRef.current = null;
            toast.success("LTM scan complete", `${(fresh || latest).summary?.buy ?? 0} BUY · ${(fresh || latest).summary?.watch ?? 0} WATCH`);
            return;
          }
          if (isCurrentScanFailed(latest, expected)) {
            throw new Error(
              latest.error_detail || latest.message || latest.detail || latest.error_code || "LTM scan failed",
            );
          }
          scanId = latest.scan_id || scanId;
          if (latest.scan_id && !ltmScanIdRef.current) ltmScanIdRef.current = String(latest.scan_id);
        }
        if (scanId) {
          try {
            const run = await fetchLtmRun(scanId);
            setLtmProgress(progressFromPayload(run));
            if (isCurrentScanCompleted(run, expected, startedAt)) {
              const fresh = await fetchLtmLatest();
              startTransition(() => setLtmPayload(fresh || latest));
              setLtmHydrated(true);
              setLtmRun({ running: false, error: null, durationSec: Math.round((Date.now() - startedAt) / 1000) });
              ltmScanIdRef.current = null;
              toast.success("LTM scan complete", `${(fresh || latest)?.summary?.buy ?? 0} BUY`);
              return;
            }
            if (isCurrentScanFailed(run, expected)) {
              throw new Error(run.error_detail || run.error_code || "LTM scan failed");
            }
          } catch (runErr: any) {
            if (runErr?.message && String(runErr.message).includes("LTM scan failed")) throw runErr;
          }
        }
        await new Promise((r) => setTimeout(r, POLL_MS));
      }
      throw new Error("LTM scan timed out waiting for completion");
    } catch (requestError: any) {
      const msg = requestError?.message || "LTM scan failed";
      setLtmRun({ running: false, error: msg, durationSec: null });
      toast.error("LTM scan failed", msg);
    } finally {
      ltmPollRef.current = false;
    }
  }, [toast]);

  const pollW52UntilDone = useCallback(async (startedAt: number) => {
    if (w52PollRef.current) return;
    w52PollRef.current = true;
    try {
      let scanId: string | undefined = w52ScanIdRef.current || undefined;
      for (let i = 0; i < POLL_LIMIT; i += 1) {
        const expected = w52ScanIdRef.current;
        const latest = await fetchW52Latest();
        if (latest) {
          setW52Progress(progressFromPayload(latest));
          setW52StartTime((t) => t ?? startedAtMs(latest) ?? startedAt);
          if (isCurrentScanCompleted(latest, expected, startedAt)) {
            const fresh = await fetchW52Latest();
            startTransition(() => setW52Payload(fresh || latest));
            setW52Hydrated(true);
            setW52Run({ running: false, error: null, durationSec: Math.round((Date.now() - startedAt) / 1000) });
            w52ScanIdRef.current = null;
            toast.success("52W scan complete", `${(fresh || latest).summary?.buy ?? 0} BUY · ${(fresh || latest).summary?.hold ?? 0} HOLD`);
            return;
          }
          if (isCurrentScanFailed(latest, expected)) {
            throw new Error(
              latest.error_detail || latest.message || latest.detail || latest.error_code || "52-Week High Breakout scan failed",
            );
          }
          scanId = latest.scan_id || scanId;
          if (latest.scan_id && !w52ScanIdRef.current) w52ScanIdRef.current = String(latest.scan_id);
        }
        if (scanId) {
          try {
            const run = await fetchW52Run(scanId);
            setW52Progress(progressFromPayload(run));
            if (isCurrentScanCompleted(run, expected, startedAt)) {
              const fresh = await fetchW52Latest();
              startTransition(() => setW52Payload(fresh || latest));
              setW52Hydrated(true);
              setW52Run({ running: false, error: null, durationSec: Math.round((Date.now() - startedAt) / 1000) });
              w52ScanIdRef.current = null;
              toast.success("52W scan complete", `${(fresh || latest)?.summary?.buy ?? 0} BUY`);
              return;
            }
            if (isCurrentScanFailed(run, expected)) {
              throw new Error(run.error_detail || run.error_code || "52-Week High Breakout scan failed");
            }
          } catch (runErr: any) {
            if (runErr?.message && String(runErr.message).includes("52-Week")) throw runErr;
          }
        }
        await new Promise((r) => setTimeout(r, POLL_MS));
      }
      throw new Error("52-Week High Breakout scan timed out waiting for completion");
    } catch (requestError: any) {
      const msg = requestError?.message || "52-Week High Breakout scan failed";
      setW52Run({ running: false, error: msg, durationSec: null });
      toast.error("52W scan failed", msg);
    } finally {
      w52PollRef.current = false;
    }
  }, [toast]);

  useEffect(() => {
    if (!isStrategyRunActive(ltmPayload) || ltmPollRef.current) return;
    if (ltmPayload?.scan_id) ltmScanIdRef.current = String(ltmPayload.scan_id);
    const started = startedAtMs(ltmPayload) || Date.now();
    setLtmStartTime((t) => t ?? started);
    setLtmRun((s) => ({ ...s, running: true, error: null }));
    setLtmProgress(progressFromPayload(ltmPayload));
    void pollLtmUntilDone(started);
  }, [ltmPayload, pollLtmUntilDone]);

  useEffect(() => {
    if (!isStrategyRunActive(w52Payload) || w52PollRef.current) return;
    if (w52Payload?.scan_id) w52ScanIdRef.current = String(w52Payload.scan_id);
    const started = startedAtMs(w52Payload) || Date.now();
    setW52StartTime((t) => t ?? started);
    setW52Run((s) => ({ ...s, running: true, error: null }));
    setW52Progress(progressFromPayload(w52Payload));
    void pollW52UntilDone(started);
  }, [w52Payload, pollW52UntilDone]);

  const handleRunLtmScan = useCallback(async () => {
    if (ltmInFlight || ltmPollRef.current) {
      toast.info("LTM scanner is already running.");
      return;
    }
    const startedAt = Date.now();
    setLtmStartTime(startedAt);
    setLtmProgress({ stage: "Starting scan...", progress: 1, current_symbol: "", processed_count: undefined, total_count: undefined });
    setLtmRun({ running: true, error: null, durationSec: null });
    try {
      const started = await startLtmScan();
      if (started?.scan_id) ltmScanIdRef.current = String(started.scan_id);
      await pollLtmUntilDone(startedAt);
    } catch (requestError: any) {
      if (requestError?.scanInProgress) {
        toast.info("LTM scanner is already running.");
        if (requestError.scanId) ltmScanIdRef.current = String(requestError.scanId);
        setLtmRun((s) => ({ ...s, running: true }));
        void pollLtmUntilDone(startedAt);
        return;
      }
      const msg = requestError?.message || "LTM scan failed";
      setLtmRun({ running: false, error: msg, durationSec: null });
      toast.error("LTM scan failed", msg);
    }
  }, [toast, ltmInFlight, pollLtmUntilDone]);

  const handleRunW52Scan = useCallback(async () => {
    if (w52InFlight || w52PollRef.current) {
      toast.info("52-Week High Breakout scan is already running.");
      return;
    }
    const startedAt = Date.now();
    setW52StartTime(startedAt);
    setW52Progress({ stage: "Starting scan...", progress: 1, current_symbol: "", processed_count: undefined, total_count: undefined });
    setW52Run({ running: true, error: null, durationSec: null });
    try {
      const started = await startW52Scan();
      if (started?.scan_id) w52ScanIdRef.current = String(started.scan_id);
      await pollW52UntilDone(startedAt);
    } catch (requestError: any) {
      if (requestError?.scanInProgress) {
        toast.info("52-Week High Breakout scanner is already running.");
        if (requestError.scanId) w52ScanIdRef.current = String(requestError.scanId);
        setW52Run((s) => ({ ...s, running: true }));
        void pollW52UntilDone(startedAt);
        return;
      }
      const msg = requestError?.message || "52-Week High Breakout scan failed";
      setW52Run({ running: false, error: msg, durationSec: null });
      toast.error("52W scan failed", msg);
    }
  }, [toast, w52InFlight, pollW52UntilDone]);

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
    const entry = preferredPaperEntry(prefill, suggestedEntry);
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
    };

    // Dedicated full-page order ticket — never open a drawer on Scanner
    navigateToPaperOrder(navigate, {
      symbol: row.symbol,
      side: "BUY",
      prefill: updatedPrefill,
      currentPrice: entry,
      signal: String(row.signal ?? "BUY"),
      score: row.score ?? row.momentumValue ?? null,
      confidence: row.confidence ?? null,
      riskReward: row.riskReward ?? null,
      returnTo: `${window.location.pathname}${window.location.search || ""}`,
    });
  }, [navigate]);

  const scannerListView = useMemo(() => (
    <div className="scanner-center">
      {/* Row 1: Title (left) + CTA & status chips (right) — trading-desk header */}
      <header className="scanner-page-header" data-testid="scanner-page-header">
        <div className="scanner-page-header__left">
          <p className="ds-label">Scanner</p>
          <h1 className="ds-display">Scanner</h1>
          <p className="ds-muted">
            Favorites and scan results
            {scannerStrategy === "09_52w_breakout"
              ? " · 52-Week High Breakout"
              : scannerStrategy === "17_long_term_mom"
                ? " · Long-Term Buy & Hold Momentum"
                : ""}
          </p>
        </div>

        <div className="scanner-page-header__right">
          <div className="scanner-page-header__cta">
            {scannerStrategy === "09_52w_breakout" ? (
              <button
                type="button"
                className="button primary-button scanner-page-header__run-btn"
                onClick={() => void handleRunW52Scan()}
                disabled={w52InFlight}
                data-testid="scanner-run-w52"
              >
                {w52InFlight ? "Running 52-Week High Breakout…" : "Run 52-Week High Breakout"}
              </button>
            ) : scannerStrategy === "17_long_term_mom" ? (
              <button
                type="button"
                className="button primary-button scanner-page-header__run-btn"
                onClick={() => void handleRunLtmScan()}
                disabled={ltmInFlight}
                data-testid="scanner-run-ltm"
              >
                {ltmInFlight ? "Running LTM Scan…" : "Run LTM scan"}
              </button>
            ) : (
              <button
                type="button"
                className="button primary-button scanner-page-header__run-btn"
                onClick={() => void handleRunScanner()}
                disabled={isLoading}
                data-testid="run-scanner-button"
              >
                {isLoading ? "Running scanner…" : "Run Scanner"}
              </button>
            )}
          </div>
          <StatusCards
            compact
            className="scanner-page-header__status"
            lastScanAt={
              scannerStrategy === "09_52w_breakout"
                ? w52Payload?.completed_at ?? null
                : scannerStrategy === "17_long_term_mom"
                  ? ltmPayload?.completed_at ?? null
                  : screenerResult?.last_scan_completed_at ??
                    screenerResult?.scanned_at ??
                    screenerResult?.analysis?.generated_at ??
                    null
            }
            isLoading={
              scannerStrategy === "09_52w_breakout"
                ? w52InFlight
                : scannerStrategy === "17_long_term_mom"
                  ? ltmInFlight
                  : isLoading
            }
            scannedSymbols={
              scannerStrategy === "09_52w_breakout"
                ? w52Payload?.summary?.evaluated ?? w52Payload?.summary?.total ?? null
                : scannerStrategy === "17_long_term_mom"
                  ? ltmPayload?.summary?.evaluated ?? ltmPayload?.summary?.total ?? null
                  : screenerResult?.scanned_symbols ?? null
            }
            durationSec={
              scannerStrategy === "09_52w_breakout"
                ? w52Run.durationSec
                : scannerStrategy === "17_long_term_mom"
                  ? ltmRun.durationSec
                  : lastScanDuration
            }
            runningLabel={
              scannerStrategy === "09_52w_breakout"
                ? "Running 52-Week High Breakout…"
                : scannerStrategy === "17_long_term_mom"
                  ? "Running LTM Scan…"
                  : "Scanning…"
            }
          />
        </div>
      </header>

      {/* Row 2: Result view tabs
          Favorites count = shortlist size.
          Scan Results count = full analyzed cohort.
      */}
      <div className="scanner-result-tabs" role="tablist" aria-label="Scanner strategy" style={{ marginBottom: 8 }}>
        {(ltmStrategies.length
          ? ltmStrategies
          : [
              { id: "17_long_term_mom", display_name: "Long-Term Buy & Hold Momentum" },
              { id: "09_52w_breakout", display_name: "52-Week High Breakout" },
            ]
        )
          .filter((s) => s.id !== "production")
          .map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={scannerStrategy === s.id}
            className={`button scanner-strategy-tab ${scannerStrategy === s.id ? "primary-button" : "ghost-button"}`}
            onClick={() => {
              const next = s.id as "production" | "17_long_term_mom" | "09_52w_breakout";
              storeScannerStrategy(next);
              setScannerStrategy(next);
              setShowAllAnalyzedStocks(false);
            }}
            data-testid={`scanner-strategy-${s.id}`}
          >
            {s.display_name}
            <span className="helper-chip">{scannerStrategy === s.id ? "Active" : "Inactive"}</span>
          </button>
        ))}
      </div>

      {scannerStrategy === "production" || scannerStrategy === "09_52w_breakout" ? (
      <div className="scanner-result-tabs" role="tablist" aria-label="Result views">
        <button
          type="button"
          role="tab"
          aria-selected={!showAllAnalyzedStocks}
          className={`button ${!showAllAnalyzedStocks ? "primary-button" : "ghost-button"}`}
          onClick={() => setShowAllAnalyzedStocks(false)}
          data-testid="scanner-favorites-tab"
        >
          Favorites (
          {scannerStrategy === "09_52w_breakout"
            ? w52CandidateRows.length
            : screenerResult?.shortlisted_symbols.length ?? 0}
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
          {scannerStrategy === "09_52w_breakout"
            ? w52ScanResultRows.length
            : screenerResult?.all_analyzed_stocks?.length ??
              screenerResult?.shortlisted_symbols?.length ??
              0}
          )
        </button>
      </div>
      ) : null}

      {isLoading && scannerStrategy === "production" ? (
        <ScannerProgress
          data={progressData}
          error={error}
          startTime={scanStartTime}
          onRetry={handleRunScanner}
        />
      ) : null}

      {error && scannerStrategy === "production" ? (
        <section className="panel error-state" role="alert">
          <h2 className="ds-title">Scan failed</h2>
          <p>{error}</p>
          <button
            type="button"
            className="button primary-button"
            onClick={() => void handleRunScanner()}
            style={{ marginTop: 12 }}
          >
            Retry scan
          </button>
        </section>
      ) : null}

      {scannerStrategy === "09_52w_breakout" ? (
        !w52Hydrated ? (
          <ViewFallback />
        ) : (
          <>
            {w52InFlight ? (
              <ScannerProgress
                title="52-WEEK HIGH BREAKOUT SCAN IN PROGRESS"
                data={w52Progress}
                error={null}
                startTime={w52StartTime}
              />
            ) : null}
            {w52Run.error || isStrategyRunFailed(w52Payload) ? (
              <ScannerProgress
                title="52-WEEK HIGH BREAKOUT SCAN IN PROGRESS"
                data={w52Progress}
                error={w52Run.error || String(w52Payload?.error_detail || w52Payload?.error_code || "Scan failed")}
                startTime={w52StartTime}
                onRetry={handleRunW52Scan}
              />
            ) : null}
            {hasDisplayableStrategyResults(w52Payload, { inFlight: false }) ? (
              <>
                {w52InFlight && w52VisibleRows.length ? (
                  <p className="ds-muted" data-testid="w52-previous-results-hint">
                    Showing last completed Favorites and Scan results while this 52-Week High Breakout run finishes.
                    New BUY and REJECT signals publish when the scan completes.
                  </p>
                ) : null}
                {w52VisibleRows.length ? (
                  <CandidateTable
                    rows={w52VisibleRows}
                    selectedSymbol={selectedRow?.symbol ?? null}
                    onSelect={handleSelectSymbol}
                    onBuy={sendRowToPaperTrading}
                    exportFilePrefix="w52-scan"
                    sectionLabel={showAllAnalyzedStocks ? "Scan results" : "Favorites"}
                    heading={showAllAnalyzedStocks ? "All analyzed stocks" : "Scan results"}
                  />
                ) : (
                  <EmptyState
                    title={
                      showAllAnalyzedStocks
                        ? "No 52-Week High Breakout scan results yet"
                        : "No 52-Week High Breakout favorites yet"
                    }
                    description={
                      w52InFlight
                        ? "Scan is running. Names that satisfy 52-Week High Breakout become BUY; all others become REJECT when this run finishes."
                        : showAllAnalyzedStocks
                          ? "Run a 52-Week High Breakout scan to classify every name as BUY or REJECT."
                          : "Names that satisfy 52-Week High Breakout appear here as BUY (HOLD if already in the book, WATCH if no free slot). Open Scan results for REJECT names."
                    }
                  />
                )}
                {!w52InFlight ? (
                  <>
                    <W52ReturnBoards payload={w52Payload} />
                    <W52RejectionBreakdown buckets={w52Payload?.rejection_breakdown || []} />
                    <W52ScanSummary payload={w52Payload} />
                    <W52OrderList orders={w52Payload?.orders || []} />
                  </>
                ) : null}
              </>
            ) : w52InFlight || w52Run.error || isStrategyRunFailed(w52Payload) ? (
              w52InFlight && !w52VisibleRows.length ? (
                <EmptyState
                  title="52-Week High Breakout scan in progress"
                  description="Favorites and Scan results will appear here when evaluation finishes. Names that satisfy the strategy become BUY; all others become REJECT."
                />
              ) : null
            ) : (
              <EmptyState
                title="No 52-Week High Breakout scan yet"
                description="Run a 52-Week High Breakout scan to populate Favorites and Scan results."
              />
            )}
          </>
        )
      ) : null}

      {scannerStrategy === "17_long_term_mom" ? (
        ltmInFlight ? (
          <ScannerProgress
            title="LTM SCAN IN PROGRESS"
            data={ltmProgress}
            error={null}
            startTime={ltmStartTime}
          />
        ) : !ltmHydrated ? (
          <ViewFallback />
        ) : (
          <>
            {ltmRun.error || isStrategyRunFailed(ltmPayload) ? (
              <ScannerProgress
                title="LTM SCAN IN PROGRESS"
                data={ltmProgress}
                error={ltmRun.error || String(ltmPayload?.error_detail || ltmPayload?.error_code || "Scan failed")}
                startTime={ltmStartTime}
                onRetry={handleRunLtmScan}
              />
            ) : null}
            {hasDisplayableStrategyResults(ltmPayload, { inFlight: false }) ? (
              <>
                {ltmCandidateRows.length ? (
                  <CandidateTable
                    rows={ltmCandidateRows}
                    selectedSymbol={selectedRow?.symbol ?? null}
                    onSelect={handleSelectSymbol}
                    onBuy={sendRowToPaperTrading}
                    exportFilePrefix="ltm-scan"
                  />
                ) : (
                  <EmptyState
                    title="No LTM recommendations yet"
                    description="Run a Long-Term Buy & Hold Momentum scan to populate this table."
                  />
                )}
                <LtmReturnBoards payload={ltmPayload} />
                <LtmScanSummary payload={ltmPayload} />
                <LtmRejectionBreakdown buckets={ltmPayload?.rejection_breakdown || []} />
              </>
            ) : ltmRun.error || isStrategyRunFailed(ltmPayload) ? null : (
              <EmptyState
                title="No LTM scan yet"
                description="Run a Long-Term Buy & Hold Momentum scan to populate this table."
              />
            )}
          </>
        )
      ) : null}

      {!isLoading && !error && scannerStrategy === "production" ? (
        showAllAnalyzedStocks ? (
          // Full-universe screener breakdown
          <AllAnalyzedStocksTable
            stocks={screenerResult?.all_analyzed_stocks ?? []}
            instruments={instrumentIndex}
          />
        ) : filteredRows.length ? (
          <CandidateTable
            rows={filteredRows}
            selectedSymbol={selectedRow?.symbol ?? null}
            onSelect={handleSelectSymbol}
            onBuy={sendRowToPaperTrading}
            exportFilePrefix="scan"
          />
        ) : screenerResult ? (
          <EmptyState
            title="No matches for these filters"
            description="Adjust signal, score range, or search from Markets to refine results."
            primaryAction={{ label: "Open Markets", onClick: () => navigate("/markets"), variant: "secondary" }}
          />
        ) : null
      ) : null}

      {scannerStrategy === "production" && !screenerResult && !isLoading && !error ? (
        <EmptyState
          title="No scan results yet"
          description="Configure and run the swing scanner from Markets. Results will appear here automatically."
          primaryAction={{ label: "Go to Markets", onClick: () => navigate("/markets"), variant: "trade" }}
        />
      ) : null}

      {screenerResult && scannerStrategy === "production" ? (
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
    handleRunScanner, handleRunLtmScan, handleRunW52Scan, handleSelectSymbol, navigate,
    screenerResult, isLoading, error, showAllAnalyzedStocks,
    analysisItems, filteredRows, shortlistRows, selectedRow?.symbol,
    progressData, scanStartTime, lastScanDuration,
    sendRowToPaperTrading, scannerStrategy, ltmPayload, ltmCandidateRows, ltmStrategies,
    w52Payload, w52CandidateRows, w52ScanResultRows, w52VisibleRows, w52InFlight, ltmInFlight, ltmRun, w52Run,
    ltmProgress, w52Progress, ltmStartTime, w52StartTime, ltmHydrated, w52Hydrated,
  ]);

  const scannerView = (
    <main className="page-container" key="scanner-view">
      {detailViewOpen && selectedRow ? (
        <Suspense fallback={<ViewFallback />}>
          <StockDetailPanel
            key={`${selectedRow.strategyId || "row"}:${selectedRow.symbol}`}
            row={selectedRow}
            onBack={handleDetailBack}
            onSendToPaperTrading={sendRowToPaperTrading}
          />
        </Suspense>
      ) : (
        scannerListView
      )}
    </main>
  );

  const paperDeskView = useMemo(() => (
    <div className="page-container page-container--wide" key="paper-desk">
      <Suspense fallback={<ViewFallback />}>
        <PaperTradingPage
          recommendationPrefill={paperTradingPrefill}
          onPrefillConsumed={() => setPaperTradingPrefill(null)}
          scannerCandidates={shortlistRows}
          lastScanAt={screenerResult?.analysis?.generated_at ?? null}
          retailMode
        />
      </Suspense>
    </div>
  ), [paperTradingPrefill, shortlistRows, screenerResult?.analysis?.generated_at]);

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
                      screenerResult={screenerResult}
                      isLoading={isLoading}
                      scanError={error}
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
      scoreKind: "composite",
      scoreLabel: "Score",
      strategyId: "production",
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


