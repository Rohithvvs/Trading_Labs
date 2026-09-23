import React from "react";
import type { StrategyResultRow } from "../../api_strategy_tester";
import type { CandlePoint } from "../../api_strategy_tester";
import type { SymbolDetail } from "../../types";
import { formatINRVal, formatVolVal } from "./StockHeader";

interface TechnicalsTabProps {
  stock: StrategyResultRow | null;
  symbolDetail?: SymbolDetail | null;
  candles?: CandlePoint[];
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export const TechnicalsTab: React.FC<TechnicalsTabProps> = ({
  stock,
  symbolDetail,
  candles = [],
  isLoading = false,
  error = null,
  onRetry,
}) => {
  if (isLoading && !stock && !symbolDetail) {
    return (
      <div className="st-card st-tab-loading" data-testid="technicals-loading">
        Loading technical data...
      </div>
    );
  }

  if (error && !stock && !symbolDetail) {
    return (
      <div className="st-card st-tab-error" data-testid="technicals-error">
        <p>{error || "Unable to load technical data."}</p>
        {onRetry && (
          <button type="button" className="st-btn-primary" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    );
  }

  const latestCandle = candles.length > 0 ? candles[candles.length - 1] : null;

  const currentPrice = stock?.exit_price ?? stock?.entry_price ?? latestCandle?.close ?? null;
  const year52High = (symbolDetail as any)?.year52_high ?? (stock as any)?.year52_high ?? null;
  const year52Low = (symbolDetail as any)?.year52_low ?? (stock as any)?.year52_low ?? null;

  const techIndicators = ((symbolDetail as any)?.technical?.[0]?.indicators as Record<string, any>) || {};

  const rsiVal =
    stock?.rsi ??
    stock?.indicators?.rsi ??
    stock?.indicators?.rsi_14 ??
    techIndicators.rsi_14 ??
    techIndicators.rsi ??
    (symbolDetail?.technical_extras as any)?.rsi ??
    latestCandle?.rsi ??
    null;

  const sma20Val =
    stock?.sma_20 ??
    stock?.indicators?.sma_20 ??
    techIndicators.sma_20 ??
    latestCandle?.sma_20 ??
    null;

  const sma50Val =
    stock?.sma_50 ??
    stock?.indicators?.sma_50 ??
    techIndicators.sma_50 ??
    latestCandle?.sma_50 ??
    null;

  const sma200Val =
    stock?.sma_200 ??
    stock?.indicators?.sma_200 ??
    techIndicators.sma_200 ??
    latestCandle?.sma_200 ??
    null;

  const ema20Val =
    stock?.indicators?.ema_20 ??
    (stock?.indicators as any)?.["ema20"] ??
    (stock?.indicators as any)?.["EMA 20"] ??
    techIndicators.ema_20 ??
    null;

  const ema50Val =
    stock?.indicators?.ema_50 ??
    (stock?.indicators as any)?.["ema50"] ??
    (stock?.indicators as any)?.["EMA 50"] ??
    techIndicators.ema_50 ??
    null;

  const volumeVal =
    stock?.volume ??
    stock?.indicators?.volume ??
    latestCandle?.volume ??
    null;

  let avgVolumeVal =
    stock?.avg_volume ??
    stock?.indicators?.avg_volume_20 ??
    stock?.indicators?.avg_volume ??
    (stock?.indicators as any)?.["volSma20"] ??
    techIndicators.avg_volume_20 ??
    techIndicators.avg_volume ??
    null;

  if (avgVolumeVal == null && candles.length >= 5) {
    const slice = candles.slice(-20);
    const validVols = slice.map((c) => c.volume).filter((v): v is number => typeof v === "number" && v > 0);
    if (validVols.length > 0) {
      avgVolumeVal = Math.round(validVols.reduce((a, b) => a + b, 0) / validVols.length);
    }
  }

  const atrVal =
    stock?.indicators?.atr_14 ??
    stock?.indicators?.atr ??
    techIndicators.atr_14 ??
    techIndicators.atr ??
    symbolDetail?.technical_extras?.atr ??
    null;

  const macdVal = stock?.indicators?.macd ?? techIndicators.macd ?? null;
  const macdSignalVal = stock?.indicators?.macd_signal ?? techIndicators.macd_signal ?? null;

  const bollingerStatus =
    symbolDetail?.technical_extras?.bollinger_status ??
    symbolDetail?.technical_extras?.bollinger_position ??
    (stock?.indicators?.bb_upper != null ? `Upper: ₹${Number(stock.indicators.bb_upper).toFixed(2)}` : null);

  const volRatio =
    volumeVal != null && avgVolumeVal != null && avgVolumeVal > 0
      ? `${(volumeVal / avgVolumeVal).toFixed(2)}x`
      : "—";

  const volStatus =
    volumeVal != null && avgVolumeVal != null
      ? volumeVal >= avgVolumeVal
        ? "Above Average"
        : "Below Average"
      : "—";

  const trend200 =
    currentPrice != null && sma200Val != null
      ? currentPrice >= sma200Val
        ? "Bullish (Above SMA 200)"
        : "Bearish (Below SMA 200)"
      : "—";

  const trend50 =
    currentPrice != null && sma50Val != null
      ? currentPrice >= sma50Val
        ? "Bullish (Above SMA 50)"
        : "Bearish (Below SMA 50)"
      : "—";

  const rsiZone =
    rsiVal != null
      ? Number(rsiVal) >= 70
        ? "Overbought (>70)"
        : Number(rsiVal) <= 30
          ? "Oversold (<30)"
          : "Neutral (30-70)"
      : "—";

  return (
    <section className="st-stock-overview-grid" aria-label="Stock technical indicators" data-testid="card-detail-technicals">
      {/* Card 1: Trend & Structure Summary */}
      <div className="st-card" data-testid="card-detail-technicals-key">
        <h2 className="st-card-title">Price & Trend Structure</h2>
        <div className="st-detail-kv-list">
          <div className="st-detail-kv-row">
            <span>Price</span>
            <span style={{ fontWeight: 700 }}>{formatINRVal(currentPrice)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>52-Week High</span>
            <span>{year52High != null ? formatINRVal(year52High) : "—"}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>52-Week Low</span>
            <span>{year52Low != null ? formatINRVal(year52Low) : "—"}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Primary Trend</span>
            <span style={{ fontWeight: 600, color: trend200.includes("Bullish") ? "#4ade80" : "#94a3b8" }}>
              {trend200}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>Medium Trend</span>
            <span style={{ fontWeight: 600, color: trend50.includes("Bullish") ? "#4ade80" : "#94a3b8" }}>
              {trend50}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>RSI Zone</span>
            <span style={{ fontWeight: 600, color: "var(--st-cyan)" }}>{rsiZone}</span>
          </div>
        </div>
      </div>

      {/* Card 2: Moving Averages */}
      <div className="st-card" data-testid="card-detail-technicals-ma">
        <h2 className="st-card-title">Moving Averages</h2>
        <div className="st-detail-kv-list">
          <div className="st-detail-kv-row">
            <span>EMA 20</span>
            <span>{formatINRVal(ema20Val)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>EMA 50</span>
            <span>{formatINRVal(ema50Val)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>SMA 20</span>
            <span>{formatINRVal(sma20Val)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>SMA 50</span>
            <span>{formatINRVal(sma50Val)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>SMA 200</span>
            <span>{formatINRVal(sma200Val)}</span>
          </div>
        </div>
      </div>

      {/* Card 3: Momentum & Volatility */}
      <div className="st-card" data-testid="card-detail-technicals-momentum">
        <h2 className="st-card-title">Momentum & Volatility</h2>
        <div className="st-detail-kv-list">
          <div className="st-detail-kv-row">
            <span>RSI (14)</span>
            <span style={{ fontWeight: 700 }}>{rsiVal != null ? Number(rsiVal).toFixed(1) : "—"}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>ATR</span>
            <span>
              {atrVal != null
                ? typeof atrVal === "number"
                  ? `₹${atrVal.toFixed(2)}`
                  : String(atrVal)
                : "—"}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>MACD</span>
            <span>{macdVal != null ? Number(macdVal).toFixed(2) : "—"}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>MACD Signal</span>
            <span>{macdSignalVal != null ? Number(macdSignalVal).toFixed(2) : "—"}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Bollinger Bands</span>
            <span>{bollingerStatus ? String(bollingerStatus).replace(/_/g, " ") : "—"}</span>
          </div>
        </div>
      </div>

      {/* Card 4: Volume & Activity */}
      <div className="st-card" data-testid="card-detail-technicals-volume">
        <h2 className="st-card-title">Volume & Participation</h2>
        <div className="st-detail-kv-list">
          <div className="st-detail-kv-row">
            <span>Current Volume</span>
            <span>{formatVolVal(volumeVal)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Average Volume (20)</span>
            <span>{formatVolVal(avgVolumeVal)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Volume Ratio</span>
            <span style={{ fontWeight: 600, color: "var(--st-cyan)" }}>{volRatio}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Participation</span>
            <span
              style={{
                fontWeight: 600,
                color: volStatus === "Above Average" ? "#4ade80" : "#94a3b8",
              }}
            >
              {volStatus}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
};
