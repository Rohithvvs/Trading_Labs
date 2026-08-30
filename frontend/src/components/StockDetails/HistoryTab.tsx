import React from "react";
import type { SymbolHistoryItem } from "../../api_strategy_tester";
import { formatINRVal } from "./StockHeader";

interface HistoryTabProps {
  symbol: string;
  history: SymbolHistoryItem[];
  loadingHistory: boolean;
}

export const HistoryTab: React.FC<HistoryTabProps> = ({
  symbol,
  history,
  loadingHistory,
}) => {
  return (
    <section className="st-card st-card-full" data-testid="card-detail-history" aria-label="Stock test run history">
      <h2 className="st-card-title">Test Run History</h2>
      {loadingHistory ? (
        <div style={{ textAlign: "center", padding: "40px 20px", color: "#64748b" }} data-testid="history-loading">
          Loading history...
        </div>
      ) : history.length === 0 ? (
        <div style={{ textAlign: "center", padding: "40px 20px", color: "#64748b" }} data-testid="history-empty">
          No past test runs for {symbol}.
        </div>
      ) : (
        <div className="st-main-table-container" style={{ marginTop: 8 }}>
          <table className="st-main-table" data-testid="table-stock-history">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Strategy Name</th>
                <th>Date</th>
                <th>Signal</th>
                <th style={{ textAlign: "right" }}>Entry Price</th>
                <th style={{ textAlign: "right" }}>Exit Price</th>
                <th style={{ textAlign: "right" }}>Return %</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h, i) => {
                const ret = h.return_pct ?? 0;
                return (
                  <tr key={h.run_id || i}>
                    <td style={{ color: "var(--st-cyan)", fontWeight: 700 }}>{h.run_id}</td>
                    <td style={{ color: "#f1f5f9", fontWeight: 500 }}>{h.strategy_name || "Momentum Strategy"}</td>
                    <td style={{ color: "#94a3b8" }}>{h.date ? new Date(h.date).toLocaleDateString("en-IN") : "—"}</td>
                    <td>
                      <span className={`st-badge-signal ${h.signal || "REJECT"}`}>
                        {h.signal || "REJECT"}
                      </span>
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {formatINRVal(h.entry_price)}
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {formatINRVal(h.exit_price)}
                    </td>
                    <td
                      style={{
                        textAlign: "right",
                        fontWeight: 700,
                        color: ret > 0 ? "#4ade80" : ret < 0 ? "#f87171" : "#94a3b8",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {ret > 0 ? `+${ret.toFixed(2)}%` : `${ret.toFixed(2)}%`}
                    </td>
                    <td>
                      <span className="st-status-badge st-status-badge--completed">
                        {h.status || "completed"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
