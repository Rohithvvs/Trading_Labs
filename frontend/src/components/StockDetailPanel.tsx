import { Component, useEffect, useMemo, useState, useRef, type ErrorInfo, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type {
  BacktestResult,
  CandidateRow,
  DetailTab,
  OHLCVPoint,
  StockAnalysisResult,
  TradePlan,
  SymbolDetail,
} from "../types";
import { fetchLtmSymbolDetail, fetchSymbolDetail } from "../api";
import { getCached } from "../utils/appCache";
import { isPrefetched } from "../utils/researchPrefetcher";
import { ResearchDashboard } from "./ResearchDashboard";
import {
  BacktestAnalyticsDashboard,
  type BacktestDashboardModel,
  type BacktestRange,
  type DashboardTrade,
} from "./BacktestAnalyticsDashboard";

type StockDetailPanelProps = {
  row: CandidateRow | null;
  onBack?: () => void;
  onSendToPaperTrading?: (row: CandidateRow, suggestedEntry?: number | null, side?: "BUY" | "SELL") => void;
};

const TABS: { id: DetailTab; label: string }[] = [
  { id: "research", label: "Research" },
  { id: "overview", label: "Overview" },
  { id: "technicals", label: "Technicals" },
  { id: "trade-plan", label: "Trade plan" },
  { id: "news", label: "News" },
  { id: "backtest", label: "Backtest" },
  { id: "chart", label: "Chart" },
];

export function StockDetailPanel({ row, onBack, onSendToPaperTrading }: StockDetailPanelProps) {
  const [tab, setTab] = useState<DetailTab>("research");
  const [riskAmount, setRiskAmount] = useState(5000);
  const [symbolDetail, setSymbolDetail] = useState<SymbolDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const fetchAttempted = useRef(false);

  // Hooks must run unconditionally (before any early return).
  const analysis = row?.analysisItem;
  const technical =
    analysis?.technical?.find((item) => item.mode === "swing") ?? analysis?.technical?.[0];
  const plan =
    analysis?.recommendation?.trade_plans?.find((item) => item.mode === "swing") ??
    analysis?.recommendation?.trade_plans?.[0];
  const backtest =
    analysis?.backtests?.find((item) => item.mode === "swing") ?? analysis?.backtests?.[0];

  const currentPrice = useMemo(() => {
    if (!row) return 0;
    const series = symbolDetail?.ohlcv?.length
      ? symbolDetail.ohlcv
      : analysis?.ohlcv?.length
        ? analysis.ohlcv
        : undefined;
    if (series && series.length) {
      const close = series[series.length - 1]?.close;
      return typeof close === "number" && Number.isFinite(close) ? close : 0;
    }
    return row.entryLow ?? row.entryHigh ?? 0;
  }, [symbolDetail, analysis, row]);

  useEffect(() => {
    let mounted = true;
    if (!row) return;

    const symbol = row.symbol;
    const RESEARCH_CACHE_KEY = `research_detail:${symbol}`;
    const cached = getCached<SymbolDetail>(RESEARCH_CACHE_KEY);

    if (cached) {
      setSymbolDetail(cached);
      setLoadingDetail(false);
      setDetailError(null);
    } else {
      setSymbolDetail(null);
      setDetailError(null);
      setLoadingDetail(true);
    }

    if (fetchAttempted.current) return;
    fetchAttempted.current = true;

    void fetchSymbolDetail(symbol)
      .then((d) => {
        if (!mounted) return;
        setSymbolDetail(d);
        setLoadingDetail(false);
      })
      .catch((err) => {
        if (!mounted) return;
        if (!cached) {
          setDetailError(err?.message ?? String(err));
        }
        setLoadingDetail(false);
      });
    return () => {
      mounted = false;
      fetchAttempted.current = false;
    };
  }, [row]);

  if (!row) {
    return (
      <section className="panel empty-state">
        <h2>No stock selected</h2>
        <p>Select a row from the candidate table to inspect the recommendation, technicals, trade plan, news, backtest, and chart.</p>
      </section>
    );
  }

  const rankReason = buildRankContext(row);

  return (
    <section className="detail-panel panel">
      {onBack ? (
        <div className="detail-toolbar detail-toolbar--back" data-testid="detail-back-toolbar">
          <button
            type="button"
            className="button ghost-button detail-back-button"
            onClick={onBack}
            data-testid="back-to-scan-results"
            aria-label="Back to scan results"
          >
            ← Back to scan results
          </button>
        </div>
      ) : null}
      <div className="detail-header">
        <div className="detail-header-info">
          <p className="section-label">Selected stock</p>
          <div className="detail-title-row">
            <h2>{row.symbol}</h2>
            {row.ltm ? <span className="helper-chip">Long-Term Buy & Hold Momentum</span> : null}
            <span className={`signal-badge signal-${row.signal.toLowerCase()}`}>{row.signal}</span>
          </div>
          <p className="detail-summary">{row.recommendationSummary}</p>
        </div>
        <div className="detail-header-metrics">
          <MetricTile label="Score" value={row.score === null || row.score === undefined ? "N/A" : row.score.toFixed(1)} help="Weighted final score after full analysis." />
          <MetricTile
            label="Confidence"
            value={row.confidence === null ? "--" : `${Math.round(row.confidence * 100)}%`}
            help="How strongly the recommendation layer supports this setup."
          />
          <MetricTile
            label="Risk / Reward"
            value={row.riskReward === null ? "--" : row.riskReward.toFixed(2)}
            help="Potential upside compared to stop-loss risk."
          />
          <MetricTile label="Rank" value={row.rank ?? "--"} help="Position in the current shortlist." />
          <MetricTile label="Readiness" value={row.tradeReadiness} help="Practical action label after data, signal, and risk checks." />
        </div>
      </div>

      {onSendToPaperTrading ? (
        <div className="detail-actions-toolbar" data-testid="detail-actions-toolbar" role="group" aria-label="Trading actions">
          <button
            type="button"
            className="ds-btn ds-btn--buy"
            onClick={() => onSendToPaperTrading(row, currentPrice ?? undefined, "BUY")}
            aria-label="Place buy trade"
          >
            BUY
          </button>
          <button
            type="button"
            className="ds-btn ds-btn--sell"
            onClick={() => onSendToPaperTrading(row, currentPrice ?? undefined, "SELL")}
            aria-label="Place sell trade"
          >
            SELL / Trade
          </button>
          <button
            type="button"
            className="ds-btn ds-btn--secondary"
            onClick={() => onSendToPaperTrading(row, currentPrice ?? undefined)}
            aria-label="Open paper trade"
          >
            Paper trade
          </button>
        </div>
      ) : null}

      <div className="detail-tabs" role="tablist" aria-label="Stock detail tabs">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`detail-tab ${tab === item.id ? "is-active" : ""}`}
            onClick={() => setTab(item.id)}
            aria-label={`${item.label} tab${tab === item.id ? " (active)" : ""}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="detail-content">
        <DetailTabErrorBoundary tabId={tab} key={tab}>
          {tab === "research" ? (
            <ResearchDashboard
              research={symbolDetail?.research as Record<string, unknown> | null | undefined}
              symbol={row.symbol}
              loading={loadingDetail}
              error={detailError}
            />
          ) : null}
          {tab === "overview" ? (
            <OverviewTab
              analysis={analysis}
              row={row}
              rankReason={rankReason}
              symbolDetail={symbolDetail}
              currentPrice={currentPrice}
              loadingDetail={loadingDetail}
              onSendToPaperTrading={onSendToPaperTrading}
            />
          ) : null}
          {tab === "technicals" ? (
            <TechnicalsTab technical={technical} row={row} symbolDetail={symbolDetail} />
          ) : null}
          {tab === "trade-plan" ? (
            <TradePlanTab
              plan={plan}
              row={row}
              riskAmount={riskAmount}
              onRiskAmountChange={setRiskAmount}
              symbolDetail={symbolDetail}
              currentPrice={currentPrice}
            />
          ) : null}
          {tab === "news" ? (
            <NewsTab analysis={analysis} row={row} symbolDetail={symbolDetail} />
          ) : null}
          {tab === "backtest" ? (
            <BacktestTab
              backtest={backtest}
              backtestDetail={symbolDetail?.backtest_extras ?? null}
              row={row}
            />
          ) : null}
          {tab === "chart" ? <ChartTab analysis={analysis} plan={plan} /> : null}
        </DetailTabErrorBoundary>
      </div>
    </section>
  );
}

/** Isolate tab render failures so the shell (header + tabs) never goes blank. */
class DetailTabErrorBoundary extends Component<
  { tabId: string; children: ReactNode },
  { error: string | null }
> {
  state: { error: string | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error: error?.message || "Tab failed to render" };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[StockDetailPanel] tab render failed", {
      tab: this.props.tabId,
      error,
      info,
    });
  }

  componentDidUpdate(prevProps: { tabId: string }) {
    if (prevProps.tabId !== this.props.tabId && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <section className="subpanel" role="alert" data-testid="detail-tab-error">
          <h3>This tab could not be displayed</h3>
          <p className="muted-copy">{this.state.error}</p>
          <p className="helper-text">Try another tab or go back to scan results. The stock header remains available.</p>
        </section>
      );
    }
    return this.props.children;
  }
}

function OverviewTab({
  analysis,
  row,
  rankReason,
  symbolDetail,
  currentPrice,
  loadingDetail,
  onSendToPaperTrading,
}: {
  analysis?: StockAnalysisResult;
  row: CandidateRow;
  rankReason: string;
  symbolDetail?: SymbolDetail | null;
  currentPrice?: number | null;
  loadingDetail?: boolean;
  onSendToPaperTrading?: (row: CandidateRow, suggestedEntry?: number | null, side?: "BUY" | "SELL") => void;
}) {
  const reco = analysis?.recommendation;
  const reasoning = reco?.reasoning;
  const techScore = row.screenerMatch?.technical_score;
  const scanScore = row.screenerMatch?.screener_score;
  const newsLabel = analysis?.news_sentiment_label;
  const newsScore = analysis?.news_sentiment_score;

  return (
    <div className="detail-grid">
      <section className="subpanel">
        <h3>Recommendation overview</h3>
        <p className="muted-copy">{reco?.summary ?? row.recommendationSummary}</p>
        <div className="reason-columns">
          <ReasonList
            title="Top reasons"
            items={
              Array.isArray(reasoning?.bullets) && reasoning!.bullets!.length
                ? reasoning!.bullets!
                : [row.recommendationSummary || "No detailed reasons available."]
            }
          />
          <ReasonList
            title="Risk warnings"
            items={
              Array.isArray(reasoning?.risk_factors) && reasoning!.risk_factors!.length
                ? reasoning!.risk_factors!
                : ["Full analysis did not return extra risk factors for this name."]
            }
          />
        </div>
        <div className="info-cards info-cards--stack">
          <div className="metric-card">
            <span className="section-label">Company</span>
            <h4 style={{ margin: 6 }}>{symbolDetail?.company_name ?? analysis?.company_name ?? row.symbol}</h4>
            <p className="muted-copy">{symbolDetail?.company_description ?? analysis?.company_description ?? "Company description unavailable"}</p>
          </div>
          <div className="metric-card">
            <span className="section-label">Sector</span>
            <h4 style={{ margin: 6 }}>{symbolDetail?.sector ?? analysis?.sector ?? "-"}</h4>
            <p className="muted-copy">Primary business sector</p>
          </div>
          <div className="metric-card">
            <span className="section-label">Industry</span>
            <h4 style={{ margin: 6 }}>{symbolDetail?.industry ?? analysis?.industry ?? "-"}</h4>
            <p className="muted-copy">Industry classification</p>
          </div>
          <div className="metric-card">
            <span className="section-label">Market cap</span>
            <h4 style={{ margin: 6 }}>{formatMarketCap(symbolDetail?.market_cap ?? analysis?.market_cap ?? null)}</h4>
            <p className="muted-copy">Reported market capitalization</p>
          </div>
        </div>
      </section>
      <section className="subpanel">
        <h3>Ranking context</h3>
        <div className="score-breakdown">
          <MetricTile label="Final score" value={row.score === null || row.score === undefined ? "N/A" : row.score.toFixed(1)} help="Combined recommendation score." />
          <MetricTile
            label="Technical"
            value={typeof techScore === "number" ? techScore.toFixed(1) : "--"}
            help="Technical strength before recommendation weighting."
          />
          <MetricTile
            label="Scanner"
            value={typeof scanScore === "number" ? scanScore.toFixed(1) : "--"}
            help="Weighted screener score used for shortlisting."
          />
          <MetricTile
            label="News"
            value={
              analysis
                ? `${newsLabel ?? "n/a"}${typeof newsScore === "number" ? ` (${newsScore.toFixed(2)})` : ""}`
                : "--"
            }
            help="How recent news supports or weakens the setup."
          />
        </div>
        <div className="mt-4 space-y-3">
          <div className="flex gap-3">
            <div className="metric-card w-full">
              <span className="section-label">52-week range</span>
              <div className="mt-2">
                <div className="w-full">
                  {symbolDetail?.year52_low != null && symbolDetail?.year52_high != null ? (
                    <RangeBar low={symbolDetail.year52_low} high={symbolDetail.year52_high} current={currentPrice ?? 0} />
                  ) : (
                    <p className="muted-copy">52-week data unavailable</p>
                  )}
                </div>
              </div>
            </div>

            <div className="metric-card w-full" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
              <div>
                <span className="section-label">Company</span>
                <h4 style={{ margin: 6 }}>{symbolDetail?.company_name ?? analysis?.company_name ?? row.symbol}</h4>
                <p className="muted-copy">{symbolDetail?.industry ?? analysis?.industry ?? "-"}</p>
              </div>
              <div>
                <span className="section-label">Market cap</span>
                <h4 style={{ margin: 6 }}>{symbolDetail?.market_cap != null || analysis?.market_cap != null ? new Intl.NumberFormat().format(symbolDetail?.market_cap ?? analysis?.market_cap ?? 0) : "-"}</h4>
              </div>
            </div>
          </div>

          <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
            <button
              type="button"
              className="ds-btn ds-btn--buy"
              onClick={() => onSendToPaperTrading?.(row, currentPrice ?? undefined, "BUY")}
              disabled={loadingDetail || !onSendToPaperTrading}
            >
              {loadingDetail ? "Loading…" : "BUY"}
            </button>
            <button
              type="button"
              className="ds-btn ds-btn--trade"
              onClick={() => onSendToPaperTrading?.(row, currentPrice ?? undefined)}
              disabled={loadingDetail || !onSendToPaperTrading}
            >
              Paper trade
            </button>
          </div>
        </div>
        <ConfidenceBreakdown analysis={analysis} />
        <DataQualityBox analysis={analysis} />
        <p className="helper-text">{rankReason}</p>
      </section>
    </div>
  );
}

function TechnicalsTab({
  technical,
  row,
  symbolDetail,
}: {
  technical?: StockAnalysisResult["technical"][number];
  row: CandidateRow;
  symbolDetail?: SymbolDetail | null;
}) {
  if (row.ltm?.technicals) {
    const t = row.ltm.technicals as Record<string, any>;
    const tiles = [
      ["Momentum 252", t.momentum_252 == null ? "unavailable" : `${(Number(t.momentum_252) * 100).toFixed(2)}%`],
      ["Close T", t.close_t ?? "unavailable"],
      ["Close T−252", t.close_t_minus_252 ?? "unavailable"],
      ["Rank among eligible", t.rank_among_eligible ?? "—"],
      ["Gate > +50%", t.gate_pass ? "Pass" : "Fail"],
      ["Selected", t.selected ? "Yes" : "No"],
      ["Clock", t.clock_status ?? "—"],
      ["Sessions to rebalance", t.sessions_to_rebalance ?? "—"],
    ];
    return (
      <div className="detail-stack" data-testid="ltm-technicals">
        <section className="subpanel">
          <div className="subpanel-header">
            <h3>Technical decision</h3>
            <span className={`signal-badge signal-${row.signal.toLowerCase()}`}>{row.signal}</span>
            <span className="helper-chip">Long-Term Buy & Hold Momentum</span>
            <span className="helper-chip">Hard filters passed: {t.hard_filters_pass ? "Yes" : "No"}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(10rem,1fr))", gap: 10 }}>
            {tiles.map(([label, value]) => (
              <div key={String(label)} className="metric-card">
                <span className="section-label">{label}</span>
                <strong>{String(value)}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>
    );
  }
  const indicators = technical?.indicators ?? {};
  const techExtra = symbolDetail?.technical_extras;
  const hardFailures = [
    !Boolean(indicators["core_trend_filter_pass"]) ? "Trend filter failed" : null,
    !Boolean(indicators["core_momentum_filter_pass"]) ? "Momentum filter failed" : null,
    !Boolean(indicators["basic_liquidity_filter_pass"]) ? "Liquidity filter failed" : null,
  ].filter(Boolean) as string[];

  const tiles = [
    {
      label: "EMA 20",
      value: formatValue(indicators["ema_20"]),
      status: Boolean(indicators["close_above_ema20"]) ? "Passed" : "Failed",
      copy: "Price above EMA 20 keeps the short-term swing trend constructive.",
    },
    {
      label: "EMA 50",
      value: indicators["ema_50"] ? formatValue(indicators["ema_50"]) : "N/A",
      status: Boolean(indicators["ema20_above_ema50"]) ? "Passed" : "Failed",
      copy: "Price above EMA 50 indicates medium-term strength.",
    },
    {
      label: "Supertrend",
      value: formatValue(indicators["supertrend"]),
      status: Boolean(indicators["supertrend_positive"]) ? "Positive" : "Negative",
      copy: "Supertrend is used as a hard trend confirmation filter.",
    },
    {
      label: "MACD",
      value: `${formatValue(indicators["macd"])} / ${formatValue(indicators["macd_signal"])}`,
      status: Boolean(indicators["macd_positive"]) ? "Positive" : "Negative",
      copy: "MACD above signal supports bullish momentum.",
    },
    {
      label: "RSI",
      value: formatValue(indicators["rsi_14"]),
      status: Boolean(indicators["rsi_supportive"]) ? "Supportive" : "Weak",
      copy: "RSI above 50 supports the current swing bias.",
    },
    {
      label: "SMA trend",
      value: String(indicators["higher_timeframe_trend"] ?? row.trend),
      status: Boolean(indicators["sma_uptrend_20d"]) ? "Rising" : "Flat",
      copy: "A rising SMA trend adds confirmation but does not hard-reject alone.",
    },
    {
      label: "HH / HL structure",
      value: formatValue(indicators["structure_score"]),
      status: Boolean(indicators["structure_supportive"]) ? "Supportive" : "Weak",
      copy: "Higher-high / higher-low structure is a score booster, not a hard filter.",
    },
    {
      label: "Volume",
      value: Boolean(indicators["volume_above_previous_day"]) ? "Expanding" : "Flat",
      status: Boolean(indicators["basic_liquidity_filter_pass"]) ? "Liquid" : "Thin",
      copy: "Liquidity must pass, while volume expansion improves confidence.",
    },
    {
      label: "Candle confirmation",
      value: Boolean(indicators["hammer_or_gravestone"]) ? "Seen" : "None",
      status: Boolean(indicators["hammer_or_gravestone"]) ? "Confirming" : "Optional",
      copy: "Hammer or gravestone are confirmation only and do not reject strong setups by themselves.",
    },
  ];

  // extras mapping
  const atrClass = String((techExtra?.atr_class ?? "")).toLowerCase();
  const atrLabel = atrClass === "low" ? "LOW" : atrClass === "medium" ? "MEDIUM" : atrClass === "high" ? "HIGH" : "-";
  const atrBadgeColor = atrClass === "low" ? "var(--positive)" : atrClass === "medium" ? "var(--warning)" : atrClass === "high" ? "var(--negative)" : "var(--text-muted)";

  function bollingerDisplay(status?: string | null) {
    switch (status) {
      case "below_lower":
        return "Below Lower Band 🔴";
      case "near_lower":
        return "Near Lower Band 🟡";
      case "mid":
        return "Middle of Bands ⚪";
      case "near_upper":
        return "Near Upper Band 🟡";
      case "above_upper":
        return "Above Upper Band 🟢";
      default:
        return status ?? "-";
    }
  }

  function mtfColor(signal?: string | null) {
    if (!signal) return "var(--text-muted)";
    const s = String(signal).toLowerCase();
    if (s.includes("bull") || s === "buy" || s === "bullish") return "var(--positive)";
    if (s.includes("bear") || s === "sell" || s === "bearish") return "var(--negative)";
    return "var(--text-muted)";
  }

  return (
    <div className="detail-stack">
      <section className="subpanel">
        <div className="subpanel-header">
          <h3>Technical decision</h3>
          <div className="meta-inline">
            <span className={`signal-badge signal-${(technical?.signal ?? "bearish").toLowerCase()}`}>{technical?.signal ?? "bearish"}</span>
            <span className="helper-chip">
              <abbr title="Hard filters are core trend, momentum, and liquidity checks that must pass before a stock can be bullish or neutral.">
                Hard filters passed
              </abbr>
              : {Boolean(indicators["hard_filters_pass"]) ? "Yes" : "No"}
            </span>
            <span className="helper-chip" style={{ background: indicators["ema50_available"] === false ? "var(--surface-sunken)" : Boolean(indicators["ema20_above_ema50"]) ? "var(--positive)" : "var(--negative)", color: "var(--text)", border: indicators["ema50_available"] === false ? "1px solid var(--border)" : "none" }}>
              {indicators["ema50_available"] === false ? "EMA50 Not Available" : "Bullish EMA Structure"}
            </span>
          </div>
        </div>
        {techExtra ? (
          <div className="mb-3">
            <div className="flex items-center gap-3">
              <div className="metric-card">
                <span className="section-label">ATR</span>
                <div className="mt-2 flex items-center justify-between">
                  <strong>{techExtra.atr != null ? techExtra.atr.toFixed(4) : "--"}</strong>
                  <span
                    className="px-2 py-1 rounded text-sm"
                    style={{
                      background: techExtra.atr_class === "low" ? "var(--positive)" : techExtra.atr_class === "medium" ? "var(--warning)" : "var(--negative)",
                      color: "var(--text)",
                    }}
                  >
                    {String(techExtra.atr_class ?? "-").toUpperCase()}
                  </span>
                </div>
                <p className="muted-copy">ATR %: {techExtra.atr_pct != null ? `${techExtra.atr_pct.toFixed(2)}%` : "--"}</p>
              </div>

              <div className="metric-card">
                <span className="section-label">Bollinger</span>
                <div className="mt-2">
                  <strong>{techExtra.bollinger_status ?? techExtra.bollinger_position ?? "--"}</strong>
                  <p className="muted-copy">Position relative to bands</p>
                </div>
              </div>

              <div className="metric-card">
                <span className="section-label">Multi-timeframe</span>
                <div className="mt-2">
                  <div className="flex gap-2">
                    <div className="status-pill" style={{ display: "flex", flexDirection: "column" }}>
                      <span className="muted-copy">Daily</span>
                      <strong>{techExtra.multi_timeframe?.daily ?? "-"}</strong>
                    </div>
                    <div className="status-pill" style={{ display: "flex", flexDirection: "column" }}>
                      <span className="muted-copy">Weekly</span>
                      <strong>{techExtra.multi_timeframe?.weekly ?? "-"}</strong>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
        <div className="score-breakdown">
          <MetricTile
            label="Technical score"
            value={
              typeof technical?.score === "number"
                ? technical.score.toFixed(1)
                : typeof row.screenerMatch?.technical_score === "number"
                  ? row.screenerMatch.technical_score.toFixed(1)
                  : "--"
            }
            help="Overall technical strength."
          />
          <MetricTile label="Trend" value={row.trend} help="Trend combines EMA, Supertrend, and higher timeframe alignment." />
          <MetricTile label="Momentum" value={row.momentum} help="Momentum uses MACD and RSI support." />
          <MetricTile label="Structure" value={formatValue(indicators["structure_score"])} help="Structure score counts recent HH/HL confirmations." />
        </div>
        <p className="helper-text">
          {technical?.summary ??
            "This stock only has scanner-stage evidence because the full technical explanation was not returned."}
        </p>
        {hardFailures.length ? (
          <div className="warning-box">
            <strong>Hard filter fail reasons</strong>
            <ul>
              {hardFailures.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="subpanel">
        <h3>Trade confidence checklist</h3>
        <div className="checklist-grid">
          {buildTechnicalChecklist(indicators, row).map((item) => (
            <article key={item.label} className={`checklist-item ${item.state === "N/A" ? "is-neutral" : item.passed ? "is-positive" : "is-risk"}`} style={item.state === "N/A" ? { opacity: 0.7 } : {}}>
              <span>{item.state === "N/A" ? "N/A" : item.passed ? "PASS" : "FAIL"}</span>
              <strong>{item.label}</strong>
              <p>{item.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="indicator-grid-panel">
        {tiles.map((tile) => (
          <article key={tile.label} className="indicator-tile">
            <div className="indicator-header">
              <h4>{tile.label}</h4>
              <span className={`status-tag ${tile.status === "Failed" || tile.status === "Negative" || tile.status === "Weak" ? "is-risk" : "is-positive"}`}>
                {tile.status}
              </span>
            </div>
            <strong>{tile.value}</strong>
            <p>{tile.copy}</p>
          </article>
        ))}
      </section>

      <section className="subpanel">
        <h3>Technical extras</h3>
        <div className="flex gap-3">
          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">ATR</span>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
              <strong>{techExtra?.atr != null ? techExtra.atr.toFixed(4) : "--"}</strong>
              <span style={{ background: atrBadgeColor, color: "var(--text)", padding: "4px 8px", borderRadius: 6 }}>{atrLabel}</span>
            </div>
            <p className="muted-copy">{techExtra?.atr_pct != null ? `ATR %: ${techExtra.atr_pct.toFixed(2)}%` : "ATR %: --"}</p>
          </div>

          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">Bollinger</span>
            <div className="mt-2">
            <strong>{bollingerDisplay(techExtra?.bollinger_status ?? techExtra?.bollinger_position)}</strong>
              <p className="muted-copy">Position relative to Bollinger Bands</p>
            </div>
          </div>

          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">Multi-timeframe</span>
            <div className="mt-2">
              <table style={{ width: "100%" }}>
                <tbody>
                  <tr>
                    <td style={{ padding: "6px 8px" }}>Daily</td>
                    <td style={{ padding: "6px 8px", textAlign: "right", color: mtfColor(techExtra?.multi_timeframe?.daily) }}>{techExtra?.multi_timeframe?.daily ?? "-"}</td>
                  </tr>
                  <tr>
                    <td style={{ padding: "6px 8px" }}>Weekly</td>
                    <td style={{ padding: "6px 8px", textAlign: "right", color: mtfColor(techExtra?.multi_timeframe?.weekly) }}>{techExtra?.multi_timeframe?.weekly ?? "-"}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function ConfidenceBreakdown({ analysis }: { analysis?: StockAnalysisResult }) {
  const breakdown = analysis?.confidence_breakdown ?? {};
  return (
    <div className="confidence-box">
      <h4>Confidence breakdown</h4>
      <div className="score-breakdown">
        <MetricTile label="Technical score" value={formatValue(breakdown.technical_score)} help="Raw technical score before weighting." />
        <MetricTile label="Technical part" value={formatValue(breakdown.technical_component)} help="Technical score contribution to final recommendation." />
        <MetricTile label="Sentiment part" value={formatValue(breakdown.sentiment_component)} help="News sentiment contribution to final score." />
        <MetricTile label="Backtest part" value={formatValue(breakdown.backtest_component)} help="Backtest contribution to final score." />
      </div>
    </div>
  );
}

function DataQualityBox({ analysis }: { analysis?: StockAnalysisResult }) {
  const quality = analysis?.data_quality ?? {};
  const mockWarning = Boolean(quality.mock_warning);
  return (
      <div className={`data-quality-box ${mockWarning ? "is-risk" : "is-positive"}`}>
        <strong>{mockWarning ? "Mock data warning" : "Data quality"}</strong>
        <p>
          Source {String(quality.source ?? analysis?.data_source ?? "unknown")} | candles {String(quality.candles ?? "--")} | Candles fetched: {String(quality.candles_fetched ?? quality.candles ?? "--")} | latest {String(quality.latest_timestamp ?? "--")}
        </p>
        {mockWarning ? <p>Do not place real trades from this result until FYERS live data is confirmed.</p> : null}
      </div>
  );
}

function buildTechnicalChecklist(indicators: Record<string, string | number | boolean>, row: CandidateRow) {
  return [
    {
      label: "Trend alignment",
      passed: Boolean(indicators["close_above_ema20"]) && Boolean(indicators["supertrend_positive"]),
      copy: "Close above EMA 20 and Supertrend positive.",
    },
    {
      label: "EMA20 Above EMA50",
      passed: Boolean(indicators["ema20_above_ema50"]),
      state: indicators["ema50_available"] === false ? "N/A" : undefined,
      copy: "EMA20 is strictly greater than EMA50.",
    },
    {
      label: "Long-term trend",
      passed: String(indicators["higher_timeframe_trend"] ?? row.trend) === "uptrend",
      copy: "Higher timeframe trend should not fight the trade.",
    },
    {
      label: "Momentum",
      passed: Boolean(indicators["macd_positive"]) && Boolean(indicators["rsi_supportive"]),
      copy: "MACD positive and RSI above 50.",
    },
    {
      label: "Volume",
      passed: Boolean(indicators["basic_liquidity_filter_pass"]) && Boolean(indicators["volume_above_previous_day"]),
      copy: "Liquidity passes and participation is expanding.",
    },
    {
      label: "Structure",
      passed: Boolean(indicators["structure_supportive"]),
      copy: "Recent higher-high / higher-low structure is supportive.",
    },
    {
      label: "Risk-reward",
      passed: (row.riskReward ?? 0) >= 2,
      copy: "Prefer at least 1:2 before taking the trade.",
    },
  ];
}

function TradePlanTab({
  plan,
  row,
  riskAmount,
  onRiskAmountChange,
  symbolDetail,
  currentPrice,
}: {
  plan?: TradePlan;
  row: CandidateRow;
  riskAmount: number;
  onRiskAmountChange: (value: number) => void;
  symbolDetail?: SymbolDetail | null;
  currentPrice?: number | null;
}) {
  if (!plan) {
    return (
      <section className="subpanel">
        <h3>No detailed trade plan</h3>
        <p>This name did not return an execution-ready trade plan. That usually means it was rejected before the deeper recommendation stage.</p>
      </section>
    );
  }

  // Trade plans may omit levels (null) — never call .toFixed on null/undefined.
  const entryLow = numOrNull(plan.entry_low);
  const entryHigh = numOrNull(plan.entry_high);
  const stopLoss = numOrNull(plan.stop_loss);
  const target1 = numOrNull(plan.target_1);
  const target2 = numOrNull(plan.target_2);
  const rr = numOrNull(plan.risk_reward_ratio);
  const priceRef =
    entryMidFrom(entryLow, entryHigh) ??
    numOrNull(currentPrice) ??
    numOrNull(row.entryLow) ??
    numOrNull(row.entryHigh);
  const entryMid = entryMidFrom(entryLow, entryHigh) ?? priceRef ?? 0;
  const riskPerShare =
    stopLoss != null && entryMid > 0 ? Math.abs(entryMid - stopLoss) : 0;
  const rewardPerShare =
    target1 != null && entryMid > 0 ? Math.abs(target1 - entryMid) : 0;
  const positionSize = riskPerShare > 0 ? Math.floor(riskAmount / riskPerShare) : 0;
  const invalidation =
    row.analysisItem?.recommendation?.reasoning?.invalidation_signals;
  const invalidationItems =
    Array.isArray(invalidation) && invalidation.length
      ? invalidation
      : ["Exit the idea if price loses structure and closes below the planned stop."];

  return (
    <div className="detail-stack">
      <section className="tradeplan-hero">
        <div>
          <p className="section-label">Execution plan</p>
          <h3>{plan.setup_type || "Swing plan"}</h3>
          <p className="muted-copy">{plan.notes || "Execution levels (partial levels shown as —)."}</p>
        </div>
        <div className="tradeplan-grid">
          <MetricTile
            label="Entry zone"
            value={
              entryLow != null || entryHigh != null
                ? `${fmtPrice(entryLow)} - ${fmtPrice(entryHigh)}`
                : priceRef != null
                  ? `≈ ${fmtPrice(priceRef)}`
                  : "—"
            }
            help="Preferred swing entry area."
          />
          <MetricTile label="Stop loss" value={fmtPrice(stopLoss)} help="If price breaks this, the setup is invalidated." />
          <MetricTile label="Target 1" value={fmtPrice(target1)} help="First realistic swing objective." />
          <MetricTile label="Target 2" value={fmtPrice(target2)} help="Second objective if momentum continues." />
        </div>
      </section>
      <section className="subpanel">
        <h3>Exit Strategy</h3>
        <div className="muted-copy" style={{ marginTop: 8 }}>
          {target1 != null && target2 != null
            ? `Exit 50% position at Target 1 (₹${fmtPrice(target1)}). Move stop loss to entry price. Let remaining 50% ride to Target 2 (₹${fmtPrice(target2)}).`
            : target1 != null
              ? `Consider taking profits near Target 1 (₹${fmtPrice(target1)}) and manage the remainder with structure / trailing stop.`
              : "Exit levels incomplete for this plan — use stop and structure rules, or wait for a fuller recommendation."}
        </div>

        <div style={{ marginTop: 12 }}>
          <div className="score-breakdown">
            <MetricTile
              label="Trailing Stop"
              value={
                symbolDetail?.technical_extras?.atr != null &&
                Number.isFinite(Number(symbolDetail.technical_extras.atr))
                  ? `₹${Number(symbolDetail.technical_extras.atr).toFixed(2)} below current price (1× ATR)`
                  : "--"
              }
              help="Suggested trailing stop distance using ATR"
            />
            <MetricTile
              label="Suggested Holding"
              value={plan.suggested_holding_days ?? (plan as { holding_horizon?: string }).holding_horizon ?? plan.timeframe ?? "--"}
              help="Suggested holding period for the trade"
            />
          </div>
        </div>
      </section>

      <section className="detail-grid">
        <div className="subpanel">
          <h3>Trade mechanics</h3>
          <div className="score-breakdown">
            <MetricTile label="Bias" value={plan.bias || "—"} help="Direction of the setup." />
            <MetricTile
              label="Risk / share"
              value={riskPerShare > 0 ? riskPerShare.toFixed(2) : "—"}
              help="Distance from entry midpoint to stop loss."
            />
            <MetricTile
              label="Reward / share"
              value={rewardPerShare > 0 ? rewardPerShare.toFixed(2) : "—"}
              help="Distance from entry midpoint to first target."
            />
            <MetricTile
              label="Risk / Reward"
              value={rr != null ? rr.toFixed(2) : "—"}
              help="Higher is better if the setup quality also holds."
            />
          </div>
          <ReasonList title="Invalidation" items={invalidationItems} />
        </div>

        <div className="subpanel">
          <h3>Position sizing</h3>
          <label className="filter-field">
            <span>Risk amount</span>
            <input type="number" min={100} step={100} value={riskAmount} onChange={(event) => onRiskAmountChange(Number(event.target.value))} />
          </label>
          <div className="score-breakdown">
            <MetricTile label="Suggested quantity" value={positionSize > 0 ? positionSize : "—"} help="Estimated quantity using risk amount / risk per share." />
            <MetricTile label="Holding horizon" value={plan.timeframe || "—"} help="Expected swing holding window." />
            <MetricTile label="Strategy" value={plan.strategy_name || "—"} help="Backtest strategy used for context." />
            <MetricTile label="Signal" value={row.signal} help="Recommendation outcome for this setup." />
          </div>
        </div>
      </section>
    </div>
  );
}

function NewsTab({ analysis, row, symbolDetail }: { analysis?: StockAnalysisResult; row: CandidateRow; symbolDetail?: SymbolDetail | null }) {
  const articles = analysis?.news_articles?.slice(0, 3) ?? [];
  const socialSentiment = symbolDetail?.news_extras?.social_sentiment ?? (analysis?.social_sentiment_score ?? null);

  const corporate = (symbolDetail?.news_extras?.corporate_events as Record<string, any> | undefined) ?? (analysis?.corporate_events as Record<string, any> | undefined) ?? {};

  const earnings = corporate?.earnings_date ?? corporate?.earnings ?? corporate?.next_earnings ?? null;
  const exDividend = corporate?.ex_dividend_date ?? corporate?.ex_dividend ?? corporate?.exdiv ?? null;
  const agm = corporate?.agm_date ?? corporate?.agm ?? null;

  function sentimentColor(score?: number | null) {
    if (score == null) return "var(--text-muted)";
    if (score > 0) return "var(--positive)";
    if (score < 0) return "var(--negative)";
    return "var(--text-muted)";
  }

  return (
    <div className="detail-stack">
      <section className="subpanel">
        <div className="subpanel-header">
          <h3>News sentiment</h3>
          <div className="meta-inline">
            <span className={`status-tag ${analysis?.news_sentiment_label === "positive" ? "is-positive" : analysis?.news_sentiment_label === "negative" ? "is-risk" : "is-neutral"}`}>
              {analysis?.news_sentiment_label ?? row.newsSentiment}
            </span>
            <span className="helper-chip">
              {analysis && typeof analysis.news_sentiment_score === "number"
                ? analysis.news_sentiment_score.toFixed(2)
                : "--"}
            </span>
            <span className="helper-chip" style={{ marginLeft: 8, background: sentimentColor(socialSentiment), color: "var(--text)" }}>
              Sentiment Score: {socialSentiment == null ? "--" : String(socialSentiment)}
            </span>
          </div>
        </div>
        <p className="muted-copy">{analysis?.news_summary ?? "No detailed news summary was available for this stock."}</p>
      </section>

      <section className="news-list">
        {articles.length ? (
          articles.map((article) => (
            <article key={article.url} className="news-item">
              <div className="news-item-meta">
                <span>{article.source}</span>
                <time>{new Date(article.published_at).toLocaleString()}</time>
              </div>
              <h4>{article.title}</h4>
              <p>{article.description}</p>
              <a href={article.url} target="_blank" rel="noreferrer">
                Open source
              </a>
            </article>
          ))
        ) : (
          <div className="subpanel">
            <p>
              No articles found from primary source. Try searching: {row.symbol} NSE news —{' '}
              <a href={`https://www.google.com/search?q=${encodeURIComponent(row.symbol + ' NSE news')}`} target="_blank" rel="noreferrer noopener">
                Google search
              </a>
            </p>
            <p className="muted-copy" style={{ marginTop: 8 }}>
              Primary news source returned no results. Use the search link above.
            </p>
          </div>
        )}
      </section>

      <section className="subpanel">
        <h3>Corporate Events</h3>
        {earnings || exDividend || agm ? (
          <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
            <div className="corporate-row"><strong>Earnings Date:</strong> <span className="muted-copy">{earnings ?? 'Not Available'}</span></div>
            <div className="corporate-row"><strong>Ex-Dividend Date:</strong> <span className="muted-copy">{exDividend ?? 'Not Available'}</span></div>
            <div className="corporate-row"><strong>AGM Date:</strong> <span className="muted-copy">{agm ?? 'Not Available'}</span></div>
          </div>
        ) : (
          <p className="muted-copy" style={{ marginTop: 8 }}>
            Corporate events data will be available when a data provider is connected.
          </p>
        )}
      </section>
    </div>
  );
}

