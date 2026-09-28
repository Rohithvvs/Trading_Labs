import React, { memo } from "react";
import type { MarketIndexItem } from "../../api";
import { Sparkline } from "../Sparkline";

interface IndexCardsProps {
  indices: MarketIndexItem[];
  vix?: MarketIndexItem | null;
  onSelectIndex?: (symbol: string) => void;
  selectedIndex?: string;
}

export const IndexCards: React.FC<IndexCardsProps> = memo(function IndexCards({
  indices,
  vix,
  onSelectIndex,
  selectedIndex,
}) {
  const cards: MarketIndexItem[] = Array.isArray(indices) ? [...indices] : [];
  if (vix && !cards.some((c) => c?.symbol === vix.symbol || (c?.label || "").toLowerCase().includes("vix"))) {
    cards.push(vix);
  }

  // Ensure we have at least standard labels if backend returns empty
  const defaultList: MarketIndexItem[] = cards.length > 0 ? cards : [
    { symbol: "NSE:NIFTY50-INDEX", label: "NIFTY 50", price: null, change_pct: null, source: "idle" },
    { symbol: "NSE:NIFTYBANK-INDEX", label: "BANK NIFTY", price: null, change_pct: null, source: "idle" },
    { symbol: "BSE:SENSEX-INDEX", label: "SENSEX", price: null, change_pct: null, source: "idle" },
    { symbol: "NSE:INDIAVIX-INDEX", label: "INDIA VIX", price: null, change_pct: null, source: "idle" },
  ];

  return (
    <section className="market-indices-row" aria-label="Major Market Indices">
      {defaultList.map((item, idx) => {
        const itemLabel = item.label || (item as any).name || item.symbol || "Index";
        const itemSymbol = item.symbol || "";
        const isVix = itemLabel.toLowerCase().includes("vix") || itemSymbol.toLowerCase().includes("vix");
        const changePct = Number(item.change_pct ?? 0);
        const changeVal = item.change != null ? Number(item.change) : null;
        const isPositive = changePct >= 0;
        const priceStr = item.price != null
          ? Number(item.price).toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 2 })
          : "—";

        // For sparkline, use real sparkline if available, or generate a smooth 5-point curve reflecting change
        const sparkData = Array.isArray(item.sparkline) && item.sparkline.length >= 3
          ? item.sparkline
          : [100, 100 + (changePct * 0.2), 100 + (changePct * 0.5), 100 + (changePct * 0.8), 100 + changePct];

        const isSelected = selectedIndex === itemSymbol || (selectedIndex === "NSE:NIFTY50-INDEX" && itemLabel === "NIFTY 50");

        return (
          <article
            key={itemSymbol || itemLabel || idx}
            className={`index-card ${isSelected ? "is-active-card" : ""}`}
            onClick={() => onSelectIndex?.(itemSymbol)}
            style={{
              cursor: onSelectIndex ? "pointer" : "default",
              borderColor: isSelected ? "var(--mk-blue)" : undefined,
            }}
          >
            <div className="index-card__top">
              <span className="index-card__name">{itemLabel}</span>
              <div style={{ width: 80, height: 28 }}>
                <Sparkline
                  values={sparkData}
                  width={80}
                  height={28}
                />
              </div>
            </div>

            <div className="index-card__price-row">
              <span className="index-card__price">{priceStr}</span>
              <div className={`index-card__change ${isPositive ? "is-positive" : "is-negative"}`}>
                <span>{isPositive ? "▲" : "▼"}</span>
                <span>
                  {changePct >= 0 ? "+" : ""}
                  {changePct.toFixed(2)}%
                </span>
                {changeVal != null && (
                  <span style={{ fontSize: "0.75rem", opacity: 0.85 }}>
                    ({changeVal >= 0 ? "+" : ""}{changeVal.toFixed(1)})
                  </span>
                )}
              </div>
            </div>

            <div className="index-card__high-low">
              <span>
                HIGH <strong>{item.high != null ? Number(item.high).toLocaleString("en-IN", { maximumFractionDigits: 1 }) : "—"}</strong>
              </span>
              <span>
                LOW <strong>{item.low != null ? Number(item.low).toLocaleString("en-IN", { maximumFractionDigits: 1 }) : "—"}</strong>
              </span>
            </div>
          </article>
        );
      })}
    </section>
  );
});
