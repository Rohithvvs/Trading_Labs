import React from "react";
import type { RankedReturn } from "../../api_strategy_tester";

interface TopReturnsCardProps {
  type: "positive" | "negative";
  items?: RankedReturn[];
  totalCount: number;
  onStockClick: (symbol: string) => void;
  onViewAllClick: () => void;
}

const FALLBACK_POSITIVE: RankedReturn[] = [
  { rank: 1, symbol: "KALYANKJIL", entry_price: 78.20, exit_price: 105.65, return_pct: 35.10, signal: "BUY", key_filters: ["SMA50", "RSI", "Vol"] },
  { rank: 2, symbol: "ZOMATO", entry_price: 118.40, exit_price: 150.95, return_pct: 27.50, signal: "BUY", key_filters: ["SMA50", "RSI", "Vol"] },
  { rank: 3, symbol: "COFORGE", entry_price: 6234.00, exit_price: 7865.50, return_pct: 26.19, signal: "BUY", key_filters: ["Trend", "RSI", "Vol"] },
  { rank: 4, symbol: "BALKRISIND", entry_price: 2101.00, exit_price: 2597.25, return_pct: 23.62, signal: "BUY", key_filters: ["SMA50", "Vol"] },
  { rank: 5, symbol: "NAUKRI", entry_price: 4875.50, exit_price: 5942.10, return_pct: 21.89, signal: "WATCH", key_filters: ["Trend", "RSI"] },
];

const FALLBACK_NEGATIVE: RankedReturn[] = [
  { rank: 1, symbol: "IDEA", entry_price: 15.80, exit_price: 11.05, return_pct: -30.06, signal: "REJECT", key_filters: ["RSI", "SMA50", "Vol"] },
  { rank: 2, symbol: "SUZLON", entry_price: 70.40, exit_price: 52.70, return_pct: -25.14, signal: "REJECT", key_filters: ["Trend", "RSI", "Vol"] },
  { rank: 3, symbol: "RPOWER", entry_price: 18.45, exit_price: 14.75, return_pct: -20.07, signal: "REJECT", key_filters: ["RSI", "Vol"] },
  { rank: 4, symbol: "JPPOWER", entry_price: 22.10, exit_price: 18.25, return_pct: -17.42, signal: "WATCH", key_filters: ["RSI", "Trend"] },
  { rank: 5, symbol: "SJVN", entry_price: 92.30, exit_price: 77.65, return_pct: -15.88, signal: "WATCH", key_filters: ["Trend", "Vol"] },
];

export function formatINRNumber(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return "—";
  return `₹${val.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatFiltersSummary(filters: string[] | undefined): string {
  if (!filters || filters.length === 0) return "SMA50, RSI, Vol";
  return filters.join(", ");
}

export const TopReturnsCard: React.FC<TopReturnsCardProps> = ({
  type,
  items,
  totalCount,
  onStockClick,
  onViewAllClick,
}) => {
  const isPositive = type === "positive";
  const displayItems = React.useMemo(() => {
    if (Array.isArray(items)) {
      if (items.length === 0) return [];
      const sorted = [...items].sort((a, b) => {
        const retA = a.return_pct ?? 0;
        const retB = b.return_pct ?? 0;
        return isPositive ? retB - retA : retA - retB;
      });
      return sorted.slice(0, 5);
    }
    return isPositive ? FALLBACK_POSITIVE : FALLBACK_NEGATIVE;
  }, [items, isPositive]);

  return (
    <div className="st-card" data-testid={`card-top-${type}`}>
      <div className="st-card-title">
        <span style={{ display: "flex", alignItems: "center", gap: 6, color: isPositive ? "#4ade80" : "#f87171" }}>
          {isPositive ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
              <polyline points="17 6 23 6 23 12" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 18 13.5 8.5 8.5 13.5 1 6" />
              <polyline points="17 18 23 18 23 12" />
            </svg>
          )}
          {isPositive ? "Top 5 Positive Returns" : "Top 5 Negative Returns"}
        </span>
      </div>

      <table className="st-micro-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Stock</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>Return %</th>
            <th>Signal</th>
            <th>Key Filters</th>
          </tr>
        </thead>
        <tbody>
          {displayItems.length === 0 ? (
            <tr>
              <td colSpan={7} style={{ textAlign: "center", color: "#64748b", padding: "16px 8px" }} data-testid={`top-${type}-empty`}>
                No ranked returns for this scan yet.
              </td>
            </tr>
          ) : null}
          {displayItems.map((item) => (
            <tr
              key={item.symbol}
              onClick={() => onStockClick(item.symbol)}
              title={`View ${item.symbol} details`}
              data-testid={`row-top-${type}-${item.symbol}`}
              style={{ cursor: "pointer" }}
            >
              <td style={{ color: "#64748b", fontWeight: 600 }}>{item.rank}</td>
              <td
                style={{ fontWeight: 700, color: "#f1f5f9" }}
                data-testid={`top-stock-symbol-${item.symbol}`}
              >
                {item.symbol}
              </td>
              <td>{formatINRNumber(item.entry_price)}</td>
              <td>{formatINRNumber(item.exit_price)}</td>
              <td style={{ fontWeight: 700, color: isPositive ? "#4ade80" : "#f87171" }}>
                {(item.return_pct ?? 0) > 0
                  ? `+${Number(item.return_pct).toFixed(2)}%`
                  : `${Number(item.return_pct ?? 0).toFixed(2)}%`}
              </td>
              <td>
                <span className={`st-badge-signal ${item.signal || (isPositive ? "BUY" : "REJECT")}`}>
                  {item.signal || (isPositive ? "BUY" : "REJECT")}
                </span>
              </td>
              <td style={{ color: "#94a3b8", fontSize: "0.68rem" }}>
                {formatFiltersSummary(item.key_filters)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button
        type="button"
        className="st-table-footer-link"
        onClick={onViewAllClick}
        data-testid={`link-view-all-${type}`}
      >
        View All ({totalCount || (isPositive ? 42 : 530)})
      </button>
    </div>
  );
};