function yearsAgo(range: BacktestRange): Date {
  const d = new Date();
  if (range === "1Y") d.setFullYear(d.getFullYear() - 1);
  else if (range === "3Y") d.setFullYear(d.getFullYear() - 3);
  else if (range === "5Y") d.setFullYear(d.getFullYear() - 5);
  else d.setFullYear(1970);
  return d;
}

function asTrade(raw: any): DashboardTrade {
  const pnl = raw?.pnl_percent ?? (raw?.pnl_pct != null ? Number(raw.pnl_pct) * (Math.abs(Number(raw.pnl_pct)) <= 2 ? 100 : 1) : null);
  return {
    entry_date: raw?.entry_date ?? null,
    exit_date: raw?.exit_date ?? null,
    type: raw?.type ?? "LONG",
    entry_price: raw?.entry_price ?? null,
    exit_price: raw?.exit_price ?? null,
    pnl_percent: pnl,
    holding_days: raw?.holding_days ?? null,
    reason: raw?.reason ?? null,
    open: Boolean(raw?.open),
  };
}

function normalizeEngineBacktest(src: any, range: BacktestRange): BacktestDashboardModel | null {
  if (!src) return null;
  const cutoff = yearsAgo(range);
  const rawEq = (src.equity_curve ?? []) as any[];
  const equity = rawEq
    .map((p) => {
      const label = String(p.label ?? p.date ?? "");
      return { date: label, label, equity: Number(p.equity ?? p.value ?? 0) };
    })
    .filter((p) => p.label && !Number.isNaN(p.equity) && new Date(p.label) >= cutoff);
  const tradesAll = ((src.trades ?? []) as any[]).map(asTrade);
  const trades = tradesAll.filter((t) => {
    const d = t.exit_date || t.entry_date;
    return !d || new Date(d) >= cutoff;
  });
  const monthly = ((src.monthly_returns ?? []) as any[])
    .filter((m) => String(m.month || "") >= cutoff.toISOString().slice(0, 7))
    .map((m) => ({ month: String(m.month), return: m.return == null ? null : Number(m.return) }));
  const winners = trades.filter((t) => (t.pnl_percent ?? 0) > 0).sort((a, b) => (b.pnl_percent ?? 0) - (a.pnl_percent ?? 0));
  const losers = trades.filter((t) => (t.pnl_percent ?? 0) < 0).sort((a, b) => (a.pnl_percent ?? 0) - (b.pnl_percent ?? 0));
  let peak = -Infinity;
  const drawdown_curve = equity.map((p) => {
    peak = Math.max(peak, p.equity);
    const dd = peak ? ((p.equity - peak) / Math.abs(peak)) * 100 : 0;
    return { date: p.date, label: p.label, drawdown: Number(dd.toFixed(4)) };
  });
  const initial = equity[0]?.equity ?? src.initial_capital ?? null;
  const ending = equity[equity.length - 1]?.equity ?? src.ending_capital ?? null;
  return {
    window: range,
    period_start: equity[0]?.date ?? null,
    period_end: equity[equity.length - 1]?.date ?? null,
    total_return: src.total_return ?? null,
    cagr: src.cagr ?? null,
    max_drawdown: src.max_drawdown ?? null,
    win_rate: src.win_rate ?? null,
    trade_count: src.trade_count ?? trades.length,
    sharpe_ratio: src.sharpe_ratio ?? null,
    profit_factor: src.profit_factor ?? null,
    initial_capital: initial,
    ending_capital: ending,
    avg_trade_return: trades.length ? trades.reduce((s, t) => s + (t.pnl_percent ?? 0), 0) / trades.length : null,
    max_consecutive_losses: null,
    verdict: src.verdict ?? null,
    equity_curve: equity,
    drawdown_curve,
    monthly_returns: monthly,
    trades,
    best_trade: src.best_trade ? asTrade(src.best_trade) : winners[0] ?? null,
    worst_trade: src.worst_trade ? asTrade(src.worst_trade) : losers[0] ?? null,
    top_winning: winners.slice(0, 5),
    top_losing: losers.slice(0, 5),
    never_selected_in_window: trades.length === 0,
  };
}

