import React from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AlternatingPeriodBar, PerformanceAnalysisModel } from "../../utils/performanceAnalysisCalculator";

const RUN_UP_COLOR = "#089981";
const DRAWDOWN_COLOR = "#f23645";
const CURRENT_RU_COLOR = "#5eead4";

interface GrowthDeclineTabProps {
  model: PerformanceAnalysisModel;
}

function fmtMoney(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  return Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  return `${n.toFixed(2)}%`;
}

export function GrowthDeclineTab({ model }: GrowthDeclineTabProps) {
  const { growthDecline } = model;
  const { metrics, alternating, comparison } = growthDecline;

  const maxVal = Math.max(
    comparison.runUp.maximumPct,
    comparison.runUp.currentPct,
    comparison.drawdown.maximumPct,
    0.01,
  );

  return (
    <div className="bt-pa-growth-tab" data-testid="performance-growth-tab">
      {/* Top 4 Metrics Row */}
      <div className="bt-pa-metrics-grid">
        {/* Metric 1: Average run-up duration */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-avg-runup-dur">
          <span className="bt-pa-metric-label">Average run-up duration</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">
              {metrics.avgRunUpDurationDays != null ? `${metrics.avgRunUpDurationDays} days` : "--"}
            </strong>
          </div>
        </div>

        {/* Metric 2: Average drawdown duration */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-avg-dd-dur">
          <span className="bt-pa-metric-label">Average drawdown duration</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">
              {metrics.avgDrawdownDurationDays != null ? `${metrics.avgDrawdownDurationDays} days` : "--"}
            </strong>
          </div>
        </div>

        {/* Metric 3: Max drawdown */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-max-dd">
          <span className="bt-pa-metric-label">Max drawdown</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">
              {metrics.maxDrawdownInr != null ? fmtMoney(metrics.maxDrawdownInr) : "--"}{" "}
              <span className="bt-pa-currency">INR</span>
            </strong>
            <span className="bt-pa-metric-pct">{fmtPct(metrics.maxDrawdownPct)}</span>
          </div>
        </div>

        {/* Metric 4: Max drawdown as % of initial capital */}
        <div className="bt-pa-metric-card" data-testid="pa-metric-max-dd-cap">
          <span className="bt-pa-metric-label">Max drawdown as % of initial capital</span>
          <div className="bt-pa-metric-value-row">
            <strong className="bt-pa-metric-value">{fmtPct(metrics.maxDrawdownCapPct)}</strong>
          </div>
        </div>
      </div>

      {/* Main 2-Column Grid: Alternating periods (Left) & Comparison (Right) */}
      <div className="bt-pa-charts-grid">
        {/* Left Chart: Alternating growth and decline */}
        <div className="bt-pa-chart-card">
          <h4 className="bt-pa-chart-title">Alternating growth and decline</h4>
          <div className="bt-pa-chart-container">
            {alternating.length ? (
              <ResponsiveContainer width="100%" height={230}>
                <ComposedChart data={alternating} margin={{ top: 15, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="label" hide />
                  <YAxis
                    orientation="right"
                    tickLine={false}
                    axisLine={false}
                    stroke="var(--text-muted, #8b9aab)"
                    fontSize={11}
                    tickFormatter={(v) => `${Number(v).toFixed(2)}%`}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const item = payload[0]?.payload as AlternatingPeriodBar;
                      if (!item) return null;
                      const isRu = item.type === "run_up";
                      const isCur = item.type === "current_run_up";
                      return (
                        <div className="bt-chart-tooltip">
                          <div className="bt-chart-tooltip__date">
                            {item.startDate} → {item.endDate} ({item.durationDays}d)
                          </div>
                          <div className="bt-chart-tooltip__row">
                            <span
                              className="bt-chart-tooltip__dot"
                              style={{
                                background: isRu ? RUN_UP_COLOR : isCur ? CURRENT_RU_COLOR : DRAWDOWN_COLOR,
                              }}
                            />
                            <span>{isRu ? "Run-up:" : isCur ? "Current run-up:" : "Drawdown:"}</span>
                            <strong className={isRu || isCur ? "bt-pos" : "bt-neg"}>
                              {item.valuePct.toFixed(2)}%
                            </strong>
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="valuePct" radius={[2, 2, 0, 0]} isAnimationActive={false} barSize={14}>
                    {alternating.map((entry) => {
                      const fill =
                        entry.type === "run_up"
                          ? RUN_UP_COLOR
                          : entry.type === "current_run_up"
                            ? CURRENT_RU_COLOR
                            : DRAWDOWN_COLOR;
                      return <Cell key={entry.id} fill={fill} />;
                    })}
                  </Bar>
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <p className="muted-copy" style={{ textAlign: "center", padding: "40px 0" }}>
                Insufficient equity data to compute alternating periods.
              </p>
            )}
          </div>

          {/* Legend */}
          <div className="bt-pa-legend">
            <span className="bt-pa-legend-item">
              <i className="bt-pa-legend-dot" style={{ background: RUN_UP_COLOR }} />
              Run-up
            </span>
            <span className="bt-pa-legend-item">
              <i className="bt-pa-legend-dot" style={{ background: DRAWDOWN_COLOR }} />
              Drawdown
            </span>
            <span className="bt-pa-legend-item">
              <i className="bt-pa-legend-dot" style={{ background: CURRENT_RU_COLOR }} />
              Current run-up
            </span>
          </div>
        </div>

        {/* Right Section: Comparison of growth and decline periods */}
        <div className="bt-pa-chart-card">
          <h4 className="bt-pa-chart-title">Comparison of growth and decline periods</h4>

          <div className="bt-pa-comparison-layout">
            {/* Run-up Group */}
            <div className="bt-pa-comparison-group">
              <span className="bt-pa-comparison-group-title">Run-up</span>

              {/* Maximum Run-up */}
              <div className="bt-pa-comparison-row">
                <span className="bt-pa-comparison-label">Maximum</span>
                <div className="bt-pa-comparison-bar-track">
                  <div
                    className="bt-pa-comparison-bar"
                    style={{
                      width: `${maxVal > 0 ? (comparison.runUp.maximumPct / maxVal) * 100 : 0}%`,
                      background: RUN_UP_COLOR,
                    }}
                  />
                </div>
                <span className="bt-pa-comparison-val">{fmtPct(comparison.runUp.maximumPct)}</span>
              </div>

              {/* Average Run-up */}
              <div className="bt-pa-comparison-row">
                <span className="bt-pa-comparison-label">Average</span>
                <div className="bt-pa-comparison-bar-track">
                  <div
                    className="bt-pa-comparison-bar"
                    style={{
                      width: `${maxVal > 0 ? (comparison.runUp.averagePct / maxVal) * 100 : 0}%`,
                      background: RUN_UP_COLOR,
                    }}
                  />
                </div>
                <span className="bt-pa-comparison-val">{fmtPct(comparison.runUp.averagePct)}</span>
              </div>

              {/* Current Run-up */}
              <div className="bt-pa-comparison-row">
                <span className="bt-pa-comparison-label">Current</span>
                <div className="bt-pa-comparison-bar-track">
                  <div
                    className="bt-pa-comparison-bar"
                    style={{
                      width: `${maxVal > 0 ? (comparison.runUp.currentPct / maxVal) * 100 : 0}%`,
                      background: CURRENT_RU_COLOR,
                    }}
                  />
                </div>
                <span className="bt-pa-comparison-val">{fmtPct(comparison.runUp.currentPct)}</span>
              </div>
            </div>

            {/* Drawdown Group */}
            <div className="bt-pa-comparison-group">
              <span className="bt-pa-comparison-group-title">Drawdown</span>

              {/* Maximum Drawdown */}
              <div className="bt-pa-comparison-row">
                <span className="bt-pa-comparison-label">Maximum</span>
                <div className="bt-pa-comparison-bar-track">
                  <div
                    className="bt-pa-comparison-bar"
                    style={{
                      width: `${maxVal > 0 ? (comparison.drawdown.maximumPct / maxVal) * 100 : 0}%`,
                      background: DRAWDOWN_COLOR,
                    }}
                  />
                </div>
                <span className="bt-pa-comparison-val">{fmtPct(comparison.drawdown.maximumPct)}</span>
              </div>

              {/* Average Drawdown */}
              <div className="bt-pa-comparison-row">
                <span className="bt-pa-comparison-label">Average</span>
                <div className="bt-pa-comparison-bar-track">
                  <div
                    className="bt-pa-comparison-bar"
                    style={{
                      width: `${maxVal > 0 ? (comparison.drawdown.averagePct / maxVal) * 100 : 0}%`,
                      background: DRAWDOWN_COLOR,
                    }}
                  />
                </div>
                <span className="bt-pa-comparison-val">{fmtPct(comparison.drawdown.averagePct)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
