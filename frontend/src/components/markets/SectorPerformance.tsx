import React, { memo, useState } from "react";
import type { MarketIndexItem } from "../../api";

interface SectorPerformanceProps {
  sectors?: MarketIndexItem[] | null;
}

const DEFAULT_SECTORS: MarketIndexItem[] = [
  { symbol: "NSE:NIFTYIT-INDEX", label: "IT", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYBANK-INDEX", label: "Banking", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYPHARMA-INDEX", label: "Pharma", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYAUTO-INDEX", label: "Auto", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYFMCG-INDEX", label: "FMCG", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYMETAL-INDEX", label: "Metals", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYREALTY-INDEX", label: "Realty", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYENERGY-INDEX", label: "Energy", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYINFRA-INDEX", label: "Infra", price: null, change_pct: null, source: "idle" },
  { symbol: "NSE:NIFTYMEDIA-INDEX", label: "Media", price: null, change_pct: null, source: "idle" },
];

export const SectorPerformance: React.FC<SectorPerformanceProps> = memo(function SectorPerformance({
  sectors,
}) {
  const [filter, setFilter] = useState<string>("1D");

  const displayList = sectors && sectors.length > 0 ? sectors : DEFAULT_SECTORS;

  // Find max absolute change to normalize bar widths
  const maxAbs = Math.max(
    ...displayList.map((s) => (s.change_pct != null ? Math.abs(Number(s.change_pct)) : 0)),
    1.0
  );

  return (
    <section className="terminal-card" aria-label="Sector Performance">
      <div className="terminal-card__header">
        <h2 className="terminal-card__title">
          <span>Sector Performance</span>
          <span style={{ fontSize: "0.75rem", color: "var(--mk-text-muted)" }}>(NSE)</span>
        </h2>

        <div className="market-timeframe-pills" role="tablist">
          {["1D", "1W", "1M"].map((f) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={filter === f}
              className={`market-pill-btn ${filter === f ? "is-active" : ""}`}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="sector-list">
        {displayList.map((item, idx) => {
          const sLabel = item.label || (item as any).name || item.symbol || "Sector";
          const hasChg = item.change_pct != null;
          const chg = hasChg ? Number(item.change_pct) : 0;
          const isPos = chg >= 0;
          const barWidth = hasChg ? Math.min(Math.round((Math.abs(chg) / maxAbs) * 100), 100) : 0;

          return (
            <div key={item.symbol || sLabel || idx} className="sector-row">
              <span className="sector-name" title={sLabel}>
                {sLabel}
              </span>

              <div className="sector-bar-track">
                {hasChg && (
                  <div
                    className={`sector-bar-fill ${isPos ? "is-pos" : "is-neg"}`}
                    style={{ width: `${barWidth}%` }}
                  />
                )}
              </div>

              <span
                className="sector-pct"
                style={{
                  color: hasChg ? (isPos ? "var(--mk-green)" : "var(--mk-red)") : "var(--mk-text-muted)",
                }}
              >
                {hasChg ? `${isPos ? "+" : ""}${chg.toFixed(2)}%` : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
});
