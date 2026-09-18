import React, { useMemo } from "react";
import type { StrategyCatalog } from "../../api_strategy_tester";
import { strategySelectOptions } from "../../utils/strategyTesterState";

interface StrategyConfigurationPanelProps {
  catalog: StrategyCatalog | null;
  selectedPresetId: string;
  selectedEngine?: string;
  strategyName: string;
  strategyDescription: string;
  universe: string;
  universeCount: number;
  timeframe: string;
  startDate: string;
  endDate: string;
  initialCapital: number;
  isRunning: boolean;
  onPresetChange: (presetId: string) => void;
  onEngineChange?: (engineId: string) => void;
  onEditStrategy: () => void;
  onStartDateChange: (dateStr: string) => void;
  onEndDateChange: (dateStr: string) => void;
  onCapitalChange: (cap: number) => void;
  onRunStrategy: () => void;
  onReset: () => void;
}

export function formatDateInput(d: string): string {
  if (!d) return "";
  const parts = d.split("-");
  if (parts.length === 3) {
    const year = parts[0];
    const monthIndex = parseInt(parts[1], 10) - 1;
    const day = parts[2];
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${day} ${months[monthIndex] || parts[1]} ${year}`;
  }
  return d;
}

export const StrategyConfigurationPanel: React.FC<StrategyConfigurationPanelProps> = ({
  catalog,
  selectedPresetId,
  selectedEngine = "LEAN",
  strategyName,
  strategyDescription,
  universe: _universe,
  universeCount,
  timeframe: _timeframe,
  startDate,
  endDate,
  initialCapital,
  isRunning,
  onPresetChange,
  onEngineChange,
  onEditStrategy,
  onStartDateChange,
  onEndDateChange,
  onCapitalChange,
  onRunStrategy,
  onReset,
}) => {
  const strategyOptions = useMemo(
    () => strategySelectOptions(catalog?.presets, catalog?.saved),
    [catalog?.presets, catalog?.saved],
  );
  const selectedValue = strategyOptions.some((opt) => opt.id === selectedPresetId)
    ? selectedPresetId
    : strategyOptions[0]?.id || selectedPresetId;

  return (
    <section className="st-config-card" aria-label="Strategy configuration">
      <div className="st-config-row">
        {/* Strategy Selector */}
        <div className="st-config-field" style={{ minWidth: 220 }}>
          <label htmlFor="st-strategy-select">Strategy</label>
          <div className="st-config-box">
            <select
              id="st-strategy-select"
              value={selectedValue}
              onChange={(e) => onPresetChange(e.target.value)}
              data-testid="select-strategy-preset"
            >
              {strategyOptions.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={onEditStrategy}
              title="Edit strategy rules"
              aria-label="Edit strategy rules"
              style={{ background: "transparent", border: "none", color: "#64748b", cursor: "pointer", padding: "0 2px" }}
              data-testid="btn-config-edit"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 20h9" />
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
            </button>
          </div>
        </div>

        {/* Market / Universe */}
        <div className="st-config-field" style={{ minWidth: 170 }}>
          <label htmlFor="st-universe-select">Market / Universe</label>
          <div className="st-config-box">
            <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.8125rem", color: "#f1f5f9" }}>
              All Stocks ({universeCount})
            </span>
            <span className="st-badge-pill">{universeCount}</span>
          </div>
        </div>

        {/* Timeframe */}
        <div className="st-config-field" style={{ minWidth: 90 }}>
          <label htmlFor="st-timeframe-select">Timeframe</label>
          <div className="st-config-box">
            <span>1 Day</span>
            <span style={{ color: "#64748b", fontSize: "0.75rem" }}>⌄</span>
          </div>
        </div>

        <div className="st-config-field" style={{ minWidth: 150 }}>
          <label>Mode</label>
          <div className="st-config-box" title="Evaluates filters on the last completed daily bar">
            <span>Universe scan</span>
          </div>
        </div>

        {/* Start Date */}
        <div className="st-config-field" style={{ minWidth: 140 }}>
          <label htmlFor="st-start-date">Start Date</label>
          <div className="st-config-box" style={{ position: "relative" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
            <input
              id="st-start-date"
              type="date"
              value={startDate}
              onChange={(e) => onStartDateChange(e.target.value)}
              style={{
                background: "transparent",
                color: "#f1f5f9",
                border: "none",
                fontSize: "0.75rem",
                outline: "none",
                cursor: "pointer",
              }}
              data-testid="input-start-date"
            />
          </div>
        </div>

        {/* End Date — last bar, same role as TradingView 1D Pine Screener */}
        <div className="st-config-field" style={{ minWidth: 140 }}>
          <label htmlFor="st-end-date">End Date (scan bar)</label>
          <div className="st-config-box" style={{ position: "relative" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
            <input
              id="st-end-date"
              type="date"
              value={endDate}
              onChange={(e) => onEndDateChange(e.target.value)}
              style={{
                background: "transparent",
                color: "#f1f5f9",
                border: "none",
                fontSize: "0.75rem",
                outline: "none",
                cursor: "pointer",
              }}
              data-testid="input-end-date"
            />
          </div>
        </div>

        {/* Initial Capital */}
        <div className="st-config-field" style={{ minWidth: 130 }}>
          <label htmlFor="st-capital-input">Initial Capital</label>
          <div className="st-config-box">
            <span style={{ color: "#64748b", fontWeight: 600 }}>₹</span>
            <input
              id="st-capital-input"
              type="text"
              value={initialCapital.toLocaleString("en-IN")}
              onChange={(e) => {
                const num = parseInt(e.target.value.replace(/,/g, ""), 10);
                if (!Number.isNaN(num)) onCapitalChange(num);
              }}
              data-testid="input-initial-capital"
            />
          </div>
        </div>

        {/* Action Buttons */}
        <button
          type="button"
          className="st-btn-run"
          onClick={onRunStrategy}
          disabled={isRunning}
          data-testid="btn-run-strategy"
        >
          {isRunning ? (
            <>
              <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="12" />
              </svg>
              Running...
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              Scan universe
            </>
          )}
        </button>

        <button
          type="button"
          className="st-btn-reset"
          onClick={onReset}
          disabled={isRunning}
          title="Reset to default Momentum parameters"
          data-testid="btn-reset-strategy"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
          </svg>
          Reset
        </button>
      </div>

      {/* Description Row */}
      <p className="st-config-desc">
        <strong>Description:</strong> {strategyDescription || `Momentum based strategy using trend, momentum and volume filters.`}
      </p>
    </section>
  );
};
