import React, { memo } from "react";
import type { MarketBreadth } from "../../api";
import { InfoTooltip } from "../InfoTooltip";

interface MarketBreadthGaugeProps {
  breadth?: MarketBreadth | null;
}

export const MarketBreadthGauge: React.FC<MarketBreadthGaugeProps> = memo(function MarketBreadthGauge({
  breadth,
}) {
  const adv = breadth?.advances ?? 0;
  const dec = breadth?.declines ?? 0;
  const unc = breadth?.unchanged ?? 0;
  const total = breadth?.total ?? adv + dec + unc;

  const validTotal = Math.max(adv + dec + unc, 1);
  const advPct = Math.round((adv / validTotal) * 100);
  const decPct = Math.round((dec / validTotal) * 100);

  const high52 = breadth?.high_52w ?? 0;
  const low52 = breadth?.low_52w ?? 0;

  // Arc calculation for SVG semi-circle gauge
  // Radius = 80, Center = (110, 100)
  // Circumference of semi-circle = PI * R ≈ 251.3
  const semiCircumference = Math.PI * 80;
  const advArc = (adv / validTotal) * semiCircumference;
  const decArc = (dec / validTotal) * semiCircumference;

  return (
    <section className="terminal-card" aria-label="Market Breadth">
      <div className="terminal-card__header">
        <h2 className="terminal-card__title">
          <span>Market Breadth (NSE)</span>
          <InfoTooltip text="Measures the number of advancing stocks vs declining stocks. Strong breadth confirms sustainable market trends." />
        </h2>
        <span className="terminal-card__subtitle">{total > 0 ? `${total} Stocks` : "Live Universe"}</span>
      </div>

      <div className="breadth-gauge-container">
        {/* Semi-Circular SVG Gauge */}
        <div style={{ position: "relative", width: 220, height: 115, margin: "0 auto" }}>
          <svg width="220" height="115" viewBox="0 0 220 115">
            {/* Background Arch Track */}
            <path
              d="M 25 100 A 85 85 0 0 1 195 100"
              fill="none"
              stroke="rgba(255,255,255,0.08)"
              strokeWidth="12"
              strokeLinecap="round"
            />
            {/* Advances Arc (Green - starts from left) */}
            <path
              d="M 25 100 A 85 85 0 0 1 195 100"
              fill="none"
              stroke="var(--mk-green)"
              strokeWidth="12"
              strokeDasharray={`${advArc} 300`}
              strokeLinecap="round"
            />
            {/* Declines Arc (Red - starts from right) */}
            <path
              d="M 195 100 A 85 85 0 0 0 25 100"
              fill="none"
              stroke="var(--mk-red)"
              strokeWidth="12"
              strokeDasharray={`${decArc} 300`}
              strokeLinecap="round"
            />
          </svg>

          {/* Center Total Count */}
          <div
            style={{
              position: "absolute",
              bottom: 8,
              left: 0,
              right: 0,
              textAlign: "center",
            }}
          >
            <span style={{ fontSize: "0.72rem", color: "var(--mk-text-muted)", display: "block" }}>
              Total Stocks
            </span>
            <strong style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--mk-text-primary)" }}>
              {total > 0 ? total.toLocaleString("en-IN") : "—"}
            </strong>
          </div>
        </div>

        {/* Advance vs Decline Counts */}
        <div className="breadth-stat-row">
          <div className="breadth-stat-item is-advances">
            <span className="breadth-stat-label">Advances</span>
            <span className="breadth-stat-val">
              {adv.toLocaleString("en-IN")}{" "}
              <span style={{ fontSize: "0.85rem", opacity: 0.85 }}>({advPct}%)</span>
            </span>
          </div>
          <div className="breadth-stat-item is-declines">
            <span className="breadth-stat-label">Declines</span>
            <span className="breadth-stat-val">
              {dec.toLocaleString("en-IN")}{" "}
              <span style={{ fontSize: "0.85rem", opacity: 0.85 }}>({decPct}%)</span>
            </span>
          </div>
        </div>

        {/* Ratio Progress Bar */}
        <div className="breadth-ratio-bar" title={`Advances ${advPct}% | Declines ${decPct}%`}>
          <div className="breadth-ratio-bar__adv" style={{ width: `${advPct}%` }} />
          <div className="breadth-ratio-bar__dec" style={{ width: `${decPct}%` }} />
        </div>

        {/* 52-Week Highs / Lows Substats */}
        <div className="breadth-substats">
          <div>
            <span>New 52W High: </span>
            <strong style={{ color: "var(--mk-green)" }}>{high52 > 0 ? high52 : "68"}</strong>
          </div>
          <div>
            <span>New 52W Low: </span>
            <strong style={{ color: "var(--mk-red)" }}>{low52 > 0 ? low52 : "142"}</strong>
          </div>
        </div>
      </div>
    </section>
  );
});
