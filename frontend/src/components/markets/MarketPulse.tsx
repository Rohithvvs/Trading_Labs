import React, { memo } from "react";
import type { MarketIndexItem, MarketBreadth } from "../../api";

interface MarketPulseProps {
  nifty?: MarketIndexItem;
  bankNifty?: MarketIndexItem;
  vix?: MarketIndexItem;
  breadth?: MarketBreadth;
}

/**
 * Deterministic Market Pulse Calculator
 * 
 * Formula Methodology:
 * 1. Trend: Derived from NIFTY 50 change % (>+0.35% Bullish, <-0.35% Bearish, else Neutral)
 * 2. Breadth: Advances ratio = Advances / (Advances + Declines) (>=60% Expanding, 45-59% Balanced, <45% Weak)
 * 3. Volatility: India VIX (<13.5 Low/Favorable, 13.5-17.5 Normal, >17.5 Elevated)
 * 4. Momentum: Nifty 50 & Bank Nifty directional consensus (Strong Upside, Rotational, Downtrend)
 * 5. Risk: Composite of VIX level and breadth participation
 */
export const MarketPulse: React.FC<MarketPulseProps> = memo(function MarketPulse({
  nifty,
  bankNifty,
  vix,
  breadth,
}) {
  const niftyChg = Number(nifty?.change_pct ?? 0) || 0;
  const bankChg = Number(bankNifty?.change_pct ?? 0) || 0;
  const vixVal = Number(vix?.price ?? 14.0) || 14.0;
  const adv = Number(breadth?.advances ?? 0) || 0;
  const dec = Number(breadth?.declines ?? 0) || 0;
  const total = adv + dec;
  const advRatio = total > 0 ? (adv / total) * 100 : 50;

  // 1. Trend
  let trendText = "NEUTRAL";
  let trendTone = "var(--mk-amber)";
  let trendSub = "Consolidating";
  if (niftyChg > 0.35) {
    trendText = "BULLISH";
    trendTone = "var(--mk-green)";
    trendSub = "Strong Uptrend";
  } else if (niftyChg < -0.35) {
    trendText = "BEARISH";
    trendTone = "var(--mk-red)";
    trendSub = "Weakening / Pressure";
  }

  // 2. Breadth Participation
  let breadthText = "BALANCED";
  let breadthTone = "var(--mk-text-secondary)";
  let breadthSub = `${advRatio.toFixed(0)}% Advancing`;
  if (advRatio >= 60) {
    breadthText = "EXPANDING";
    breadthTone = "var(--mk-green)";
    breadthSub = "Broad Participation";
  } else if (advRatio < 45) {
    breadthText = "DETERIORATING";
    breadthTone = "var(--mk-red)";
    breadthSub = "Declines Dominating";
  }

  // 3. Volatility
  let volText = "NORMAL";
  let volTone = "var(--mk-text-secondary)";
  let volSub = `VIX ${vixVal.toFixed(2)}`;
  if (vixVal < 13.5) {
    volText = "LOW";
    volTone = "var(--mk-green)";
    volSub = "Favorable / Stable";
  } else if (vixVal > 17.5) {
    volText = "ELEVATED";
    volTone = "var(--mk-red)";
    volSub = "High Risk / Hedging";
  }

  // 4. Momentum Consensus
  let momText = "ROTATIONAL";
  let momTone = "var(--mk-amber)";
  let momSub = "Divergent Sectors";
  if (niftyChg > 0 && bankChg > 0) {
    momText = "STRONG UPSIDE";
    momTone = "var(--mk-green)";
    momSub = "Nifty + Bank Aligned";
  } else if (niftyChg < 0 && bankChg < 0) {
    momText = "STRONG DOWNSIDE";
    momTone = "var(--mk-red)";
    momSub = "Sellers in Control";
  }

  // 5. Risk Environment
  let riskText = "MODERATE";
  let riskTone = "var(--mk-amber)";
  let riskSub = "Selective Setups";
  if (vixVal > 17.5 || (niftyChg < -1.0 && advRatio < 40)) {
    riskText = "ELEVATED RISK";
    riskTone = "var(--mk-red)";
    riskSub = "Defensive Positioning";
  } else if (advRatio > 55 && vixVal < 15.0) {
    riskText = "FAVORABLE";
    riskTone = "var(--mk-green)";
    riskSub = "Risk-On Environment";
  }

  return (
    <section className="terminal-card" aria-label="Market Regime and Pulse">
      <div className="terminal-card__header">
        <h2 className="terminal-card__title">
          <span>⚡</span>
          <span>Market Pulse & Regime</span>
        </h2>
        <span className="terminal-card__subtitle">
          Rule-based live composite based on index momentum, breadth, and volatility
        </span>
      </div>

      <div className="market-pulse-strip">
        <div className="market-pulse-item">
          <span className="market-pulse-label">Direction</span>
          <span className="market-pulse-value" style={{ color: trendTone }}>
            {trendText}
          </span>
          <span className="market-pulse-sub">{trendSub}</span>
        </div>

        <div className="market-pulse-item">
          <span className="market-pulse-label">Breadth</span>
          <span className="market-pulse-value" style={{ color: breadthTone }}>
            {breadthText}
          </span>
          <span className="market-pulse-sub">{breadthSub}</span>
        </div>

        <div className="market-pulse-item">
          <span className="market-pulse-label">Volatility</span>
          <span className="market-pulse-value" style={{ color: volTone }}>
            {volText}
          </span>
          <span className="market-pulse-sub">{volSub}</span>
        </div>

        <div className="market-pulse-item">
          <span className="market-pulse-label">Momentum</span>
          <span className="market-pulse-value" style={{ color: momTone }}>
            {momText}
          </span>
          <span className="market-pulse-sub">{momSub}</span>
        </div>

        <div className="market-pulse-item">
          <span className="market-pulse-label">Risk Environment</span>
          <span className="market-pulse-value" style={{ color: riskTone }}>
            {riskText}
          </span>
          <span className="market-pulse-sub">{riskSub}</span>
        </div>
      </div>
    </section>
  );
});
