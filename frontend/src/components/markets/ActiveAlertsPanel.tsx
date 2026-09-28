import React, { memo, useState } from "react";
import { createWorkstationAlert, deleteWorkstationAlert } from "../../api";

interface AlertItem {
  id: number;
  name: string;
  symbol?: string;
  condition?: string;
  target_price?: number;
  status?: string;
}

interface ActiveAlertsPanelProps {
  alerts: AlertItem[];
  onRefreshAlerts: () => void;
}

const DEFAULT_ALERTS: AlertItem[] = [
  { id: 1, name: "Reliance Breakout", symbol: "RELIANCE", condition: ">=", target_price: 2600, status: "ACTIVE" },
  { id: 2, name: "TCS Support", symbol: "TCS", condition: "<=", target_price: 3700, status: "ACTIVE" },
  { id: 3, name: "Nifty Level", symbol: "NIFTY 50", condition: "<=", target_price: 22500, status: "ACTIVE" },
];

export const ActiveAlertsPanel: React.FC<ActiveAlertsPanelProps> = memo(function ActiveAlertsPanel({
  alerts,
  onRefreshAlerts,
}) {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");
  const [newCondition, setNewCondition] = useState<">=" | "<=">(">=");
  const [newTarget, setNewTarget] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const displayAlerts = alerts && alerts.length > 0 ? alerts : DEFAULT_ALERTS;

  const handleDelete = async (id: number) => {
    try {
      await deleteWorkstationAlert(id);
      onRefreshAlerts();
    } catch {
      // Ignore or let parent reload
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol.trim() || !newTarget) return;

    setSubmitting(true);
    try {
      await createWorkstationAlert({
        alert_type: "PRICE",
        name: `${newSymbol.toUpperCase()} price alert`,
        symbol: newSymbol.trim().toUpperCase(),
        condition: newCondition,
        target_price: Number(newTarget),
      });
      setNewSymbol("");
      setNewTarget("");
      setShowCreateModal(false);
      onRefreshAlerts();
    } catch (err: any) {
      alert(err?.message || "Failed to create alert");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="terminal-card" aria-label="Active Price Alerts">
      <div className="terminal-card__header">
        <h3 className="terminal-card__title">
          <span>Alerts</span>
          <span className="terminal-card__subtitle">({displayAlerts.length} Active)</span>
        </h3>
        <button
          type="button"
          className="terminal-link-btn"
          onClick={() => setShowCreateModal(true)}
        >
          + Create alert
        </button>
      </div>

      <div className="alerts-list">
        {displayAlerts.map((alert) => {
          const sym = alert.symbol || alert.name;
          const cond = alert.condition || ">=";
          const target = alert.target_price
            ? Number(alert.target_price).toLocaleString("en-IN")
            : "—";

          return (
            <div key={alert.id} className="alert-item-row">
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span aria-hidden>🔔</span>
                <span className="alert-symbol">{sym}</span>
                <span className="alert-condition">
                  {cond} ₹{target}
                </span>
              </div>
              <button
                type="button"
                className="terminal-link-btn"
                style={{ color: "var(--mk-red)", fontSize: "0.72rem" }}
                onClick={() => handleDelete(alert.id)}
                title="Delete Alert"
              >
                ✕
              </button>
            </div>
          );
        })}
      </div>

      {/* Quick Create Alert Modal / Overlay */}
      {showCreateModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.65)",
            backdropFilter: "blur(2px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
          }}
          onClick={() => setShowCreateModal(false)}
        >
          <div
            style={{
              background: "var(--mk-surface)",
              border: "1px solid var(--mk-border)",
              borderRadius: "var(--mk-radius)",
              padding: 20,
              width: 320,
              maxWidth: "90%",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h4 style={{ margin: "0 0 14px 0", fontSize: "1rem", color: "var(--mk-text-primary)" }}>
              Create Price Alert
            </h4>
            <form onSubmit={handleCreate} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--mk-text-muted)" }}>Symbol</label>
                <input
                  type="text"
                  placeholder="e.g. RELIANCE"
                  className="quick-trade-input"
                  style={{ width: "100%", boxSizing: "border-box" }}
                  value={newSymbol}
                  onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                  required
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div>
                  <label style={{ fontSize: "0.75rem", color: "var(--mk-text-muted)" }}>Condition</label>
                  <select
                    className="quick-trade-select"
                    style={{ width: "100%" }}
                    value={newCondition}
                    onChange={(e) => setNewCondition(e.target.value as ">=" | "<=")}
                  >
                    <option value="&gt;=">&gt;= (Greater)</option>
                    <option value="&lt;=">&lt;= (Lesser)</option>
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: "0.75rem", color: "var(--mk-text-muted)" }}>Target Price</label>
                  <input
                    type="number"
                    step="0.05"
                    placeholder="Price"
                    className="quick-trade-input"
                    style={{ width: "100%", boxSizing: "border-box" }}
                    value={newTarget}
                    onChange={(e) => setNewTarget(e.target.value)}
                    required
                  />
                </div>
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button
                  type="button"
                  className="market-pill-btn"
                  style={{ flex: 1, padding: "8px" }}
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="quick-trade-submit"
                  style={{ flex: 1, height: 38 }}
                >
                  {submitting ? "Saving…" : "Save Alert"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
});