function decToPct(value: unknown): number | null {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
  return Number(value) * 100;
}

function hydrateLtmPieces(row: CandidateRow | undefined, range: BacktestRange, api?: Record<string, any> | null): BacktestDashboardModel | null {
  if (api?.dashboard && (api.dashboard.equity_curve?.length || api.dashboard.trade_count != null)) {
    return api.dashboard as BacktestDashboardModel;
  }
  const ltm = row?.ltm;
  const bt = (api?.backtest || ltm?.backtest_1y || {}) as Record<string, any>;
  const curveRaw = (api?.equity_curve || ltm?.equity_curve || []) as any[];
  const metrics = (api?.book_metrics || ltm?.book_metrics || {}) as Record<string, any>;
  const want = String(row?.symbol || "").toUpperCase();
  const tradesSrc = ((api?.dashboard?.trades || bt.trades || ltm?.blotter || []) as any[]).filter((t) => {
    const s = String(t?.symbol || "").toUpperCase();
    return !s || !want || s === want;
  });
  const hasCurve = Array.isArray(curveRaw) && curveRaw.length > 0;
  const hasTrades = Array.isArray(tradesSrc) && tradesSrc.length > 0;
  const hasMetrics = metrics && (metrics.total_return != null || metrics.cagr != null);
  if (!hasCurve && !hasTrades && !hasMetrics) return null;

  const cutoff = yearsAgo(range);
  const equity = curveRaw
    .map((p) => ({
      date: String(p.date ?? p.label ?? ""),
      label: String(p.date ?? p.label ?? ""),
      equity: Number(p.equity ?? p.value ?? 0),
    }))
    .filter((p) => p.date && !Number.isNaN(p.equity) && new Date(p.date) >= cutoff);
  const trades = (hasTrades ? tradesSrc : []).map(asTrade).filter((t) => {
    const d = t.exit_date || t.entry_date;
    return !d || new Date(d) >= cutoff;
  });
  const winners = trades.filter((t) => (t.pnl_percent ?? 0) > 0).sort((a, b) => (b.pnl_percent ?? 0) - (a.pnl_percent ?? 0));
  const losers = trades.filter((t) => (t.pnl_percent ?? 0) < 0).sort((a, b) => (a.pnl_percent ?? 0) - (b.pnl_percent ?? 0));
  let peak = -Infinity;
  const drawdown_curve = equity.map((p) => {
    peak = Math.max(peak, p.equity);
    const dd = peak ? ((p.equity - peak) / Math.abs(peak)) * 100 : 0;
    return { date: p.date, label: p.label, drawdown: Number(dd.toFixed(4)) };
  });
  const monthlyMap: Record<string, number[]> = {};
  for (const p of equity) {
    const m = p.date.slice(0, 7);
    if (m.length < 7) continue;
    (monthlyMap[m] ||= []).push(p.equity);
  }
  const months = Object.keys(monthlyMap).sort();
  let prev = equity[0]?.equity;
  const monthly_returns = months.map((month) => {
    const end = monthlyMap[month][monthlyMap[month].length - 1];
    const ret = prev ? end / prev - 1 : null;
    prev = end;
    return { month, return: ret };
  });
  const benchRaw = (api?.index_curve || ltm?.index_curve || []) as any[];
  return {
    window: range,
    period_start: equity[0]?.date ?? null,
    period_end: equity[equity.length - 1]?.date ?? null,
    total_return: decToPct(metrics.total_return) ?? decToPct(bt.net_return),
    cagr: decToPct(metrics.cagr),
    max_drawdown: decToPct(metrics.max_dd ?? metrics.max_drawdown ?? bt.max_drawdown),
    win_rate: bt.win_rate == null ? null : Number(bt.win_rate) <= 1.0001 ? Number(bt.win_rate) * 100 : Number(bt.win_rate),
    trade_count: bt.trade_count ?? trades.length,
    sharpe_ratio: metrics.sharpe_ratio ?? null,
    profit_factor: bt.profit_factor ?? null,
    profit_factor_infinite: bt.profit_factor == null && (bt.win_rate ?? 0) > 0,
    initial_capital: Number(metrics.initial_capital ?? ltm?.initial_capital ?? equity[0]?.equity ?? null),
    ending_capital: Number(metrics.ending_equity ?? equity[equity.length - 1]?.equity ?? null),
    avg_trade_return: trades.length ? trades.reduce((s, t) => s + (t.pnl_percent ?? 0), 0) / trades.length : decToPct(bt.net_return),
    verdict: null,
    equity_curve: equity,
    drawdown_curve,
    benchmark_curve: benchRaw.map((p) => ({ date: String(p.date ?? p.label ?? ""), close: Number(p.close ?? p.equity) })),
    monthly_returns,
    trades,
    best_trade: winners[0] ?? null,
    worst_trade: losers[0] ?? null,
    top_winning: winners.slice(0, 5),
    top_losing: losers.slice(0, 5),
    never_selected_in_window: trades.length === 0 && !hasCurve,
  };
}

