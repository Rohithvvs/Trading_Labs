import React from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MarginPoint, PerformanceAnalysisModel } from "../../utils/performanceAnalysisCalculator";

const MARGIN_BLUE = "#3b82f6";

interface MarginUsageTabProps {
  model: PerformanceAnalysisModel;
}

function fmtMoney(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  return Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function MarginUsageTab({ model }: MarginUsageTabProps) {
  const { marginUsage } = model;
  const { metrics, series } = marginUsage;

  return (
    <div className="bt-pa-margin-tab" data-testid="performance-margin-tab">
      {/* Top 4 Metrics Row */}
      <div className="bt-pa-metrics-grid">
        {/* Metric 1: Margin efficiency */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-margin-efficiency">
          <span className="bt-pa-metric-label">Margin efficiency</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">
              {metrics.marginEfficiency != null ? fmtMoney(metrics.marginEfficiency) : "--"}{" "}
              <span className="bt-pa-currency">INR</span>
            </strong>
          </div>
        </div>

        {/* Metric 2: Average margin used */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-avg-margin">
          <span className="bt-pa-metric-label">Average margin used</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">
              {fmtMoney(metrics.avgMarginUsed)}{" "}
              <span className="bt-pa-currency">INR</span>
            </strong>
          </div>
        </div>

        {/* Metric 3: Margin calls */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-margin-calls">
          <span className="bt-pa-metric-label">Margin calls</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">{metrics.marginCalls}</strong>
          </div>
        </div>

        {/* Metric 4: Total liquidated volume */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-liquidated-vol">
          <span className="bt-pa-metric-label">Total liquidated volume</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">
              {fmtMoney(metrics.totalLiquidatedVolume)}{" "}
              <span className="bt-pa-currency">INR</span>
            </strong>
          </div>
        </div>
      </div>

      {/* Main Margin Utilization Chart Section */}
      <div className="bt-pa-section">
        <div className="bt-pa-section-header">
          <h4 className="bt-pa-section-title">Margin utilization</h4>
        </div>

        <div className="bt-pa-chart-container" style={{ padding: "0 10px" }}>
          {series.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={series} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="marginGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={MARGIN_BLUE} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={MARGIN_BLUE} stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={{ stroke: "rgba(255,255,255,0.12)" }}
                  stroke="var(--text-muted, #8b9aab)"
                  fontSize={11}
                  minTickGap={40}
                  tickFormatter={(v) => {
                    const d = new Date(v);
                    return Number.isNaN(d.getTime()) ? v : String(d.getFullYear());
                  }}
                />
                <YAxis
                  orientation="right"
                  domain={[0, 100]}
                  tickLine={false}
                  axisLine={false}
                  stroke="var(--text-muted, #8b9aab)"
                  fontSize={11}
                  tickFormatter={(v) => `${Number(v).toFixed(2)}%`}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const item = payload[0]?.payload as MarginPoint;
                    if (!item) return null;
                    return (
                      <div className="bt-chart-tooltip">
                        <div className="bt-chart-tooltip__date">{item.date}</div>
                        <div className="bt-chart-tooltip__row">
                          <span className="bt-chart-tooltip__dot" style={{ background: MARGIN_BLUE }} />
                          <span>Margin utilization:</span>
                          <strong>{item.utilizationPct.toFixed(2)}%</strong>
                        </div>
                      </div>
                    );
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="utilizationPct"
                  stroke={MARGIN_BLUE}
                  strokeWidth={2}
                  fill="url(#marginGrad)"
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <p className="muted-copy" style={{ textAlign: "center", padding: "40px 0" }}>
              Margin utilization data unavailable
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
