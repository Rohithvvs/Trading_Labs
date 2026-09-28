import React, { memo } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkline } from "../Sparkline";

interface WatchlistPanelProps {
  watchlist: string[];
  stocksData?: Record<string, { ltp?: number | null; change_pct?: number | null }>;
}

export const WatchlistPanel: React.FC<WatchlistPanelProps> = memo(function WatchlistPanel({
  watchlist,
  stocksData = {},
}) {
  const navigate = useNavigate();

  const handleStockClick = (symbol: string) => {
    navigate(`/scanner?symbol=${encodeURIComponent(symbol)}`);
  };

  const hasWatchlist = Array.isArray(watchlist) && watchlist.length > 0;

  const items = hasWatchlist
    ? watchlist.slice(0, 6).map((sym) => {
        const d = stocksData[sym] || {};
        return {
          symbol: sym,
          price: d.ltp != null ? d.ltp : null,
          change_pct: d.change_pct != null ? d.change_pct : null,
        };
      })
    : [];

  return (
    <section className="terminal-card" aria-label="My Watchlist" data-testid="markets-watchlist-card">
      <div className="terminal-card__header">
        <h3 className="terminal-card__title">
          <span>Watchlist</span>
          <span className="terminal-card__subtitle">({items.length} Tracked)</span>
        </h3>
        <button
          type="button"
          className="terminal-link-btn"
          onClick={() => navigate("/watchlist")}
        >
          View all
        </button>
      </div>

      <table className="terminal-table">
        <thead>
          <tr>
            <th style={{ width: 20 }}>★</th>
            <th>Symbol</th>
            <th style={{ textAlign: "right" }}>LTP</th>
            <th style={{ width: 60 }}>Trend</th>
            <th style={{ textAlign: "right" }}>% Change</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td
                colSpan={5}
                style={{
                  textAlign: "center",
                  color: "var(--mk-text-muted)",
                  padding: "20px 0",
                  fontSize: "0.85rem",
                }}
              >
                No symbols in watchlist. Star stocks in Scanner to track here.
              </td>
            </tr>
          ) : (
            items.map((stock, idx) => {
              const sym = stock.symbol || "—";
              const chg = Number(stock.change_pct ?? 0);
              const isPos = chg >= 0;
              const priceStr =
                stock.price != null
                  ? Number(stock.price).toLocaleString("en-IN", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })
                  : "—";

              const sparkData = [100, 100 + chg * 0.3, 100 + chg * 0.7, 100 + chg];

              return (
                <tr key={sym || idx}>
                  <td style={{ color: "#eab308", fontSize: "0.85rem", cursor: "pointer" }}>★</td>
                <td>
                  <button
                    type="button"
                    className="stock-symbol-link"
                    onClick={() => handleStockClick(stock.symbol)}
                  >
                    {stock.symbol}
                  </button>
                </td>
                <td style={{ textAlign: "right", fontWeight: 600 }}>{priceStr}</td>
                <td style={{ width: 60 }}>
                  <div style={{ width: 50, height: 18 }}>
                    <Sparkline values={sparkData} width={50} height={18} />
                  </div>
                </td>
                <td
                  style={{
                    textAlign: "right",
                    fontWeight: 600,
                    color: isPos ? "var(--mk-green)" : "var(--mk-red)",
                  }}
                >
                  {isPos ? "+" : ""}
                  {chg.toFixed(2)}%
                </td>
              </tr>
            );
          }))}
        </tbody>
      </table>
    </section>
  );
});
