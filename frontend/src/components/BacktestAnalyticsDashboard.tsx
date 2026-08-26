import { useState } from "react";
import { PerformanceAnalysis } from "./PerformanceAnalysis";
import { TradesAnalysis } from "./TradesAnalysis";
import { TradingViewBacktestOverview } from "./TradingViewBacktest";

export type BacktestRange = "1Y" | "3Y" | "5Y" | "8Y" | "ALL" | "CUSTOM";
export type ChartView = "equity" | "benchmark" | "drawdown";
export type TradeFilter = "ALL" | "WINNERS" | "LOSERS" | "OPEN";
export type TradeTypeFilter = "ALL" | "LONG" | "SHORT";
export type SortColumn = "index" | "entry_date" | "exit_date" | "pnl_percent" | "holding_days" | "entry_price" | "exit_price";
export type SortDirection = "asc" | "desc";

export type DashboardTrade = {
  trade_id?: string | null;
  entry_date?: string | null;
  exit_date?: string | null;
  type?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  pnl_percent?: number | null;
  holding_days?: number | null;
  reason?: string | null;
  exit_reason?: string | null;
  open?: boolean;
  outcome?: string | null;
  net_pnl?: number | null;
  commission?: number | null;
  slippage?: number | null;
  signal_time?: string | null;
  entry_fill_time?: string | null;
  exit_fill_time?: string | null;
};

export type BacktestDashboardModel = {
  window?: string;
  period_start?: string | null;
  period_end?: string | null;
  total_return?: number | null;
  cagr?: number | null;
  max_drawdown?: number | null;
  max_drawdown_inr?: number | null;
  win_rate?: number | null;
  trade_count?: number | null;
  net_pnl?: number | null;
  gross_profit?: number | null;
  gross_loss?: number | null;
  commission?: number | null;
  outlier_pnl?: number | null;
  sharpe_ratio?: number | null;
  profit_factor?: number | null;
  profit_factor_infinite?: boolean;
  initial_capital?: number | null;
  ending_capital?: number | null;
  avg_trade_return?: number | null;
  max_consecutive_losses?: number | null;
  verdict?: string | null;
  equity_curve?: { date?: string; label?: string; equity: number }[];
  drawdown_curve?: { date?: string; label?: string; drawdown: number }[];
  benchmark_curve?: { date?: string; label?: string; close?: number; equity?: number }[];
  monthly_returns?: { month: string; return: number | null }[];
  trades?: DashboardTrade[];
  best_trade?: DashboardTrade | null;
  worst_trade?: DashboardTrade | null;
  top_winning?: DashboardTrade[];
  top_losing?: DashboardTrade[];
  never_selected_in_window?: boolean;
  unavailable_reason?: string | null;
  replay_kind?: string | null;
  symbol?: string | null;
  data_hash?: string | null;
  coverage?: {
    requested_start?: string | null;
    requested_end?: string | null;
    actual_start?: string | null;
    actual_end?: string | null;
    candle_count?: number | null;
    expected_sessions?: number | null;
    coverage_ratio?: number | null;
  } | null;
  strategy_id?: string | null;
  strategy_name?: string | null;
  ledger?: {
    total_trades?: number;
    winning_trades?: number;
    losing_trades?: number;
    breakeven_trades?: number;
    win_rate?: number | null;
    average_profit?: number | null;
    average_loss?: number | null;
    expected_payoff?: number | null;
    expected_payoff_inr?: number | null;
    largest_profit?: number | null;
    largest_loss?: number | null;
    largest_profit_inr?: number | null;
    largest_loss_inr?: number | null;
    gross_profit?: number | null;
    gross_loss?: number | null;
    net_pnl?: number | null;
    commission?: number | null;
    outlier_pnl?: number | null;
    outlier_trades?: number;
    source?: string;
  } | null;
  execution?: {
    profile?: string;
    order_fill_delay?: string;
    historical_fill_mode?: string;
    trail_touch?: string;
  } | null;
  incomplete?: boolean;
  trade_distribution?: {
    total_trades?: number;
    winners?: number;
    losers?: number;
    breakevens?: number;
    open_trades?: number;
    source?: string;
  } | null;
  persisted?: boolean;
  strategy_tester?: {
    total_pnl?: number | null;
    max_drawdown?: number | null;
    total_trades?: number | null;
    profitable_trades?: number | null;
    losing_trades?: number | null;
    breakeven?: number | null;
    profit_factor?: number | null;
    gross_profit?: number | null;
    gross_loss?: number | null;
    commission?: number | null;
    expected_payoff?: number | null;
    largest_profit?: number | null;
    largest_loss?: number | null;
    average_winning_trade?: number | null;
    average_losing_trade?: number | null;
    outlier_pnl?: number | null;
  } | null;
};

