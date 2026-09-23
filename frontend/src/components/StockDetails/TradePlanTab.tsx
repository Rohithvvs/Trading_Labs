import React from "react";
import type { StrategyResultRow, StrategyRunStatus } from "../../api_strategy_tester";
import type { SymbolDetail } from "../../types";
import { resolveTradePlanDetails } from "../../utils/indicatorScanDetail";
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

  const plan = resolveTradePlanDetails({
    stock,
    symbolDetail,
    runStatus,
    runId,
  });

  const signal = plan.signal;
  const isIndicatorScan = plan.isIndicatorScan;
  const positionRules = (runStatus?.strategy_snapshot as any)?.position_rules || {};
  const position = plan.position;
  const entryPrice = plan.entryPrice;
  const exitPrice = plan.exitPrice;
  const returnPct = stock?.return_pct ?? null;
  const resolvedRun = runId || runStatus?.run_id || (stock as any)?.run_id || "STR-20260826-001";

  const closePrice =
    stock?.close ??
    (stock as any)?.ohlcv?.close ??
    (stock as any)?.candidate_entry_price ??
    (isIndicatorScan ? exitPrice : null) ??
    entryPrice;
  const closeT252 =
    (stock?.indicators as any)?.["Close t-252"] ??
    (stock as any)?.close_t252 ??
    (isIndicatorScan && entryPrice != null && entryPrice !== closePrice ? entryPrice : null) ??
    (closePrice != null && returnPct != null && returnPct !== 0 ? Math.round((closePrice / (1 + returnPct / 100)) * 100) / 100 : null);

  const displayEntryPrice = plan.displayEntryPrice;
  const displayExitPrice = plan.displayExitPrice;
  const stopLoss = plan.stopLoss;
  const target = plan.target;
  const riskAmount = plan.riskAmount;
  const riskPct = plan.riskPct;
  const rewardAmount = plan.rewardAmount;
  const rewardPct = plan.rewardPct;

  const formatRiskText = () => {
    if (riskAmount == null) return "—";
    const inr = formatINRVal(riskAmount);
    return riskPct != null ? `${inr} (${riskPct.toFixed(1)}%)` : inr;
  };

  const formatRewardText = () => {
    if (rewardAmount == null) return "—";
    const inr = formatINRVal(rewardAmount);
    return rewardPct != null ? `${inr} (${rewardPct.toFixed(1)}%)` : inr;
  };

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
  const calcExact = isIndicatorScan
    ? closePrice != null && closeT252 != null
      ? `((${closePrice.toFixed(2)} / ${closeT252.toFixed(2)} − 1) × 100)`
      : "—"
    : entryPrice != null && exitPrice != null
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
            <span style={{ fontWeight: 600 }}>{displayEntryPrice != null ? formatINRVal(displayEntryPrice) : "—"}</span>
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
            <span>Risk</span>
            <span style={{ color: "#f87171", fontWeight: 600 }}>{formatRiskText()}</span>
          </div>
          <div className="st-detail-kv-row">
            <span>Reward</span>
            <span style={{ color: "#4ade80", fontWeight: 600 }}>{formatRewardText()}</span>
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
