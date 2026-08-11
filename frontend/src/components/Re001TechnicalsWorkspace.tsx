import { useMemo } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CandidateRow } from "../types";
import { InfoTooltip } from "./InfoTooltip";

// ─────────────────────────────────────────────
// Formatting helpers (pure — no calc logic)
// ─────────────────────────────────────────────
function fmt(n: unknown, digits = 2): string {
  if (n === null || n === undefined || n === "") return "—";
  const v = typeof n === "number" ? n : Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function fmtInt(n: unknown): string {
  if (n === null || n === undefined || n === "") return "—";
  const v = typeof n === "number" ? n : Number(n);
  if (!Number.isFinite(v)) return "—";
  return Math.round(v).toLocaleString("en-IN");
}

function fmtCur(n: unknown, digits = 2): string {
  const s = fmt(n, digits);
  return s === "—" ? "—" : `₹${s}`;
}

function gateLabel(ok: unknown): string {
  if (ok === true) return "PASS";
  if (ok === false) return "FAIL";
  return "—";
}

function numOf(n: unknown): number | null {
  if (n === null || n === undefined || n === "") return null;
  const v = typeof n === "number" ? n : Number(n);
  return Number.isFinite(v) ? v : null;
}

// ─────────────────────────────────────────────
// Tooltip definitions
// ─────────────────────────────────────────────
const TIPS: Record<string, string> = {
  ema20:
    "EMA 20 — 20-day Exponential Moving Average. RE-001 uses it as the baseline trend anchor. Price above EMA 20 signals a short-term uptrend.",
  atr14:
    "ATR 14 — Average True Range over 14 days. Measures recent volatility. Used by RE-001 to set the ATR stop-loss (entry − 1.5×ATR).",
  keltner:
    "Keltner Channel — Volatility envelope around EMA 20 built with ATR. RE-001 requires the Close to be BELOW the Upper Band; price at/above it signals overextension.",
  keltnerWidth:
    "Keltner Width — (Upper − Lower) ÷ EMA 20, expressed as %. Wider = higher volatility. RE-001 monitors it for overextension context.",
  relVol:
    "Relative Volume — Current volume ÷ 20-day average volume. RE-001 requires RV ≥ 1.0 for volume gate PASS (confirmation of institutional interest).",
  ha: "Heikin-Ashi — Modified candlestick type that smooths noise. RE-001 requires a Bullish HA candle with zero lower wick for HA gate PASS.",
  rsi: "RSI 14 — Relative Strength Index over 14 days. Momentum oscillator ranging 0–100. RE-001 requires RSI ≥ threshold (default 50) for RSI gate PASS.",
  composite:
    "Composite Score — Weighted sum of Volume (35%), Trend (30%), Heikin-Ashi (20%) and RSI (15%) raw scores, calculated exclusively by the RE-001 backend.",
  gate: "Decision Gate — A mandatory hard rule. ALL gates must PASS for the final decision to be BUY. A single FAIL = REJECT, regardless of the Composite Score.",
  atrStop:
    "ATR Stop — Stop-loss set at Entry − 1.5 × ATR 14. Moves the stop away from normal volatility noise.",
  emaStop:
    "EMA Stop — The current EMA 20 value used as a secondary stop-loss reference. RE-001 picks the higher of ATR Stop and EMA Stop as the selected SL.",
  rr: "Risk/Reward — Ratio of reward (TP − Entry) to risk (Entry − SL). RE-001 targets a minimum of 3:1.",
  breakeven:
    "Breakeven Trigger — Price level at which RE-001 moves the stop-loss to entry (risk-free). Triggered once price reaches this level.",
};

// ─────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────

/** Compact status badge */
function Badge({ pass, size = "sm" }: { pass: boolean | null; size?: "sm" | "md" | "lg" }) {
  const sizeStyles: Record<string, React.CSSProperties> = {
    sm: { fontSize: "0.65rem", padding: "2px 8px", borderRadius: 999 },
    md: { fontSize: "0.75rem", padding: "3px 10px", borderRadius: 999 },
    lg: { fontSize: "0.85rem", padding: "5px 14px", borderRadius: 999, fontWeight: 700 },
  };
  const base: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 4,
    fontWeight: 600,
    letterSpacing: "0.05em",
    textTransform: "uppercase",
    ...sizeStyles[size],
  };
  if (pass === true) {
    return (
      <span style={{ ...base, background: "rgba(34,197,94,0.15)", color: "#4ade80" }}>
        ✓ PASS
      </span>
    );
  }
  if (pass === false) {
    return (
      <span style={{ ...base, background: "rgba(239,68,68,0.15)", color: "#f87171" }}>
        ✕ FAIL
      </span>
    );
  }
  return (
    <span style={{ ...base, background: "rgba(139,154,171,0.15)", color: "#8b9aab" }}>
      — N/A
    </span>
  );
}

/** Horizontal progress bar */
function ProgressBar({
  value,
  max = 100,
  color = "#3b82f6",
  label,
}: {
  value: number;
  max?: number;
  color?: string;
  label?: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          flex: 1,
          height: 8,
          background: "var(--surface-3)",
          borderRadius: 999,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: 999,
            transition: "width 0.6s var(--ease-out)",
          }}
        />
      </div>
      {label !== undefined && (
        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", minWidth: 36, textAlign: "right" }}>
          {label}
        </span>
      )}
    </div>
  );
}

