import React, { useState } from "react";
import type { IndicatorBacktestOptions } from "../../api_indicator_scanner";
import { isoDateIST } from "../../utils/tradingHours";

export interface IndicatorLeanBacktestModalProps {
  isOpen: boolean;
  onClose: () => void;
  indicatorName: string;
  onStartBacktest: (options: IndicatorBacktestOptions) => Promise<void>;
  isStarting?: boolean;
}

export const IndicatorLeanBacktestModal: React.FC<IndicatorLeanBacktestModalProps> = ({
  isOpen,
  onClose,
  indicatorName,
  onStartBacktest,
  isStarting = false,
}) => {
  const [startDate, setStartDate] = useState("2020-01-01");
  const [endDate, setEndDate] = useState(() => isoDateIST());
  const [initialCapital, setInitialCapital] = useState(100000);
  const [universeId, setUniverseId] = useState("nse-755");
  const [maxPositions, setMaxPositions] = useState(10);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!startDate || !endDate) {
      setError("Please specify both start and end dates.");
      return;
    }
    if (startDate >= endDate) {
      setError("Start date must be earlier than end date.");
      return;
    }
    if (initialCapital < 1000) {
      setError("Initial capital must be at least ₹1,000.");
      return;
    }
    try {
      await onStartBacktest({
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
        universe_id: universeId,
        engine: "LEAN",
        max_positions: maxPositions,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to launch backtest.");
    }
  };

  return (
    <div className="st-modal-overlay" onClick={onClose} data-testid="indicator-lean-backtest-modal">
      <div
        className="st-modal-card"
        style={{ maxWidth: 540 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="st-modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "1.2rem" }}>⚡</span>
            <h2>Portfolio backtest (event engine)</h2>
          </div>
          <button
            type="button"
            className="st-detail-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="st-modal-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ background: "#0d1527", padding: "10px 14px", borderRadius: 6, border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "0.75rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>
                Selected Indicator Strategy
              </div>
              <div style={{ fontSize: "0.95rem", color: "#f8fafc", fontWeight: 600, marginTop: 2 }}>
                {indicatorName}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: 4 }}>
                Execution Engine: <strong style={{ color: "#38bdf8" }}>Labs event engine (NSE delivery, next-bar open)</strong>
              </div>
            </div>

            {error && (
              <div
                style={{
                  background: "rgba(239, 68, 68, 0.1)",
                  border: "1px solid #ef4444",
                  color: "#fca5a5",
                  padding: "8px 12px",
                  borderRadius: 6,
                  fontSize: "0.85rem",
                }}
              >
                {error}
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8125rem", color: "#94a3b8" }}>
                <span>Start Date</span>
                <input
                  type="date"
                  value={startDate}
                  max={endDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="st-filter-input"
                  style={{ width: "100%", padding: "6px 10px", background: "#090d16", border: "1px solid #334155", borderRadius: 4, color: "#f8fafc" }}
                  data-testid="lean-start-date"
                />
              </label>

              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8125rem", color: "#94a3b8" }}>
                <span>End Date</span>
                <input
                  type="date"
                  value={endDate}
                  min={startDate}
                  max={isoDateIST()}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="st-filter-input"
                  style={{ width: "100%", padding: "6px 10px", background: "#090d16", border: "1px solid #334155", borderRadius: 4, color: "#f8fafc" }}
                  data-testid="lean-end-date"
                />
              </label>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8125rem", color: "#94a3b8" }}>
                <span>Initial Capital (₹)</span>
                <input
                  type="number"
                  min={1000}
                  step={10000}
                  value={initialCapital}
                  onChange={(e) => setInitialCapital(Number(e.target.value))}
                  className="st-filter-input"
                  style={{ width: "100%", padding: "6px 10px", background: "#090d16", border: "1px solid #334155", borderRadius: 4, color: "#f8fafc" }}
                  data-testid="lean-initial-capital"
                />
              </label>

              <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8125rem", color: "#94a3b8" }}>
                <span>Max Portfolio Positions</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={maxPositions}
                  onChange={(e) => setMaxPositions(Number(e.target.value))}
                  className="st-filter-input"
                  style={{ width: "100%", padding: "6px 10px", background: "#090d16", border: "1px solid #334155", borderRadius: 4, color: "#f8fafc" }}
                  data-testid="lean-max-positions"
                />
              </label>
            </div>

            <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.8125rem", color: "#94a3b8" }}>
              <span>Stock Universe</span>
              <select
                value={universeId}
                onChange={(e) => setUniverseId(e.target.value)}
                style={{ width: "100%", padding: "6px 10px", background: "#090d16", border: "1px solid #334155", borderRadius: 4, color: "#f8fafc" }}
                data-testid="lean-universe"
              >
                <option value="nse-755">NSE 755 (All Equities Universe)</option>
              </select>
            </label>

            <div style={{ fontSize: "0.75rem", color: "#64748b", lineHeight: 1.4 }}>
              LEAN simulates multi-asset order routing with realistic NSE delivery transaction costs (0.05% brokerage, 0.05% slippage, Next-Bar-Open fills, and strict point-in-time universe lookbacks).
            </div>
          </div>

          <div
            className="st-modal-footer"
            style={{
              padding: "12px 16px",
              borderTop: "1px solid #1e293b",
              display: "flex",
              justifyContent: "flex-end",
              gap: 10,
            }}
          >
            <button
              type="button"
              className="st-btn-dark"
              onClick={onClose}
              disabled={isStarting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="st-btn-primary"
              disabled={isStarting}
              onClick={handleSubmit}
              data-testid="btn-confirm-start-lean-backtest"
              style={{
                background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {isStarting ? (
                <>
                  <span className="animate-spin">⏳</span>
                  <span>Launching…</span>
                </>
              ) : (
                <>
                  <span>⚡</span>
                  <span>Run LEAN Backtest</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
