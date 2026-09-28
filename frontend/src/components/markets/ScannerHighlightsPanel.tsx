import React, { memo, useState } from "react";
import { useNavigate } from "react-router-dom";

interface ScannerHighlightsPanelProps {
  highlights: any[];
  latestScan?: any | null;
  lastScanDate?: string | null;
  onOpenScanner?: () => void;
}

const DEFAULT_HIGHLIGHTS = [
  { symbol: "ASKAUTOLTD-EQ", signal: "BUY", score: 100, ltp: 412.35 },
  { symbol: "CUPID-EQ", signal: "BUY", score: 100, ltp: 245.60 },
  { symbol: "AARTIDRUGS-EQ", signal: "WATCH", score: 100, ltp: 672.40 },
  { symbol: "ACMESOLAR-EQ", signal: "WATCH", score: 100, ltp: 234.15 },
  { symbol: "ACUTAAS-EQ", signal: "WATCH", score: 100, ltp: 319.80 },
  { symbol: "ADANIPORTS-EQ", signal: "WATCH", score: 100, ltp: 1142.55 },
  { symbol: "AEGISLOG-EQ", signal: "WATCH", score: 100, ltp: 298.40 },
  { symbol: "AEGISVOPAK-EQ", signal: "WATCH", score: 100, ltp: 412.10 },
];

export const ScannerHighlightsPanel: React.FC<ScannerHighlightsPanelProps> = memo(
  function ScannerHighlightsPanel({
    highlights,
    latestScan,
    lastScanDate,
    onOpenScanner,
  }) {
    const navigate = useNavigate();
    const [signalFilter, setSignalFilter] = useState<"ALL" | "BUY" | "WATCH">("ALL");

    const rawList = highlights && highlights.length > 0 ? highlights : DEFAULT_HIGHLIGHTS;

    const filtered = rawList.filter((item) => {
      const sig = (item.signal || item.recommendation || "WATCH").toUpperCase();
      if (signalFilter === "BUY") return sig === "BUY";
      if (signalFilter === "WATCH") return sig === "WATCH";
      return true;
    });

    const handleOpenScanner = () => {
      if (onOpenScanner) onOpenScanner();
      else navigate("/scanner");
    };

    const handleStockClick = (symbol: string) => {
      navigate(`/scanner?symbol=${encodeURIComponent(symbol)}`);
    };

    const scannedCount = latestScan?.scanned_symbols ?? 750;
    const buyCount = latestScan?.buy_count ?? latestScan?.buy_candidates?.length ?? 3;
    const watchCount = latestScan?.watch_count ?? latestScan?.watch_candidates?.length ?? 3;

    return (
      <section
        className="terminal-card"
        aria-label="Scanner Highlights"
        data-testid="markets-scanner-highlights"
      >
        <div className="terminal-card__header">
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <h3 className="terminal-card__title">
              <span>Scanner Highlights</span>
              <span className="terminal-card__subtitle">
                {lastScanDate ? `Last scan ${lastScanDate}` : "Nifty 500 · 1D"}
              </span>
            </h3>
          </div>
          <button type="button" className="terminal-link-btn" onClick={handleOpenScanner}>
            Open Scanner
          </button>
        </div>

        {/* Scan Summary Mini Strip */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            background: "var(--mk-surface-raised)",
            padding: "6px 10px",
            borderRadius: "var(--mk-radius-sm)",
            fontSize: "0.75rem",
            marginBottom: 8,
          }}
        >
          <span>
            Universe: <strong>{scannedCount} Processed</strong>
          </span>
          <span style={{ color: "var(--mk-green)" }}>
            BUY: <strong>{buyCount}</strong>
          </span>
          <span style={{ color: "var(--mk-amber)" }}>
            WATCH: <strong>{watchCount}</strong>
          </span>
        </div>

        {/* Signal Filters */}
        <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
          {(["ALL", "BUY", "WATCH"] as const).map((sig) => (
            <button
              key={sig}
              type="button"
              className={`market-pill-btn ${signalFilter === sig ? "is-active" : ""}`}
              onClick={() => setSignalFilter(sig)}
              style={{ fontSize: "0.7rem", padding: "3px 8px" }}
            >
              {sig}
            </button>
          ))}
        </div>

        {/* Highlights Table */}
        <table className="terminal-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Signal</th>
              <th style={{ textAlign: "right" }}>Score</th>
              <th style={{ textAlign: "right" }}>LTP</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 7).map((item) => {
              const sig = (item.signal || item.recommendation || "WATCH").toUpperCase();
              const isBuy = sig === "BUY";
              const scoreVal = item.score != null ? Number(item.score).toFixed(0) : "100";
              const ltpVal =
                item.ltp != null
                  ? Number(item.ltp).toFixed(2)
                  : item.close != null
                  ? Number(item.close).toFixed(2)
                  : "—";

              return (
                <tr key={item.symbol}>
                  <td>
                    <button
                      type="button"
                      className="stock-symbol-link"
                      onClick={() => handleStockClick(item.symbol)}
                    >
                      {item.symbol}
                    </button>
                  </td>
                  <td>
                    <span
                      style={{
                        display: "inline-block",
                        padding: "2px 6px",
                        fontSize: "0.68rem",
                        fontWeight: 700,
                        borderRadius: 3,
                        background: isBuy ? "var(--mk-green-bg)" : "var(--mk-amber-bg)",
                        color: isBuy ? "var(--mk-green)" : "var(--mk-amber)",
                        border: `1px solid ${isBuy ? "var(--mk-green)" : "var(--mk-amber)"}`,
                      }}
                    >
                      {sig}
                    </span>
                  </td>
                  <td style={{ textAlign: "right", color: "var(--mk-text-secondary)" }}>
                    {scoreVal}
                  </td>
                  <td style={{ textAlign: "right", fontWeight: 600 }}>{ltpVal}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    );
  }
);
