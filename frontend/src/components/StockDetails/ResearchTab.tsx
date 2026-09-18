import React from "react";
import type { StrategyResultRow, StrategyRunStatus } from "../../api_strategy_tester";
import type { SymbolDetail } from "../../types";
import { formatINRVal, formatPctVal, formatVolVal } from "./StockHeader";
import type { FilterEvalItem } from "./types";
import { ResearchDashboard } from "../ResearchDashboard";

interface ResearchTabProps {
  symbol: string;
  companyName: string;
  exchange?: string;
  stock: StrategyResultRow | null;
  runStatus: StrategyRunStatus | null;
  symbolDetail?: SymbolDetail | null;
  filterResults: FilterEvalItem[];
  strategyName: string;
  resolvedRunId: string;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export const ResearchTab: React.FC<ResearchTabProps> = ({
  symbol,
  companyName,
  exchange = "NSE",
  stock,
  runStatus,
  symbolDetail,
  filterResults,
  strategyName,
  resolvedRunId,
  isLoading = false,
  error = null,
  onRetry,
}) => {
  if (isLoading && !stock && !symbolDetail) {
    return (
      <div className="st-card st-card-full st-tab-loading" data-testid="research-loading">
        Loading research...
      </div>
    );
  }

  if (error && !stock && !symbolDetail) {
    return (
      <div className="st-card st-card-full st-tab-error" data-testid="research-error">
        <p>{error || "Unable to load research data."}</p>
        {onRetry && (
          <button type="button" className="st-btn-primary" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    );
  }

  const signal = (stock?.signal || "WATCH").toUpperCase();
  const entryPrice = stock?.entry_price ?? null;
  const exitPrice = stock?.exit_price ?? null;
  const returnPct = stock?.return_pct ?? null;

  const rsiVal =
    stock?.rsi ??
    stock?.indicators?.rsi ??
    stock?.indicators?.rsi_14 ??
    (symbolDetail?.technical_extras as any)?.rsi ??
    null;

  const sma20Val = stock?.sma_20 ?? stock?.indicators?.sma_20 ?? null;
  const sma50Val = stock?.sma_50 ?? stock?.indicators?.sma_50 ?? null;
  const sma200Val = stock?.sma_200 ?? stock?.indicators?.sma_200 ?? null;
  const volumeVal = stock?.volume ?? stock?.indicators?.volume ?? null;
  const avgVolumeVal =
    stock?.avg_volume ??
    stock?.indicators?.avg_volume_20 ??
    stock?.indicators?.avg_volume ??
    null;

  const atrVal =
    stock?.indicators?.atr_14 ??
    stock?.indicators?.atr ??
    symbolDetail?.technical_extras?.atr ??
    null;

  const sector = symbolDetail?.sector || "Data unavailable";
  const industry = symbolDetail?.industry || "Data unavailable";
  const marketCap =
    symbolDetail?.market_cap != null ? formatINRVal(symbolDetail.market_cap) : "Data unavailable";
  const description = symbolDetail?.company_description || "Data unavailable";
  const year52High =
    symbolDetail?.year52_high != null ? formatINRVal(symbolDetail.year52_high) : "Data unavailable";
  const year52Low =
    symbolDetail?.year52_low != null ? formatINRVal(symbolDetail.year52_low) : "Data unavailable";

  const hasDeepResearch = Boolean(symbolDetail?.research && !symbolDetail.research.error);

  return (
    <div className="st-stock-detail-stack" style={{ display: "flex", flexDirection: "column", gap: 14 }} data-testid="card-detail-research">
      {/* 1. Consolidated Research Grid */}
      <section className="st-stock-overview-grid" aria-label="Stock research overview">
        {/* Card 1: Company Overview */}
        <div className="st-card" data-testid="card-detail-research-company">
          <h2 className="st-card-title">Company Overview</h2>
          <div className="st-detail-kv-list">
            <div className="st-detail-kv-row">
              <span>Company</span>
              <span style={{ fontWeight: 700 }}>{companyName}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>Symbol</span>
              <span style={{ color: "var(--st-cyan)", fontWeight: 700 }}>{symbol}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>Exchange</span>
              <span>{exchange}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>Sector</span>
              <span>{sector}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>Industry</span>
              <span>{industry}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>Market Cap</span>
              <span>{marketCap}</span>
            </div>
          </div>
          {description !== "Data unavailable" && (
            <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
              <p style={{ color: "#94a3b8", fontSize: "0.75rem", lineHeight: 1.4, margin: 0 }}>
                {description}
              </p>
            </div>
          )}
        </div>

        {/* Card 2: Market & 52-Week Range */}
        <div className="st-card" data-testid="card-detail-research-market">
          <h2 className="st-card-title">Market Information</h2>
          <div className="st-detail-kv-list">
            <div className="st-detail-kv-row">
              <span>Current / Exit Price</span>
              <span style={{ fontWeight: 700 }}>{formatINRVal(exitPrice ?? entryPrice)}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>52-Week High</span>
              <span style={{ color: "#4ade80" }}>{year52High}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>52-Week Low</span>
              <span style={{ color: "#f87171" }}>{year52Low}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>Volume</span>
              <span>{formatVolVal(volumeVal)}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>Avg Volume (20)</span>
              <span>{formatVolVal(avgVolumeVal)}</span>
            </div>
          </div>
        </div>

        {/* Card 3: Technical Snapshot */}
        <div className="st-card" data-testid="card-detail-research-technical">
          <h2 className="st-card-title">Technical Snapshot</h2>
          <div className="st-detail-kv-list">
            <div className="st-detail-kv-row">
              <span>RSI</span>
              <span style={{ fontWeight: 700 }}>{rsiVal != null ? Number(rsiVal).toFixed(1) : "—"}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>SMA 20</span>
              <span>{formatINRVal(sma20Val)}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>SMA 50</span>
              <span>{formatINRVal(sma50Val)}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>SMA 200</span>
              <span>{formatINRVal(sma200Val)}</span>
            </div>
            <div className="st-detail-kv-row">
              <span>ATR</span>
              <span>
                {atrVal != null
                  ? typeof atrVal === "number"
                    ? `₹${atrVal.toFixed(2)}`
                    : String(atrVal)
                  : "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Card 4: Strategy Snapshot */}
        <div className="st-card" data-testid="card-detail-research-strategy">
          <h2 className="st-card-title">Strategy Snapshot</h2>
          <div className="st-detail-kv-list" style={{ marginBottom: 8 }}>
            <div className="st-detail-kv-row">
              <span>Signal</span>
              <div>
                <span className={`st-badge-signal ${signal}`}>{signal}</span>
              </div>
            </div>
            <div className="st-detail-kv-row">
              <span>Strategy</span>
              <span style={{ color: "var(--st-cyan)", fontWeight: 600 }}>{strategyName}</span>
            </div>
          </div>
          <h3 className="st-detail-section-title" style={{ marginTop: 6 }}>Key Filters</h3>
          <div className="st-filter-eval-list">
            {filterResults.map((f, i) => (
              <div key={f.name || i} className="st-filter-eval-item">
                <span className="st-filter-eval-name">{f.name}</span>
                <span className={`st-filter-eval-status ${f.passed ? "passed" : "failed"}`}>
                  {f.passed ? "✓ Passed" : "✕ Failed"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Card 5: Recent Performance */}
      <section className="st-card st-card-full" data-testid="card-detail-research-performance">
        <h2 className="st-card-title">Recent Performance</h2>
        <div className="st-detail-kv-list">
          <div className="st-detail-kv-row">
            <span>Return %</span>
            <span
              style={{
                fontWeight: 700,
                fontSize: "1rem",
                color: (returnPct ?? 0) >= 0 ? "#4ade80" : "#f87171",
              }}
            >
              {formatPctVal(returnPct)}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>Entry Price</span>
            <span>{formatINRVal(entryPrice)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Exit Price</span>
            <span>{formatINRVal(exitPrice)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Test Run ID</span>
            <span style={{ color: "var(--st-cyan)", fontWeight: 600 }}>{resolvedRunId}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Status</span>
            <span className="st-status-badge st-status-badge--completed">
              {stock?.status || "completed"}
            </span>
          </div>
        </div>
      </section>

      {/* Deep AI Research Module (if available from data) */}
      {hasDeepResearch && (
        <section className="st-card st-card-full" data-testid="card-detail-deep-research" style={{ padding: 12 }}>
          <ResearchDashboard
            research={symbolDetail?.research as Record<string, unknown>}
            symbol={symbol}
            loading={isLoading}
            error={error}
          />
        </section>
      )}
    </div>
  );
};
