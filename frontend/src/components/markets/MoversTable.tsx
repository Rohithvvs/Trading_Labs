import React, { memo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { MarketIndexItem } from "../../api";

interface MoversTableProps {
  gainers: MarketIndexItem[];
  losers: MarketIndexItem[];
  onOpenScanner?: () => void;
}

export const MoversTable: React.FC<MoversTableProps> = memo(function MoversTable({
  gainers,
  losers,
  onOpenScanner,
}) {
  const navigate = useNavigate();
  const [mobileTab, setMobileTab] = useState<"gainers" | "losers">("gainers");

  const gList = Array.isArray(gainers) ? gainers : [];
  const lList = Array.isArray(losers) ? losers : [];

  const handleStockClick = (symbol: string) => {
    navigate(`/scanner?symbol=${encodeURIComponent(symbol)}`);
  };

  const handleViewAll = () => {
    if (onOpenScanner) onOpenScanner();
    else navigate("/scanner");
  };

  const renderTable = (list: MarketIndexItem[], isGainer: boolean) => (
    <table className="terminal-table">
      <thead>
        <tr>
          <th style={{ width: 28 }}>#</th>
          <th>Symbol</th>
          <th style={{ textAlign: "right" }}>LTP</th>
          <th style={{ textAlign: "right" }}>% Change</th>
        </tr>
      </thead>
      <tbody>
        {list.length === 0 ? (
          <tr>
            <td
              colSpan={4}
              style={{
                textAlign: "center",
                color: "var(--mk-text-muted)",
                padding: "20px 0",
                fontSize: "0.85rem",
              }}
            >
              No {isGainer ? "gainers" : "losers"} data available.
            </td>
          </tr>
        ) : (
          list.slice(0, 5).map((stock, i) => {
            const sym = stock.symbol || (stock as any).name || "—";
            const chg = Number(stock.change_pct ?? 0);
            const priceStr = stock.price != null
              ? Number(stock.price).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
              : "—";

            return (
              <tr key={sym || i}>
                <td style={{ color: "var(--mk-text-muted)", fontSize: "0.75rem" }}>{i + 1}</td>
                <td>
                  <button
                    type="button"
                    className="stock-symbol-link"
                    onClick={() => handleStockClick(sym)}
                    title={`Analyze ${sym}`}
                  >
                    {sym}
                  </button>
                </td>
                <td style={{ textAlign: "right", fontWeight: 600 }}>{priceStr}</td>
              <td
                style={{
                  textAlign: "right",
                  fontWeight: 600,
                  color: isGainer ? "var(--mk-green)" : "var(--mk-red)",
                }}
              >
                {isGainer ? "▲ +" : "▼ "}
                {chg.toFixed(2)}%
              </td>
            </tr>
          );
        }))}
      </tbody>
    </table>
  );

  return (
    <div>
      {/* Mobile Tab Switcher */}
      <div className="movers-mobile-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mobileTab === "gainers"}
          className={`market-pill-btn ${mobileTab === "gainers" ? "is-active" : ""}`}
          onClick={() => setMobileTab("gainers")}
          style={{ flex: 1, padding: "8px" }}
        >
          Top Gainers
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mobileTab === "losers"}
          className={`market-pill-btn ${mobileTab === "losers" ? "is-active" : ""}`}
          onClick={() => setMobileTab("losers")}
          style={{ flex: 1, padding: "8px" }}
        >
          Top Losers
        </button>
      </div>

      <div className="movers-container">
        {/* Gainers Card */}
        <section
          className="terminal-card"
          style={{ display: mobileTab === "losers" ? undefined : "flex" }}
          aria-label="Top Gainers"
        >
          <div className="terminal-card__header">
            <h3 className="terminal-card__title">
              <span>Top Gainers</span>
              <span className="terminal-card__subtitle">(Nifty 500)</span>
            </h3>
            <button type="button" className="terminal-link-btn" onClick={handleViewAll}>
              View all
            </button>
          </div>
          {renderTable(gList, true)}
        </section>

        {/* Losers Card */}
        <section
          className="terminal-card"
          style={{ display: mobileTab === "gainers" ? undefined : "flex" }}
          aria-label="Top Losers"
        >
          <div className="terminal-card__header">
            <h3 className="terminal-card__title">
              <span>Top Losers</span>
              <span className="terminal-card__subtitle">(Nifty 500)</span>
            </h3>
            <button type="button" className="terminal-link-btn" onClick={handleViewAll}>
              View all
            </button>
          </div>
          {renderTable(lList, false)}
        </section>
      </div>
    </div>
  );
});