const UP = "#38b26d";
const DOWN = "#c05c54";
const BENCH = "#3b82f6";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function fmtPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

function fmtNum(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function fmtMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function fmtPnl(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  const abs = Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n < 0) return `−₹${abs}`;
  if (n > 0) return `+₹${abs}`;
  return `₹${abs}`;
}

function fmtShare(count: number, total: number): string {
  if (!total) return `${count} / 0`;
  return `${count} / ${total} = ${((count / total) * 100).toFixed(2)}%`;
}

function fmtPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `₹${Number(value).toFixed(2)}`;
}

function fmtDate(value?: string | null): string {
  if (!value) return "--";
  return String(value).slice(0, 10);
}

function pnlClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return value >= 0 ? "bt-pos" : "bt-neg";
}

function heatColor(r: number | undefined): string {
  if (r === undefined || Number.isNaN(Number(r))) return "var(--bg-card, var(--surface))";
  if (r >= 0.1) return "var(--positive, #38b26d)";
  if (r >= 0.04) return "rgba(56, 178, 109, 0.7)";
  if (r > 0) return "rgba(56, 178, 109, 0.35)";
  if (r <= -0.1) return "var(--negative, #c05c54)";
  if (r <= -0.04) return "rgba(192, 92, 84, 0.7)";
  return "rgba(192, 92, 84, 0.35)";
}

function deriveStrength(model: BacktestDashboardModel | null): { label: string; tone: "favorable" | "mixed" | "weak" | "insufficient" } {
  if (!model) return { label: "Insufficient Data", tone: "insufficient" };
  const reason = (model as { unavailable_reason?: string | null }).unavailable_reason;
  if (reason === "insufficient_history" || model.coverage?.coverage_ratio === 0 || (model.trade_count === 0 && !model.equity_curve?.length)) {
    return { label: "Insufficient Data", tone: "insufficient" };
  }
  const v = (model.verdict || "").toLowerCase();
  if (v === "favorable") return { label: "Favorable", tone: "favorable" };
  if (v === "weak" || reason === "backtest_failed") return { label: "Weak", tone: "weak" };
  if (v === "mixed") return { label: "Mixed", tone: "mixed" };

  if (model.total_return != null) {
    if (model.total_return > 0 && (model.win_rate ?? 0) >= 45 && (model.profit_factor ?? 0) >= 1) {
      return { label: "Favorable", tone: "favorable" };
    }
    if (model.total_return < 0 && (model.win_rate ?? 0) < 40) {
      return { label: "Weak", tone: "weak" };
    }
    return { label: "Mixed", tone: "mixed" };
  }
  return { label: "Insufficient Data", tone: "insufficient" };
}

