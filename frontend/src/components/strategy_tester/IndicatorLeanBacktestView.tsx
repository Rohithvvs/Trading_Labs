import React, { useMemo, useState } from "react";
import type { IndicatorBacktestJob, LeanBacktestResult, LeanTrade } from "../../api_indicator_scanner";

export interface IndicatorLeanBacktestViewProps {
  job: IndicatorBacktestJob | null;
  result: LeanBacktestResult | null;
  loading: boolean;
  onCancel?: () => void;
  onClose?: () => void;
  onRerun?: () => void;
}

function formatINR(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return "₹0.00";
  const sign = val < 0 ? "-" : "";
  const abs = Math.abs(val);
  return `${sign}₹${abs.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPct(val: number | null | undefined): string {
  if (val === null || val === undefined || isNaN(val)) return "0.00%";
  const sign = val > 0 ? "+" : "";
  return `${sign}${(val).toFixed(2)}%`;
}

export const IndicatorLeanBacktestView: React.FC<IndicatorLeanBacktestViewProps> = ({
  job,
  result,
  loading,
  onCancel,
  onClose,
  onRerun,
}) => {
  const [tradeFilter, setTradeFilter] = useState<"ALL" | "WINNERS" | "LOSERS">("ALL");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [tradePage, setTradePage] = useState(1);
  const pageSize = 20;

  const isRunning = job?.status === "RUNNING" || job?.status === "QUEUED" || loading;
  const isFailed = job?.status === "FAILED";

  const allTrades = useMemo(() => result?.trades || [], [result]);

  const filteredTrades = useMemo(() => {
    let list = allTrades;
    if (tradeFilter === "WINNERS") {
      list = list.filter((t) => t.netPnL > 0);
    } else if (tradeFilter === "LOSERS") {
      list = list.filter((t) => t.netPnL < 0);
    }
    if (symbolSearch.trim()) {
      const q = symbolSearch.trim().toUpperCase();
      list = list.filter((t) => t.symbol.toUpperCase().includes(q));
    }
    return list;
  }, [allTrades, tradeFilter, symbolSearch]);

  const paginatedTrades = useMemo(() => {
    const start = (tradePage - 1) * pageSize;
    return filteredTrades.slice(start, start + pageSize);
  }, [filteredTrades, tradePage, pageSize]);

  const totalPages = Math.max(1, Math.ceil(filteredTrades.length / pageSize));

  // Export CSV functionality
  const handleExportTradesCsv = () => {
    if (!result || !allTrades.length) return;
    const headers = [
      "Trade ID",
      "Symbol",
      "Direction",
      "Entry Date",
      "Entry Price",
      "Exit Date",
      "Exit Price",
      "Quantity",
      "Gross P&L",
      "Commission",
      "Slippage",
      "Net P&L",
      "Return %",
      "Holding Days",
      "Entry Reason",
      "Exit Reason",
    ];
    const rows = allTrades.map((t) => [
      t.tradeId,
      t.symbol,
      t.direction,
      t.entryDate,
      t.entryPrice.toFixed(2),
      t.exitDate || "",
      t.exitPrice !== null && t.exitPrice !== undefined ? t.exitPrice.toFixed(2) : "",
      t.quantity,
      t.grossPnL.toFixed(2),
      t.commission.toFixed(2),
      t.slippage.toFixed(2),
      t.netPnL.toFixed(2),
      (t.returnPct * 100).toFixed(2),
      t.holdingPeriod,
      `"${(t.entryReason || "").replace(/"/g, '""')}"`,
      `"${(t.exitReason || "").replace(/"/g, '""')}"`,
    ]);

    const csvContent = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `LEAN_${result.strategyId || "Backtest"}_Trades.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Render SVG Equity Curve
  const equityPoints = result?.equityCurve || [];
  const svgChart = useMemo(() => {
    if (equityPoints.length < 2) return null;
    const width = 800;
    const height = 220;
    const padX = 40;
    const padY = 20;

    const values = equityPoints.map((p) => p.equity);
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const valRange = maxVal - minVal || 1;

    const getX = (index: number) => padX + (index / (equityPoints.length - 1)) * (width - padX * 2);
    const getY = (val: number) => height - padY - ((val - minVal) / valRange) * (height - padY * 2);

    const pointsStr = equityPoints.map((p, idx) => `${getX(idx).toFixed(1)},${getY(p.equity).toFixed(1)}`).join(" ");
    const areaStr = `${pointsStr} ${getX(equityPoints.length - 1).toFixed(1)},${height - padY} ${getX(0).toFixed(1)},${height - padY}`;

    const startVal = values[0];
    const endVal = values[values.length - 1];
    const isGain = endVal >= startVal;
    const strokeColor = isGain ? "#10b981" : "#ef4444";
    const gradientId = `equityGrad_${isGain ? "green" : "red"}`;

    return (
      <div style={{ width: "100%", overflowX: "auto" }} data-testid="lean-equity-chart">
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", height: "auto", maxHeight: 240, display: "block" }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.3" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1={padX} y1={padY} x2={width - padX} y2={padY} stroke="#1e293b" strokeDasharray="4" />
          <line x1={padX} y1={height / 2} x2={width - padX} y2={height / 2} stroke="#1e293b" strokeDasharray="4" />
          <line x1={padX} y1={height - padY} x2={width - padX} y2={height - padY} stroke="#1e293b" />

          {/* Value labels */}
          <text x={padX} y={padY - 4} fill="#64748b" fontSize="10" textAnchor="start">
            {formatINR(maxVal)}
          </text>
          <text x={padX} y={height - padY + 14} fill="#64748b" fontSize="10" textAnchor="start">
            {formatINR(minVal)}
          </text>
          <text x={width - padX} y={height - padY + 14} fill="#94a3b8" fontSize="10" textAnchor="end">
            {equityPoints[equityPoints.length - 1]?.date || ""}
          </text>
          <text x={padX} y={height - padY + 14} fill="#94a3b8" fontSize="10" textAnchor="start" dx="50">
            {equityPoints[0]?.date || ""}
          </text>

          {/* Shaded Area */}
          <polygon points={areaStr} fill={`url(#${gradientId})`} />

          {/* Main curve */}
          <polyline fill="none" stroke={strokeColor} strokeWidth="2" points={pointsStr} />
        </svg>
      </div>
    );
  }, [equityPoints]);

  return (
    <div
      className="st-card"
      style={{
        background: "#0b1222",
        border: "1px solid #1e293b",
        borderRadius: 8,
        padding: 16,
        marginBottom: 20,
      }}
      data-testid="indicator-lean-backtest-panel"
    >
      {/* Header bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 12,
          borderBottom: "1px solid #1e293b",
          paddingBottom: 12,
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              background: "linear-gradient(135deg, #1e3a8a, #2563eb)",
              color: "#fff",
              padding: "6px 10px",
              borderRadius: 6,
              fontWeight: 700,
              fontSize: "0.85rem",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>⚡ QuantConnect LEAN</span>
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: "1.05rem", color: "#f8fafc", fontWeight: 600 }}>
              {result?.strategyName || job?.strategyName || "Indicator Strategy Backtest"}
            </h3>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8", display: "flex", gap: 12, marginTop: 2 }}>
              <span>Job: {job?.jobId || result?.jobId || "—"}</span>
              {result && (
                <span>
                  Period: {result.startDate} to {result.endDate}
                </span>
              )}
              {result?.summary?.dataSource && <span>Source: {result.summary.dataSource}</span>}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {allTrades.length > 0 && (
            <button
              type="button"
              className="st-btn-dark"
              onClick={handleExportTradesCsv}
              title="Export all trades to CSV"
              data-testid="btn-export-lean-trades"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Export CSV
            </button>
          )}
          {onRerun && (
            <button
              type="button"
              className="st-btn-dark"
              onClick={onRerun}
              title="Configure & Rerun Backtest"
              data-testid="btn-rerun-lean-backtest"
            >
              ↻ Settings
            </button>
          )}
          {onClose && (
            <button
              type="button"
              className="st-btn-dark"
              onClick={onClose}
              title="Close Backtest View"
              data-testid="btn-close-lean-panel"
            >
              ✕ Close
            </button>
          )}
        </div>
      </div>

      {/* In Progress Banner */}
      {isRunning && (
        <div
          style={{
            background: "#0d182e",
            border: "1px solid #1e3a8a",
            borderRadius: 6,
            padding: 16,
            marginBottom: 16,
          }}
          data-testid="lean-running-card"
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: "0.875rem", color: "#93c5fd", fontWeight: 600 }}>
              Execution in progress: {job?.stage || "Running QuantConnect LEAN engine..."}
            </span>
            <span style={{ fontSize: "1.1rem", fontWeight: 700, color: "#60a5fa" }}>
              {job?.progressPct || 0}%
            </span>
          </div>
          <div style={{ width: "100%", height: 8, background: "#1e293b", borderRadius: 4, overflow: "hidden" }}>
            <div
              style={{
                width: `${Math.max(5, Math.min(100, job?.progressPct || 0))}%`,
                height: "100%",
                background: "linear-gradient(90deg, #2563eb, #38bdf8)",
                transition: "width 0.3s ease",
              }}
            />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
            <span style={{ fontSize: "0.75rem", color: "#64748b" }}>
              Simulating multi-asset portfolio orders across historical sessions...
            </span>
            {onCancel && (
              <button
                type="button"
                className="st-btn-reset"
                onClick={onCancel}
                style={{ padding: "3px 8px", fontSize: "0.75rem" }}
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}

      {/* Failed Banner */}
      {isFailed && (
        <div
          style={{
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid #ef4444",
            borderRadius: 6,
            padding: 14,
            marginBottom: 16,
            color: "#fca5a5",
          }}
          data-testid="lean-error-card"
        >
          <strong>Backtest Failed:</strong> {job?.error || "Unknown execution error."}
        </div>
      )}

      {/* Completed Results Dashboard */}
      {result && result.summary && (
        <>
          {/* Top KPI Cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
              gap: 10,
              marginBottom: 16,
            }}
            data-testid="lean-kpi-grid"
          >
            {/* Net Profit */}
            <div style={{ background: "#0d1527", padding: "10px 12px", borderRadius: 6, border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>
                Net Profit
              </div>
              <div
                style={{
                  fontSize: "1.05rem",
                  fontWeight: 700,
                  color: result.summary.netProfit >= 0 ? "#10b981" : "#ef4444",
                  marginTop: 2,
                }}
              >
                {formatINR(result.summary.netProfit)}
              </div>
              <div style={{ fontSize: "0.75rem", color: result.summary.netProfit >= 0 ? "#10b981" : "#ef4444" }}>
                {formatPct(result.summary.netProfitPct)}
              </div>
            </div>

            {/* CAGR */}
            <div style={{ background: "#0d1527", padding: "10px 12px", borderRadius: 6, border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>
                CAGR
              </div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#f8fafc", marginTop: 2 }}>
                {result.summary.cagr !== null && result.summary.cagr !== undefined
                  ? `${(result.summary.cagr * 100).toFixed(2)}%`
                  : "—"}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>Annualized</div>
            </div>

            {/* Sharpe Ratio */}
            <div style={{ background: "#0d1527", padding: "10px 12px", borderRadius: 6, border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>
                Sharpe Ratio
              </div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#f8fafc", marginTop: 2 }}>
                {result.summary.sharpeRatio.toFixed(2)}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
                Sortino: {result.summary.sortinoRatio.toFixed(2)}
              </div>
            </div>

            {/* Max Drawdown */}
            <div style={{ background: "#0d1527", padding: "10px 12px", borderRadius: 6, border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>
                Max Drawdown
              </div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#ef4444", marginTop: 2 }}>
                -{(result.summary.maximumDrawdownPct * 100).toFixed(2)}%
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
                {formatINR(-result.summary.maximumDrawdown)}
              </div>
            </div>

            {/* Win Rate */}
            <div style={{ background: "#0d1527", padding: "10px 12px", borderRadius: 6, border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>
                Win Rate
              </div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#f8fafc", marginTop: 2 }}>
                {(result.summary.winRate * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
                Profit Factor: {result.summary.profitFactor.toFixed(2)}
              </div>
            </div>

            {/* Total Trades */}
            <div style={{ background: "#0d1527", padding: "10px 12px", borderRadius: 6, border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>
                Trades Count
              </div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#f8fafc", marginTop: 2 }}>
                {result.summary.totalTrades}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
                <span style={{ color: "#10b981" }}>{result.summary.winningTrades} W</span> /{" "}
                <span style={{ color: "#ef4444" }}>{result.summary.losingTrades} L</span>
              </div>
            </div>

            {/* Final Equity */}
            <div style={{ background: "#0d1527", padding: "10px 12px", borderRadius: 6, border: "1px solid #1e293b" }}>
              <div style={{ fontSize: "0.7rem", color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>
                Ending Equity
              </div>
              <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "#f8fafc", marginTop: 2 }}>
                {formatINR(result.summary.finalEquity)}
              </div>
              <div style={{ fontSize: "0.75rem", color: "#64748b" }}>
                Init: {formatINR(result.summary.initialCapital)}
              </div>
            </div>
          </div>

          {/* Equity Chart Section */}
          <div
            style={{
              background: "#0d1527",
              border: "1px solid #1e293b",
              borderRadius: 6,
              padding: 12,
              marginBottom: 16,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: "0.8125rem", color: "#94a3b8", fontWeight: 600 }}>
                Portfolio Equity Curve (₹)
              </span>
              <span style={{ fontSize: "0.75rem", color: "#64748b" }}>
                Model: {result.summary.executionModel} · Coverage: {(result.summary.dataCoverageRatio * 100).toFixed(0)}%
              </span>
            </div>
            {svgChart}
          </div>

          {/* Closed Trades Table Section */}
          <div
            style={{
              background: "#0d1527",
              border: "1px solid #1e293b",
              borderRadius: 6,
              padding: 12,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 10,
                marginBottom: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: "0.875rem", color: "#f8fafc", fontWeight: 600 }}>
                  Closed Trades ({filteredTrades.length})
                </span>
                <div style={{ display: "flex", gap: 4 }}>
                  <button
                    type="button"
                    className={`st-btn-dark ${tradeFilter === "ALL" ? "is-active" : ""}`}
                    onClick={() => {
                      setTradeFilter("ALL");
                      setTradePage(1);
                    }}
                    style={{
                      padding: "3px 8px",
                      fontSize: "0.75rem",
                      background: tradeFilter === "ALL" ? "#2563eb" : undefined,
                    }}
                  >
                    All ({allTrades.length})
                  </button>
                  <button
                    type="button"
                    className={`st-btn-dark ${tradeFilter === "WINNERS" ? "is-active" : ""}`}
                    onClick={() => {
                      setTradeFilter("WINNERS");
                      setTradePage(1);
                    }}
                    style={{
                      padding: "3px 8px",
                      fontSize: "0.75rem",
                      background: tradeFilter === "WINNERS" ? "#10b981" : undefined,
                    }}
                  >
                    Wins ({result.summary.winningTrades})
                  </button>
                  <button
                    type="button"
                    className={`st-btn-dark ${tradeFilter === "LOSERS" ? "is-active" : ""}`}
                    onClick={() => {
                      setTradeFilter("LOSERS");
                      setTradePage(1);
                    }}
                    style={{
                      padding: "3px 8px",
                      fontSize: "0.75rem",
                      background: tradeFilter === "LOSERS" ? "#ef4444" : undefined,
                    }}
                  >
                    Losses ({result.summary.losingTrades})
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="text"
                  placeholder="Filter by symbol..."
                  value={symbolSearch}
                  onChange={(e) => {
                    setSymbolSearch(e.target.value);
                    setTradePage(1);
                  }}
                  style={{
                    padding: "4px 8px",
                    background: "#090d16",
                    border: "1px solid #334155",
                    borderRadius: 4,
                    color: "#f8fafc",
                    fontSize: "0.75rem",
                    width: 140,
                  }}
                />
              </div>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: "0.75rem",
                  color: "#cbd5e1",
                }}
                data-testid="lean-trades-table"
              >
                <thead>
                  <tr style={{ borderBottom: "1px solid #1e293b", color: "#64748b", textAlign: "left" }}>
                    <th style={{ padding: "6px 8px" }}>#</th>
                    <th style={{ padding: "6px 8px" }}>Symbol</th>
                    <th style={{ padding: "6px 8px" }}>Direction</th>
                    <th style={{ padding: "6px 8px" }}>Entry Date</th>
                    <th style={{ padding: "6px 8px" }}>Entry Price</th>
                    <th style={{ padding: "6px 8px" }}>Exit Date</th>
                    <th style={{ padding: "6px 8px" }}>Exit Price</th>
                    <th style={{ padding: "6px 8px" }}>Qty</th>
                    <th style={{ padding: "6px 8px" }}>Return %</th>
                    <th style={{ padding: "6px 8px" }}>Net P&L</th>
                    <th style={{ padding: "6px 8px" }}>Holding</th>
                    <th style={{ padding: "6px 8px" }}>Exit Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedTrades.map((t: LeanTrade) => {
                    const isWin = t.netPnL >= 0;
                    return (
                      <tr
                        key={`${t.tradeId}-${t.symbol}-${t.entryDate}`}
                        style={{ borderBottom: "1px solid #0f172a" }}
                      >
                        <td style={{ padding: "6px 8px", color: "#64748b" }}>{t.tradeId}</td>
                        <td style={{ padding: "6px 8px", fontWeight: 600, color: "#f8fafc" }}>{t.symbol}</td>
                        <td style={{ padding: "6px 8px" }}>
                          <span
                            style={{
                              padding: "2px 5px",
                              borderRadius: 3,
                              background: "rgba(16, 185, 129, 0.15)",
                              color: "#10b981",
                              fontWeight: 600,
                              fontSize: "0.7rem",
                            }}
                          >
                            {t.direction}
                          </span>
                        </td>
                        <td style={{ padding: "6px 8px" }}>{t.entryDate}</td>
                        <td style={{ padding: "6px 8px" }}>₹{t.entryPrice.toFixed(2)}</td>
                        <td style={{ padding: "6px 8px" }}>{t.exitDate || "—"}</td>
                        <td style={{ padding: "6px 8px" }}>
                          {t.exitPrice !== null && t.exitPrice !== undefined ? `₹${t.exitPrice.toFixed(2)}` : "—"}
                        </td>
                        <td style={{ padding: "6px 8px" }}>{t.quantity}</td>
                        <td
                          style={{
                            padding: "6px 8px",
                            fontWeight: 600,
                            color: isWin ? "#10b981" : "#ef4444",
                          }}
                        >
                          {(t.returnPct * 100) > 0 ? `+${(t.returnPct * 100).toFixed(2)}%` : `${(t.returnPct * 100).toFixed(2)}%`}
                        </td>
                        <td
                          style={{
                            padding: "6px 8px",
                            fontWeight: 600,
                            color: isWin ? "#10b981" : "#ef4444",
                          }}
                        >
                          {formatINR(t.netPnL)}
                        </td>
                        <td style={{ padding: "6px 8px" }}>{t.holdingPeriod} d</td>
                        <td style={{ padding: "6px 8px", color: "#94a3b8" }}>{t.exitReason}</td>
                      </tr>
                    );
                  })}
                  {paginatedTrades.length === 0 && (
                    <tr>
                      <td colSpan={12} style={{ padding: "16px", textAlign: "center", color: "#64748b" }}>
                        No trades found matching current filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: 10,
                  fontSize: "0.75rem",
                  color: "#64748b",
                }}
              >
                <span>
                  Page {tradePage} of {totalPages} ({filteredTrades.length} trades)
                </span>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    type="button"
                    className="st-btn-dark"
                    disabled={tradePage <= 1}
                    onClick={() => setTradePage((p) => Math.max(1, p - 1))}
                    style={{ padding: "2px 8px" }}
                  >
                    Prev
                  </button>
                  <button
                    type="button"
                    className="st-btn-dark"
                    disabled={tradePage >= totalPages}
                    onClick={() => setTradePage((p) => Math.min(totalPages, p + 1))}
                    style={{ padding: "2px 8px" }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
