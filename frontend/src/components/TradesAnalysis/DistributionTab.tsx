import React from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TradesAnalysisModel } from "../../utils/tradeAnalysisCalculator";

const WIN_COLOR = "#089981";
const LOSS_COLOR = "#f23645";
const BE_COLOR = "#f59e0b";

interface DistributionTabProps {
  model: TradesAnalysisModel;
}

function fmtMoney(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const abs = Math.abs(Number(val)).toFixed(2);
  return abs;
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function fmtPctRaw(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  return `${n.toFixed(2)}%`;
}

export function DistributionTab({ model }: DistributionTabProps) {
  const { topMetrics, returnsDistribution, tradesDistribution } = model;
  const { bins, avgWinPct, avgLossPct, avgWinBinLabel, avgLossBinLabel } = returnsDistribution;

  const pieData = [
    { name: "Winners", value: tradesDistribution.winCount, color: WIN_COLOR, pct: tradesDistribution.winPct },
    { name: "Losers", value: tradesDistribution.lossCount, color: LOSS_COLOR, pct: tradesDistribution.lossPct },
    { name: "Breakevens", value: tradesDistribution.breakEvenCount, color: BE_COLOR, pct: tradesDistribution.breakEvenPct },
  ].filter((d) => d.value > 0);

  // If no trades, provide a single placeholder slice
  const renderPieData = pieData.length
    ? pieData
    : [{ name: "No trades", value: 1, color: "rgba(255, 255, 255, 0.1)", pct: 0 }];

  return (
    <div className="bt-ta-distribution-tab" data-testid="distribution-tab-content">
      {/* 4 Metric Cards */}
      <div className="bt-ta-metrics-grid">
        {/* Metric 1: Expected payoff */}
        <div className="bt-ta-metric-card" data-testid="metric-expected-payoff">
          <span className="bt-ta-metric-label">Expected payoff</span>
          <div className="bt-ta-metric-value-row">
            <strong className="bt-ta-metric-value">
              {topMetrics.expectedPayoffInr != null ? fmtMoney(topMetrics.expectedPayoffInr) : "--"}{" "}
              <span className="bt-ta-currency">INR</span>
            </strong>
            {topMetrics.expectedPayoffPct != null && (
              <span className="bt-ta-metric-pct">
                {topMetrics.expectedPayoffPct >= 0 ? "+" : ""}
                {fmtPctRaw(topMetrics.expectedPayoffPct)}
              </span>
            )}
          </div>
        </div>

        {/* Metric 2: Outliers PnL */}
        <div className="bt-ta-metric-card" data-testid="metric-outliers-pnl">
          <span className="bt-ta-metric-label">Outliers PnL</span>
          <div className="bt-ta-metric-value-row">
            <strong className="bt-ta-metric-value">
              {topMetrics.outliersPnlInr != null ? fmtMoney(topMetrics.outliersPnlInr) : "0.00"}{" "}
              <span className="bt-ta-currency">INR</span>
            </strong>
            {topMetrics.outliersPnlPct != null && (
              <span className="bt-ta-metric-pct">
                {fmtPctRaw(Math.abs(topMetrics.outliersPnlPct))}
              </span>
            )}
          </div>
        </div>

        {/* Metric 3: Largest profit */}
        <div className="bt-ta-metric-card" data-testid="metric-largest-profit">
          <span className="bt-ta-metric-label">Largest profit</span>
          <div className="bt-ta-metric-value-row">
            <strong className="bt-ta-metric-value">
              {topMetrics.largestProfitInr != null ? fmtMoney(topMetrics.largestProfitInr) : "--"}{" "}
              <span className="bt-ta-currency">INR</span>
            </strong>
          </div>
        </div>

        {/* Metric 4: Largest loss */}
        <div className="bt-ta-metric-card" data-testid="metric-largest-loss">
          <span className="bt-ta-metric-label">Largest loss</span>
          <div className="bt-ta-metric-value-row">
            <strong className="bt-ta-metric-value">
              {topMetrics.largestLossInr != null ? fmtMoney(topMetrics.largestLossInr) : "--"}{" "}
              <span className="bt-ta-currency">INR</span>
            </strong>
          </div>
        </div>
      </div>

      {/* Main Charts Grid: Returns distribution (Left) & Trades distribution (Right) */}
      <div className="bt-ta-charts-grid">
        {/* Returns distribution Histogram */}
        <div className="bt-ta-chart-card bt-ta-returns-card">
          <h4 className="bt-ta-chart-title">Returns distribution</h4>
          <div className="bt-ta-hist-container">
            <ResponsiveContainer width="100%" height={230}>
              <ComposedChart data={bins} margin={{ top: 18, right: 28, left: -20, bottom: 0 }}>
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
                  allowDecimals={false}
                  tickLine={false}
                  axisLine={false}
                  stroke="var(--text-muted, #8b9aab)"
                  fontSize={11}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const item = payload[0]?.payload;
                    if (!item) return null;
                    return (
                      <div className="bt-chart-tooltip">
                        <div>
                          Return bucket: <strong>{item.label} ({item.min}% to {item.max}%)</strong>
                        </div>
                        <div>
                          Trades: <strong>{item.count}</strong>
                        </div>
                      </div>
                    );
                  }}
                />
                {/* Average loss reference line */}
                {avgLossBinLabel && (
                  <ReferenceLine
                    x={avgLossBinLabel}
                    stroke={LOSS_COLOR}
                    strokeDasharray="3 3"
                    strokeWidth={1.5}
                  />
                )}
                {/* Average profit reference line */}
                {avgWinBinLabel && (
                  <ReferenceLine
                    x={avgWinBinLabel}
                    stroke={WIN_COLOR}
                    strokeDasharray="3 3"
                    strokeWidth={1.5}
                  />
                )}
                <Bar dataKey="count" radius={[2, 2, 0, 0]} isAnimationActive={false} barSize={22}>
                  {bins.map((entry, idx) => (
                    <Cell
                      key={`hist-cell-${idx}`}
                      fill={entry.isPositive ? WIN_COLOR : LOSS_COLOR}
                    />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Histogram Legend */}
          <div className="bt-ta-hist-legend">
            <span className="bt-ta-legend-item">
              <i className="bt-ta-legend-dot bt-ta-legend-dot--loss" />
              Losers
            </span>
            <span className="bt-ta-legend-item">
              <i className="bt-ta-legend-dot bt-ta-legend-dot--win" />
              Winners
            </span>
            <span className="bt-ta-legend-item">
              <i className="bt-ta-legend-dash bt-ta-legend-dash--loss" />
              Average loss{" "}
              <strong className="bt-ta-legend-val">
                {avgLossPct != null ? fmtPct(avgLossPct) : "--"}
              </strong>
            </span>
            <span className="bt-ta-legend-item">
              <i className="bt-ta-legend-dash bt-ta-legend-dash--win" />
              Average profit{" "}
              <strong className="bt-ta-legend-val">
                {avgWinPct != null ? fmtPct(avgWinPct) : "--"}
              </strong>
            </span>
          </div>
        </div>

        {/* Trades distribution Donut */}
        <div className="bt-ta-chart-card bt-ta-donut-card">
          <h4 className="bt-ta-chart-title">Trades distribution</h4>
          <div className="bt-ta-donut-layout">
            <div className="bt-ta-donut-chart-wrap">
              <ResponsiveContainer width={180} height={180}>
                <PieChart>
                  <Pie
                    data={renderPieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={75}
                    paddingAngle={renderPieData.length > 1 ? 2 : 0}
                    dataKey="value"
                    isAnimationActive={false}
                    startAngle={90}
                    endAngle={-270}
                  >
                    {renderPieData.map((entry, idx) => (
                      <Cell key={`pie-cell-${idx}`} fill={entry.color} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const item = payload[0]?.payload;
                      if (!item || item.name === "No trades") return null;
                      return (
                        <div className="bt-chart-tooltip">
                          <div>
                            <strong>{item.name}</strong>
                          </div>
                          <div>Trades: <strong>{item.value}</strong></div>
                          <div>Share: <strong>{item.pct?.toFixed(2)}%</strong></div>
                        </div>
                      );
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              {/* Center Donut Label */}
              <div className="bt-ta-donut-center">
                <span className="bt-ta-donut-total">{tradesDistribution.totalTrades}</span>
                <span className="bt-ta-donut-sub">Total trades</span>
              </div>
            </div>

            {/* Right-side Legend / Table */}
            <div className="bt-ta-donut-legend">
              <div className="bt-ta-donut-legend-row">
                <span className="bt-ta-donut-dot bt-ta-donut-dot--win" />
                <span className="bt-ta-donut-cat">Winners</span>
                <span className="bt-ta-donut-count">{tradesDistribution.winCount} trades</span>
                <span className="bt-ta-donut-pct">{tradesDistribution.winPct.toFixed(2)}%</span>
              </div>
              <div className="bt-ta-donut-legend-row">
                <span className="bt-ta-donut-dot bt-ta-donut-dot--loss" />
                <span className="bt-ta-donut-cat">Losers</span>
                <span className="bt-ta-donut-count">{tradesDistribution.lossCount} trades</span>
                <span className="bt-ta-donut-pct">{tradesDistribution.lossPct.toFixed(2)}%</span>
              </div>
              <div className="bt-ta-donut-legend-row">
                <span className="bt-ta-donut-dot bt-ta-donut-dot--be" />
                <span className="bt-ta-donut-cat">Breakevens</span>
                <span className="bt-ta-donut-count">{tradesDistribution.breakEvenCount} trades</span>
                <span className="bt-ta-donut-pct">{tradesDistribution.breakEvenPct.toFixed(2)}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
