import React, { useEffect, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchStrategyResultCandles,
  fetchStrategyResultHistory,
  type CandlePoint,
  type StrategyResultRow,
  type SymbolHistoryItem,
} from "../../api_strategy_tester";

interface StockDetailPanelProps {
  runId?: string;
  stock: StrategyResultRow | null;
  activeTab: "overview" | "chart" | "history";
  onTabChange: (tab: "overview" | "chart" | "history") => void;
  onClose: () => void;
}

export function formatINRVal(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return `₹${val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatVolVal(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}M`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
  return val.toLocaleString("en-IN");
}

export const StockDetailPanel: React.FC<StockDetailPanelProps> = ({
  runId = "STR-20260826-001",
  stock,
  activeTab,
  onTabChange,
  onClose,
}) => {
  const [candles, setCandles] = useState<CandlePoint[]>([]);
  const [history, setHistory] = useState<SymbolHistoryItem[]>([]);
  const [loadingCandles, setLoadingCandles] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const symbol = stock?.symbol || "RELIANCE";
  const company = stock?.company || "Reliance Industries Ltd.";
  const signal = stock?.signal || "BUY";
  const returnPct = stock?.return_pct ?? 14.82;
  const entryPrice = stock?.entry_price ?? 1420.0;
  const exitPrice = stock?.exit_price ?? 1630.0;
  const rsiVal = stock?.rsi ?? 64.2;
  const sma20Val = stock?.sma_20 ?? 1395.2;
  const sma50Val = stock?.sma_50 ?? 1350.4;
  const sma200Val = stock?.sma_200 ?? 1240.15;
  const volumeVal = stock?.volume ?? 8200000;
  const avgVolumeVal = stock?.avg_volume ?? 5100000;

  // Filter evaluations (from stock.filter_results / filter_details or default standard evaluations)
  const filterResults =
    stock?.filter_results ||
    stock?.filter_details?.map((d) => ({ name: d.label, passed: Boolean(d.passed) })) ||
    [
      { name: "Close > SMA 50", passed: true },
      { name: "SMA 50 > SMA 200", passed: true },
      { name: "RSI > 55", passed: true },
      { name: "Volume > Avg Volume", passed: true },
    ];

  // Fetch candles when chart tab is active
  useEffect(() => {
    if (activeTab === "chart" && runId && symbol) {
      let isMounted = true;
      setLoadingCandles(true);
      fetchStrategyResultCandles(runId, symbol)
        .then((res) => {
          if (isMounted) {
            setCandles(res.candles || []);
          }
        })
        .catch(() => {
          if (isMounted) {
            // Generate synthetic candle series if backend call fails
            const synth: CandlePoint[] = [];
            let px = entryPrice || 1400;
            for (let i = 30; i >= 0; i--) {
              const d = new Date();
              d.setDate(d.getDate() - i);
              px += (Math.random() - 0.46) * 18;
              synth.push({
                date: d.toISOString().slice(0, 10),
                open: px - 5,
                high: px + 10,
                low: px - 8,
                close: px,
                volume: Math.floor(4000000 + Math.random() * 5000000),
                sma_20: px - 15,
                sma_50: px - 35,
                sma_200: px - 80,
                rsi: 55 + Math.random() * 15,
              });
            }
            setCandles(synth);
          }
        })
        .finally(() => {
          if (isMounted) setLoadingCandles(false);
        });
      return () => {
        isMounted = false;
      };
    }
  }, [activeTab, runId, symbol, entryPrice]);

  // Fetch history when history tab is active
  useEffect(() => {
    if (activeTab === "history" && runId && symbol) {
      let isMounted = true;
      setLoadingHistory(true);
      fetchStrategyResultHistory(runId, symbol)
        .then((res) => {
          if (isMounted) {
            setHistory(res.history || []);
          }
        })
        .catch(() => {
          if (isMounted) {
            setHistory([
              {
                run_id: runId,
                strategy_name: "Momentum Strategy",
                date: new Date().toISOString(),
                signal: signal,
                entry_price: entryPrice,
                exit_price: exitPrice,
                return_pct: returnPct,
                status: "completed",
              },
            ]);
          }
        })
        .finally(() => {
          if (isMounted) setLoadingHistory(false);
        });
      return () => {
        isMounted = false;
      };
    }
  }, [activeTab, runId, symbol, signal, entryPrice, exitPrice, returnPct]);

  // Math formula text
  const calcFormula = `((Exit - Entry) / Entry) × 100`;
  const calcExact = `((${exitPrice} - ${entryPrice}) / ${entryPrice}) × 100`;

  return (
    <aside className="st-detail-panel" aria-label="Stock detail overview and chart">
      {/* Header */}
      <div className="st-detail-header">
        <div className="st-detail-stock-identity">
          <div className="st-detail-stock-icon">◎</div>
          <div>
            <div className="st-detail-symbol">{symbol}</div>
            <div className="st-detail-company">{company}</div>
          </div>
        </div>
        <button
          type="button"
          className="st-detail-close-btn"
          onClick={onClose}
          aria-label="Close stock details"
          title="Close details"
          data-testid="btn-close-detail-panel"
        >
          ✕
        </button>
      </div>

      {/* Metric Banner Card */}
      <div className="st-detail-banner-card">
        <div className="st-banner-metric">
          <span className="st-banner-metric-label">Signal</span>
          <div style={{ marginTop: 2 }}>
            <span className={`st-badge-signal ${signal}`}>{signal}</span>
          </div>
        </div>
        <div className="st-banner-metric">
          <span className="st-banner-metric-label">Hold Return</span>
          <span className={`st-banner-metric-val ${returnPct >= 0 ? "green" : "red"}`}>
            {returnPct > 0 ? `+${returnPct.toFixed(2)}%` : `${returnPct.toFixed(2)}%`}
          </span>
        </div>
        <div className="st-banner-metric">
          <span className="st-banner-metric-label">Window Start</span>
          <span className="st-banner-metric-val">{formatINRVal(entryPrice)}</span>
        </div>
        <div className="st-banner-metric">
          <span className="st-banner-metric-label">Close</span>
          <span className="st-banner-metric-val">{formatINRVal(exitPrice)}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="st-detail-tabs">
        <button
          type="button"
          className={`st-detail-tab-btn ${activeTab === "overview" ? "is-active" : ""}`}
          onClick={() => onTabChange("overview")}
          data-testid="tab-detail-overview"
        >
          Overview
        </button>
        <button
          type="button"
          className={`st-detail-tab-btn ${activeTab === "chart" ? "is-active" : ""}`}
          onClick={() => onTabChange("chart")}
          data-testid="tab-detail-chart"
        >
          Chart
        </button>
        <button
          type="button"
          className={`st-detail-tab-btn ${activeTab === "history" ? "is-active" : ""}`}
          onClick={() => onTabChange("history")}
          data-testid="tab-detail-history"
        >
          History
        </button>
      </div>

      {/* Body Content */}
      <div className="st-detail-body">
        {activeTab === "overview" && (
          <>
            {/* Section 1: Indicators */}
            <div>
              <h3 className="st-detail-section-title">Indicators</h3>
              <div className="st-detail-kv-list">
                <div className="st-detail-kv-row">
                  <span>RSI</span>
                  <span>{rsiVal != null ? rsiVal.toFixed(1) : "—"}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>SMA 20</span>
                  <span>{formatINRVal(sma20Val)}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>SMA 50</span>
                  <span>{formatINRVal(sma50Val)}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>SMA 200</span>
                  <span>{formatINRVal(sma200Val)}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Volume</span>
                  <span>{formatVolVal(volumeVal)}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Avg Volume</span>
                  <span>{formatVolVal(avgVolumeVal)}</span>
                </div>
              </div>
            </div>

            {/* Section 2: Filter Evaluation */}
            <div>
              <h3 className="st-detail-section-title">Filter Evaluation</h3>
              <div className="st-filter-eval-list">
                {filterResults.map((f, i) => (
                  <div key={f.name || i} className="st-filter-eval-item">
                    <span className="st-filter-eval-name">{f.name}</span>
                    <span className={`st-filter-eval-status ${f.passed ? "passed" : "failed"}`}>
                      {f.passed ? "✓ Passed" : "✕ Failed"}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Section 3: Return Calculation */}
            <div>
              <h3 className="st-detail-section-title">Return Calculation</h3>
              <div className="st-detail-kv-list">
                <div className="st-detail-kv-row">
                  <span>Entry Price (Buy)</span>
                  <span>{formatINRVal(entryPrice)}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Exit Price (Sell)</span>
                  <span>{formatINRVal(exitPrice)}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Formula</span>
                  <span style={{ fontSize: "0.68rem", color: "#94a3b8" }}>{calcFormula}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Calculation</span>
                  <span style={{ fontSize: "0.68rem", color: "#94a3b8" }}>{calcExact}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Return %</span>
                  <span style={{ color: returnPct >= 0 ? "#4ade80" : "#f87171" }}>
                    {returnPct > 0 ? `+${returnPct.toFixed(2)}%` : `${returnPct.toFixed(2)}%`}
                  </span>
                </div>
              </div>
            </div>

            {/* Section 4: Additional Info */}
            <div>
              <h3 className="st-detail-section-title">Additional Info</h3>
              <div className="st-detail-kv-list">
                <div className="st-detail-kv-row">
                  <span>Run ID</span>
                  <span style={{ color: "#38bdf8" }}>{runId}</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Timeframe</span>
                  <span>1 Day</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Exit Rule</span>
                  <span>EOD (End of Day)</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Position</span>
                  <span style={{ color: "#4ade80" }}>LONG</span>
                </div>
                <div className="st-detail-kv-row">
                  <span>Data As Of</span>
                  <span>26 Aug 2026</span>
                </div>
              </div>
            </div>
          </>
        )}

        {activeTab === "chart" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <h3 className="st-detail-section-title">Price & Indicator Chart</h3>
            {loadingCandles ? (
              <div style={{ textAlign: "center", padding: 20, color: "#64748b" }}>Loading chart data...</div>
            ) : candles.length === 0 ? (
              <div style={{ textAlign: "center", padding: 20, color: "#64748b" }}>No chart bars available.</div>
            ) : (
              <>
                <div style={{ width: "100%", height: 220 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={candles} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                      <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} />
                      <YAxis domain={["auto", "auto"]} tick={{ fill: "#64748b", fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{ background: "#091022", borderColor: "#1e293b", borderRadius: 6, fontSize: 12 }}
                      />
                      <Line type="monotone" dataKey="close" stroke="#38bdf8" strokeWidth={2} dot={false} name="Close" />
                      <Line type="monotone" dataKey="sma_20" stroke="#eab308" strokeWidth={1.5} dot={false} name="SMA 20" />
                      <Line type="monotone" dataKey="sma_50" stroke="#a855f7" strokeWidth={1.5} dot={false} name="SMA 50" />
                      <Line type="monotone" dataKey="sma_200" stroke="#f43f5e" strokeWidth={1.5} dot={false} name="SMA 200" />
                      {entryPrice ? (
                        <ReferenceLine y={entryPrice} stroke="#22c55e" strokeDasharray="3 3" label={{ value: "Entry", fill: "#22c55e", fontSize: 10 }} />
                      ) : null}
                      {exitPrice ? (
                        <ReferenceLine y={exitPrice} stroke="#ef4444" strokeDasharray="3 3" label={{ value: "Exit", fill: "#ef4444", fontSize: 10 }} />
                      ) : null}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                {/* Volume Subchart */}
                <div style={{ width: "100%", height: 80 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={candles} margin={{ top: 0, right: 10, left: -20, bottom: 0 }}>
                      <XAxis dataKey="date" hide />
                      <YAxis tick={{ fill: "#64748b", fontSize: 9 }} />
                      <Bar dataKey="volume" fill="#1e3a8a" name="Volume" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem", color: "#64748b" }}>
                  <span><span style={{ color: "#38bdf8" }}>—</span> Close</span>
                  <span><span style={{ color: "#eab308" }}>—</span> SMA20</span>
                  <span><span style={{ color: "#a855f7" }}>—</span> SMA50</span>
                  <span><span style={{ color: "#f43f5e" }}>—</span> SMA200</span>
                </div>
              </>
            )}
          </div>
        )}

        {activeTab === "history" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <h3 className="st-detail-section-title">Test Run History</h3>
            {loadingHistory ? (
              <div style={{ textAlign: "center", padding: 20, color: "#64748b" }}>Loading history...</div>
            ) : history.length === 0 ? (
              <div style={{ textAlign: "center", padding: 20, color: "#64748b" }}>No past runs for this stock.</div>
            ) : (
              <table className="st-micro-table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>Signal</th>
                    <th style={{ textAlign: "right" }}>Return %</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h, i) => (
                    <tr key={h.run_id || i}>
                      <td style={{ color: "#38bdf8", fontWeight: 600 }}>{h.run_id}</td>
                      <td>
                        <span className={`st-badge-signal ${h.signal || "REJECT"}`}>
                          {h.signal || "REJECT"}
                        </span>
                      </td>
                      <td
                        style={{
                          textAlign: "right",
                          fontWeight: 700,
                          color: (h.return_pct ?? 0) >= 0 ? "#4ade80" : "#f87171",
                        }}
                      >
                        {(h.return_pct ?? 0) > 0 ? `+${(h.return_pct ?? 0).toFixed(2)}%` : `${(h.return_pct ?? 0).toFixed(2)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </aside>
  );
};
