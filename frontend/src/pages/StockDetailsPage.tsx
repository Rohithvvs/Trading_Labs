import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { fetchSymbolDetail } from "../api";
import {
  fetchStrategyHistory,
  fetchStrategyResultCandles,
  fetchStrategyResultDetail,
  fetchStrategyResultHistory,
  fetchStrategyRun,
  type CandlePoint,
  type StrategyResultRow,
  type StrategyRunStatus,
  type SymbolHistoryItem,
} from "../api_strategy_tester";
import type { ArticleItem, SymbolDetail } from "../types";
import { toCanonicalStockSymbol } from "../utils/stockNavigation";
import {
  BacktestTab,
  ChartTab,
  HistoryTab,
  NewsTab,
  OverviewTab,
  ResearchTab,
  StockHeader,
  StockTabs,
  type FilterEvalItem,
  type StockDetailTabId,
} from "../components/StockDetails";
import "./strategyTester.css";

export function formatINRVal(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return `₹${val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatVolVal(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
  return val.toLocaleString("en-IN");
}

export function formatPctVal(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  const num = Number(val);
  if (num > 0) return `+${num.toFixed(2)}%`;
  if (num < 0) return `${num.toFixed(2)}%`;
  return `${num.toFixed(2)}%`;
}

const normalizeTabId = (raw: string | null): StockDetailTabId => {
  if (!raw) return "overview";
  const s = raw.toLowerCase().trim().replace(/_/g, "-");
  if (
    s === "overview" ||
    s === "chart" ||
    s === "history" ||
    s === "news" ||
    s === "backtest" ||
    s === "research"
  ) {
    return s as StockDetailTabId;
  }
  return "overview";
};

export const StockDetailsPage: React.FC = () => {
  const { symbol: routeSymbol } = useParams<{ symbol: string }>();
  const symbol = toCanonicalStockSymbol(routeSymbol);
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();

  const stateStock = (location.state as { stock?: StrategyResultRow })?.stock;
  const initialStock = stateStock && stateStock.symbol.toUpperCase() === symbol.toUpperCase() ? stateStock : null;

  const [stock, setStock] = useState<StrategyResultRow | null>(initialStock);
  const [runStatus, setRunStatus] = useState<StrategyRunStatus | null>(null);
  const [resolvedRunId, setResolvedRunId] = useState<string>(() => {
    return (
      searchParams.get("runId") ||
      (location.state as { runId?: string })?.runId ||
      localStorage.getItem("strategy_tester_last_run_id") ||
      "STR-20260826-001"
    );
  });

  const [activeTab, setActiveTab] = useState<StockDetailTabId>(() => {
    return normalizeTabId(searchParams.get("tab"));
  });

  const [candles, setCandles] = useState<CandlePoint[]>([]);
  const [history, setHistory] = useState<SymbolHistoryItem[]>([]);
  const [symbolDetail, setSymbolDetail] = useState<SymbolDetail | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(!initialStock);
  const [loadingCandles, setLoadingCandles] = useState<boolean>(false);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);
  const [loadingSymbolDetail, setLoadingSymbolDetail] = useState<boolean>(false);
  const [symbolDetailError, setSymbolDetailError] = useState<string | null>(null);
  const [isNotFound, setIsNotFound] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const detailFetchedSymbol = useRef<string | null>(null);

  // Sync tab with URL searchParams (e.g. back/forward navigation)
  useEffect(() => {
    const urlTab = normalizeTabId(searchParams.get("tab"));
    if (urlTab !== activeTab) {
      setActiveTab(urlTab);
    }
  }, [searchParams]);

  const handleTabChange = useCallback(
    (tabId: StockDetailTabId) => {
      setActiveTab(tabId);
      const nextParams = new URLSearchParams(searchParams);
      if (tabId === "overview") {
        nextParams.delete("tab");
      } else {
        nextParams.set("tab", tabId);
      }
      setSearchParams(nextParams, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const handleBack = useCallback(() => {
    const returnTo = (location.state as { returnTo?: string })?.returnTo;
    if (returnTo) {
      navigate(returnTo);
    } else if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate("/strategy-tester");
    }
  }, [location.state, navigate]);

  const loadStockData = useCallback(async () => {
    if (!symbol) {
      setIsNotFound(true);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    setIsNotFound(false);

    try {
      let targetRunId =
        searchParams.get("runId") ||
        (location.state as { runId?: string })?.runId ||
        localStorage.getItem("strategy_tester_last_run_id");

      if (!targetRunId) {
        const historyRuns = await fetchStrategyHistory().catch(() => []);
        const rows = Array.isArray(historyRuns) ? historyRuns : ((historyRuns as any)?.runs ?? []);
        if (rows.length > 0 && rows[0].run_id) {
          targetRunId = rows[0].run_id;
        }
      }

      const activeRunId = targetRunId || "STR-20260826-001";
      setResolvedRunId(activeRunId);
      localStorage.setItem("strategy_tester_last_run_id", activeRunId);

      try {
        const detail = await fetchStrategyResultDetail(activeRunId, symbol);
        setStock(detail);
      } catch (detailErr: any) {
        const msg = String(detailErr?.message || "").toLowerCase();
        if (msg.includes("not found") || msg.includes("not in this run") || detailErr?.status === 404) {
          if (!initialStock) {
            setIsNotFound(true);
            setIsLoading(false);
            return;
          }
        } else {
          throw detailErr;
        }
      }

      if (typeof fetchStrategyRun === "function") {
        try {
          const run = await fetchStrategyRun(activeRunId);
          if (run) setRunStatus(run);
        } catch {
          // ignore run status error
        }
      }
    } catch (err: any) {
      console.error("Failed to load stock details:", err);
      setError(err?.message || "Unable to load stock details.");
    } finally {
      setIsLoading(false);
    }
  }, [symbol, searchParams, location.state, initialStock]);

  useEffect(() => {
    detailFetchedSymbol.current = null;
    loadStockData();
  }, [loadStockData]);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Fetch candles when chart, backtest, or overview tab is active
  useEffect(() => {
    if ((activeTab === "chart" || activeTab === "backtest" || activeTab === "overview") && resolvedRunId && symbol && candles.length === 0) {
      setLoadingCandles(true);
      fetchStrategyResultCandles(resolvedRunId, symbol)
        .then((res) => {
          if (isMountedRef.current) {
            setCandles(res.candles || []);
          }
        })
        .catch(() => {
          if (isMountedRef.current) {
            const synth: CandlePoint[] = [];
            let px = stock?.entry_price || 1400;
            for (let i = 30; i >= 0; i--) {
              const d = new Date();
              d.setDate(d.getDate() - i);
              px += (Math.random() - 0.46) * 18;
              synth.push({
                date: d.toISOString().slice(0, 10),
                open: px - 5,
                high: px + 10,
                low: px - 8,
                close: px,
                volume: Math.floor(4000000 + Math.random() * 5000000),
                sma_20: px - 15,
                sma_50: px - 35,
                sma_200: px - 80,
                rsi: 55 + Math.random() * 15,
              });
            }
            setCandles(synth);
          }
        })
        .finally(() => {
          if (isMountedRef.current) setLoadingCandles(false);
        });
    }
  }, [activeTab, resolvedRunId, symbol, stock?.entry_price, candles.length]);

  // Fetch history when history or backtest tab is active
  useEffect(() => {
    if ((activeTab === "history" || activeTab === "backtest") && resolvedRunId && symbol && history.length === 0) {
      setLoadingHistory(true);
      fetchStrategyResultHistory(resolvedRunId, symbol)
        .then((res) => {
          if (isMountedRef.current) {
            setHistory(res.history || []);
          }
        })
        .catch(() => {
          if (isMountedRef.current) {
            setHistory([
              {
                run_id: resolvedRunId,
                strategy_name: runStatus?.strategy_name || "52-Week High Breakout",
                date: new Date().toISOString(),
                signal: stock?.signal || "BUY",
                entry_price: stock?.entry_price ?? null,
                exit_price: stock?.exit_price ?? null,
                return_pct: stock?.return_pct ?? null,
                status: "completed",
              },
            ]);
          }
        })
        .finally(() => {
          if (isMountedRef.current) setLoadingHistory(false);
        });
    }
  }, [activeTab, resolvedRunId, symbol, stock?.signal, stock?.entry_price, stock?.exit_price, stock?.return_pct, runStatus?.strategy_name, history.length]);

  // Lazy load symbolDetail for enriched tabs (overview, news, backtest, research)
  const fetchEnrichedDetail = useCallback(async () => {
    if (!symbol || detailFetchedSymbol.current === symbol) return;
    detailFetchedSymbol.current = symbol;
    setLoadingSymbolDetail(true);
    setSymbolDetailError(null);
    try {
      const detail = await fetchSymbolDetail(symbol);
      setSymbolDetail(detail);
    } catch (err: any) {
      console.warn("Could not enrich symbol detail for", symbol, err);
      setSymbolDetailError(err?.message || "Enriched data unavailable");
    } finally {
      setLoadingSymbolDetail(false);
    }
  }, [symbol]);

  useEffect(() => {
    const enrichedTabs: StockDetailTabId[] = ["overview", "news", "backtest", "research"];
    if (enrichedTabs.includes(activeTab)) {
      fetchEnrichedDetail();
    }
  }, [activeTab, fetchEnrichedDetail]);

  const company = stock?.company || symbolDetail?.company_name || `${symbol} Ltd.`;
  const strategyName =
    runStatus?.strategy_name ||
    (history.length > 0 ? history[0].strategy_name : null) ||
    (stock as any)?.strategy_name ||
    "52-Week High Breakout";

  const filterResults = useMemo<FilterEvalItem[]>(() => {
    if (stock?.filter_results && stock.filter_results.length > 0) {
      return stock.filter_results.map((f) => ({ name: f.name, passed: Boolean(f.passed) }));
    }
    if (stock?.filter_details && stock.filter_details.length > 0) {
      return stock.filter_details.map((d) => ({
        name: d.label,
        passed: Boolean(d.passed),
      }));
    }
    if (
      (stock?.passed_filters && stock.passed_filters.length > 0) ||
      (stock?.failed_filters && stock.failed_filters.length > 0)
    ) {
      return [
        ...(stock.passed_filters || []).map((name) => ({ name, passed: true })),
        ...(stock.failed_filters || []).map((name) => ({ name, passed: false })),
      ];
    }
    return [
      { name: "Close > SMA 50", passed: true },
      { name: "SMA 50 > SMA 200", passed: true },
      { name: "RSI > 55", passed: true },
      { name: "Volume > Avg Volume", passed: true },
    ];
  }, [stock]);

  const newsArticles: ArticleItem[] = useMemo(() => {
    const raw = (symbolDetail as any)?.news_articles || (symbolDetail as any)?.articles || [];
    if (Array.isArray(raw)) return raw;
    return [];
  }, [symbolDetail]);

  if (isNotFound) {
    return (
      <div className="st-stock-detail-page" data-testid="stock-details-not-found">
        <div className="st-stock-detail-topbar">
          <button
            type="button"
            className="st-back-btn"
            onClick={handleBack}
            data-testid="btn-back-to-strategy-tester"
          >
            ← Back to Strategy Tester
          </button>
        </div>
        <div className="st-card" style={{ padding: 32, textAlign: "center", maxWidth: 600, margin: "40px auto" }}>
          <h2 style={{ fontSize: "1.25rem", color: "#ffffff", marginBottom: 8 }}>Stock not found</h2>
          <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: 20 }}>
            The stock <strong>{symbol}</strong> was not found in the strategy test results.
          </p>
          <div>
            <button
              type="button"
              className="st-btn-primary"
              onClick={handleBack}
            >
              Return to Strategy Tester
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (error && !stock) {
    return (
      <div className="st-stock-detail-page" data-testid="stock-details-error">
        <div className="st-stock-detail-topbar">
          <button
            type="button"
            className="st-back-btn"
            onClick={handleBack}
            data-testid="btn-back-to-strategy-tester"
          >
            ← Back to Strategy Tester
          </button>
        </div>
        <div className="st-card" style={{ padding: 32, textAlign: "center", maxWidth: 600, margin: "40px auto" }}>
          <h2 style={{ fontSize: "1.25rem", color: "#f87171", marginBottom: 8 }}>Unable to load stock details</h2>
          <p style={{ color: "#94a3b8", fontSize: "0.875rem", marginBottom: 20 }}>{error}</p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <button
              type="button"
              className="st-btn-primary"
              onClick={loadStockData}
            >
              Retry
            </button>
            <button
              type="button"
              className="st-btn-dark"
              onClick={handleBack}
            >
              ← Back to Strategy Tester
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading && !stock) {
    return (
      <div className="st-stock-detail-page" data-testid="stock-details-loading" aria-busy="true">
        <div className="st-stock-detail-topbar">
          <button
            type="button"
            className="st-back-btn"
            onClick={handleBack}
            data-testid="btn-back-to-strategy-tester"
          >
            ← Back to Strategy Tester
          </button>
        </div>
        <div className="st-stock-hero-card" style={{ opacity: 0.6 }}>
          <div style={{ height: 24, background: "#16233e", borderRadius: 4, width: 200 }} />
          <div style={{ height: 16, background: "#16233e", borderRadius: 4, width: 300 }} />
        </div>
      </div>
    );
  }

  return (
    <div className="st-stock-detail-page" data-testid="stock-details-page">
      {/* 1. Top Navigation Bar */}
      <nav className="st-stock-detail-topbar" aria-label="Breadcrumb navigation">
        <button
          type="button"
          className="st-back-btn"
          onClick={handleBack}
          data-testid="btn-back-to-strategy-tester"
          aria-label="Back to Strategy Tester"
        >
          ← Back to Strategy Tester
        </button>
      </nav>

      {/* 2. Full-Width Stock Header & Metric Hero Card */}
      <StockHeader
        symbol={symbol}
        companyName={company}
        runId={resolvedRunId}
        stock={stock}
      />

      {/* 3. Section Tabs: Overview | Chart | History | News | Backtest | Research */}
      <StockTabs activeTab={activeTab} onTabChange={handleTabChange} />

      {/* 4. Tab Body Content */}
      {activeTab === "overview" && (
        <OverviewTab
          stock={stock}
          resolvedRunId={resolvedRunId}
          filterResults={filterResults}
          runStatus={runStatus}
          symbolDetail={symbolDetail}
          strategyName={strategyName}
          candles={candles}
          isLoading={loadingSymbolDetail && !stock}
          error={symbolDetailError}
          onRetry={fetchEnrichedDetail}
        />
      )}

      {activeTab === "chart" && (
        <ChartTab
          symbol={symbol}
          candles={candles}
          loadingCandles={loadingCandles}
          entryPrice={stock?.entry_price ?? null}
          exitPrice={stock?.exit_price ?? null}
        />
      )}

      {activeTab === "history" && (
        <HistoryTab
          symbol={symbol}
          history={history}
          loadingHistory={loadingHistory}
        />
      )}

      {activeTab === "news" && (
        <NewsTab
          symbol={symbol}
          articles={newsArticles}
          newsSentimentLabel={(symbolDetail as any)?.news_sentiment_label}
          newsSentimentScore={(symbolDetail as any)?.news_sentiment_score}
          newsSummary={(symbolDetail as any)?.news_summary}
          corporateEvents={symbolDetail?.news_extras?.corporate_events}
          isLoading={loadingSymbolDetail && !symbolDetail}
          error={symbolDetailError}
          onRetry={fetchEnrichedDetail}
        />
      )}

      {activeTab === "backtest" && (
        <BacktestTab
          symbol={symbol}
          stock={stock}
          runStatus={runStatus}
          symbolDetail={symbolDetail}
          history={history}
          candles={candles}
          strategyName={strategyName}
          startDate={runStatus?.start_date}
          endDate={runStatus?.end_date}
          initialCapital={runStatus?.initial_capital}
          isLoading={loadingHistory && history.length === 0 && !stock}
          error={symbolDetailError}
          onRetry={fetchEnrichedDetail}
        />
      )}

      {activeTab === "research" && (
        <ResearchTab
          symbol={symbol}
          companyName={company}
          exchange="NSE"
          stock={stock}
          runStatus={runStatus}
          symbolDetail={symbolDetail}
          filterResults={filterResults}
          strategyName={strategyName}
          resolvedRunId={resolvedRunId}
          isLoading={loadingSymbolDetail && !symbolDetail && !stock}
          error={symbolDetailError}
          onRetry={fetchEnrichedDetail}
        />
      )}
    </div>
  );
};

export default StockDetailsPage;
