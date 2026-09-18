import React from "react";
import type { StrategyResultRow } from "../../api_strategy_tester";

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

interface StockHeaderProps {
  symbol: string;
  companyName: string;
  runId: string;
  stock: StrategyResultRow | null;
}

export const StockHeader: React.FC<StockHeaderProps> = ({
  symbol,
  companyName,
  runId,
  stock,
}) => {
  const signal = (stock?.signal || "WATCH").toUpperCase();
  const returnPct = stock?.return_pct ?? 0;
  const isPos = returnPct > 0;
  const isNeg = returnPct < 0;
  const entryPrice = stock?.entry_price ?? null;
  const exitPrice = stock?.exit_price ?? null;

  return (
    <section className="st-stock-hero-card" aria-label="Stock overview header">
      <div className="st-stock-hero-header">
        <div className="st-stock-hero-identity">
          <div className="st-stock-hero-icon" aria-hidden>◎</div>
          <div>
            <h1 className="st-stock-hero-title" data-testid="stock-details-symbol">{symbol}</h1>
            <p className="st-stock-hero-company" data-testid="stock-details-company">{companyName}</p>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="st-badge-pill" title="Strategy Test Run">
            Run: {runId}
          </span>
        </div>
      </div>

      {/* 4 Metric Boxes */}
      <div className="st-hero-metrics-grid" role="group" aria-label="Key stock metrics">
        <div className="st-hero-metric-box">
          <span className="st-hero-metric-label">Signal</span>
          <div style={{ marginTop: 2 }}>
            <span className={`st-badge-signal ${signal}`} data-testid="stock-detail-signal">{signal}</span>
          </div>
        </div>

        <div className="st-hero-metric-box">
          <span className="st-hero-metric-label">Return</span>
          <span
            className={`st-hero-metric-val ${isPos ? "green" : isNeg ? "red" : ""}`}
            data-testid="stock-detail-return"
          >
            {returnPct > 0 ? `+${returnPct.toFixed(2)}%` : `${returnPct.toFixed(2)}%`}
          </span>
        </div>

        <div className="st-hero-metric-box">
          <span className="st-hero-metric-label">Entry Price</span>
          <span className="st-hero-metric-val" data-testid="stock-detail-entry-price">
            {formatINRVal(entryPrice)}
          </span>
        </div>

        <div className="st-hero-metric-box">
          <span className="st-hero-metric-label">Exit Price</span>
          <span className="st-hero-metric-val" data-testid="stock-detail-exit-price">
            {formatINRVal(exitPrice)}
          </span>
        </div>
      </div>
    </section>
  );
};
