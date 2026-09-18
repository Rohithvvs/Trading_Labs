import React from "react";
import type { TradesAnalysisModel } from "../../utils/tradeAnalysisCalculator";

interface StreaksTabProps {
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

export function StreaksTab({ model }: StreaksTabProps) {
  const { streaks } = model;

  return (
    <div className="bt-ta-streaks-tab" data-testid="streaks-tab-content">
      {/* Top Level Streak Metric Cards */}
      <div className="bt-ta-metrics-grid">
        <div className="bt-ta-metric-card">
          <span className="bt-ta-metric-label">Max winning streak</span>
          <div className="bt-ta-metric-value-row">
            <strong className="bt-ta-metric-value bt-pos">{streaks.maxWinStreak}</strong>
            <span className="bt-ta-metric-sub">trades</span>
          </div>
        </div>

        <div className="bt-ta-metric-card">
          <span className="bt-ta-metric-label">Max losing streak</span>
          <div className="bt-ta-metric-value-row">
            <strong className="bt-ta-metric-value bt-neg">{streaks.maxLossStreak}</strong>
            <span className="bt-ta-metric-sub">trades</span>
          </div>
        </div>

        <div className="bt-ta-metric-card">
          <span className="bt-ta-metric-label">Current winning streak</span>
          <div className="bt-ta-metric-value-row">
            <strong className={`bt-ta-metric-value ${streaks.currentWinStreak > 0 ? "bt-pos" : ""}`}>
              {streaks.currentWinStreak}
            </strong>
            <span className="bt-ta-metric-sub">trades</span>
          </div>
        </div>

        <div className="bt-ta-metric-card">
          <span className="bt-ta-metric-label">Current losing streak</span>
          <div className="bt-ta-metric-value-row">
            <strong className={`bt-ta-metric-value ${streaks.currentLossStreak > 0 ? "bt-neg" : ""}`}>
              {streaks.currentLossStreak}
            </strong>
            <span className="bt-ta-metric-sub">trades</span>
          </div>
        </div>
      </div>

      {/* Detailed Streak Statistics Grid */}
      <div className="bt-ta-streaks-grid">
        {/* Card 1: Winning Streaks Analysis */}
        <div className="bt-ta-streaks-card bt-ta-streaks-card--win">
          <h4 className="bt-ta-card-title bt-pos">Winning Streak Analysis</h4>
          <dl className="bt-summary-list">
            <div className="bt-summary-list__row">
              <dt>Current winning streak</dt>
              <dd className="bt-pos">{streaks.currentWinStreak} trades</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Maximum winning streak</dt>
              <dd className="bt-pos">{streaks.maxWinStreak} trades</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average winning streak</dt>
              <dd>{streaks.avgWinStreak} trades</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Total winning streaks</dt>
              <dd>{streaks.winStreakCount}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Max consecutive profit</dt>
              <dd className="bt-pos">
                {streaks.maxConsecutiveProfitInr != null ? `+₹${fmtMoney(streaks.maxConsecutiveProfitInr)}` : "--"}
                {streaks.maxConsecutiveProfitPct != null ? ` (${fmtPct(streaks.maxConsecutiveProfitPct)})` : ""}
              </dd>
            </div>
          </dl>
        </div>

        {/* Card 2: Losing Streaks Analysis */}
        <div className="bt-ta-streaks-card bt-ta-streaks-card--loss">
          <h4 className="bt-ta-card-title bt-neg">Losing Streak Analysis</h4>
          <dl className="bt-summary-list">
            <div className="bt-summary-list__row">
              <dt>Current losing streak</dt>
              <dd className="bt-neg">{streaks.currentLossStreak} trades</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Maximum losing streak</dt>
              <dd className="bt-neg">{streaks.maxLossStreak} trades</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Average losing streak</dt>
              <dd>{streaks.avgLossStreak} trades</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Total losing streaks</dt>
              <dd>{streaks.lossStreakCount}</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Max consecutive loss</dt>
              <dd className="bt-neg">
                {streaks.maxConsecutiveLossInr != null ? `−₹${fmtMoney(streaks.maxConsecutiveLossInr)}` : "--"}
                {streaks.maxConsecutiveLossPct != null ? ` (${fmtPct(streaks.maxConsecutiveLossPct)})` : ""}
              </dd>
            </div>
          </dl>
        </div>

        {/* Card 3: Breakeven & Overall Behavior */}
        <div className="bt-ta-streaks-card">
          <h4 className="bt-ta-card-title">Streak Stability & Sequence</h4>
          <dl className="bt-summary-list">
            <div className="bt-summary-list__row">
              <dt>Current breakeven streak</dt>
              <dd>{streaks.currentBreakevenStreak} trades</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Maximum breakeven streak</dt>
              <dd>{streaks.maxBreakevenStreak} trades</dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Win / Loss streak ratio</dt>
              <dd>
                {streaks.avgLossStreak > 0
                  ? (streaks.avgWinStreak / streaks.avgLossStreak).toFixed(2)
                  : "--"}
              </dd>
            </div>
            <div className="bt-summary-list__row">
              <dt>Total distinct streaks</dt>
              <dd>{streaks.winStreakCount + streaks.lossStreakCount}</dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}