function BacktestTab({
  backtest,
  backtestDetail,
  row,
}: {
  backtest?: BacktestResult;
  backtestDetail?: any | null;
  row?: CandidateRow;
}) {
  const [range, setRange] = useState<BacktestRange>("3Y");
  const [ltmDash, setLtmDash] = useState<BacktestDashboardModel | null>(null);
  const [ltmLoading, setLtmLoading] = useState(false);
  const [ltmError, setLtmError] = useState<string | null>(null);
  const [niftyData, setNiftyData] = useState<{label: string, close: number}[]>([]);

  useEffect(() => {
    if (!row?.ltm || !row.symbol) {
      setLtmDash(null);
      setLtmError(null);
      return;
    }
    let cancelled = false;
    setLtmLoading(true);
    setLtmError(null);
    fetchLtmSymbolDetail(row.symbol, range)
      .then((res) => {
        if (cancelled) return;
        const dash = hydrateLtmPieces(row, range, res);
        setLtmDash(dash);
        if (!dash) setLtmError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const fallback = hydrateLtmPieces(row, range, null);
        setLtmDash(fallback);
        if (!fallback) setLtmError(err instanceof Error ? err.message : "Unable to load backtest data");
      })
      .finally(() => {
        if (!cancelled) setLtmLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [row?.ltm, row?.symbol, range]);

  useEffect(() => {
    if (row?.ltm) return;
    fetchSymbolDetail("NIFTY 500")
      .then((res: any) => {
        if (res?.ohlcv) {
          setNiftyData(
            res.ohlcv.map((c: any) => ({
              label: new Date(c.timestamp).toISOString().split("T")[0],
              close: c.close,
            })),
          );
        }
      })
      .catch(() => {});
  }, [row?.ltm]);

  const engineModel = useMemo(() => {
    if (row?.ltm) return ltmDash ?? hydrateLtmPieces(row, range, null);
    const src = backtestDetail ?? backtest ?? null;
    const model = normalizeEngineBacktest(src, range);
    if (model && niftyData.length) {
      model.benchmark_curve = niftyData.map((n) => ({ date: n.label, label: n.label, close: n.close }));
    }
    return model;
  }, [row?.ltm, row, ltmDash, backtest, backtestDetail, range, niftyData]);

  return (
    <BacktestAnalyticsDashboard
      model={engineModel}
      range={range}
      onRangeChange={setRange}
      loading={Boolean(row?.ltm && ltmLoading)}
      loadError={row?.ltm ? ltmError : null}
    />
  );
}


function ChartTab({ analysis, plan }: { analysis?: StockAnalysisResult; plan?: TradePlan }) {
  if (!analysis?.ohlcv?.length) {
    return (
      <section className="subpanel">
        <h3>Chart unavailable</h3>
        <p>No candle series was returned for this stock.</p>
      </section>
    );
  }

  const allCandles = analysis.ohlcv;
  const [timeframe, setTimeframe] = useState<"1D" | "1W" | "1M">("1D");
  const [visibleCount, setVisibleCount] = useState<number>(60);

  // adjust default visible counts per timeframe
  useEffect(() => {
    if (timeframe === "1D") setVisibleCount(60);
    else if (timeframe === "1W") setVisibleCount(26);
    else setVisibleCount(12);
  }, [timeframe]);

  function getWeekKey(d: Date) {
    const tmp = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    tmp.setUTCDate(tmp.getUTCDate() + 4 - (tmp.getUTCDay() || 7));
    const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((tmp.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
    return `${tmp.getUTCFullYear()}-W${weekNo}`;
  }

  function resampleCandles(candles: typeof allCandles, tf: string) {
    if (tf === "1D") return candles;
    const groups: Record<string, typeof candles> = {};
    for (const c of candles) {
      const d = new Date(c.timestamp);
      const key = tf === "1W" ? getWeekKey(d) : `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
      groups[key] = groups[key] || [];
      groups[key].push(c);
    }
    const out: typeof candles = [];
    for (const k of Object.keys(groups)) {
      const arr = groups[k];
      const open = arr[0].open;
      const close = arr[arr.length - 1].close;
      const high = Math.max(...arr.map((x) => x.high));
      const low = Math.min(...arr.map((x) => x.low));
      const volume = arr.reduce((s, x) => s + (x.volume ?? 0), 0);
      const timestamp = arr[arr.length - 1].timestamp;
      out.push({ timestamp, open, high, low, close, volume });
    }
    // ensure chronological order
    out.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    return out;
  }

  const resampled = useMemo(() => resampleCandles(allCandles, timeframe), [allCandles, timeframe]);
  const visible = resampled.slice(-visibleCount);

  function zoomIn() {
    setVisibleCount((v) => Math.max(10, Math.floor(v / 2)));
  }
  function zoomOut() {
    setVisibleCount((v) => Math.min(resampled.length, v * 2));
  }

  return (
    <div className="detail-stack">
      <section className="subpanel">
        <div className="chart-toolbar">
          <div className="chart-toolbar__group">
            <button type="button" className={`button ${timeframe === "1D" ? "is-active" : ""}`} onClick={() => setTimeframe("1D")}>1D</button>
            <button type="button" className={`button ${timeframe === "1W" ? "is-active" : ""}`} onClick={() => setTimeframe("1W")}>1W</button>
            <button type="button" className={`button ${timeframe === "1M" ? "is-active" : ""}`} onClick={() => setTimeframe("1M")}>1M</button>
          </div>
          <div className="chart-toolbar__group">
            <button type="button" className="button" onClick={zoomIn}>−</button>
            <span className="chart-toolbar__bars">{visible.length} bars</span>
            <button type="button" className="button" onClick={zoomOut}>+</button>
          </div>
        </div>
        <h3 style={{ marginTop: 12 }}>Price structure</h3>
        <p className="helper-text">Candles, EMA 20, Supertrend flips, zoom and timeframe controls are available.</p>
      </section>
      <CandlestickChart candles={visible} plan={plan} />
    </div>
  );
}

function ReasonList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h4>{title}</h4>
      <ul className="reason-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function MetricTile({
  label,
  value,
  help,
}: {
  label: string;
  value: string | number;
  help: string;
}) {
  return (
    <div className="metric-tile">
      <span>
        <abbr title={help}>{label}</abbr>
      </span>
      <strong>{value}</strong>
    </div>
  );
}

function CandlestickChart({ candles, plan }: { candles: OHLCVPoint[]; plan?: TradePlan }) {
  const width = 920;
  const height = 360;
  const volumeHeight = 70;
  const chartTop = 20;
  const chartHeight = height - volumeHeight - 40;
  const allPrices = candles.flatMap((candle) => [candle.high, candle.low]);
  const minPrice = Math.min(...allPrices) * 0.995;
  const maxPrice = Math.max(...allPrices) * 1.005;
  const volumeMax = Math.max(...candles.map((candle) => candle.volume), 1);
  const candleWidth = Math.max(6, width / (candles.length * 1.8));

  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const ema20 = calculateEmaSeries(candles, 20);
  const supertrend = calculateApproxSupertrend(candles, 10, 3);

  const xFor = (index: number) => 30 + (index * (width - 60)) / Math.max(candles.length - 1, 1);
  const yFor = (price: number) => chartTop + ((maxPrice - price) / (maxPrice - minPrice)) * chartHeight;

  const emaPath = buildPath(ema20, xFor, yFor);
  const supertrendPath = buildPath(supertrend, xFor, yFor);
  // detect supertrend flips (direction changes)
  const directions = candles.map((c, i) => (Number(c.close ?? 0) >= Number(supertrend[i] ?? 0) ? "bull" : "bear"));
  const flips: { index: number; type: "bullish" | "bearish" }[] = [];
  for (let i = 1; i < directions.length; i++) {
    if (directions[i] !== directions[i - 1]) {
      flips.push({ index: i, type: directions[i] === "bull" ? "bullish" : "bearish" });
    }
  }
  const tradeLevels = [
    {
      label: "Entry",
      value: plan
        ? entryMidFrom(numOrNull(plan.entry_low), numOrNull(plan.entry_high))
        : null,
      className: "chart-line-entry",
    },
    { label: "Stop", value: numOrNull(plan?.stop_loss), className: "chart-line-stop" },
    { label: "T1", value: numOrNull(plan?.target_1), className: "chart-line-target" },
    { label: "T2", value: numOrNull(plan?.target_2), className: "chart-line-target" },
  ].filter(
    (item): item is { label: string; value: number; className: string } =>
      item.value != null && Number.isFinite(item.value),
  );

  return (
    <div className="subpanel chart-shell" style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${width} ${height}`} className="price-chart" role="img" aria-label="Swing candlestick chart">
        <rect x="0" y="0" width={width} height={height} fill="transparent" />

        {tradeLevels.map((level) => {
          const y = yFor(level.value);
          return (
            <g key={`${level.label}-${level.value}`}>
              <line x1={20} x2={width - 20} y1={y} y2={y} className={level.className} />
              <text x={width - 16} y={y - 4} className="chart-label">
                {level.label} {level.value.toFixed(2)}
              </text>
            </g>
          );
        })}

        <path d={emaPath} className="chart-line-ema" />
        <path d={supertrendPath} className="chart-line-supertrend" />

        <g className="candles">
          {candles.map((candle, index) => {
            const x = xFor(index);
            const openY = yFor(candle.open);
            const closeY = yFor(candle.close);
            const highY = yFor(candle.high);
            const lowY = yFor(candle.low);
            const isUp = candle.close >= candle.open;
            const bodyTop = Math.min(openY, closeY);
            const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
            const volumeBarHeight = (candle.volume / volumeMax) * volumeHeight;

            return (
              <g key={`${candle.timestamp}-${index}`}>
                <line x1={x} x2={x} y1={highY} y2={lowY} className={isUp ? "candle-wick-up" : "candle-wick-down"} />
                <rect
                  x={x - candleWidth / 2}
                  y={bodyTop}
                  width={candleWidth}
                  height={bodyHeight}
                  className={isUp ? "candle-body-up" : "candle-body-down"}
                  rx="1"
                />
                <rect
                  x={x - candleWidth / 2}
                  y={height - volumeBarHeight - 16}
                  width={candleWidth}
                  height={volumeBarHeight}
                  className="volume-bar"
                  rx="1"
                />
              </g>
            );
          })}
        </g>

        {/* supertrend flip markers */}
        {flips.map((f) => {
          const idx = f.index;
          const cx = xFor(idx);
          const c = candles[idx];
          if (!c) return null;
          if (f.type === "bullish") {
            const y = yFor(c.low) + 12;
            return <polygon key={`flip-${idx}`} points={`${cx},${y} ${cx - 6},${y + 10} ${cx + 6},${y + 10}`} fill="#38b26d" />;
          }
          const y = yFor(c.high) - 12;
          return <polygon key={`flip-${idx}`} points={`${cx},${y} ${cx - 6},${y - 10} ${cx + 6},${y - 10}`} fill="#c05c54" />;
        })}

        {/* interactive overlay for crosshair */}
        <rect
          x={20}
          y={chartTop}
          width={width - 40}
          height={chartHeight}
          fill="transparent"
          onMouseMove={(e) => {
            try {
              const rect = (e.target as SVGRectElement).ownerSVGElement!.getBoundingClientRect();
              const x = e.clientX - rect.left;
              const step = Math.max(1, (width - 60) / Math.max(candles.length - 1, 1));
              let idx = Math.round((x - 30) / step);
              idx = Math.max(0, Math.min(candles.length - 1, idx));
              setHoverIndex(idx);
            } catch (_) {
            }
          }}
          onMouseLeave={() => setHoverIndex(null)}
        />

        {/* crosshair lines */}
        {hoverIndex != null && hoverIndex >= 0 && hoverIndex < candles.length ? (
          (() => {
            const cx = xFor(hoverIndex);
            const c = candles[hoverIndex];
            const cy = yFor(c.close);
            return (
              <g key={`hover-${hoverIndex}`}>
                <line x1={cx} x2={cx} y1={chartTop} y2={height - 16} stroke="#9aa7b8" strokeDasharray="3 3" strokeWidth={1} />
                <line x1={20} x2={width - 20} y1={cy} y2={cy} stroke="#9aa7b8" strokeDasharray="3 3" strokeWidth={1} />
              </g>
            );
          })()
        ) : null}
      </svg>

      {/* tooltip (HTML overlay) */}
      {hoverIndex != null && hoverIndex >= 0 && hoverIndex < candles.length ? (
        (() => {
          const c = candles[hoverIndex];
          const cx = xFor(hoverIndex);
          const tooltipLeft = Math.max(8, Math.min(width - 220, cx + 8));
          return (
            <div style={{ position: "absolute", left: tooltipLeft, top: 8, background: "var(--surface)", color: "var(--text)", padding: 8, borderRadius: 6, boxShadow: "var(--shadow)" }}>
              <div style={{ fontWeight: 600 }}>{new Date(c.timestamp).toLocaleString()}</div>
              <div>O: {c.open.toFixed(2)} H: {c.high.toFixed(2)} L: {c.low.toFixed(2)} C: {c.close.toFixed(2)}</div>
              <div className="muted-copy">Vol: {new Intl.NumberFormat().format(c.volume)}</div>
            </div>
          );
        })()
      ) : null}

      <div className="chart-legend">
        <span><i className="legend-swatch legend-ema" /> EMA 20</span>
        <span><i className="legend-swatch legend-supertrend" /> Supertrend</span>
        <span><i className="legend-swatch legend-entry" /> Trade levels</span>
      </div>
    </div>
  );
}

function calculateEmaSeries(candles: OHLCVPoint[], period: number) {
  const multiplier = 2 / (period + 1);
  let previous = candles[0]?.close ?? 0;
  return candles.map((candle, index) => {
    if (index === 0) {
      previous = candle.close;
      return previous;
    }
    previous = candle.close * multiplier + previous * (1 - multiplier);
    return previous;
  });
}

function calculateApproxSupertrend(candles: OHLCVPoint[], period: number, multiplier: number) {
  const trs = candles.map((candle, index) => {
    if (index === 0) {
      return candle.high - candle.low;
    }
    const previousClose = candles[index - 1].close;
    return Math.max(
      candle.high - candle.low,
      Math.abs(candle.high - previousClose),
      Math.abs(candle.low - previousClose),
    );
  });

  let atr = trs[0] ?? 0;
  return candles.map((candle, index) => {
    atr = index === 0 ? trs[0] ?? 0 : ((atr * (period - 1)) + trs[index]) / period;
    const mid = (candle.high + candle.low) / 2;
    return mid - (multiplier * atr);
  });
}

function buildPath(series: number[], xFor: (index: number) => number, yFor: (price: number) => number) {
  return series
    .map((value, index) => `${index === 0 ? "M" : "L"} ${xFor(index)} ${yFor(value)}`)
    .join(" ");
}

function formatValue(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toFixed(2);
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value ?? "--");
}

/** Safe numeric parse — never throws on null/undefined/NaN. */
function numOrNull(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function fmtPrice(value: number | null | undefined): string {
  const n = numOrNull(value);
  return n != null ? n.toFixed(2) : "—";
}

function entryMidFrom(low: number | null, high: number | null): number | null {
  if (low != null && high != null) return (low + high) / 2;
  if (high != null) return high;
  if (low != null) return low;
  return null;
}

function formatDate(input?: string | null) {
  if (!input) return "-";
  try {
    const d = new Date(input);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  } catch {
    return String(input);
  }
}

function RangeBar({ low, high, current }: { low: number; high: number; current: number }) {
  if (low == null || high == null || high <= low) return <div className="muted-copy">Range data unavailable</div>;
  const pct = Math.max(0, Math.min(100, ((current - low) / (high - low)) * 100));
  return (
    <div className="w-full h-3 rounded-md relative" style={{ background: "var(--surface-2)" }}>
      <div
        className="absolute left-0 top-0 h-full rounded-md"
        style={{ width: `${pct}%`, background: "linear-gradient(90deg, var(--negative) 0%, var(--positive) 100%)" }}
      />
      <div className="absolute top-0" style={{ left: `${pct}%`, transform: "translateX(-50%) translateY(-6px)" }}>
        <div style={{ width: 10, height: 10, borderRadius: 8, background: "#ffffff", border: "2px solid var(--surface)" }} />
      </div>
      <div className="flex justify-between mt-2 text-xs muted-copy" style={{ marginTop: 8 }}>
        <span>{low.toFixed(2)}</span>
        <span>{high.toFixed(2)}</span>
      </div>
    </div>
  );
}

function formatMarketCap(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "-";
  const abs = Math.abs(value);
  if (abs >= 1e9) {
    return `₹${(value / 1e9).toFixed(2)}B`;
  }
  // show in crores
  return `₹${(value / 1e7).toFixed(2)}Cr`;
}

function buildRankContext(row: CandidateRow) {
  if (row.rank === null) {
    return "This name is outside the ranked BUY/WATCH list, so it should be treated as lower priority until the next scan improves.";
  }
  if (row.signal === "BUY") {
    return `This stock is ranked #${row.rank} because its technical quality, trade plan, and supporting evidence place it above the rest of the shortlist.`;
  }
  if (row.signal === "WATCH") {
    return `This stock still has rank #${row.rank}, but the recommendation layer prefers waiting for cleaner confirmation before promoting it to BUY.`;
  }
  return `This stock was shortlisted but fell below the final quality bar, so it remains lower in the decision stack despite passing earlier scan stages.`;
}
