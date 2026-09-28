import React, { memo, useEffect, useState, useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Line,
} from "recharts";
import { fetchIndexCandles, type IndexCandlePoint } from "../../api";

interface MainMarketChartProps {
  selectedSymbol: string;
  onSymbolChange: (sym: string) => void;
  timeframe: string;
  onTimeframeChange: (tf: string) => void;
}

const INDEX_OPTIONS = [
  { symbol: "NSE:NIFTY50-INDEX", label: "Nifty 50" },
  { symbol: "NSE:NIFTYBANK-INDEX", label: "Nifty Bank" },
  { symbol: "BSE:SENSEX-INDEX", label: "Sensex" },
  { symbol: "NSE:INDIAVIX-INDEX", label: "India VIX" },
];

/** Custom Candlestick shape rendered by Recharts */
const CandlestickShape = (props: any) => {
  const { x, y, width, height, payload, yAxis } = props;
  if (!payload || x == null || y == null) return null;

  const open = Number(payload.open);
  const high = Number(payload.high);
  const low = Number(payload.low);
  const close = Number(payload.close);
  if (isNaN(open) || isNaN(high) || isNaN(low) || isNaN(close)) return null;

  const isUp = close >= open;
  const stroke = isUp ? "var(--mk-green)" : "var(--mk-red)";
  const fill = isUp ? "var(--mk-green)" : "var(--mk-red)";

  let yOpen: number;
  let yClose: number;
  let yHigh: number;
  let yLow: number;

  if (yAxis && typeof yAxis.scale === "function") {
    try {
      yOpen = yAxis.scale(open);
      yClose = yAxis.scale(close);
      yHigh = yAxis.scale(high);
      yLow = yAxis.scale(low);
    } catch {
      yOpen = y;
      yClose = y;
      yHigh = y;
      yLow = y + (height || 0);
    }
  } else {
    yOpen = y;
    yClose = y;
    yHigh = y;
    yLow = y + (height || 0);
  }

  if (isNaN(yOpen) || isNaN(yClose) || isNaN(yHigh) || isNaN(yLow)) {
    return null;
  }

  const w = Math.max(width || 10, 4);
  const candleW = Math.max(w * 0.7, 3);
  const candleX = x + (w - candleW) / 2;
  const bodyY = Math.min(yOpen, yClose);
  const bodyH = Math.max(Math.abs(yClose - yOpen), 1.5);
  const midX = x + w / 2;

  return (
    <g>
      {/* Upper and lower wick */}
      <line x1={midX} y1={yHigh} x2={midX} y2={yLow} stroke={stroke} strokeWidth={1.2} />
      {/* Candle real body */}
      <rect
        x={candleX}
        y={bodyY}
        width={candleW}
        height={bodyH}
        fill={fill}
        stroke={stroke}
        strokeWidth={1}
        rx={1}
      />
    </g>
  );
};

