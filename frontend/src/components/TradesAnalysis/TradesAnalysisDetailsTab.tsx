import React from "react";
import type { TradesAnalysisModel } from "../../utils/tradeAnalysisCalculator";

interface TradesAnalysisDetailsTabProps {
  model: TradesAnalysisModel;
}

function fmtPnl(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  const abs = Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n < 0) return `−₹${abs}`;
  if (n > 0) return `+₹${abs}`;
  return `₹${abs}`;
}

function fmtPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  const n = Number(val);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function fmtNum(val: number | null | undefined, digits = 2): string {
  if (val == null || Number.isNaN(Number(val))) return "--";
  return Number(val).toFixed(digits);
}

function pnlClass(val: number | null | undefined): string {
  if (val == null || Number.isNaN(Number(val))) return "";
  return Number(val) >= 0 ? "bt-pos" : "bt-neg";
}

export function TradesAnalysisDetailsTab({ model }: TradesAnalysisDetailsTabProps) {
  const { details } = model;
  const pf = details.profitFactorInfinite ? "∞" : fmtNum(details.profitFactor);

  return (
    <div className="bt-ta-details-tab" data-testid="trades-analysis-details-tab-content">
      <div className="bt-ta-details-grid">
        {/* Section 1: Trade Overview */}
        <div className="bt-ta-details-card">
          <h4 className="bt-ta-card-title">Trade Overview & Distribution</h4>
          <dl className="bt-summary-list">
            <div className="bt-summary-list__row">
              <dt>Total trades</dt>
              <dd><strong>{details.totalTrades}</strong></dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Winning trades</dt>
              <dd className="bt-pos">
                {details.winCount} ({details.winRate != null ? `${details.winRate.toFixed(2)}%` : "--"})
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Losing trades</dt>
              <dd className="bt-neg">
                {details.lossCount} ({details.lossRate != null ? `${details.lossRate.toFixed(2)}%` : "--"})
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Breakeven trades</dt>
              <dd>
                {details.breakEvenCount} ({details.breakEvenRate != null ? `${details.breakEvenRate.toFixed(2)}%` : "--"})
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Win rate</dt>
              <dd className="bt-pos">{details.winRate != null ? `${details.winRate.toFixed(2)}%` : "--"}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Loss rate</dt>
              <dd className="bt-neg">{details.lossRate != null ? `${details.lossRate.toFixed(2)}%` : "--"}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Breakeven rate</dt>
              <dd>{details.breakEvenRate != null ? `${details.breakEvenRate.toFixed(2)}%` : "--"}</dd>
            </div>
          </dl>
        </div>

        {/* Section 2: Financial Performance & Payoff */}
        <div className="bt-ta-details-card">
          <h4 className="bt-ta-card-title">Financial Performance & Payoff</h4>
          <dl className="bt-summary-list">
            <div className="bt-summary-list__row">
              <dt>Gross profit</dt>
              <dd className="bt-pos">{fmtPnl(details.grossProfitInr)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Gross loss</dt>
              <dd className="bt-neg">{fmtPnl(details.grossLossInr)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Net profit</dt>
              <dd className={pnlClass(details.netProfitInr)}>{fmtPnl(details.netProfitInr)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Profit factor</dt>
              <dd><strong>{pf}</strong></dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Expected payoff</dt>
              <dd className={pnlClass(details.expectedPayoffInr ?? details.expectedPayoffPct)}>
                {details.expectedPayoffInr != null ? fmtPnl(details.expectedPayoffInr) : "--"}
                {details.expectedPayoffPct != null ? ` (${fmtPct(details.expectedPayoffPct)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average trade return</dt>
              <dd className={pnlClass(details.avgTradeInr ?? details.avgTradePct)}>
                {details.avgTradeInr != null ? fmtPnl(details.avgTradeInr) : "--"}
                {details.avgTradePct != null ? ` (${fmtPct(details.avgTradePct)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Commission</dt>
              <dd>{fmtPnl(details.commissionInr)}</dd>
            </div>
          </dl>
        </div>

        {/* Section 3: Trade Averages & Extremes */}
        <div className="bt-ta-details-card">
          <h4 className="bt-ta-card-title">Trade Averages & Extremes</h4>
          <dl className="bt-summary-list">
            <div className="bt-summary-list__row">
              <dt>Average winning trade</dt>
              <dd className="bt-pos">
                {details.avgWinInr != null ? fmtPnl(details.avgWinInr) : "--"}
                {details.avgWinPct != null ? ` (${fmtPct(details.avgWinPct)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average losing trade</dt>
              <dd className="bt-neg">
                {details.avgLossInr != null ? fmtPnl(details.avgLossInr) : "--"}
                {details.avgLossPct != null ? ` (${fmtPct(details.avgLossPct)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Win / Loss ratio</dt>
              <dd>{fmtNum(details.winLossRatio)}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Largest profit</dt>
              <dd className="bt-pos">
                {details.largestProfitInr != null ? fmtPnl(details.largestProfitInr) : "--"}
                {details.largestProfitPct != null ? ` (${fmtPct(details.largestProfitPct)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Largest loss</dt>
              <dd className="bt-neg">
                {details.largestLossInr != null ? fmtPnl(details.largestLossInr) : "--"}
                {details.largestLossPct != null ? ` (${fmtPct(details.largestLossPct)})` : ""}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Outliers P&L</dt>
              <dd className={pnlClass(details.outlierPnlInr)}>
                {fmtPnl(details.outlierPnlInr)}
                {details.outlierTradesCount ? ` (${details.outlierTradesCount} trades)` : ""}
              </dd>
            </div>
          </dl>
        </div>

        {/* Section 4: Holding Duration */}
        <div className="bt-ta-details-card">
          <h4 className="bt-ta-card-title">Holding Duration (Days)</h4>
          <dl className="bt-summary-list">
            <div className="bt-summary-list__row">
              <dt>Average holding period</dt>
              <dd>{details.avgHoldingDays != null ? `${details.avgHoldingDays.toFixed(1)} days` : "--"}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average winning trade duration</dt>
              <dd className="bt-pos">{details.avgWinHoldingDays != null ? `${details.avgWinHoldingDays.toFixed(1)} days` : "--"}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average losing trade duration</dt>
              <dd className="bt-neg">{details.avgLossHoldingDays != null ? `${details.avgLossHoldingDays.toFixed(1)} days` : "--"}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Median holding period</dt>
              <dd>{details.medianHoldingDays != null ? `${details.medianHoldingDays} days` : "--"}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
