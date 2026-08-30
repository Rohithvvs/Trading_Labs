import React from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CandlePoint } from "../../api_strategy_tester";

interface ChartTabProps {
  symbol: string;
  candles: CandlePoint[];
  loadingCandles: boolean;
  entryPrice: number | null;
  exitPrice: number | null;
}

export const ChartTab: React.FC<ChartTabProps> = ({
  symbol,
  candles,
  loadingCandles,
  entryPrice,
  exitPrice,
}) => {
  return (
    <section className="st-card st-card-full" data-testid="card-detail-chart" aria-label="Stock price and indicators chart">
      <div className="st-card-title">
        <span>Price & Indicator Chart</span>
        <div style={{ display: "flex", gap: 14, fontSize: "0.75rem", color: "#94a3b8", flexWrap: "wrap" }}>
          <span><span style={{ color: "#38bdf8", fontWeight: "bold" }}>—</span> Close</span>
          <span><span style={{ color: "#eab308", fontWeight: "bold" }}>—</span> SMA 20</span>
          <span><span style={{ color: "#a855f7", fontWeight: "bold" }}>—</span> SMA 50</span>
          <span><span style={{ color: "#f43f5e", fontWeight: "bold" }}>—</span> SMA 200</span>
          <span><span style={{ color: "#22c55e", fontWeight: "bold" }}>---</span> Entry</span>
          <span><span style={{ color: "#ef4444", fontWeight: "bold" }}>---</span> Exit</span>
        </div>
      </div>

      {loadingCandles ? (
        <div style={{ textAlign: "center", padding: "60px 20px", color: "#64748b" }} data-testid="chart-loading">
          Loading chart data...
        </div>
      ) : candles.length === 0 ? (
        <div style={{ textAlign: "center", padding: "60px 20px", color: "#64748b" }} data-testid="chart-empty">
          No chart bars available for {symbol}.
        </div>
      ) : (
        <div style={{ width: "100%", marginTop: 8 }}>
          {/* Main Price & SMA Chart */}
          <div style={{ width: "100%", height: 360 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={candles} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
                <YAxis domain={["auto", "auto"]} tick={{ fill: "#64748b", fontSize: 11 }} orientation="right" />
                <Tooltip
                  contentStyle={{ background: "#091022", borderColor: "#1e293b", borderRadius: 8, fontSize: 12, color: "#f8fafc" }}
                />
                <Line type="monotone" dataKey="close" stroke="#38bdf8" strokeWidth={2} dot={false} name="Close" />
                <Line type="monotone" dataKey="sma_20" stroke="#eab308" strokeWidth={1.5} dot={false} name="SMA 20" />
                <Line type="monotone" dataKey="sma_50" stroke="#a855f7" strokeWidth={1.5} dot={false} name="SMA 50" />
                <Line type="monotone" dataKey="sma_200" stroke="#f43f5e" strokeWidth={1.5} dot={false} name="SMA 200" />
                {entryPrice != null && (
                  <ReferenceLine
                    y={entryPrice}
                    stroke="#22c55e"
                    strokeDasharray="4 4"
                    label={{ value: `Entry ₹${entryPrice}`, fill: "#22c55e", fontSize: 11, position: "left" }}
                  />
                )}
                {exitPrice != null && (
                  <ReferenceLine
                    y={exitPrice}
                    stroke="#ef4444"
                    strokeDasharray="4 4"
                    label={{ value: `Exit ₹${exitPrice}`, fill: "#ef4444", fontSize: 11, position: "left" }}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Volume Subchart */}
          <div style={{ width: "100%", height: 100, marginTop: 12 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={candles} margin={{ top: 0, right: 20, left: 0, bottom: 0 }}>
                <XAxis dataKey="date" hide />
                <YAxis tick={{ fill: "#64748b", fontSize: 10 }} orientation="right" />
                <Bar dataKey="volume" fill="#1e3a8a" name="Volume" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  );
};
