import React, { useState, useRef, useEffect } from "react";
import type { BacktestRange } from "../BacktestAnalyticsDashboard";
import type { TvViewMode, TvDetailization, TvScriptStatus } from "./types";
import { fmtTvCapital, fmtTvDateRange } from "./tvFormatters";

interface TvToolbarProps {
  viewMode: TvViewMode;
  onViewModeChange: (mode: TvViewMode) => void;
  startDate?: string | null;
  endDate?: string | null;
  range?: BacktestRange;
  onRangeChange?: (range: BacktestRange) => void;
  onCustomRange?: (start: string, end: string) => void;
  initialCapital?: number | null;
  currency?: string;
  detailization: TvDetailization;
  onDetailizationChange: (d: TvDetailization) => void;
  scriptStatus?: TvScriptStatus;
  tradeCount?: number;
  onOpenConfigModal?: () => void;
  symbol?: string | null;
  strategyName?: string | null;
}

export const TvToolbar: React.FC<TvToolbarProps> = ({
  viewMode,
  onViewModeChange,
  startDate,
  endDate,
  range = "3Y",
  onRangeChange,
  onCustomRange,
  initialCapital = 100000,
  currency = "INR",
  detailization,
  onDetailizationChange,
  scriptStatus = "completed",
  tradeCount = 0,
  onOpenConfigModal,
  symbol,
  strategyName,
}) => {
  const [showRangeDropdown, setShowRangeDropdown] = useState(false);
  const [showDetailDropdown, setShowDetailDropdown] = useState(false);
  const [showScriptDropdown, setShowScriptDropdown] = useState(false);
  const [showCapitalDropdown, setShowCapitalDropdown] = useState(false);

  const rangeRef = useRef<HTMLDivElement>(null);
  const detailRef = useRef<HTMLDivElement>(null);
  const scriptRef = useRef<HTMLDivElement>(null);
  const capitalRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (rangeRef.current && !rangeRef.current.contains(e.target as Node)) {
        setShowRangeDropdown(false);
      }
      if (detailRef.current && !detailRef.current.contains(e.target as Node)) {
        setShowDetailDropdown(false);
      }
      if (scriptRef.current && !scriptRef.current.contains(e.target as Node)) {
        setShowScriptDropdown(false);
      }
      if (capitalRef.current && !capitalRef.current.contains(e.target as Node)) {
        setShowCapitalDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const dateRangeText = fmtTvDateRange(startDate, endDate);
  const capitalText = fmtTvCapital(initialCapital, currency);

  return (
    <div className="tv-toolbar" data-testid="tv-toolbar">
      {/* 1. View Toggle: Chart vs Table */}
      <div className="tv-toolbar__view-group" role="group" aria-label="View selection">
        <button
          type="button"
          className={`tv-toolbar__view-btn ${viewMode === "chart" ? "is-active" : ""}`}
          onClick={() => onViewModeChange("chart")}
          title="Chart view: Key stats and performance chart"
          aria-label="Chart view"
          data-testid="tv-view-chart-btn"
        >
          {/* Chart icon */}
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 3v18h18" />
            <path d="m19 9-5 5-4-4-3 3" />
          </svg>
        </button>
        <button
          type="button"
          className={`tv-toolbar__view-btn ${viewMode === "table" ? "is-active" : ""}`}
          onClick={() => onViewModeChange("table")}
          title="Table view: List of trades"
          aria-label="Table view"
          data-testid="tv-view-table-btn"
        >
          {/* Table icon */}
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18" />
            <path d="M3 15h18" />
            <path d="M9 3v18" />
            <path d="M15 3v18" />
          </svg>
        </button>
      </div>

      {/* 2. Date Range Control */}
      <div className="tv-toolbar__dropdown-wrapper" ref={rangeRef}>
        <button
          type="button"
          className="tv-toolbar__pill-btn"
          onClick={() => setShowRangeDropdown(!showRangeDropdown)}
          aria-expanded={showRangeDropdown}
          aria-label={`Date range: ${dateRangeText}`}
          title="Change backtest date range"
        >
          {/* Calendar icon */}
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
          <span className="tv-toolbar__date-text">{dateRangeText}</span>
          <span className="tv-toolbar__deep-badge">DEEP</span>
          <svg className="tv-toolbar__chevron" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {showRangeDropdown && (
          <div className="tv-dropdown-menu tv-dropdown-menu--range">
            <div className="tv-dropdown-header">Backtest Window</div>
            <div className="tv-range-quick-grid">
              {(["1Y", "3Y", "5Y", "8Y", "ALL"] as BacktestRange[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`tv-range-quick-btn ${range === r ? "is-active" : ""}`}
                  onClick={() => {
                    onRangeChange?.(r);
                    setShowRangeDropdown(false);
                  }}
                >
                  {r === "ALL" ? "All" : r}
                </button>
              ))}
            </div>
            <div className="tv-custom-dates-row">
              <label className="tv-date-input-wrap">
                <span>From</span>
                <input
                  type="date"
                  aria-label="Backtest start date"
                  value={startDate || ""}
                  max={endDate || undefined}
                  onChange={(e) => {
                    if (e.target.value && endDate) onCustomRange?.(e.target.value, endDate);
                  }}
                />
              </label>
              <label className="tv-date-input-wrap">
                <span>To</span>
                <input
                  type="date"
                  aria-label="Backtest end date"
                  value={endDate || ""}
                  min={startDate || undefined}
                  onChange={(e) => {
                    if (startDate && e.target.value) onCustomRange?.(startDate, e.target.value);
                  }}
                />
              </label>
            </div>
          </div>
        )}
      </div>

      {/* 3. Capital / Currency Control */}
      <div className="tv-toolbar__dropdown-wrapper" ref={capitalRef}>
        <button
          type="button"
          className="tv-toolbar__pill-btn"
          onClick={() => setShowCapitalDropdown(!showCapitalDropdown)}
          aria-expanded={showCapitalDropdown}
          aria-label={`Capital: ${capitalText}`}
          title="Backtest capital & currency"
        >
          <span className="tv-toolbar__currency-circle">$</span>
          <span className="tv-toolbar__capital-text">{capitalText}</span>
          <svg className="tv-toolbar__chevron" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {showCapitalDropdown && (
          <div className="tv-dropdown-menu">
            <div className="tv-dropdown-header">Initial Capital</div>
            <div className="tv-dropdown-item is-selected">
              <span>₹ {(initialCapital || 100000).toLocaleString("en-IN")} INR</span>
            </div>
            <div className="tv-dropdown-note">Configured via Backtest Settings</div>
          </div>
        )}
      </div>

      {/* 4. Detailization Control */}
      <div className="tv-toolbar__dropdown-wrapper" ref={detailRef}>
        <button
          type="button"
          className="tv-toolbar__pill-btn"
          onClick={() => setShowDetailDropdown(!showDetailDropdown)}
          aria-expanded={showDetailDropdown}
          aria-label="Detailization options"
          title="Chart detailization granularity"
        >
          {/* Sliders / Gauge icon */}
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="4" y1="21" x2="4" y2="14" />
            <line x1="4" y1="10" x2="4" y2="3" />
            <line x1="12" y1="21" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12" y2="3" />
            <line x1="20" y1="21" x2="20" y2="16" />
            <line x1="20" y1="12" x2="20" y2="3" />
            <line x1="1" y1="14" x2="7" y2="14" />
            <line x1="9" y1="8" x2="15" y2="8" />
            <line x1="17" y1="16" x2="23" y2="16" />
          </svg>
          <span>
            {detailization === "default"
              ? "Default detailization"
              : detailization === "trade_by_trade"
                ? "Trade by trade"
                : "Bar by bar"}
          </span>
          <svg className="tv-toolbar__chevron" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {showDetailDropdown && (
          <div className="tv-dropdown-menu">
            <div className="tv-dropdown-header">Detailization</div>
            <button
              type="button"
              className={`tv-dropdown-item ${detailization === "default" ? "is-selected" : ""}`}
              onClick={() => {
                onDetailizationChange("default");
                setShowDetailDropdown(false);
              }}
            >
              Default detailization
            </button>
            <button
              type="button"
              className={`tv-dropdown-item ${detailization === "trade_by_trade" ? "is-selected" : ""}`}
              onClick={() => {
                onDetailizationChange("trade_by_trade");
                setShowDetailDropdown(false);
              }}
            >
              Trade by trade
            </button>
            <button
              type="button"
              className={`tv-dropdown-item ${detailization === "bar_by_bar" ? "is-selected" : ""}`}
              onClick={() => {
                onDetailizationChange("bar_by_bar");
                setShowDetailDropdown(false);
              }}
            >
              Bar by bar
            </button>
          </div>
        )}
      </div>

      {/* 5. Script Execution Control */}
      <div className="tv-toolbar__dropdown-wrapper" ref={scriptRef}>
        <button
          type="button"
          className="tv-toolbar__pill-btn"
          onClick={() => setShowScriptDropdown(!showScriptDropdown)}
          aria-expanded={showScriptDropdown}
          aria-label="Script execution status"
          title="Execution engine status"
        >
          {/* Sparkline icon */}
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          <span>Script execution</span>
          <span className={`tv-toolbar__status-badge tv-toolbar__status-badge--${scriptStatus}`}>
            {scriptStatus === "completed" ? "1" : "●"}
          </span>
          <svg className="tv-toolbar__chevron" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {showScriptDropdown && (
          <div className="tv-dropdown-menu">
            <div className="tv-dropdown-header">Script Execution</div>
            <div className="tv-dropdown-item">
              <span className="tv-status-dot is-green" />
              <span>Engine: Backtest Engine v2.0</span>
            </div>
            <div className="tv-dropdown-item">
              <span>Status: {scriptStatus === "completed" ? "Completed" : scriptStatus}</span>
            </div>
            <div className="tv-dropdown-item">
              <span>Strategy: {strategyName || "52-Week High Breakout"}</span>
            </div>
            <div className="tv-dropdown-item">
              <span>Symbol: {symbol || "All"}</span>
            </div>
            <div className="tv-dropdown-item">
              <span>Closed Trades: {tradeCount}</span>
            </div>
          </div>
        )}
      </div>

      {/* 6. Right Actions: Config / History / Logs */}
      <div className="tv-toolbar__right-actions">
        <button
          type="button"
          className="tv-toolbar__icon-btn"
          onClick={onOpenConfigModal}
          title="Backtest configuration and history"
          aria-label="Backtest configuration details"
        >
          {/* Clock with plus icon */}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </button>
      </div>
    </div>
  );
};
