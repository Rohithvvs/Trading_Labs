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
import type { BenchmarkBar, PerformanceAnalysisModel } from "../../utils/performanceAnalysisCalculator";

const STRAT_COLOR = "#3b82f6";
const BENCH_COLOR = "#94a3b8";

interface BenchmarkingTabProps {
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

export function BenchmarkingTab({ model }: BenchmarkingTabProps) {
  const { benchmarking } = model;
  const { metrics, weekly, quarterly, yearly } = benchmarking;
  const [periodType, setPeriodType] = useState<"weekly" | "quarterly" | "yearly">("weekly");
  const [pageIndex, setPageIndex] = useState(0);
  const pageSize = 20;

  const activeSeries =
    periodType === "weekly" ? weekly : periodType === "quarterly" ? quarterly : yearly;

  const totalPages = Math.max(1, Math.ceil(activeSeries.length / pageSize));
  const currentPage = Math.min(pageIndex, totalPages - 1);
  const start = currentPage * pageSize;
  const pagedData = activeSeries.slice(start, start + pageSize);

  return (
    <div className="bt-pa-benchmarking-tab" data-testid="performance-benchmarking-tab">
      {/* Top 4 Metrics Row */}
      <div className="bt-pa-metrics-grid">
        {/* Metric 1: Strategy return */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-strat-return">
          <span className="bt-pa-metric-label">Strategy return</span>
          <div className="bt-pa-metric-value-row">
            <strong className={`bt-pa-metric-value ${pnlClass(metrics.strategyReturn)}`}>
              {fmtPct(metrics.strategyReturn)}
            </strong>
          </div>
        </div>

        {/* Metric 2: Buy and hold return */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-bench-return">
          <span className="bt-pa-metric-label">Buy and hold return</span>
          <div className="bt-pa-metric-value-row">
            <strong className={`bt-pa-metric-value ${pnlClass(metrics.buyAndHoldReturn)}`}>
              {fmtPct(metrics.buyAndHoldReturn)}
            </strong>
          </div>
        </div>

        {/* Metric 3: Strategy outperformance */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-outperformance">
          <span className="bt-pa-metric-label">Strategy outperformance</span>
          <div className="bt-pa-metric-value-row">
            <strong className={`bt-pa-metric-value ${pnlClass(metrics.outperformance)}`}>
              {fmtPct(metrics.outperformance)}
            </strong>
          </div>
        </div>

        {/* Metric 4: Correlation */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-correlation">
          <span className="bt-pa-metric-label">Correlation</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">{fmtNum(metrics.correlation, 3)}</strong>
          </div>
        </div>
      </div>

      {/* Main Benchmarking Chart Section */}
      <div className="bt-pa-section">
        <div className="bt-pa-section-header">
          <h4 className="bt-pa-section-title">Strategy vs benchmark</h4>
          {/* Period Selector */}
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
          <button
            type="button"
            className="bt-pa-nav-btn bt-pa-nav-btn--left"
            onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
            disabled={currentPage === 0}
            aria-label="Previous periods"
          >
            ‹
          </button>

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
                    tickFormatter={(v) => `₹${(Number(v) / 1000).toFixed(0)}K`}
                  />
                  <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const item = payload[0]?.payload as BenchmarkBar;
                      if (!item) return null;
                      return (
                        <div className="bt-chart-tooltip">
                          <div className="bt-chart-tooltip__date">{item.periodKey} ({item.label})</div>
                          <div className="bt-chart-tooltip__row">
                            <span className="bt-chart-tooltip__dot" style={{ background: STRAT_COLOR }} />
                            <span>Strategy PnL:</span>
                            <strong className={pnlClass(item.strategyPnl)}>
                              {item.strategyPnl >= 0 ? "+" : "−"}₹{Math.abs(item.strategyPnl).toFixed(2)}
                            </strong>
                          </div>
                          <div className="bt-chart-tooltip__row">
                            <span className="bt-chart-tooltip__dot" style={{ background: BENCH_COLOR }} />
                            <span>Buy & hold PnL:</span>
                            <strong className={pnlClass(item.benchmarkPnl)}>
                              {item.benchmarkPnl >= 0 ? "+" : "−"}₹{Math.abs(item.benchmarkPnl).toFixed(2)}
                            </strong>
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="strategyPnl" fill={STRAT_COLOR} radius={[2, 2, 0, 0]} isAnimationActive={false} barSize={12} />
                  <Bar dataKey="benchmarkPnl" fill={BENCH_COLOR} radius={[2, 2, 0, 0]} isAnimationActive={false} barSize={12} />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <p className="muted-copy" style={{ textAlign: "center", padding: "40px 0" }}>
                No benchmark comparison series available.
              </p>
            )}
          </div>

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

        {/* Legend */}
        <div className="bt-pa-legend">
          <span className="bt-pa-legend-item">
            <i className="bt-pa-legend-dot" style={{ background: STRAT_COLOR }} />
            Strategy PnL
          </span>
          <span className="bt-pa-legend-item">
            <i className="bt-pa-legend-dot" style={{ background: BENCH_COLOR }} />
            Buy and hold PnL
          </span>
        </div>
      </div>
    </div>
  );
}
