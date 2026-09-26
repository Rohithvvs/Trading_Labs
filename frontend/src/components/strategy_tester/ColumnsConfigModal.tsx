import React from "react";

interface ColumnsConfigModalProps {
  isOpen: boolean;
  visibleColumns: Set<string>;
  onClose: () => void;
  onToggleColumn: (colKey: string) => void;
  onResetColumns: () => void;
}

const ALL_COLUMNS: { key: string; label: string }[] = [
  { key: "rank", label: "Rank" },
  { key: "symbol", label: "Symbol" },
  { key: "company", label: "Company Name" },
  { key: "signal", label: "Signal" },
  { key: "entry", label: "Entry Price" },
  { key: "stop_loss", label: "Stop Loss" },
  { key: "target", label: "Target" },
  { key: "rr", label: "RR (Risk / Reward)" },
  { key: "return_pct", label: "Return %" },
  { key: "evaluation_date", label: "Scan Date" },
  { key: "pass_count", label: "Passed Filters Count" },
  { key: "fail_count", label: "Failed Filters Count" },
  { key: "primary_failure", label: "Primary Failure Reason" },
  { key: "window_start", label: "Window Start (Close 1Y Ago)" },
  { key: "high_252", label: "Prior 252-Session High" },
  { key: "rsi", label: "RSI" },
  { key: "sma_20", label: "SMA 20" },
  { key: "sma_50", label: "SMA 50" },
  { key: "sma_200", label: "SMA 200" },
  { key: "volume", label: "Volume" },
  { key: "avg_volume", label: "Avg Volume" },
];

export const ColumnsConfigModal: React.FC<ColumnsConfigModalProps> = ({
  isOpen,
  visibleColumns,
  onClose,
  onToggleColumn,
  onResetColumns,
}) => {
  if (!isOpen) return null;

  return (
    <div className="st-modal-overlay" onClick={onClose} data-testid="modal-columns-config">
      <div className="st-modal-card" style={{ maxWidth: 440 }} onClick={(e) => e.stopPropagation()}>
        <div className="st-modal-header">
          <h2>Customize Visible Columns</h2>
          <button
            type="button"
            className="st-detail-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        <div className="st-modal-body">
          <p style={{ color: "#94a3b8", fontSize: "0.78rem", margin: 0 }}>
            Select which columns you want to display in the main results table:
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 6 }}>
            {ALL_COLUMNS.map((col) => {
              const isChecked =
                visibleColumns.has(col.key) ||
                (col.key === "entry" && (visibleColumns.has("exit_price") || visibleColumns.has("entry_price"))) ||
                (col.key === "rr" && visibleColumns.has("risk_reward"));
              return (
                <label
                  key={col.key}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: "0.78rem",
                    color: isChecked ? "#f1f5f9" : "#64748b",
                    cursor: "pointer",
                    padding: "4px 6px",
                    borderRadius: 4,
                    background: isChecked ? "rgba(59, 130, 246, 0.08)" : "transparent",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => onToggleColumn(col.key)}
                  />
                  <span>{col.label}</span>
                </label>
              );
            })}
          </div>
        </div>

        <div className="st-modal-footer">
          <button type="button" className="st-btn-dark" onClick={onResetColumns}>
            Reset All
          </button>
          <button type="button" className="st-btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