export const MainMarketChart: React.FC<MainMarketChartProps> = memo(function MainMarketChart({
  selectedSymbol,
  onSymbolChange,
  timeframe,
  onTimeframeChange,
}) {
  const [candles, setCandles] = useState<IndexCandlePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [showIndicators, setShowIndicators] = useState(true);
  const [hoveredCandle, setHoveredCandle] = useState<IndexCandlePoint | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchIndexCandles(selectedSymbol, timeframe)
      .then((data) => {
        if (!active) return;
        setCandles(data || []);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedSymbol, timeframe]);

  // Calculate Moving Averages (SMA 20, SMA 50) for indicators
  const chartData = useMemo(() => {
    return candles.map((c, i, arr) => {
      let sma20: number | null = null;
      let sma50: number | null = null;
      if (i >= 19) {
        const slice20 = arr.slice(i - 19, i + 1);
        sma20 = slice20.reduce((acc, curr) => acc + curr.close, 0) / 20;
      }
      if (i >= 49) {
        const slice50 = arr.slice(i - 49, i + 1);
        sma50 = slice50.reduce((acc, curr) => acc + curr.close, 0) / 50;
      }
      return {
        ...c,
        sma20: sma20 ? Math.round(sma20 * 100) / 100 : null,
        sma50: sma50 ? Math.round(sma50 * 100) / 100 : null,
      };
    });
  }, [candles]);

  const activeCandle = hoveredCandle || (chartData.length > 0 ? chartData[chartData.length - 1] : null);

  const priceMin = useMemo(() => {
    if (!candles || !candles.length) return "auto";
    const lows = candles.map((c) => Number(c.low)).filter((v) => !isNaN(v) && v > 0);
    if (!lows.length) return "auto";
    const min = Math.min(...lows);
    return Math.floor(min * 0.995);
  }, [candles]);

  const priceMax = useMemo(() => {
    if (!candles || !candles.length) return "auto";
    const highs = candles.map((c) => Number(c.high)).filter((v) => !isNaN(v) && v > 0);
    if (!highs.length) return "auto";
    const max = Math.max(...highs);
    return Math.ceil(max * 1.005);
  }, [candles]);

  const activeLabel = INDEX_OPTIONS.find((o) => o.symbol === selectedSymbol)?.label || "Nifty 50";

  return (
    <section className="terminal-card chart-container-card" aria-label="Main Market Candlestick Chart">
      {/* Chart Top Header */}
      <div className="chart-header-row">
        <div className="chart-symbol-tabs" role="tablist">
          {INDEX_OPTIONS.map((opt) => (
            <button
              key={opt.symbol}
              type="button"
              role="tab"
              aria-selected={selectedSymbol === opt.symbol}
              className={`chart-symbol-tab ${selectedSymbol === opt.symbol ? "is-active" : ""}`}
              onClick={() => onSymbolChange(opt.symbol)}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            type="button"
            className="market-pill-btn"
            style={{
              background: showIndicators ? "var(--mk-blue)" : "var(--mk-surface-raised)",
              color: showIndicators ? "#ffffff" : "var(--mk-text-secondary)",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
            }}
            onClick={() => setShowIndicators((s) => !s)}
            title="Toggle Moving Averages (SMA 20 & SMA 50)"
          >
            <span>fx</span>
            <span>Indicators</span>
          </button>

          <div className="market-timeframe-pills" role="tablist">
            {["1D", "1W", "1M", "3M", "6M", "1Y"].map((tf) => (
              <button
                key={tf}
                type="button"
                role="tab"
                aria-selected={timeframe === tf}
                className={`market-pill-btn ${timeframe === tf ? "is-active" : ""}`}
                onClick={() => onTimeframeChange(tf)}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* OHLC Bar Legend */}
      {activeCandle && (
        <div className="chart-legend-ohlc">
          <span style={{ fontWeight: 700, color: "var(--mk-text-primary)" }}>
            {activeLabel} · {timeframe}
          </span>
          <span>
            O <strong>{activeCandle.open?.toLocaleString("en-IN")}</strong>
          </span>
          <span>
            H <strong>{activeCandle.high?.toLocaleString("en-IN")}</strong>
          </span>
          <span>
            L <strong>{activeCandle.low?.toLocaleString("en-IN")}</strong>
          </span>
          <span>
            C{" "}
            <strong
              style={{
                color:
                  activeCandle.close >= activeCandle.open
                    ? "var(--mk-green)"
                    : "var(--mk-red)",
              }}
            >
              {activeCandle.close?.toLocaleString("en-IN")}
            </strong>
          </span>
          <span>
            Vol <strong>{(activeCandle.volume / 1_000_000).toFixed(1)}M</strong>
          </span>
          {showIndicators && activeCandle.sma20 && (
            <span style={{ color: "#eab308" }}>
              SMA20 <strong>{activeCandle.sma20.toLocaleString("en-IN")}</strong>
            </span>
          )}
          {showIndicators && activeCandle.sma50 && (
            <span style={{ color: "#a855f7" }}>
              SMA50 <strong>{activeCandle.sma50.toLocaleString("en-IN")}</strong>
            </span>
          )}
        </div>
      )}

      {/* Candlestick & MA Price Area */}
      <div className="chart-area-wrapper">
        {loading ? (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--mk-text-muted)",
              fontSize: "0.85rem",
            }}
          >
            Loading market chart...
          </div>
        ) : chartData.length === 0 ? (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--mk-text-muted)",
              fontSize: "0.85rem",
            }}
          >
            No price bars available for this index.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chartData}
              margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
              onMouseMove={(state: any) => {
                if (state && state.activePayload && state.activePayload[0]) {
                  setHoveredCandle(state.activePayload[0].payload);
                }
              }}
              onMouseLeave={() => setHoveredCandle(null)}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} />
              <YAxis
                domain={[priceMin, priceMax]}
                orientation="right"
                tick={{ fill: "#64748b", fontSize: 11 }}
                tickFormatter={(v) => Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              />
              <Tooltip
                content={() => null} // We use header legend for clean non-obstructive values
              />
              {/* Candlestick Bar */}
              <Bar dataKey="close" shape={<CandlestickShape />} isAnimationActive={false} />
              {showIndicators && (
                <Line
                  type="monotone"
                  dataKey="sma20"
                  stroke="#eab308"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  name="SMA 20"
                />
              )}
              {showIndicators && (
                <Line
                  type="monotone"
                  dataKey="sma50"
                  stroke="#a855f7"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                  name="SMA 50"
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Volume Subchart */}
      <div className="chart-volume-wrapper">
        {!loading && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
              <XAxis dataKey="date" hide />
              <YAxis
                orientation="right"
                tick={{ fill: "#64748b", fontSize: 9 }}
                tickFormatter={(v) => `${(v / 1_000_000).toFixed(0)}M`}
              />
              <Bar
                dataKey="volume"
                fill="rgba(59, 130, 246, 0.4)"
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
});
