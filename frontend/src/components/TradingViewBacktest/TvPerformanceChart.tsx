import React, { useState, useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TvChartLayer, TvPerformancePoint } from "./types";
import { fmtTvDate, fmtTvPnl, fmtTvPct } from "./tvFormatters";

interface TvPerformanceChartProps {
  points: TvPerformancePoint[];
  currency?: string;
  loading?: boolean;
  onOpenSettings?: () => void;
}

const GREEN = "#089981";
const RED = "#f23645";
const BLUE = "#2962ff";
const PURPLE = "#ab47bc";
const RUNUP_GREEN = "#26a69a";
const DD_RED = "#ef5350";

export const TvPerformanceChart: React.FC<TvPerformanceChartProps> = ({
  points,
  currency = "INR",
  loading = false,
  onOpenSettings,
}) => {
  const [layersCollapsed, setLayersCollapsed] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [activeLayers, setActiveLayers] = useState<Record<TvChartLayer, boolean>>({
    cumulative: true,
    buy_and_hold: false,
    excursions: false,
    runups_drawdowns: false,
  });

  const toggleLayer = (layer: TvChartLayer) => {
    setActiveLayers((prev) => ({ ...prev, [layer]: !prev[layer] }));
  };

  const latestPoint = points.length ? points[points.length - 1] : null;
  const latestPnlFormatted = fmtTvPnl(latestPoint?.cumulativePnl, true);

  // Y-Domain calculation with padding
  const yDomain = useMemo(() => {
    if (!points.length) return [-100, 100];
    let min = 0;
    let max = 0;
    for (const pt of points) {
      if (pt.cumulativePnl < min) min = pt.cumulativePnl;
      if (pt.cumulativePnl > max) max = pt.cumulativePnl;
      if (activeLayers.buy_and_hold && pt.buyAndHoldPnl != null) {
        if (pt.buyAndHoldPnl < min) min = pt.buyAndHoldPnl;
        if (pt.buyAndHoldPnl > max) max = pt.buyAndHoldPnl;
      }
      if (activeLayers.runups_drawdowns) {
        if (pt.drawdownInr != null && -Math.abs(pt.drawdownInr) < min) min = -Math.abs(pt.drawdownInr);
        if (pt.runUpInr != null && pt.runUpInr > max) max = pt.runUpInr;
      }
    }
    const pad = Math.max(Math.abs(max - min) * 0.1, 50);
    return [Math.floor((min - pad) / 50) * 50, Math.ceil((max + pad) / 50) * 50];
  }, [points, activeLayers]);

  // Handle Snapshot / Export
  const handleSnapshot = () => {
    if (!points.length) return;
    const rows = [
      ["Date", "Cumulative PnL (INR)", "Cumulative PnL (%)", "Buy & Hold (INR)", "Drawdown (INR)", "RunUp (INR)"],
      ...points.map((p) => [
        p.date,
        p.cumulativePnl.toFixed(2),
        p.cumulativePnlPct.toFixed(2),
        p.buyAndHoldPnl != null ? p.buyAndHoldPnl.toFixed(2) : "",
        p.drawdownInr != null ? p.drawdownInr.toFixed(2) : "",
        p.runUpInr != null ? p.runUpInr.toFixed(2) : "",
      ]),
    ];
    const csvContent = "data:text/csv;charset=utf-8," + rows.map((e) => e.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `performance_curve_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) {
    return (
      <section className="tv-performance-card" data-testid="tv-performance-section">
        <div className="tv-performance-header">
          <div className="tv-performance-title-row">
            <h3 className="tv-performance-title">Performance</h3>
          </div>
        </div>
        <div className="tv-chart-loading-wrap">
          <div className="bt-spinner" />
          <p className="muted-copy" style={{ marginTop: 12 }}>Loading performance series...</p>
        </div>
      </section>
    );
  }

  return (
    <section
      className={`tv-performance-card ${isFullscreen ? "is-fullscreen" : ""}`}
      data-testid="tv-performance-section"
    >
      {/* Header */}
      <div className="tv-performance-header">
        <div className="tv-performance-title-row">
          <h3 className="tv-performance-title">Performance</h3>
          <span
            className="tv-info-icon"
            title="TradingView strategy performance equity and realized PnL trajectory"
          >
            ?
          </span>
        </div>

        <div className="tv-performance-actions">
          <button
            type="button"
            className="tv-tool-icon-btn"
            onClick={onOpenSettings}
            title="Chart settings"
            aria-label="Chart settings"
          >
            {/* Settings Gear */}
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
          <button
            type="button"
            className="tv-tool-icon-btn"
            onClick={handleSnapshot}
            title="Download performance curve data as CSV"
            aria-label="Take snapshot"
          >
            {/* Camera icon */}
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </button>
          <button
            type="button"
            className="tv-tool-icon-btn"
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? "Exit fullscreen" : "Expand chart fullscreen"}
            aria-label="Expand fullscreen"
          >
            {/* Fullscreen icon */}
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 3 21 3 21 9" />
              <polyline points="9 21 3 21 3 15" />
              <line x1="21" y1="3" x2="14" y2="10" />
              <line x1="3" y1="21" x2="10" y2="14" />
            </svg>
          </button>
        </div>
      </div>

      {/* Layer Selectors */}
      <div className="tv-chart-layers-container">
        <div className="tv-chart-layers-list">
          {/* 1. Cumulative PnL */}
          <button
            type="button"
            className={`tv-layer-toggle-btn ${activeLayers.cumulative ? "is-active" : ""}`}
            onClick={() => toggleLayer("cumulative")}
          >
            <span className="tv-layer-indicator" style={{ background: GREEN }} />
            <span>Cumulative PnL</span>
          </button>

          {/* 2. Buy and hold */}
          <button
            type="button"
            className={`tv-layer-toggle-btn ${activeLayers.buy_and_hold ? "is-active" : ""}`}
            onClick={() => toggleLayer("buy_and_hold")}
          >
            <span className="tv-layer-indicator" style={{ background: BLUE }} />
            <span>Buy and hold</span>
            {!activeLayers.buy_and_hold && (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            )}
          </button>

          {!layersCollapsed && (
            <>
              {/* 3. Trades excursions */}
              <button
                type="button"
                className={`tv-layer-toggle-btn ${activeLayers.excursions ? "is-active" : ""}`}
                onClick={() => toggleLayer("excursions")}
              >
                <span className="tv-layer-indicator" style={{ background: PURPLE }} />
                <span>Trades excursions</span>
              </button>

              {/* 4. Run-ups and drawdowns */}
              <button
                type="button"
                className={`tv-layer-toggle-btn ${activeLayers.runups_drawdowns ? "is-active" : ""}`}
                onClick={() => toggleLayer("runups_drawdowns")}
              >
                <span className="tv-layer-indicator" style={{ background: RUNUP_GREEN }} />
                <span>Run-ups and drawdowns</span>
              </button>
            </>
          )}

          {/* Collapse / Expand toggle */}
          <button
            type="button"
            className="tv-layer-collapse-btn"
            onClick={() => setLayersCollapsed(!layersCollapsed)}
            title={layersCollapsed ? "Show all layers" : "Collapse layers"}
            aria-label="Toggle layer visibility"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points={layersCollapsed ? "6 9 12 15 18 9" : "18 15 12 9 6 15"} />
            </svg>
          </button>
        </div>
      </div>

      {/* Chart Canvas */}
      {points.length ? (
        <div className="tv-chart-body">
          <div className="tv-chart-wrapper" style={{ height: isFullscreen ? "550px" : "330px" }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={points} margin={{ top: 12, right: 64, left: 10, bottom: 4 }}>
                <defs>
                  {/* Cumulative PnL gradient */}
                  <linearGradient id="tvPnlGreen" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={GREEN} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={GREEN} stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="tvPnlRed" x1="0" y1="1" x2="0" y2="0">
                    <stop offset="5%" stopColor={RED} stopOpacity={0.35} />
                    <stop offset="95%" stopColor={RED} stopOpacity={0.0} />
                  </linearGradient>

                  {/* Run-up & Drawdown gradient */}
                  <linearGradient id="tvRuGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={RUNUP_GREEN} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={RUNUP_GREEN} stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="tvDdGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={DD_RED} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={DD_RED} stopOpacity={0.0} />
                  </linearGradient>
                </defs>

                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255, 255, 255, 0.05)" />

                <ReferenceLine y={0} stroke="rgba(255, 255, 255, 0.15)" strokeWidth={1} />

                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={{ stroke: "rgba(255, 255, 255, 0.08)" }}
                  stroke="var(--text-muted, #8b9aab)"
                  minTickGap={40}
                  tickFormatter={(v) => {
                    const d = new Date(v);
                    return Number.isNaN(d.getTime()) ? String(v) : `${d.getFullYear()}`;
                  }}
                />

                {/* Right-aligned Y-Axis like TradingView */}
                <YAxis
                  orientation="right"
                  domain={yDomain}
                  tickLine={false}
                  axisLine={false}
                  stroke="var(--text-muted, #8b9aab)"
                  width={56}
                  tickFormatter={(v) => {
                    const n = Number(v);
                    if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
                    if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
                    return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
                  }}
                />

                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const item = payload[0]?.payload as TvPerformancePoint;
                    if (!item) return null;

                    const pnlFmt = fmtTvPnl(item.cumulativePnl, true);
                    const pnlPctFmt = fmtTvPct(item.cumulativePnlPct, true);

                    return (
                      <div className="tv-chart-tooltip" data-testid="tv-chart-tooltip">
                        <div className="tv-tooltip-date">{fmtTvDate(item.date)}</div>
                        <div className="tv-tooltip-row">
                          <span className="tv-tooltip-dot" style={{ background: item.cumulativePnl >= 0 ? GREEN : RED }} />
                          <span className="tv-tooltip-label">Cumulative PnL:</span>
                          <strong className={item.cumulativePnl >= 0 ? "is-pos" : "is-neg"}>
                            {pnlFmt.formatted} {currency} ({pnlPctFmt.formatted})
                          </strong>
                        </div>
                        {activeLayers.buy_and_hold && item.buyAndHoldPnl != null && (
                          <div className="tv-tooltip-row">
                            <span className="tv-tooltip-dot" style={{ background: BLUE }} />
                            <span className="tv-tooltip-label">Buy & Hold:</span>
                            <strong>
                              {fmtTvPnl(item.buyAndHoldPnl, true).formatted} {currency} ({fmtTvPct(item.buyAndHoldPct, true).formatted})
                            </strong>
                          </div>
                        )}
                        {activeLayers.runups_drawdowns && item.drawdownInr != null && (
                          <div className="tv-tooltip-row">
                            <span className="tv-tooltip-dot" style={{ background: DD_RED }} />
                            <span className="tv-tooltip-label">Drawdown:</span>
                            <strong className="is-neg">
                              -{Math.abs(item.drawdownInr).toFixed(2)} {currency} (-{Math.abs(item.drawdownPct || 0).toFixed(2)}%)
                            </strong>
                          </div>
                        )}
                      </div>
                    );
                  }}
                />

                {/* 1. Cumulative PnL Line / Area */}
                {activeLayers.cumulative && (
                  <Area
                    type="monotone"
                    dataKey="cumulativePnl"
                    stroke={latestPoint && latestPoint.cumulativePnl >= 0 ? GREEN : RED}
                    strokeWidth={2}
                    fill={latestPoint && latestPoint.cumulativePnl >= 0 ? "url(#tvPnlGreen)" : "url(#tvPnlRed)"}
                    name="Cumulative PnL"
                    isAnimationActive={false}
                  />
                )}

                {/* 2. Buy and Hold Line */}
                {activeLayers.buy_and_hold && (
                  <Line
                    type="monotone"
                    dataKey="buyAndHoldPnl"
                    stroke={BLUE}
                    strokeWidth={1.8}
                    strokeDasharray="4 4"
                    dot={false}
                    name="Buy and Hold"
                    isAnimationActive={false}
                  />
                )}

                {/* 3. Run-ups and Drawdowns */}
                {activeLayers.runups_drawdowns && (
                  <>
                    <Area
                      type="monotone"
                      dataKey="runUpInr"
                      stroke={RUNUP_GREEN}
                      strokeWidth={1.2}
                      fill="url(#tvRuGrad)"
                      name="Run-up"
                      isAnimationActive={false}
                    />
                    <Area
                      type="monotone"
                      dataKey="drawdownInr"
                      stroke={DD_RED}
                      strokeWidth={1.2}
                      fill="url(#tvDdGrad)"
                      name="Drawdown"
                      isAnimationActive={false}
                    />
                  </>
                )}
              </ComposedChart>
            </ResponsiveContainer>

            {/* Active Pill Badge on Right Y-Axis */}
            {latestPoint && (
              <div
                className={`tv-latest-axis-pill ${latestPoint.cumulativePnl >= 0 ? "is-pos" : "is-neg"}`}
                style={{
                  top: "24px",
                  right: "0px",
                }}
              >
                {latestPnlFormatted.formatted}
              </div>
            )}
          </div>

          {/* Bottom Winning / Losing Interval Strip */}
          <div className="tv-bottom-intervals-strip" title="Winning (green) vs losing (red) periods">
            {points.map((pt, idx) => (
              <div
                key={idx}
                className="tv-interval-segment"
                style={{
                  background: pt.isWinningInterval ? GREEN : RED,
                  opacity: 0.7,
                }}
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="tv-chart-empty-state">
          <p className="muted-copy">No performance curve series available for this backtest window.</p>
        </div>
      )}
    </section>
  );
};
