import React, { useState } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PerformanceAnalysisModel, PeriodicalBar } from "../../utils/performanceAnalysisCalculator";

const PROFIT_COLOR = "#089981";
const LOSS_COLOR = "#f23645";
const FAV_COLOR = "#99f6e4";
const ADV_COLOR = "#fecaca";

interface PeriodicalTabProps {
  model: PerformanceAnalysisModel;
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function fmtNum(val: number | null | undefined, digits = 3): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  return Number(val).toFixed(digits);
}

function pnlClass(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "";
  return Number(val) >= 0 ? "bt-pos" : "bt-neg";
}

export function PeriodicalTab({ model }: PeriodicalTabProps) {
  const { periodical } = model;
  const { metrics, weekly, quarterly, yearly } = periodical;
  const [periodType, setPeriodType] = useState<"weekly" | "quarterly" | "yearly">("weekly");
  const [pageIndex, setPageIndex] = useState(0);
  const pageSize = 20;

  const activeSeries =
    periodType === "weekly" ? weekly : periodType === "quarterly" ? quarterly : yearly;

  const totalPages = Math.max(1, Math.ceil(activeSeries.length / pageSize));
  const currentPage = Math.min(pageIndex, totalPages - 1);
  const start = currentPage * pageSize;
  const pagedData = activeSeries.slice(start, start + pageSize);

  const titleText =
    periodType === "weekly"
      ? "Weekly PnL"
      : periodType === "quarterly"
        ? "Quarterly PnL"
        : "Yearly PnL";

  return (
    <div className="bt-pa-periodical-tab" data-testid="performance-periodical-tab">
      {/* Top 4 Metrics Row */}
      <div className="bt-pa-metrics-grid">
        {/* Metric 1: CAGR */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-cagr">
          <span className="bt-pa-metric-label">Annualized return (CAGR)</span>
          <div className="bt-pa-metric-value-row">
            <strong className={`bt-pa-metric-value ${pnlClass(metrics.cagr)}`}>
              {fmtPct(metrics.cagr)}
            </strong>
          </div>
        </div>

        {/* Metric 2: Total return */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-total-return">
          <span className="bt-pa-metric-label">Total return</span>
          <div className="bt-pa-metric-value-row">
            <strong className={`bt-pa-metric-value ${pnlClass(metrics.totalReturn)}`}>
              {fmtPct(metrics.totalReturn)}
            </strong>
          </div>
        </div>

        {/* Metric 3: Sharpe ratio */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-sharpe">
          <span className="bt-pa-metric-label">Sharpe ratio</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">{fmtNum(metrics.sharpeRatio, 3)}</strong>
          </div>
        </div>

        {/* Metric 4: Sortino ratio */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-sortino">
          <span className="bt-pa-metric-label">Sortino ratio</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">{fmtNum(metrics.sortinoRatio, 3)}</strong>
          </div>
        </div>
      </div>

      {/* Main Periodical Chart Section */}
      <div className="bt-pa-section">
        <div className="bt-pa-section-header">
          <h4 className="bt-pa-section-title">{titleText}</h4>
          {/* Period Selector: Weekly, Quarterly, Yearly */}
          <div className="bt-pa-segmented-control" role="group" aria-label="Period selector">
            <button
              type="button"
              className={`bt-pa-seg-btn ${periodType === "weekly" ? "is-active" : ""}`}
              onClick={() => {
                setPeriodType("weekly");
                setPageIndex(0);
              }}
            >
              Weekly
            </button>
            <button
              type="button"
              className={`bt-pa-seg-btn ${periodType === "quarterly" ? "is-active" : ""}`}
              onClick={() => {
                setPeriodType("quarterly");
                setPageIndex(0);
              }}
            >
              Quarterly
            </button>
            <button
              type="button"
              className={`bt-pa-seg-btn ${periodType === "yearly" ? "is-active" : ""}`}
              onClick={() => {
                setPeriodType("yearly");
                setPageIndex(0);
              }}
            >
              Yearly
            </button>
          </div>
        </div>

        {/* Chart Container with Navigation buttons */}
        <div className="bt-pa-chart-nav-wrapper">
          {/* Left Nav Button */}
          <button
            type="button"
            className="bt-pa-nav-btn bt-pa-nav-btn--left"
            onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
            disabled={currentPage === 0}
            aria-label="Previous periods"
          >
            ‹
          </button>

          {/* Chart */}
          <div className="bt-pa-chart-container">
            {pagedData.length ? (
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={pagedData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
                  <XAxis
                    dataKey="label"
                    tickLine={false}
                    axisLine={{ stroke: "rgba(255,255,255,0.12)" }}
                    stroke="var(--text-muted, #8b9aab)"
                    fontSize={11}
                  />
                  <YAxis
                    orientation="right"
                    tickLine={false}
                    axisLine={false}
                    stroke="var(--text-muted, #8b9aab)"
                    fontSize={11}
                    tickFormatter={(v) => Number(v).toFixed(2)}
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const item = payload[0]?.payload as PeriodicalBar;
                      if (!item) return null;
                      return (
                        <div className="bt-chart-tooltip">
                          <div className="bt-chart-tooltip__date">{item.periodKey} ({item.label})</div>
                          <div className="bt-chart-tooltip__row">
                            <span className="bt-chart-tooltip__dot" style={{ background: PROFIT_COLOR }} />
                            <span>Realized profit:</span>
                            <strong className="bt-pos">+₹{item.realizedProfit.toFixed(2)}</strong>
                          </div>
                          <div className="bt-chart-tooltip__row">
                            <span className="bt-chart-tooltip__dot" style={{ background: LOSS_COLOR }} />
                            <span>Realized loss:</span>
                            <strong className="bt-neg">−₹{item.realizedLoss.toFixed(2)}</strong>
                          </div>
                          <div className="bt-chart-tooltip__row">
                            <span className="bt-chart-tooltip__dot" style={{ background: FAV_COLOR }} />
                            <span>Favorable excursion:</span>
                            <strong>+₹{item.favorableExcursion.toFixed(2)}</strong>
                          </div>
                          <div className="bt-chart-tooltip__row">
                            <span className="bt-chart-tooltip__dot" style={{ background: ADV_COLOR }} />
                            <span>Adverse excursion:</span>
                            <strong>−₹{item.adverseExcursion.toFixed(2)}</strong>
                          </div>
                          <div className="bt-chart-tooltip__row" style={{ borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: 4, marginTop: 4 }}>
                            <span>Net PnL:</span>
                            <strong className={pnlClass(item.netPnl)}>
                              {item.netPnl >= 0 ? "+" : "−"}₹{Math.abs(item.netPnl).toFixed(2)}
                            </strong>
                          </div>
                        </div>
                      );
                    }}
                  />
                  {/* Realized profit bars (Positive) */}
                  <Bar dataKey="realizedProfit" fill={PROFIT_COLOR} radius={[2, 2, 0, 0]} isAnimationActive={false} barSize={14} />
                  {/* Realized loss bars (Negative) */}
                  <Bar
                    dataKey={(d: PeriodicalBar) => (d.realizedLoss > 0 ? -d.realizedLoss : 0)}
                    fill={LOSS_COLOR}
                    radius={[0, 0, 2, 2]}
                    isAnimationActive={false}
                    barSize={14}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <p className="muted-copy" style={{ textAlign: "center", padding: "40px 0" }}>
                No completed trades to compute periodic P&L.
              </p>
            )}
          </div>

          {/* Right Nav Button */}
          <button
            type="button"
            className="bt-pa-nav-btn bt-pa-nav-btn--right"
            onClick={() => setPageIndex((p) => Math.min(totalPages - 1, p + 1))}
            disabled={currentPage >= totalPages - 1}
            aria-label="Next periods"
          >
            ›
          </button>
        </div>

        {/* Legend below chart matching Screenshot 2026-08-24 232623.png */}
        <div className="bt-pa-legend">
          <span className="bt-pa-legend-item">
            <i className="bt-pa-legend-dot" style={{ background: PROFIT_COLOR }} />
            Realized profit
          </span>
          <span className="bt-pa-legend-item">
            <i className="bt-pa-legend-dot" style={{ background: LOSS_COLOR }} />
            Realized loss
          </span>
          <span className="bt-pa-legend-item">
            <i className="bt-pa-legend-dot" style={{ background: FAV_COLOR }} />
            Favorable excursion
          </span>
          <span className="bt-pa-legend-item">
            <i className="bt-pa-legend-dot" style={{ background: ADV_COLOR }} />
            Adverse excursion
          </span>
        </div>
      </div>
    </div>
  );
}