export function BacktestAnalyticsDashboard({
  model,
  range,
  onRangeChange,
  startDate,
  endDate,
  onCustomRange,
  loading,
  loadError,
  symbol,
  strategyName,
  timeframe = "1D",
}: {
  model: BacktestDashboardModel | null;
  range: BacktestRange;
  onRangeChange: (next: BacktestRange) => void;
  startDate?: string;
  endDate?: string;
  onCustomRange?: (start: string, end: string) => void;
  loading?: boolean;
  loadError?: string | null;
  symbol?: string;
  strategyName?: string;
  timeframe?: string;
}) {
  const [showConfigModal, setShowConfigModal] = useState(false);

  const currentSymbol = symbol || model?.symbol || "--";
  const currentStrategy = strategyName || model?.strategy_name || "52-Week High Breakout";
  const currentPeriodText = `${fmtDate(model?.period_start || startDate)} → ${fmtDate(model?.period_end || endDate)}`;
  const currentInitialCapital = fmtMoney(model?.initial_capital ?? 100000);

  const yearsLabel =
    range === "CUSTOM"
      ? `${fmtDate(startDate || model?.period_start)} → ${fmtDate(endDate || model?.period_end)}`
      : range === "ALL"
        ? "All"
        : `${range.replace("Y", "")} Years`;

  const periodControls = (
    <div className="bt-range" role="group" aria-label="Backtest period">
      {(["1Y", "3Y", "5Y", "8Y", "ALL"] as BacktestRange[]).map((r) => (
        <button
          key={r}
          type="button"
          className={`bt-range__btn ${range === r ? "is-active" : ""}`}
          onClick={() => onRangeChange(r)}
        >
          {r === "ALL" ? "All" : r}
        </button>
      ))}
      <label className="bt-date">
        <span>From</span>
        <input
          type="date"
          aria-label="Backtest start date"
          value={startDate || ""}
          max={endDate || undefined}
          onChange={(e) => {
            const next = e.target.value;
            if (next && endDate) onCustomRange?.(next, endDate);
          }}
        />
      </label>
      <label className="bt-date">
        <span>To</span>
        <input
          type="date"
          aria-label="Backtest end date"
          value={endDate || ""}
          min={startDate || undefined}
          onChange={(e) => {
            const next = e.target.value;
            if (startDate && next) onCustomRange?.(startDate, next);
          }}
        />
      </label>
    </div>
  );

  // Loading State
  if (loading) {
    return (
      <div className="bt-dash bt-dash--loading" data-testid="backtest-loading-state">
        <TradingViewBacktestOverview
          model={null}
          range={range}
          onRangeChange={onRangeChange}
          startDate={startDate}
          endDate={endDate}
          onCustomRange={onCustomRange}
          loading={true}
          symbol={currentSymbol}
          strategyName={currentStrategy}
          currency="INR"
          onOpenConfigModal={() => setShowConfigModal(true)}
        />
        <div style={{ marginTop: "16px", textAlign: "center" }} className="muted-copy">
          Running {yearsLabel.toLowerCase()} backtest for {currentSymbol}...
        </div>
      </div>
    );
  }

  // Load Error State
  if (loadError && !model) {
    return (
      <section className="subpanel" role="alert" data-testid="backtest-error-state">
        <h3>Unable to load backtest data</h3>
        <p>{loadError}</p>
        <div style={{ marginTop: "12px" }}>{periodControls}</div>
      </section>
    );
  }

  // Empty / No Model State
  if (!model) {
    return (
      <section className="subpanel" data-testid="backtest-empty-state">
        <h3>No backtest support</h3>
        <p>The backend confirmed no historical backtest is available for this symbol and strategy.</p>
        <div style={{ marginTop: "12px" }}>{periodControls}</div>
      </section>
    );
  }

  const cardsEmpty =
    model.total_return == null &&
    model.cagr == null &&
    model.max_drawdown == null &&
    model.win_rate == null &&
    model.trade_count == null &&
    model.sharpe_ratio == null &&
    model.profit_factor == null &&
    !model.profit_factor_infinite;

  const unavailableReason =
    (model as { unavailable_reason?: string | null }).unavailable_reason ||
    (model.never_selected_in_window ? "never_selected_in_window" : null);

  return (
    <div className="bt-dash" data-testid="backtest-analytics-dashboard">
      {/* Unavailable reason notice if present */}
      {(cardsEmpty || unavailableReason) && (
        <section className="subpanel bt-unavailable-alert" data-testid="backtest-unavailable">
          <div className="bt-unavailable-alert__content">
            <span className="bt-unavailable-alert__badge">Notice</span>
            <p>
              {unavailableReason === "never_selected_in_window"
                ? "Reason: this name was not selected in the strategy book during the selected window."
                : unavailableReason === "backtest_failed"
                  ? "Reason: attribution for this name failed."
                  : unavailableReason === "insufficient_history"
                    ? `Insufficient historical data for the requested ${yearsLabel.toLowerCase()} backtest.` +
                      (model.coverage?.requested_start
                        ? ` Requested: ${model.coverage.requested_start} → ${model.coverage.requested_end}. Available: ${model.coverage.actual_start ?? "none"} → ${model.coverage.actual_end ?? "none"} (${model.coverage.candle_count ?? 0} sessions).`
                        : "")
                    : cardsEmpty
                      ? "Reason: no completed backtest metrics were returned for this strategy and period."
                      : "Reason: backtest data unavailable."}
            </p>
          </div>
        </section>
      )}

      {/* SECTION: TRADINGVIEW-STYLE BACKTEST OVERVIEW + LIST OF TRADES */}
      <TradingViewBacktestOverview
        model={model}
        range={range}
        onRangeChange={onRangeChange}
        startDate={startDate}
        endDate={endDate}
        onCustomRange={onCustomRange}
        loading={loading}
        symbol={currentSymbol}
        strategyName={currentStrategy}
        currency="INR"
        onOpenConfigModal={() => setShowConfigModal(true)}
      />

      {/* SECTION: TRADINGVIEW-STYLE PERFORMANCE ANALYSIS */}
      <PerformanceAnalysis
        model={model}
        loading={loading}
        initialCapital={model.initial_capital ?? 100000}
      />

      {/* SECTION: TRADINGVIEW-STYLE TRADES ANALYSIS */}
      <TradesAnalysis
        model={model}
        loading={loading}
        initialCapital={model.initial_capital ?? 100000}
      />

      {/* CONFIGURATION DETAILS MODAL */}
      {showConfigModal && (
        <div className="bt-modal-backdrop" onClick={() => setShowConfigModal(false)}>
          <div className="bt-modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="bt-modal-panel__header">
              <h3>Backtest Configuration</h3>
              <button
                type="button"
                className="bt-modal-close"
                onClick={() => setShowConfigModal(false)}
                aria-label="Close configuration modal"
              >
                ✕
              </button>
            </div>
            <div className="bt-modal-panel__body">
              <dl className="bt-summary-list">
                <div className="bt-summary-list__row">
                  <dt>Target Stock</dt>
                  <dd>{currentSymbol}</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Strategy</dt>
                  <dd>{currentStrategy}</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Timeframe</dt>
                  <dd>{timeframe}</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Backtest Window</dt>
                  <dd>{range} ({currentPeriodText})</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Initial Capital</dt>
                  <dd>{currentInitialCapital}</dd>
                </div>
                <div className="bt-summary-list__row">
                  <dt>Replay Mode</dt>
                  <dd>{model.replay_kind || "symbol_window"}</dd>
                </div>
                {model.data_hash && (
                  <div className="bt-summary-list__row">
                    <dt>Dataset Hash</dt>
                    <dd style={{ fontSize: "0.75rem", fontFamily: "monospace" }}>{model.data_hash.slice(0, 16)}...</dd>
                  </div>
                )}
                {model.coverage && (
                  <>
                    <div className="bt-summary-list__row">
                      <dt>Candle Sessions</dt>
                      <dd>{model.coverage.candle_count ?? "--"} bars</dd>
                    </div>
                    <div className="bt-summary-list__row">
                      <dt>Coverage Ratio</dt>
                      <dd>{model.coverage.coverage_ratio != null ? `${(model.coverage.coverage_ratio * 100).toFixed(1)}%` : "--"}</dd>
                    </div>
                  </>
                )}
              </dl>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export { fmtPct, fmtNum, fmtMoney, fmtPnl, fmtShare, fmtPrice, fmtDate, pnlClass, heatColor, deriveStrength };
