import React from "react";
import type { TvKeyStatsData } from "./types";
import { fmtTvPnl, fmtTvPct } from "./tvFormatters";

interface TvKeyStatsProps {
  stats: TvKeyStatsData;
  currency?: string;
  loading?: boolean;
}

export const TvKeyStats: React.FC<TvKeyStatsProps> = ({
  stats,
  currency = "INR",
  loading = false,
}) => {
  const pnlFormatted = fmtTvPnl(stats.totalPnlInr, true);
  const pnlPctFormatted = fmtTvPct(stats.totalPnlPct, true);

  const ddPnlFormatted = fmtTvPnl(stats.maxDrawdownInr != null ? Math.abs(stats.maxDrawdownInr) : null, false);
  const ddPctFormatted = fmtTvPct(stats.maxDrawdownPct != null ? Math.abs(stats.maxDrawdownPct) : null, false);

  const winPctFormatted = fmtTvPct(stats.winRatePct, false);
  const winFraction = stats.totalTrades > 0 ? `${stats.winCount}/${stats.totalTrades}` : "--/--";

  let pfDisplay = "--";
  if (stats.profitFactorInfinite) {
    pfDisplay = "∞";
  } else if (stats.profitFactor != null && !Number.isNaN(stats.profitFactor)) {
    pfDisplay = Number(stats.profitFactor).toFixed(3);
  }

  if (loading) {
    return (
      <section className="tv-keystats-card" data-testid="tv-keystats">
        <h3 className="tv-keystats-title">Key stats</h3>
        <div className="tv-keystats-grid">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="tv-keystat-col tv-keystat-col--skeleton">
              <div className="skeleton skeleton--text" style={{ width: "50%", height: "14px" }} />
              <div className="skeleton skeleton--text" style={{ width: "80%", height: "24px", marginTop: "8px" }} />
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="tv-keystats-card" data-testid="tv-keystats">
      <h3 className="tv-keystats-title">Key stats</h3>
      <div className="tv-keystats-grid">
        {/* 1. Total PnL */}
        <div className="tv-keystat-col">
          <span className="tv-keystat-label">Total PnL</span>
          <div className="tv-keystat-value-row">
            <span className={`tv-keystat-value ${pnlFormatted.isPositive ? "is-pos" : pnlFormatted.isNegative ? "is-neg" : ""}`}>
              {pnlFormatted.formatted}
              <span className="tv-keystat-currency">{currency}</span>
            </span>
            <span className={`tv-keystat-sub-pct ${pnlPctFormatted.isPositive ? "is-pos" : pnlPctFormatted.isNegative ? "is-neg" : ""}`}>
              {pnlPctFormatted.formatted}
            </span>
          </div>
        </div>

        {/* 2. Max Drawdown */}
        <div className="tv-keystat-col">
          <span className="tv-keystat-label">Max drawdown</span>
          <div className="tv-keystat-value-row">
            <span className="tv-keystat-value">
              {ddPnlFormatted.formatted}
              {ddPnlFormatted.formatted !== "--" && <span className="tv-keystat-currency">{currency}</span>}
            </span>
            <span className="tv-keystat-sub-pct">
              {ddPctFormatted.formatted}
            </span>
          </div>
        </div>

        {/* 3. Profitable Trades */}
        <div className="tv-keystat-col">
          <span className="tv-keystat-label">Profitable trades</span>
          <div className="tv-keystat-value-row">
            <span className="tv-keystat-value">{winPctFormatted.formatted}</span>
            <span className="tv-keystat-sub-pct">{winFraction}</span>
          </div>
        </div>

        {/* 4. Profit Factor */}
        <div className="tv-keystat-col">
          <span className="tv-keystat-label">Profit factor</span>
          <div className="tv-keystat-value-row">
            <span className="tv-keystat-value">{pfDisplay}</span>
          </div>
        </div>
      </div>
    </section>
  );
};