/** Circular score gauge rendered with SVG */
function ScoreGauge({ score, max = 100, threshold }: { score: number; max?: number; threshold?: number }) {
  const R = 60;
  const cx = 80;
  const cy = 80;
  const strokeW = 12;
  // Arc from 135° to 405° (270° sweep)
  const startAngle = 135;
  const sweepAngle = 270;
  const angle = startAngle + (sweepAngle * Math.min(score, max)) / max;

  function polarToCartesian(cx: number, cy: number, r: number, deg: number) {
    const rad = ((deg - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function describeArc(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
    const s = polarToCartesian(cx, cy, r, startDeg);
    const e = polarToCartesian(cx, cy, r, endDeg);
    const largeArcFlag = endDeg - startDeg <= 180 ? 0 : 1;
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${largeArcFlag} 1 ${e.x} ${e.y}`;
  }

  const endAngle = startAngle + sweepAngle;
  const bgPath = describeArc(cx, cy, R, startAngle, endAngle);
  const fgPath = describeArc(cx, cy, R, startAngle, Math.min(angle, endAngle));

  // Colour gradient based on score
  const gaugeColor =
    score >= 80 ? "#22c55e" : score >= 60 ? "#f59e0b" : "#ef4444";

  return (
    <svg viewBox="0 0 160 160" width={160} height={160} style={{ display: "block", margin: "0 auto" }}>
      {/* Background track */}
      <path
        d={bgPath}
        fill="none"
        stroke="var(--surface-3)"
        strokeWidth={strokeW}
        strokeLinecap="round"
      />
      {/* Foreground arc */}
      <path
        d={fgPath}
        fill="none"
        stroke={gaugeColor}
        strokeWidth={strokeW}
        strokeLinecap="round"
        style={{ filter: `drop-shadow(0 0 6px ${gaugeColor}60)` }}
      />
      {/* Score text */}
      <text x={cx} y={cy - 6} textAnchor="middle" fontSize={28} fontWeight={700} fill="var(--text)">
        {fmt(score, 1)}
      </text>
      <text x={cx} y={cy + 16} textAnchor="middle" fontSize={12} fill="var(--text-muted)">
        / {max}
      </text>
      {threshold !== undefined && (
        <text x={cx} y={cy + 32} textAnchor="middle" fontSize={10} fill="var(--text-muted)">
          BUY &gt; {threshold}
        </text>
      )}
    </svg>
  );
}

/** RSI horizontal gauge */
function RSIGauge({ rsi, threshold = 50 }: { rsi: number; threshold?: number }) {
  const pct = Math.min(100, Math.max(0, rsi));
  const isOverbought = rsi >= 80;
  const isOversold = rsi <= 30;
  const rsiColor = isOversold ? "#ef4444" : isOverbought ? "#f59e0b" : "#22c55e";

  return (
    <div style={{ padding: "0 4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>
        <span>Oversold 0</span>
        <span style={{ color: "#f59e0b" }}>OB 80</span>
        <span>100</span>
      </div>
      <div style={{ position: "relative", height: 20, background: "var(--surface-3)", borderRadius: 999, overflow: "visible" }}>
        {/* Threshold marker */}
        <div
          style={{
            position: "absolute",
            left: `${threshold}%`,
            top: -4,
            bottom: -4,
            width: 2,
            background: "#3b82f6",
            borderRadius: 2,
            zIndex: 2,
          }}
        />
        {/* Overbought zone */}
        <div
          style={{
            position: "absolute",
            left: "80%",
            right: 0,
            top: 0,
            bottom: 0,
            background: "rgba(245,158,11,0.15)",
            borderRadius: "0 999px 999px 0",
          }}
        />
        {/* Fill */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: `${pct}%`,
            background: rsiColor,
            borderRadius: 999,
            transition: "width 0.6s var(--ease-out)",
            opacity: 0.85,
          }}
        />
        {/* Current RSI dot */}
        <div
          style={{
            position: "absolute",
            left: `calc(${pct}% - 10px)`,
            top: "50%",
            transform: "translateY(-50%)",
            width: 20,
            height: 20,
            background: rsiColor,
            borderRadius: "50%",
            border: "2px solid var(--surface)",
            boxShadow: `0 0 8px ${rsiColor}80`,
            zIndex: 3,
          }}
        />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
        <span style={{ fontSize: "0.7rem", color: "#3b82f6" }}>
          ▲ Threshold {threshold}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: "1.1rem", fontWeight: 700, color: rsiColor }}>{fmt(rsi, 1)}</span>
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
            {isOverbought ? "Overbought" : isOversold ? "Oversold" : "Healthy"}
          </span>
        </div>
      </div>
    </div>
  );
}

/** Heikin-Ashi single candle renderer */
function HACandleDisplay({
  open,
  high,
  low,
  close,
}: {
  open: number;
  high: number;
  low: number;
  close: number;
}) {
  const isBullish = close >= open;
  const svgH = 120;
  const svgW = 60;
  const padding = 12;
  const bodyX = svgW / 2 - 12;
  const bodyW = 24;
  const range = high - low;
  if (range === 0)
    return <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>No candle data</div>;

  const scale = (v: number) => padding + ((high - v) / range) * (svgH - 2 * padding);
  const bodyTop = scale(Math.max(open, close));
  const bodyBot = scale(Math.min(open, close));
  const bodyH = Math.max(bodyBot - bodyTop, 2);
  const color = isBullish ? "#22c55e" : "#ef4444";

  return (
    <svg viewBox={`0 0 ${svgW} ${svgH}`} width={svgW} height={svgH} style={{ display: "block", margin: "0 auto" }}>
      {/* Wick */}
      <line x1={svgW / 2} y1={scale(high)} x2={svgW / 2} y2={scale(low)} stroke={color} strokeWidth={2} />
      {/* Body */}
      <rect
        x={bodyX}
        y={bodyTop}
        width={bodyW}
        height={bodyH}
        fill={color}
        rx={2}
        style={{ filter: `drop-shadow(0 0 4px ${color}60)` }}
      />
    </svg>
  );
}

/** Price Level Ladder for Risk/Reward */
function PriceLadder({
  entry,
  stopLoss,
  breakeven,
  takeProfit,
  riskPerShare,
  rewardPerShare,
  rr,
}: {
  entry: number;
  stopLoss: number;
  breakeven: number;
  takeProfit: number;
  riskPerShare: number;
  rewardPerShare: number;
  rr: number;
}) {
  const allPrices = [stopLoss, entry, breakeven, takeProfit];
  const minP = Math.min(...allPrices);
  const maxP = Math.max(...allPrices);
  const range = maxP - minP;

  const pos = (p: number) => ((p - minP) / range) * 100;

  const levels = [
    { label: "TAKE PROFIT", price: takeProfit, color: "#22c55e", bold: true },
    { label: "BREAKEVEN", price: breakeven, color: "#3b82f6", bold: false },
    { label: "ENTRY", price: entry, color: "#f59e0b", bold: true },
    { label: "STOP LOSS", price: stopLoss, color: "#ef4444", bold: true },
  ].sort((a, b) => b.price - a.price);

  return (
    <div style={{ display: "flex", gap: 12, alignItems: "stretch" }}>
      {/* Ladder column */}
      <div style={{ position: "relative", width: 28, flexShrink: 0 }}>
        {/* Risk bar */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
            width: 6,
            top: `${100 - pos(entry)}%`,
            bottom: `${pos(stopLoss)}%`,
            background: "rgba(239,68,68,0.6)",
            borderRadius: 3,
          }}
        />
        {/* Reward bar */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
            width: 6,
            top: `${100 - pos(takeProfit)}%`,
            bottom: `${pos(entry)}%`,
            background: "rgba(34,197,94,0.6)",
            borderRadius: 3,
          }}
        />
        {/* Full spine */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
            width: 2,
            top: `${100 - pos(takeProfit)}%`,
            bottom: `${pos(stopLoss)}%`,
            background: "var(--border)",
          }}
        />
        {/* Level dots */}
        {levels.map((lv) => (
          <div
            key={lv.label}
            style={{
              position: "absolute",
              left: "50%",
              top: `${100 - pos(lv.price)}%`,
              transform: "translate(-50%, -50%)",
              width: lv.bold ? 12 : 8,
              height: lv.bold ? 12 : 8,
              borderRadius: "50%",
              background: lv.color,
              border: "2px solid var(--surface)",
              boxShadow: `0 0 6px ${lv.color}80`,
            }}
          />
        ))}
      </div>
      {/* Labels column */}
      <div style={{ flex: 1, position: "relative", minHeight: 200 }}>
        {levels.map((lv) => (
          <div
            key={lv.label}
            style={{
              position: "absolute",
              top: `${100 - pos(lv.price)}%`,
              transform: "translateY(-50%)",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <div>
              <div style={{ fontSize: "0.65rem", color: lv.color, fontWeight: 700, letterSpacing: "0.06em" }}>
                {lv.label}
              </div>
              <div style={{ fontSize: "0.9rem", fontWeight: lv.bold ? 700 : 500, color: "var(--text)" }}>
                ₹{fmt(lv.price)}
              </div>
            </div>
          </div>
        ))}
      </div>
      {/* Stats column */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          paddingTop: 8,
          paddingBottom: 8,
          minWidth: 90,
        }}
      >
        <div style={{ textAlign: "center", padding: "6px 8px", background: "rgba(34,197,94,0.1)", borderRadius: 8, border: "1px solid rgba(34,197,94,0.2)" }}>
          <div style={{ fontSize: "0.65rem", color: "#4ade80", fontWeight: 700 }}>REWARD</div>
          <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "#4ade80" }}>₹{fmt(rewardPerShare)}</div>
        </div>
        <div style={{ textAlign: "center", padding: "6px 8px", background: "rgba(59,130,246,0.1)", borderRadius: 8, border: "1px solid rgba(59,130,246,0.2)" }}>
          <div style={{ fontSize: "0.65rem", color: "#60a5fa", fontWeight: 700 }}>R:R</div>
          <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "#60a5fa" }}>1 : {fmt(rr, 2)}</div>
        </div>
        <div style={{ textAlign: "center", padding: "6px 8px", background: "rgba(239,68,68,0.1)", borderRadius: 8, border: "1px solid rgba(239,68,68,0.2)" }}>
          <div style={{ fontSize: "0.65rem", color: "#f87171", fontWeight: 700 }}>RISK</div>
          <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "#f87171" }}>₹{fmt(riskPerShare)}</div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────

/** Display-only RE-001 Technicals — values come from backend technical_analysis. */
export function Re001TechnicalsWorkspace({ row }: { row: CandidateRow }) {
  // @ts-ignore - allow dynamic engine fields
  const engineData = row.analysisItem?.lab_engines?.["RE-001"];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tech: any = engineData?.technical_analysis;

  if (!tech || tech.error) {
    return (
      <div className="detail-stack p-4">
        <p className="text-muted text-sm">
          {tech?.error
            ? `Engine technical analysis error: ${tech.error}`
            : "Engine-specific technical analysis is not available for this run."}
        </p>
      </div>
    );
  }

  const baseline = tech.baseline || {};
  const scoring = tech.scoring || {};
  const decision = tech.decision || {};
  const risk = tech.risk || {};
  const components: Array<{
    component: string;
    weight: number;
    raw: number;
    contribution: number;
  }> = Array.isArray(scoring.components) ? scoring.components : [];

  const finalDecision =
    decision.final_decision || tech.final_decision || engineData?.recommendation_state || "—";

  // ── Extracted values (presentation only) ──
  const currentClose = numOf(baseline.current_close);
  const ema20 = numOf(baseline.ema_20);
  const atr14 = numOf(baseline.atr_14);
  const upperKeltner = numOf(baseline.upper_keltner_band);
  const lowerKeltner = numOf(baseline.lower_keltner_band);
  const keltnerWidth = numOf(baseline.keltner_width);
  const currentVolume = numOf(baseline.current_volume);
  const volumeSMA20 = numOf(baseline.volume_sma_20 ?? baseline.avg_volume_20d);
  const relativeVolume = numOf(baseline.relative_volume ?? baseline.volume_ratio);
  const rsi14 = numOf(baseline.rsi_14);
  const rsiThreshold = numOf(baseline.rsi_threshold ?? 50) ?? 50;
  const compositeScore = numOf(scoring.composite_score ?? tech.composite_score) ?? 0;
  const buyThreshold = numOf(scoring.buy_threshold ?? 75) ?? 75;
  const haOpen = numOf(baseline.ha_open);
  const haHigh = numOf(baseline.ha_high);
  const haLow = numOf(baseline.ha_low);
  const haClose = numOf(baseline.ha_close);
  const haDirection: string = baseline.ha_direction || baseline.heikin_ashi_state || "";
  const haLowerWick = numOf(baseline.ha_lower_wick);
  const haLowerWickPct = numOf(baseline.ha_lower_wick_pct ?? baseline.lower_wick_percentage);
  const entryPrice = numOf(risk.entry) ?? numOf(currentClose) ?? 0;
  const atrStop = numOf(risk.atr_stop);
  const emaStop = numOf(risk.ema_stop);
  const selectedSL = numOf(risk.selected_sl) ?? numOf(atrStop) ?? 0;
  const riskPerShare = numOf(risk.risk_per_share) ?? 0;
  const positionSize = numOf(risk.position_size);
  const takeProfit = numOf(risk.take_profit) ?? 0;
  const rrRatio = numOf(risk.risk_reward) ?? 0;
  const breakevenTrigger = numOf(risk.breakeven_trigger);
  const emaTrailingStop = numOf(risk.current_ema_trailing_stop);

  // Derived presentation values (no calculation, just subtraction for display)
  const rewardPerShare =
    takeProfit && entryPrice ? takeProfit - entryPrice : null;

  const emaPct =
    ema20 && currentClose ? ((currentClose - ema20) / ema20) * 100 : null;

  // Decision gates
  const gates = [
    { label: "Keltner", key: "keltner_gate", value: decision.keltner_gate },
    { label: "Volume", key: "volume_gate", value: decision.volume_gate },
    { label: "Heikin-Ashi", key: "ha_gate", value: decision.ha_gate },
    { label: "Wick", key: "wick_gate", value: decision.wick_gate },
    { label: "RSI", key: "rsi_gate", value: decision.rsi_gate },
    { label: "Earnings", key: "earnings_gate", value: decision.earnings_gate },
  ];

  const passedGates = gates.filter((g) => g.value === true).length;
  const failedGates = gates.filter((g) => g.value === false);
  const totalGates = gates.filter((g) => g.value !== undefined && g.value !== null).length || gates.length;

  const isBuy = String(finalDecision).toUpperCase() === "BUY";
  const isWatch = String(finalDecision).toUpperCase() === "WATCH";
  const decisionColor = isBuy ? "#22c55e" : isWatch ? "#f59e0b" : "#ef4444";

  // OHLCV historical data for the Keltner / price chart
  const ohlcv = row.analysisItem?.ohlcv ?? [];

  // Volume chart data: last 20 bars from ohlcv
  const volumeChartData = useMemo(() => {
    const recent = ohlcv.slice(-20);
    return recent.map((bar, idx) => ({
      idx,
      date: bar.timestamp ? bar.timestamp.slice(5, 10) : idx,
      volume: bar.volume,
      isCurrent: idx === recent.length - 1,
    }));
  }, [ohlcv]);

  // Price/Keltner chart data using raw ohlcv + static overlay values
  const priceChartData = useMemo(() => {
    const recent = ohlcv.slice(-30);
    return recent.map((bar, idx) => ({
      idx,
      date: bar.timestamp ? bar.timestamp.slice(5, 10) : idx,
      close: bar.close,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      // Overlay the current calculated EMA/Keltner on all bars for reference
      ema20: idx === recent.length - 1 ? ema20 : undefined,
      upperKeltner: idx === recent.length - 1 ? upperKeltner : undefined,
      lowerKeltner: idx === recent.length - 1 ? lowerKeltner : undefined,
    }));
  }, [ohlcv, ema20, upperKeltner, lowerKeltner]);

  // Technical interpretation bullet points built from backend values
  const interpretation = useMemo(() => {
    const bullets: string[] = [];
    if (currentClose != null && ema20 != null) {
      bullets.push(
        currentClose > ema20
          ? `Price (₹${fmt(currentClose)}) is above EMA 20 (₹${fmt(ema20)}) — short-term trend is bullish.`
          : `Price (₹${fmt(currentClose)}) is below EMA 20 (₹${fmt(ema20)}) — trend is bearish.`
      );
    }
    if (currentVolume != null && volumeSMA20 != null) {
      bullets.push(
        currentVolume > volumeSMA20
          ? `Volume (${fmtInt(currentVolume)}) is above 20D average (${fmtInt(volumeSMA20)}) — institutional activity confirmed.`
          : `Volume (${fmtInt(currentVolume)}) is below 20D average (${fmtInt(volumeSMA20)}) — low conviction move.`
      );
    }
    if (haDirection) {
      bullets.push(
        haDirection.toLowerCase().includes("bull")
          ? `Heikin-Ashi candle is Bullish${haLowerWick === 0 ? " with no lower wick" : ""} — momentum is constructive.`
          : `Heikin-Ashi candle is ${haDirection} — momentum is mixed.`
      );
    }
    if (rsi14 != null) {
      bullets.push(
        rsi14 >= rsiThreshold
          ? `RSI (${fmt(rsi14, 1)}) is above threshold (${rsiThreshold}) — momentum gate passes.`
          : `RSI (${fmt(rsi14, 1)}) is below threshold (${rsiThreshold}) — momentum gate fails.`
      );
    }
    if (upperKeltner != null && currentClose != null) {
      const pct = ((upperKeltner - currentClose) / upperKeltner) * 100;
      bullets.push(
        pct < 1
          ? `Price (₹${fmt(currentClose)}) is near the Upper Keltner Band (₹${fmt(upperKeltner)}) — Keltner gate FAILS, indicating overextension.`
          : `Price is within the Keltner Channel — channel has room.`
      );
    }
    if (rrRatio) {
      bullets.push(`Risk/Reward is 1:${fmt(rrRatio, 2)} — ${rrRatio >= 3 ? "meets" : "below"} RE-001's 3:1 target.`);
    }
    if (failedGates.length > 0) {
      bullets.push(
        `Final Decision is ${String(finalDecision).toUpperCase()} because ${failedGates.map((g) => g.label).join(", ")} gate${failedGates.length > 1 ? "s" : ""} failed.`
      );
    }
    return bullets;
  }, [
    currentClose, ema20, currentVolume, volumeSMA20, haDirection,
    haLowerWick, rsi14, rsiThreshold, upperKeltner, rrRatio, failedGates, finalDecision,
  ]);

  // ─────────────────────────────────
  // Styles helpers
  // ─────────────────────────────────
  const card: React.CSSProperties = {
    background: "var(--surface)",
    backgroundImage: "var(--gradient-card)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-lg)",
    padding: "16px",
    boxShadow: "var(--shadow-sm)",
  };

  const sectionLabel: React.CSSProperties = {
    fontSize: "0.65rem",
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "var(--text-muted)",
    marginBottom: 10,
    display: "flex",
    alignItems: "center",
    gap: 6,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTION 1 — TECHNICAL SUMMARY HEADER
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div
        style={{
          background: "linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          padding: 20,
        }}
      >
        {/* Engine label */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <div style={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "#3b82f6", background: "rgba(59,130,246,0.1)", padding: "4px 10px", borderRadius: 999, border: "1px solid rgba(59,130,246,0.25)" }}>
            RE-001
          </div>
          <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Trend Continuation Engine</span>
        </div>

        {/* KPI row */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
            gap: 12,
            marginBottom: 16,
          }}
        >
          {/* Current Price */}
          <div style={{ background: "var(--surface-2)", borderRadius: 12, padding: "12px 14px", border: "1px solid var(--border)" }}>
            <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
              Current Price
            </div>
            <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text)" }}>{fmtCur(currentClose)}</div>
            {emaPct != null && (
              <div style={{ fontSize: "0.7rem", color: emaPct >= 0 ? "#4ade80" : "#f87171", marginTop: 2 }}>
                {emaPct >= 0 ? "▲" : "▼"} {fmt(Math.abs(emaPct), 1)}% vs EMA20
              </div>
            )}
          </div>

          {/* Composite Score */}
          <div style={{ background: "var(--surface-2)", borderRadius: 12, padding: "12px 14px", border: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
              Composite Score
              <InfoTooltip content={TIPS.composite} />
            </div>
            <div style={{ fontSize: "1.25rem", fontWeight: 700, color: compositeScore >= buyThreshold ? "#4ade80" : "#f87171" }}>
              {fmt(compositeScore, 1)}
            </div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>BUY &gt; {buyThreshold}</div>
          </div>

          {/* Final Decision */}
          <div style={{ background: "var(--surface-2)", borderRadius: 12, padding: "12px 14px", border: `1px solid ${decisionColor}40` }}>
            <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
              Final Decision
            </div>
            <div style={{ fontSize: "1.25rem", fontWeight: 800, color: decisionColor, letterSpacing: "0.05em" }}>
              {String(finalDecision).toUpperCase()}
            </div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>{passedGates} / {totalGates} gates</div>
          </div>

          {/* Risk/Reward */}
          <div style={{ background: "var(--surface-2)", borderRadius: 12, padding: "12px 14px", border: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
              Risk / Reward
              <InfoTooltip content={TIPS.rr} />
            </div>
            <div style={{ fontSize: "1.25rem", fontWeight: 700, color: rrRatio >= 3 ? "#4ade80" : "#f87171" }}>
              1 : {fmt(rrRatio, 2)}
            </div>
            {positionSize != null && (
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>{fmtInt(positionSize)} shares</div>
            )}
          </div>
        </div>

        {/* Gate quick summary */}
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 14 }}>
          <div style={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
            Technical Status
            <InfoTooltip content={TIPS.gate} />
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {gates.map((g) => {
              const isPass = g.value === true;
              const isFail = g.value === false;
              return (
                <div
                  key={g.key}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                    padding: "5px 10px",
                    borderRadius: 999,
                    background: isFail
                      ? "rgba(239,68,68,0.12)"
                      : isPass
                      ? "rgba(34,197,94,0.1)"
                      : "var(--surface-3)",
                    border: isFail
                      ? "1px solid rgba(239,68,68,0.35)"
                      : isPass
                      ? "1px solid rgba(34,197,94,0.25)"
                      : "1px solid var(--border)",
                    fontSize: "0.72rem",
                    fontWeight: 600,
                    color: isFail ? "#f87171" : isPass ? "#4ade80" : "var(--text-muted)",
                  }}
                >
                  <span>{isFail ? "✕" : isPass ? "✓" : "—"}</span>
                  <span>{g.label}</span>
                </div>
              );
            })}
          </div>

          {/* Failed gate alert */}
          {failedGates.length > 0 && (
            <div
              style={{
                marginTop: 12,
                padding: "10px 14px",
                background: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.3)",
                borderRadius: 10,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span style={{ fontSize: "1.1rem" }}>⚠</span>
              <div>
                <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#f87171", letterSpacing: "0.05em" }}>
                  {failedGates.map((g) => g.label.toUpperCase()).join(" + ")} GATE{failedGates.length > 1 ? "S" : ""} FAILED
                </div>
                <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>
                  This is the primary reason for the {String(finalDecision).toUpperCase()} decision.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTION 2 — PRICE + KELTNER CHART
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div style={card}>
        <div style={sectionLabel}>
          Price + Keltner Channel
          <InfoTooltip content={TIPS.keltner} />
        </div>
        {priceChartData.length > 0 ? (
          <div>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={priceChartData} margin={{ top: 8, right: 80, bottom: 4, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.5} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--text-muted)" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis
                  domain={["auto", "auto"]}
                  tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `₹${v}`}
                  width={55}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 12,
                    color: "var(--text)",
                  }}
                  formatter={(v: unknown, name: string) => [
                    `₹${fmt(v as number)}`,
                    name,
                  ]}
                />
                {/* Close price area */}
                <Area
                  type="monotone"
                  dataKey="close"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="rgba(59,130,246,0.08)"
                  dot={false}
                  name="Close"
                />
                {/* EMA 20 reference line */}
                {ema20 != null && (
                  <ReferenceLine
                    y={ema20}
                    stroke="#f59e0b"
                    strokeDasharray="6 3"
                    strokeWidth={1.5}
                    label={{ value: `EMA₂₀ ₹${fmt(ema20)}`, position: "right", fontSize: 10, fill: "#f59e0b", dx: 4 }}
                  />
                )}
                {/* Upper Keltner */}
                {upperKeltner != null && (
                  <ReferenceLine
                    y={upperKeltner}
                    stroke="#ef4444"
                    strokeDasharray="4 3"
                    strokeWidth={1.5}
                    label={{ value: `UK ₹${fmt(upperKeltner)}`, position: "right", fontSize: 10, fill: "#ef4444", dx: 4 }}
                  />
                )}
                {/* Lower Keltner */}
                {lowerKeltner != null && (
                  <ReferenceLine
                    y={lowerKeltner}
                    stroke="#22c55e"
                    strokeDasharray="4 3"
                    strokeWidth={1.5}
                    label={{ value: `LK ₹${fmt(lowerKeltner)}`, position: "right", fontSize: 10, fill: "#22c55e", dx: 4 }}
                  />
                )}
                {/* Stop Loss */}
                {selectedSL > 0 && (
                  <ReferenceLine
                    y={selectedSL}
                    stroke="#ef4444"
                    strokeDasharray="2 4"
                    strokeWidth={1}
                    label={{ value: `SL ₹${fmt(selectedSL)}`, position: "right", fontSize: 9, fill: "#ef4444", dx: 4 }}
                  />
                )}
                {/* Take Profit */}
                {takeProfit > 0 && (
                  <ReferenceLine
                    y={takeProfit}
                    stroke="#22c55e"
                    strokeDasharray="2 4"
                    strokeWidth={1}
                    label={{ value: `TP ₹${fmt(takeProfit)}`, position: "right", fontSize: 9, fill: "#22c55e", dx: 4 }}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>

            {/* Keltner info row */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
              {[
                { label: "Upper Keltner", value: fmtCur(upperKeltner), color: "#ef4444" },
                { label: "Current Price", value: fmtCur(currentClose), color: "#3b82f6" },
                { label: "EMA 20", value: fmtCur(ema20), color: "#f59e0b" },
                { label: "Lower Keltner", value: fmtCur(lowerKeltner), color: "#22c55e" },
                { label: "Keltner Width", value: keltnerWidth != null ? `${fmt(keltnerWidth, 2)}%` : "—", color: "var(--text-muted)" },
              ].map((item) => (
                <div key={item.label} style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 90 }}>
                  <span style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600 }}>{item.label}</span>
                  <span style={{ fontSize: "0.85rem", fontWeight: 700, color: item.color }}>{item.value}</span>
                </div>
              ))}

              {/* Keltner gate status */}
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center" }}>
                <Badge pass={decision.keltner_gate} size="md" />
              </div>
            </div>

            {/* Contextual insight */}
            {upperKeltner != null && currentClose != null && (
              <div
                style={{
                  marginTop: 8,
                  padding: "8px 12px",
                  background: decision.keltner_gate === false ? "rgba(239,68,68,0.07)" : "rgba(34,197,94,0.07)",
                  borderRadius: 8,
                  border: `1px solid ${decision.keltner_gate === false ? "rgba(239,68,68,0.2)" : "rgba(34,197,94,0.2)"}`,
                  fontSize: "0.75rem",
                  color: "var(--text-secondary)",
                }}
              >
                {decision.keltner_gate === false
                  ? `⚠ Price (₹${fmt(currentClose)}) is near/at the Upper Keltner Band (₹${fmt(upperKeltner)}) — Keltner Gate: FAIL`
                  : `✓ Price is within the Keltner Channel — Keltner Gate: PASS`}
              </div>
            )}
          </div>
        ) : (
          // Fallback: static Keltner level display when no OHLCV
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              { label: "Upper Keltner", value: upperKeltner, color: "#ef4444", note: "Resistance / Gate boundary" },
              { label: "Current Price", value: currentClose, color: "#3b82f6", note: "Entry / current level" },
              { label: "EMA 20", value: ema20, color: "#f59e0b", note: "Trend anchor" },
              { label: "Lower Keltner", value: lowerKeltner, color: "#22c55e", note: "Support" },
            ].map((item, idx) => {
              const allVals = [upperKeltner, currentClose, ema20, lowerKeltner].filter((v): v is number => v != null);
              const min = Math.min(...allVals);
              const max = Math.max(...allVals);
              const pct = item.value != null ? ((item.value - min) / (max - min)) * 100 : 50;
              return (
                <div key={idx} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 100, fontSize: "0.7rem", color: item.color, fontWeight: 600, textAlign: "right" }}>
                    {item.label}
                  </div>
                  <div style={{ flex: 1, position: "relative" }}>
                    <div style={{ height: 4, background: "var(--surface-3)", borderRadius: 999, position: "relative" }}>
                      <div
                        style={{
                          position: "absolute",
                          left: `${pct}%`,
                          transform: "translateX(-50%)",
                          width: 12,
                          height: 12,
                          background: item.color,
                          borderRadius: "50%",
                          top: "50%",
                          marginTop: -6,
                          border: "2px solid var(--surface)",
                        }}
                      />
                    </div>
                  </div>
                  <div style={{ width: 80, fontSize: "0.82rem", fontWeight: 700, color: item.color }}>{fmtCur(item.value)}</div>
                  <div style={{ fontSize: "0.67rem", color: "var(--text-muted)", width: 120 }}>{item.note}</div>
                </div>
              );
            })}
            <div style={{ marginTop: 6, padding: "6px 10px", background: "var(--surface-3)", borderRadius: 8, fontSize: "0.72rem", color: "var(--text-muted)", display: "flex", justifyContent: "space-between" }}>
              <span>Keltner Width: {keltnerWidth != null ? `${fmt(keltnerWidth, 2)}%` : "—"}</span>
              <Badge pass={decision.keltner_gate} size="sm" />
            </div>
          </div>
        )}
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTIONS 3 + 4 — TREND STRUCTURE + VOLATILITY
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Trend Structure */}
        <div style={card}>
          <div style={sectionLabel}>
            Trend Structure
            <InfoTooltip content={TIPS.ema20} />
          </div>
          {/* Price vs EMA ladder */}
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {[
              { label: "Upper Keltner", value: upperKeltner, color: "#ef4444", note: "Resistance" },
              { label: "Current Price", value: currentClose, color: "#3b82f6", note: "Now" },
              { label: "EMA 20", value: ema20, color: "#f59e0b", note: "Trend anchor" },
              { label: "Lower Keltner", value: lowerKeltner, color: "#22c55e", note: "Support" },
            ]
              .filter((item) => item.value != null)
              .sort((a, b) => (b.value as number) - (a.value as number))
              .map((item, idx, arr) => {
                const vals = arr.map((i) => i.value as number);
                const min = Math.min(...vals);
                const max = Math.max(...vals);
                const range = max - min || 1;
                const pctFromBottom = ((item.value as number) - min) / range;
                return (
                  <div
                    key={idx}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "6px 0",
                      borderBottom: idx < arr.length - 1 ? "1px solid var(--border)" : "none",
                    }}
                  >
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: item.color,
                        flexShrink: 0,
                        boxShadow: `0 0 6px ${item.color}80`,
                      }}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600 }}>{item.label}</div>
                      <div style={{ fontSize: "0.9rem", fontWeight: 700, color: item.color }}>₹{fmt(item.value)}</div>
                    </div>
                    {/* Mini distance bar */}
                    <div style={{ width: 60 }}>
                      <div style={{ height: 3, background: "var(--surface-3)", borderRadius: 999, overflow: "hidden" }}>
                        <div style={{ width: `${pctFromBottom * 100}%`, height: "100%", background: item.color, opacity: 0.7 }} />
                      </div>
                    </div>
                  </div>
                );
              })}
          </div>

          {/* EMA distance indicator */}
          {emaPct != null && (
            <div style={{ marginTop: 12, padding: "8px 10px", background: emaPct >= 0 ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)", borderRadius: 8, border: `1px solid ${emaPct >= 0 ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}` }}>
              <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>Distance from EMA 20</div>
              <div style={{ fontSize: "1rem", fontWeight: 700, color: emaPct >= 0 ? "#4ade80" : "#f87171" }}>
                {emaPct >= 0 ? "+" : ""}{fmt(emaPct, 2)}%
              </div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>
                Trend: {emaPct >= 0 ? "BULLISH" : "BEARISH"}
              </div>
            </div>
          )}
        </div>

        {/* Volatility */}
        <div style={card}>
          <div style={sectionLabel}>
            Volatility
            <InfoTooltip content={TIPS.atr14} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* ATR value */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 600 }}>ATR 14</span>
                <span style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text)" }}>₹{fmt(atr14)}</span>
              </div>
              {atr14 != null && currentClose != null && (
                <ProgressBar
                  value={(atr14 / currentClose) * 100}
                  max={10}
                  color="#f59e0b"
                  label={`${fmt((atr14 / currentClose) * 100, 1)}%`}
                />
              )}
              <div style={{ fontSize: "0.67rem", color: "var(--text-muted)", marginTop: 4 }}>
                {atr14 != null && currentClose != null
                  ? `ATR is ${fmt((atr14 / currentClose) * 100, 1)}% of price — ${(atr14 / currentClose) * 100 > 3 ? "high" : "normal"} volatility`
                  : ""}
              </div>
            </div>

            {/* Keltner Width */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 600 }}>
                  Keltner Width
                  <InfoTooltip content={TIPS.keltnerWidth} />
                </span>
                <span style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text)" }}>
                  {keltnerWidth != null ? `${fmt(keltnerWidth, 2)}%` : "—"}
                </span>
              </div>
              {keltnerWidth != null && (
                <ProgressBar
                  value={keltnerWidth}
                  max={30}
                  color="#8b5cf6"
                  label={`${fmt(keltnerWidth, 1)}%`}
                />
              )}
            </div>

            {/* Volatility scale */}
            <div>
              <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", marginBottom: 6, fontWeight: 600 }}>Volatility Scale</div>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>LOW</span>
                <div style={{ flex: 1, height: 8, background: "linear-gradient(90deg, #22c55e, #f59e0b, #ef4444)", borderRadius: 999, position: "relative" }}>
                  {keltnerWidth != null && (
                    <div
                      style={{
                        position: "absolute",
                        left: `${Math.min(98, (keltnerWidth / 30) * 100)}%`,
                        top: "50%",
                        transform: "translate(-50%, -50%)",
                        width: 14,
                        height: 14,
                        background: "white",
                        borderRadius: "50%",
                        border: "3px solid #8b5cf6",
                        boxShadow: "0 0 6px rgba(139,92,246,0.6)",
                      }}
                    />
                  )}
                </div>
                <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>HIGH</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTIONS 5 + 6 — VOLUME + RSI
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Volume */}
        <div style={card}>
          <div style={sectionLabel}>
            Volume Confirmation
            <InfoTooltip content={TIPS.relVol} />
          </div>

          {/* Volume bar chart */}
          {volumeChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={130}>
              <BarChart data={volumeChartData} margin={{ top: 0, right: 4, bottom: 0, left: 0 }}>
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "var(--text-muted)" }} tickLine={false} axisLine={false} interval={4} />
                <Tooltip
                  contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 11, color: "var(--text)" }}
                  formatter={(v: unknown) => [fmtInt(v as number), "Volume"]}
                />
                <Bar dataKey="volume" radius={[2, 2, 0, 0]}>
                  {volumeChartData.map((entry, index) => (
                    <Cell
                      key={index}
                      fill={entry.isCurrent ? "#3b82f6" : "var(--surface-3)"}
                      opacity={entry.isCurrent ? 1 : 0.7}
                    />
                  ))}
                </Bar>
                {/* Average volume reference line */}
                {volumeSMA20 != null && (
                  <ReferenceLine
                    y={volumeSMA20}
                    stroke="#f59e0b"
                    strokeDasharray="4 3"
                    strokeWidth={1.5}
                  />
                )}
              </BarChart>
            </ResponsiveContainer>
          ) : (
            /* Fallback: static comparison bar */
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>
                  <span>20D Average</span>
                  <span>{fmtInt(volumeSMA20)}</span>
                </div>
                <ProgressBar value={100} max={100} color="var(--surface-3)" />
              </div>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4 }}>
                  <span>Current Volume</span>
                  <span>{fmtInt(currentVolume)}</span>
                </div>
                {currentVolume != null && volumeSMA20 != null && (
                  <ProgressBar value={currentVolume} max={volumeSMA20 * 2} color="#3b82f6" />
                )}
              </div>
            </div>
          )}

          {/* Volume stats */}
          <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Current Volume</span>
              <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text)" }}>{fmtInt(currentVolume)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>20D Average</span>
              <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)" }}>{fmtInt(volumeSMA20)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 6, borderTop: "1px solid var(--border)" }}>
              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                Relative Volume
                <InfoTooltip content={TIPS.relVol} />
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: "0.9rem", fontWeight: 700, color: (relativeVolume ?? 0) >= 1 ? "#4ade80" : "#f87171" }}>
                  {relativeVolume != null ? `${fmt(relativeVolume, 2)}×` : "—"}
                </span>
                <Badge pass={baseline.volume_condition} size="sm" />
              </div>
            </div>
          </div>
        </div>

        {/* RSI */}
        <div style={card}>
          <div style={sectionLabel}>
            RSI 14
            <InfoTooltip content={TIPS.rsi} />
          </div>

          {/* RSI big number */}
          <div style={{ textAlign: "center", marginBottom: 12 }}>
            <div style={{ fontSize: "2rem", fontWeight: 800, color: rsi14 != null && rsi14 >= rsiThreshold ? "#4ade80" : "#f87171" }}>
              {rsi14 != null ? fmt(rsi14, 1) : "—"}
            </div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>RSI 14-period</div>
          </div>

          {/* RSI gauge */}
          {rsi14 != null && <RSIGauge rsi={rsi14} threshold={rsiThreshold} />}

          {/* RSI zones */}
          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, textAlign: "center" }}>
            {[
              { zone: "Oversold", range: "< 30", color: "#ef4444", active: (rsi14 ?? 0) < 30 },
              { zone: "Healthy", range: "30–80", color: "#22c55e", active: (rsi14 ?? 0) >= 30 && (rsi14 ?? 0) < 80 },
              { zone: "Overbought", range: "> 80", color: "#f59e0b", active: (rsi14 ?? 0) >= 80 },
            ].map((z) => (
              <div
                key={z.zone}
                style={{
                  padding: "4px 6px",
                  borderRadius: 8,
                  background: z.active ? `${z.color}20` : "var(--surface-3)",
                  border: z.active ? `1px solid ${z.color}40` : "1px solid transparent",
                }}
              >
                <div style={{ fontSize: "0.65rem", fontWeight: z.active ? 700 : 400, color: z.active ? z.color : "var(--text-muted)" }}>{z.zone}</div>
                <div style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>{z.range}</div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Threshold: {rsiThreshold}</span>
            <Badge pass={baseline.rsi_condition} size="sm" />
          </div>
        </div>
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTIONS 7 + 8 — HEIKIN-ASHI + DECISION GATES
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Heikin-Ashi */}
        <div style={card}>
          <div style={sectionLabel}>
            Heikin-Ashi
            <InfoTooltip content={TIPS.ha} />
          </div>
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
            {/* Candle visual */}
            {haOpen != null && haHigh != null && haLow != null && haClose != null && (
              <div style={{ flexShrink: 0 }}>
                <HACandleDisplay open={haOpen} high={haHigh} low={haLow} close={haClose} />
                <div style={{ textAlign: "center", marginTop: 4 }}>
                  <span
                    style={{
                      fontSize: "0.65rem",
                      fontWeight: 700,
                      color: haDirection.toLowerCase().includes("bull") ? "#4ade80" : "#f87171",
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                    }}
                  >
                    {haDirection || "—"}
                  </span>
                </div>
              </div>
            )}
            {/* OHLC values */}
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
              {[
                { label: "HA Open", value: haOpen },
                { label: "HA High", value: haHigh },
                { label: "HA Low", value: haLow },
                { label: "HA Close", value: haClose },
              ].map((item) => (
                <div key={item.label} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78rem" }}>
                  <span style={{ color: "var(--text-muted)" }}>{item.label}</span>
                  <span style={{ fontWeight: 600, color: "var(--text)" }}>₹{fmt(item.value)}</span>
                </div>
              ))}
              <div style={{ paddingTop: 6, borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem" }}>
                  <span style={{ color: "var(--text-muted)" }}>Lower Wick</span>
                  <span style={{ fontWeight: 600, color: haLowerWick === 0 ? "#4ade80" : "#f87171" }}>
                    ₹{fmt(haLowerWick)} ({haLowerWickPct != null ? `${fmt(haLowerWickPct, 4)}%` : "—"})
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
            <Badge pass={baseline.ha_condition} size="md" />
          </div>
        </div>

        {/* Decision Gates */}
        <div style={card}>
          <div style={sectionLabel}>
            RE-001 Decision Gates
            <InfoTooltip content={TIPS.gate} />
          </div>

          {/* Gate grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {gates.map((g) => {
              const isPass = g.value === true;
              const isFail = g.value === false;
              const color = isFail ? "#ef4444" : isPass ? "#22c55e" : "var(--text-muted)";
              return (
                <div
                  key={g.key}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    padding: "12px 8px",
                    background: isFail ? "rgba(239,68,68,0.08)" : isPass ? "rgba(34,197,94,0.07)" : "var(--surface-3)",
                    border: `1px solid ${isFail ? "rgba(239,68,68,0.3)" : isPass ? "rgba(34,197,94,0.2)" : "var(--border)"}`,
                    borderRadius: 12,
                    gap: 6,
                  }}
                >
                  <div
                    style={{
                      fontSize: "1.3rem",
                      fontWeight: 700,
                      color,
                      lineHeight: 1,
                      filter: `drop-shadow(0 0 6px ${color}60)`,
                    }}
                  >
                    {isFail ? "✕" : isPass ? "✓" : "—"}
                  </div>
                  <div style={{ fontSize: "0.68rem", fontWeight: 700, color: "var(--text-secondary)", textAlign: "center" }}>
                    {g.label}
                  </div>
                  <div style={{ fontSize: "0.62rem", fontWeight: 700, color, letterSpacing: "0.06em" }}>
                    {gateLabel(g.value)}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Gate summary */}
          <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--surface-2)", borderRadius: 10, border: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>Gates Passed</div>
              <div style={{ fontSize: "1.1rem", fontWeight: 700, color: passedGates === totalGates ? "#4ade80" : "#f87171" }}>
                {passedGates} / {totalGates}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 2, textAlign: "right" }}>Final Decision</div>
              <div style={{ fontSize: "1.1rem", fontWeight: 800, color: decisionColor, letterSpacing: "0.05em", textAlign: "right" }}>
                {String(finalDecision).toUpperCase()}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTIONS 9 + 10 — SCORE + WHY THIS DECISION
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Score gauge + breakdown */}
        <div style={card}>
          <div style={sectionLabel}>
            Score Breakdown
            <InfoTooltip content={TIPS.composite} />
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            {/* Gauge */}
            <div style={{ flexShrink: 0 }}>
              <ScoreGauge score={compositeScore} threshold={buyThreshold} />
            </div>
            {/* Contribution bars */}
            <div style={{ flex: 1, paddingTop: 8 }}>
              {components.length > 0 ? (
                components.map((s, idx) => {
                  const weightPct = Math.round((s.weight ?? 0) * 100);
                  const barColor = s.raw >= 80 ? "#22c55e" : s.raw >= 50 ? "#3b82f6" : "#ef4444";
                  return (
                    <div key={idx} style={{ marginBottom: 10 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "var(--text-secondary)" }}>{s.component}</span>
                          <span style={{ fontSize: "0.62rem", color: "var(--text-muted)", background: "var(--surface-3)", padding: "1px 6px", borderRadius: 999 }}>{weightPct}%</span>
                        </div>
                        <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
                          <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text)" }}>{fmt(s.raw, 1)}</span>
                          <span style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>→ {fmt(s.contribution, 1)}</span>
                        </div>
                      </div>
                      <ProgressBar value={s.raw} max={100} color={barColor} />
                    </div>
                  );
                })
              ) : (
                <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Scoring breakdown not available</div>
              )}
            </div>
          </div>
        </div>

        {/* Why REJECT explanation */}
        {failedGates.length > 0 && (
          <div
            style={{
              ...card,
              border: "1px solid rgba(239,68,68,0.3)",
              background: "linear-gradient(135deg, var(--surface) 0%, rgba(239,68,68,0.03) 100%)",
            }}
          >
            <div style={sectionLabel}>Why {String(finalDecision).toUpperCase()} despite high score?</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {/* Score */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "rgba(34,197,94,0.08)", borderRadius: 8, border: "1px solid rgba(34,197,94,0.2)" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 600 }}>Composite Score</span>
                <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "#4ade80" }}>{fmt(compositeScore, 1)} / 100</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "rgba(34,197,94,0.08)", borderRadius: 8, border: "1px solid rgba(34,197,94,0.2)" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 600 }}>BUY Threshold</span>
                <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "#4ade80" }}>&gt; {buyThreshold}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "rgba(34,197,94,0.08)", borderRadius: 8, border: "1px solid rgba(34,197,94,0.2)" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 600 }}>Score Status</span>
                <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "#4ade80" }}>PASS</span>
              </div>
              {/* But indicator */}
              <div style={{ textAlign: "center", fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 700, letterSpacing: "0.05em" }}>
                — BUT —
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "rgba(239,68,68,0.08)", borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 600 }}>Decision Gates</span>
                <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "#f87171" }}>{passedGates} / {totalGates}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: "rgba(239,68,68,0.08)", borderRadius: 8, border: "1px solid rgba(239,68,68,0.25)" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 600 }}>Failed Gate{failedGates.length > 1 ? "s" : ""}</span>
                <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "#f87171" }}>{failedGates.map((g) => g.label).join(", ")}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", background: `${decisionColor}15`, borderRadius: 8, border: `1px solid ${decisionColor}40` }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 600 }}>Final Decision</span>
                <span style={{ fontSize: "0.9rem", fontWeight: 800, color: decisionColor }}>{String(finalDecision).toUpperCase()}</span>
              </div>
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", lineHeight: 1.5, margin: 0, fontStyle: "italic", paddingTop: 4 }}>
                Composite score alone does not determine the final RE-001 decision.
                All required decision gates must also pass.
              </p>
            </div>
          </div>
        )}

        {/* When all gates pass, show score card on full width */}
        {failedGates.length === 0 && (
          <div style={card}>
            <div style={sectionLabel}>Technical Health Scorecard</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {components.length > 0 ? (
                components.map((s, idx) => {
                  const barColor = s.raw >= 80 ? "#22c55e" : s.raw >= 50 ? "#3b82f6" : "#ef4444";
                  return (
                    <div key={idx}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", marginBottom: 4 }}>
                        <span style={{ color: "var(--text-secondary)", fontWeight: 600 }}>{s.component}</span>
                        <span style={{ fontWeight: 700, color: barColor }}>{fmt(s.raw, 1)}</span>
                      </div>
                      <ProgressBar value={s.raw} max={100} color={barColor} />
                    </div>
                  );
                })
              ) : (
                <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>No scoring data available</div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTION 15 — TECHNICAL HEALTH SCORECARD
          (standalone when gates fail, showing both WHY + scorecard)
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {failedGates.length > 0 && components.length > 0 && (
        <div style={card}>
          <div style={sectionLabel}>Technical Health Scorecard</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 14 }}>
            {components.map((s, idx) => {
              const barColor = s.raw >= 80 ? "#22c55e" : s.raw >= 50 ? "#3b82f6" : "#ef4444";
              return (
                <div key={idx} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "0.7rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{s.component}</span>
                    <span style={{ fontSize: "0.85rem", fontWeight: 700, color: barColor }}>{fmt(s.raw, 1)}</span>
                  </div>
                  <ProgressBar value={s.raw} max={100} color={barColor} />
                  <div style={{ fontSize: "0.62rem", color: "var(--text-muted)" }}>
                    Weight {Math.round((s.weight ?? 0) * 100)}% → Contrib {fmt(s.contribution, 1)}
                  </div>
                </div>
              );
            })}
            {/* Failed gate summary */}
            {failedGates.map((g) => (
              <div
                key={g.key}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  justifyContent: "center",
                  alignItems: "center",
                  background: "rgba(239,68,68,0.08)",
                  border: "1px solid rgba(239,68,68,0.25)",
                  borderRadius: 10,
                  padding: "10px 8px",
                }}
              >
                <div style={{ fontSize: "0.7rem", fontWeight: 700, color: "#f87171", textTransform: "uppercase", letterSpacing: "0.05em" }}>{g.label}</div>
                <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#f87171" }}>FAIL</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTIONS 11–13 — RISK / REWARD
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div style={card}>
        <div style={sectionLabel}>Risk / Reward Visualization</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, alignItems: "start" }}>
          {/* Price ladder */}
          <div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 12 }}>PRICE LADDER</div>
            {entryPrice && selectedSL && takeProfit && breakevenTrigger && rewardPerShare != null ? (
              <PriceLadder
                entry={entryPrice}
                stopLoss={selectedSL}
                breakeven={breakevenTrigger}
                takeProfit={takeProfit}
                riskPerShare={riskPerShare}
                rewardPerShare={rewardPerShare}
                rr={rrRatio}
              />
            ) : (
              <div style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Insufficient risk data</div>
            )}
          </div>

          {/* Risk details */}
          <div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 12 }}>RISK PARAMETERS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { label: "Entry", value: fmtCur(risk.entry), tip: undefined },
                { label: "ATR Stop", value: fmtCur(risk.atr_stop), tip: TIPS.atrStop },
                { label: "EMA Stop", value: fmtCur(risk.ema_stop), tip: TIPS.emaStop },
                { label: "Selected SL", value: fmtCur(risk.selected_sl), highlight: true, color: "#ef4444", tip: undefined },
                { label: "Risk / Share", value: `₹${fmt(risk.risk_per_share)}`, tip: undefined },
                { label: "Position Size", value: fmtInt(risk.position_size), tip: undefined },
                { label: "Take Profit", value: fmtCur(risk.take_profit), highlight: true, color: "#4ade80", tip: undefined },
                { label: "Risk / Reward", value: `1 : ${fmt(risk.risk_reward, 2)}`, highlight: true, color: rrRatio >= 3 ? "#4ade80" : "#f87171", tip: TIPS.rr },
                { label: "Breakeven Trigger", value: fmtCur(risk.breakeven_trigger), tip: TIPS.breakeven },
                { label: "EMA Trailing Stop", value: fmtCur(risk.current_ema_trailing_stop), tip: undefined },
              ].map((item) => (
                <div
                  key={item.label}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "5px 0",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                    {item.label}
                    {item.tip && <InfoTooltip content={item.tip} />}
                  </span>
                  <span
                    style={{
                      fontSize: item.highlight ? "0.88rem" : "0.8rem",
                      fontWeight: item.highlight ? 700 : 600,
                      color: item.color ?? "var(--text)",
                    }}
                  >
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* R:R Bar visualization */}
        {riskPerShare > 0 && rewardPerShare != null && rewardPerShare > 0 && (
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 10 }}>R:R VISUALIZATION</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: "0.65rem", color: "#f87171", fontWeight: 700, width: 52, textAlign: "right" }}>RISK</span>
                <div style={{ flex: 1, height: 14, background: "var(--surface-3)", borderRadius: 999, overflow: "hidden" }}>
                  <div
                    style={{
                      width: `${(riskPerShare / (riskPerShare + rewardPerShare)) * 100}%`,
                      height: "100%",
                      background: "linear-gradient(90deg, #ef4444, #f87171)",
                      borderRadius: 999,
                    }}
                  />
                </div>
                <span style={{ fontSize: "0.72rem", fontWeight: 700, color: "#f87171", minWidth: 52 }}>₹{fmt(riskPerShare)}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: "0.65rem", color: "#4ade80", fontWeight: 700, width: 52, textAlign: "right" }}>REWARD</span>
                <div style={{ flex: 1, height: 14, background: "var(--surface-3)", borderRadius: 999, overflow: "hidden" }}>
                  <div
                    style={{
                      width: `${(rewardPerShare / (riskPerShare + rewardPerShare)) * 100}%`,
                      height: "100%",
                      background: "linear-gradient(90deg, #22c55e, #4ade80)",
                      borderRadius: 999,
                    }}
                  />
                </div>
                <span style={{ fontSize: "0.72rem", fontWeight: 700, color: "#4ade80", minWidth: 52 }}>₹{fmt(rewardPerShare)}</span>
              </div>
            </div>
            <div style={{ textAlign: "center", marginTop: 8, fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Ratio: <strong style={{ color: rrRatio >= 3 ? "#4ade80" : "#f87171" }}>1 : {fmt(rrRatio, 2)}</strong>
              {" "} | Target: 1 : 3.0
            </div>
          </div>
        )}
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          SECTION 14 — WHAT THIS MEANS (Technical Interpretation)
      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {interpretation.length > 0 && (
        <div
          style={{
            ...card,
            background: "linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%)",
          }}
        >
          <div style={sectionLabel}>What This Means</div>
          <ul style={{ margin: 0, padding: "0 0 0 4px", listStyle: "none", display: "flex", flexDirection: "column", gap: 8 }}>
            {interpretation.map((bullet, idx) => {
              const isFail = bullet.toLowerCase().includes("fail") || bullet.toLowerCase().includes("below");
              const isPass = bullet.toLowerCase().includes("pass") || bullet.toLowerCase().includes("above") || bullet.toLowerCase().includes("confirmed") || bullet.toLowerCase().includes("bullish");
              return (
                <li
                  key={idx}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 10,
                    fontSize: "0.8rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.5,
                  }}
                >
                  <span
                    style={{
                      flexShrink: 0,
                      marginTop: 2,
                      fontSize: "0.7rem",
                      color: isFail ? "#f87171" : isPass ? "#4ade80" : "#3b82f6",
                      fontWeight: 700,
                    }}
                  >
                    {isFail ? "✕" : isPass ? "✓" : "→"}
                  </span>
                  <span>{bullet}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Earnings */}
      {(baseline.next_earnings_date || baseline.trading_days_until_earnings != null) && (
        <div style={{ ...card, padding: "12px 16px" }}>
          <div style={sectionLabel}>Earnings</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
            <div>
              <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>Next Earnings</div>
              <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text)" }}>{baseline.next_earnings_date || "—"}</div>
            </div>
            <div>
              <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>Trading Days Until</div>
              <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text)" }}>
                {baseline.trading_days_until_earnings != null ? String(baseline.trading_days_until_earnings) : "—"}
              </div>
            </div>
            <div style={{ marginLeft: "auto" }}>
              <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 600, marginBottom: 2 }}>Gate</div>
              <Badge pass={baseline.earnings_condition} size="md" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
