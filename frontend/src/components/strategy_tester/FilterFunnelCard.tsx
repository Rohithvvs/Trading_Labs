import React from "react";
import type { FunnelStep } from "../../api_strategy_tester";

interface FilterFunnelCardProps {
  steps?: FunnelStep[];
  totalUniverse?: number;
  onStepClick?: (step: FunnelStep) => void;
}

const FALLBACK_FUNNEL: FunnelStep[] = [
  { step: 0, filter_id: null, label: "Start Universe", remaining: 755, drop: 0, retention_pct: 100 },
  { step: 1, filter_id: "1", label: "Close > SMA 50", remaining: 620, drop: 135, retention_pct: 82.1 },
  { step: 2, filter_id: "2", label: "SMA 50 > SMA 200", remaining: 410, drop: 210, retention_pct: 54.3 },
  { step: 3, filter_id: "3", label: "RSI > 55", remaining: 285, drop: 125, retention_pct: 37.7 },
  { step: 4, filter_id: "4", label: "Volume > Avg Volume", remaining: 195, drop: 90, retention_pct: 25.8 },
  { step: 5, filter_id: "final", label: "Final BUY Signals", remaining: 42, drop: 153, retention_pct: 5.6 },
];

const FUNNEL_COLORS = [
  "#2563eb", // blue (Start Universe)
  "#16a34a", // green (Filter 1)
  "#ca8a04", // amber (Filter 2)
  "#ea580c", // orange (Filter 3)
  "#dc2626", // red (Filter 4)
  "#9333ea", // purple (Final BUY Signals)
];

function formatStepLabel(step: FunnelStep, idx: number, total: number): string {
  if (idx === 0 || step.step === 0) return "Start Universe";
  if (
    idx === total - 1 ||
    step.filter_id === "final" ||
    step.label?.toLowerCase().includes("final buy")
  ) {
    return "Final BUY Signals";
  }
  let label = step.label || `Filter ${idx}`;
  label = label.replace(/CLOSE > SMA 50/i, "Close > SMA 50");
  label = label.replace(/SMA 50 > SMA 200/i, "SMA 50 > SMA 200");
  label = label.replace(/RSI > 55/i, "RSI > 55");
  label = label.replace(/VOLUME > AVG_VOLUME 20/i, "Volume > Avg Volume");
  label = label.replace(/VOLUME > AVG_VOLUME/i, "Volume > Avg Volume");
  return label;
}

export const FilterFunnelCard: React.FC<FilterFunnelCardProps> = ({
  steps,
  totalUniverse: _totalUniverse = 755,
  onStepClick,
}) => {
  const displaySteps = steps && steps.length > 0 ? steps : FALLBACK_FUNNEL;
  const numSteps = displaySteps.length;

  return (
    <div className="st-card st-funnel-card" data-testid="card-filter-funnel">
      <div className="st-card-title">Filter Funnel (Sequential)</div>

      <div className="st-funnel-container">
        {displaySteps.map((step, idx) => {
          const color = FUNNEL_COLORS[idx % FUNNEL_COLORS.length];
          const isFinal = idx === numSteps - 1;
          const label = formatStepLabel(step, idx, numSteps);

          // Calculate decreasing trapezoid widths
          const topInset = Math.min(30, (idx / Math.max(1, numSteps)) * 34);
          const botInset = isFinal
            ? topInset + 2
            : Math.min(34, ((idx + 1) / Math.max(1, numSteps)) * 34);

          const clipPath = `polygon(${topInset}% 0%, ${100 - topInset}% 0%, ${100 - botInset}% 100%, ${botInset}% 100%)`;

          return (
            <div
              key={step.step ?? step.filter_id ?? idx}
              className="st-funnel-row"
              onClick={() => onStepClick?.(step)}
              title={`${label}: ${step.remaining} stocks`}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onStepClick?.(step);
                }
              }}
            >
              {/* Funnel Segment Trapezoid */}
              <div className="st-funnel-segment-wrapper">
                <div
                  className="st-funnel-trapezoid-bar"
                  style={{
                    backgroundColor: color,
                    clipPath,
                  }}
                >
                  <span className="st-funnel-number">{step.remaining}</span>
                </div>
              </div>

              {/* Arrow Connector */}
              <div className="st-funnel-arrow-line">
                <svg width="20" height="12" viewBox="0 0 20 12" fill="none">
                  <line x1="0" y1="6" x2="14" y2="6" stroke="#475569" strokeWidth="1.5" />
                  <polygon points="13,3 18,6 13,9" fill="#475569" />
                </svg>
              </div>

              {/* Stage Label */}
              <div className="st-funnel-label-col">
                <span className="st-funnel-stage-name" title={label}>
                  {label}
                </span>
                <span className="st-funnel-stage-count">({step.remaining})</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
