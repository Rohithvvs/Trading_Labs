import React from "react";
import type { StrategyResultRow, StrategyRunStatus } from "../../api_strategy_tester";
import type { SymbolDetail } from "../../types";
import { formatINRVal, formatPctVal } from "./StockHeader";
import type { FilterEvalItem } from "./types";

export function formatFilterDisplayName(name: string): string {
  if (!name) return "";
  return name
    .replace(/\s+null\b/gi, "")
    .replace(/\s+undefined\b/gi, "")
    .replace(/\bCLOSE\b/g, "Close")
    .replace(/\bHIGH\b/g, "High")
    .replace(/\bLOW\b/g, "Low")
    .replace(/\bOPEN\b/g, "Open")
    .replace(/\bVOLUME\b/g, "Volume")
    .replace(/\bAVG_VOLUME\b/g, "Avg Volume");
}

export interface TradePlanTabProps {
  stock: StrategyResultRow | null;
  runStatus: StrategyRunStatus | null;
  symbolDetail?: SymbolDetail | null;
  filterResults: FilterEvalItem[];
  strategyName: string;
  runId?: string;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export const TradePlanTab: React.FC<TradePlanTabProps> = ({
  stock,
  runStatus,
  symbolDetail,
  filterResults,
  strategyName,
  runId,
  isLoading = false,
  error = null,
  onRetry,
}) => {
  if (isLoading && !stock) {
    return (
      <div className="st-card st-tab-loading" data-testid="tradeplan-loading">
        Loading trade plan...
      </div>
    );
  }

  if (error && !stock) {
    return (
      <div className="st-card st-tab-error" data-testid="tradeplan-error">
        <p>{error || "Unable to load trade plan."}</p>
        {onRetry && (
          <button type="button" className="st-btn-primary" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    );
  }

  const signal = (stock?.signal || "WATCH").toUpperCase();
  const isIndicatorScan = (stock as any)?.source === "indicator_scanner" || String(runId || "").startsWith("IND-");
  const positionRules = (runStatus?.strategy_snapshot as any)?.position_rules || {};
  const position = (positionRules.side || (runStatus?.strategy_snapshot as any)?.side || "LONG").toUpperCase();
  const entryPrice = stock?.entry_price ?? null;
  const exitPrice = stock?.exit_price ?? null;
  const returnPct = stock?.return_pct ?? null;
  const resolvedRun = runId || runStatus?.run_id || (stock as any)?.run_id || "STR-20260826-001";

  // Real risk & target values if provided, otherwise "—"
  const stopLoss =
    (stock as any)?.stop_loss ??
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.stop_loss ??
    null;

  const target =
    (stock as any)?.target ??
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.target_1 ??
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.target ??
    null;

  const riskReward =
    (stock as any)?.risk_reward ??
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.risk_reward_ratio ??
    ((symbolDetail as any)?.recommendation?.trade_plans?.[0] as any)?.risk_reward ??
    null;

  const exitRule =
    positionRules.exit_rule ||
    positionRules.return_method ||
    (isIndicatorScan
      ? "Scan only — no trade is opened"
      : strategyName.toLowerCase().includes("52-week")
        ? "Close < Trailing Stop"
        : "EOD (End of Day)");

  const calcFormula = isIndicatorScan
    ? "(Close / Close t-252 − 1) × 100"
    : `((Exit - Entry) / Entry) × 100`;
  const calcExact =
    entryPrice != null && exitPrice != null
      ? `((${exitPrice.toFixed(2)} - ${entryPrice.toFixed(2)}) / ${entryPrice.toFixed(2)}) × 100`
      : "—";

  return (
    <section className="st-stock-overview-grid" aria-label="Stock trade plan" data-testid="card-detail-tradeplan">
      {/* Card 1: Strategy & Position Plan */}
      <div className="st-card" data-testid="card-detail-tradeplan-overview">
        <h2 className="st-card-title">Strategy & Position Plan</h2>
        <div className="st-detail-kv-list">
          <div className="st-detail-kv-row">
            <span>Signal</span>
            <div>
              <span className={`st-badge-signal ${signal}`} data-testid="tradeplan-signal">
                {signal}
              </span>
            </div>
          </div>
          <div className="st-detail-kv-row">
            <span>Position</span>
            <span style={{ color: position === "LONG" ? "#4ade80" : "#f87171", fontWeight: 700 }}>
              {position}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>Entry Price</span>
            <span style={{ fontWeight: 600 }}>{formatINRVal(entryPrice)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Exit Price</span>
            <span style={{ fontWeight: 600 }}>{formatINRVal(exitPrice)}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Strategy</span>
            <span style={{ color: "var(--st-cyan)", fontWeight: 600 }}>{strategyName}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Execution Status</span>
            <span className="st-status-badge st-status-badge--completed">
              {stock?.status || "completed"}
            </span>
          </div>
        </div>
      </div>

      {/* Card 2: Risk Management & Targets */}
      <div className="st-card" data-testid="card-detail-tradeplan-risk">
        <h2 className="st-card-title">Risk Management & Targets</h2>
        <div className="st-detail-kv-list">
          <div className="st-detail-kv-row">
            <span>Stop Loss</span>
            <span>{stopLoss != null ? formatINRVal(stopLoss) : "—"}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Target</span>
            <span>{target != null ? formatINRVal(target) : "—"}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Risk / Reward</span>
            <span>
              {riskReward != null
                ? typeof riskReward === "number"
                  ? riskReward.toFixed(2)
                  : String(riskReward)
                : "—"}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>Exit Rule</span>
            <span style={{ color: "#cbd5e1", fontWeight: 500 }}>{exitRule}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Timeframe</span>
            <span>{runStatus?.timeframe || "1 Day"}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Run ID</span>
            <span style={{ color: "var(--st-cyan)", fontWeight: 600 }}>{resolvedRun}</span>
          </div>
        </div>
      </div>

      {/* Card 3: Entry Conditions */}
      <div className="st-card" data-testid="card-detail-tradeplan-conditions">
        <h2 className="st-card-title">{isIndicatorScan ? "Scan Filters" : "Entry Conditions"}</h2>
        {signal === "REJECT" && !isIndicatorScan ? (
          <p className="st-reject-not-a-trade" data-testid="reject-not-a-trade">
            Failed entry conditions mean this name was not selected. Return % is buy-and-hold from the
            window start to the scan bar (WINDOW_END), not a strategy trade.
          </p>
        ) : null}
        {isIndicatorScan ? (
          <p className="st-reject-not-a-trade" data-testid="indicator-scan-not-a-trade">
            Each row is an entry condition from the selected strategy, evaluated on the scan bar.
          </p>
        ) : null}
        <div className="st-filter-eval-list">
          {filterResults.length === 0 ? (
            <div className="st-filter-eval-item">
              <span className="st-filter-eval-name">No scan filters recorded for this run.</span>
            </div>
          ) : (
            filterResults.map((f, i) => (
              <div key={f.name || i} className="st-filter-eval-item">
                <span className="st-filter-eval-name">{formatFilterDisplayName(f.name)}</span>
                <span className={`st-filter-eval-status ${f.passed ? "passed" : "failed"}`}>
                  {f.passed ? "✓ Passed" : "✕ Failed"}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Card 4: Exit Rule & Return Mechanics */}
      <div className="st-card" data-testid="card-detail-tradeplan-exit">
        <h2 className="st-card-title">Return Calculation & Mechanics</h2>
        <div className="st-detail-kv-list">
          <div className="st-detail-kv-row">
            <span>Return %</span>
            <span
              style={{
                fontWeight: 700,
                fontSize: "0.95rem",
                color: (returnPct ?? 0) >= 0 ? "#4ade80" : "#f87171",
              }}
            >
              {formatPctVal(returnPct)}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>Formula</span>
            <span style={{ fontSize: "0.75rem", color: "#94a3b8", fontFamily: "monospace" }}>
              {calcFormula}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>Calculation</span>
            <span style={{ fontSize: "0.75rem", color: "#94a3b8", fontFamily: "monospace" }}>
              {calcExact}
            </span>
          </div>
          <div className="st-detail-kv-row">
            <span>Exit Rule</span>
            <span style={{ color: "var(--st-cyan)", fontWeight: 600 }}>{exitRule}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Position Mode</span>
            <span style={{ color: "#cbd5e1" }}>EOD (End of Day)</span>
          </div>
        </div>
      </div>
    </section>
  );
};
