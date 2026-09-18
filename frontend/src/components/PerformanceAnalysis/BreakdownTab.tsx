import React, { useState } from "react";
import type { PerformanceAnalysisModel } from "../../utils/performanceAnalysisCalculator";

interface BreakdownTabProps {
  model: PerformanceAnalysisModel;
}

function fmtMoney(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  return Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPnl(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  const abs = Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n < 0) return `−${abs} INR`;
  if (n > 0) return `+${abs} INR`;
  return `${abs} INR`;
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  return `${n.toFixed(2)}%`;
}

function fmtNum(val: number | null | undefined, digits = 3): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  return Number(val).toFixed(digits);
}

export function BreakdownTab({ model }: BreakdownTabProps) {
  const { breakdown } = model;
  const { metrics, bySignals, bySide } = breakdown;
  const [viewMode, setViewMode] = useState<"signals" | "side">("signals");

  const pf = metrics.profitFactorInfinite ? "∞" : fmtNum(metrics.profitFactor, 3);
  const rows = viewMode === "signals" ? bySignals : bySide;

  // Compute maximum scale width for diverging bars
  const maxSpan = Math.max(
    ...rows.map((r) => r.grossLoss + r.grossProfit),
    1,
  );

  return (
    <div className="bt-pa-breakdown-tab" data-testid="performance-breakdown-tab">
      {/* Top 4 Metrics Row */}
      <div className="bt-pa-metrics-grid">
        {/* Metric 1: Gross profit */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-gross-profit">
          <span className="bt-pa-metric-label">Gross profit</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">
              {fmtMoney(metrics.grossProfitInr)}{" "}
              <span className="bt-pa-currency">INR</span>
            </strong>
            <span className="bt-pa-metric-pct">{fmtPct(metrics.grossProfitPct)}</span>
          </div>
        </div>

        {/* Metric 2: Gross loss */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-gross-loss">
          <span className="bt-pa-metric-label">Gross loss</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">
              {fmtMoney(metrics.grossLossInr)}{" "}
              <span className="bt-pa-currency">INR</span>
            </strong>
            <span className="bt-pa-metric-pct">{fmtPct(metrics.grossLossPct)}</span>
          </div>
        </div>

        {/* Metric 3: Profit factor */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-profit-factor">
          <span className="bt-pa-metric-label">Profit factor</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">{pf}</strong>
          </div>
        </div>

        {/* Metric 4: Commission load */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-commission-load">
          <span className="bt-pa-metric-label">Commission load</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">{fmtPct(metrics.commissionLoadPct)}</strong>
          </div>
        </div>
      </div>

      {/* Profits and losses Section */}
      <div className="bt-pa-section">
        <div className="bt-pa-section-header">
          <h4 className="bt-pa-section-title">Profits and losses</h4>
          {/* Segmented Control: By signals vs By side */}
          <div className="bt-pa-segmented-control" role="group" aria-label="Profits and losses grouping">
            <button
              type="button"
              className={`bt-pa-seg-btn ${viewMode === "signals" ? "is-active" : ""}`}
              onClick={() => setViewMode("signals")}
            >
              By signals
            </button>
            <button
              type="button"
              className={`bt-pa-seg-btn ${viewMode === "side" ? "is-active" : ""}`}
              onClick={() => setViewMode("side")}
            >
              By side
            </button>
          </div>
        </div>

        {/* Diverging Bar Table */}
        <div className="bt-pa-diverging-list">
          {rows.map((row) => {
            const name = "name" in row ? row.name : row.side;
            const lossWidth = maxSpan > 0 ? (row.grossLoss / maxSpan) * 45 : 0;
            const profitWidth = maxSpan > 0 ? (row.grossProfit / maxSpan) * 45 : 0;
            const isPos = row.netPnl >= 0;

            return (
              <div key={name} className="bt-pa-diverging-row">
                <span className="bt-pa-diverging-name" title={name}>
                  {name}
                </span>

                {/* Stacked / Diverging Horizontal Bar */}
                <div className="bt-pa-diverging-bar-track">
                  {/* Loss Segment (Red / Pink) */}
                  <div
                    className="bt-pa-diverging-bar bt-pa-diverging-bar--loss"
                    style={{ width: `${Math.max(lossWidth, row.grossLoss > 0 ? 4 : 0)}%` }}
                    title={`Gross Loss: ₹${fmtMoney(row.grossLoss)}`}
                  />
                  {/* Profit Segment (Dark Green) */}
                  <div
                    className="bt-pa-diverging-bar bt-pa-diverging-bar--win"
                    style={{ width: `${Math.max(profitWidth * 0.6, row.grossProfit > 0 ? 3 : 0)}%` }}
                    title={`Realized Profit: ₹${fmtMoney(row.grossProfit)}`}
                  />
                  {/* Favorable/Net Segment (Light Teal) */}
                  <div
                    className="bt-pa-diverging-bar bt-pa-diverging-bar--favorable"
                    style={{ width: `${Math.max(profitWidth * 0.4, row.grossProfit > 0 ? 3 : 0)}%` }}
                    title={`Favorable contribution: ₹${fmtMoney(row.grossProfit)}`}
                  />
                </div>

                {/* Net PnL on right */}
                <span className={`bt-pa-diverging-pnl ${isPos ? "bt-pos" : "bt-neg"}`}>
                  {fmtPnl(row.netPnl)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
