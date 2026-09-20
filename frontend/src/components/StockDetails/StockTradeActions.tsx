import React, { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { StrategyResultRow } from "../../api_strategy_tester";
import { isIndicatorScanId } from "../../utils/indicatorScanDetail";
import { navigateToPaperOrder } from "../../utils/paperOrderNavigation";

type StockTradeActionsProps = {
  symbol: string;
  strategyName: string;
  runId?: string | null;
  stock?: StrategyResultRow | null;
};

export const StockTradeActions: React.FC<StockTradeActionsProps> = ({
  symbol,
  strategyName,
  runId,
  stock,
}) => {
  const navigate = useNavigate();
  const location = useLocation();

  const openPaperOrder = useCallback(
    (side: "BUY" | "SELL") => {
      const entry =
        stock?.close != null && Number(stock.close) > 0
          ? Number(stock.close)
          : stock?.entry_price != null && Number(stock.entry_price) > 0
            ? Number(stock.entry_price)
            : null;
      const returnTo = `${location.pathname}${location.search || ""}`;
      navigateToPaperOrder(navigate, {
        symbol,
        side,
        currentPrice: entry,
        signal: stock?.signal ?? side,
        returnTo,
        strategyName,
        runId: runId || null,
        prefill: {
          symbol,
          suggested_entry: entry,
          suggested_stop: null,
          suggested_targets: [],
          recommendation_meta: {
            signal: stock?.signal || side,
            strategy_name: strategyName,
            strategy_id: runId || "",
            source: isIndicatorScanId(runId) ? "indicator_scanner" : "strategy_tester",
          },
        },
      });
    },
    [location.pathname, location.search, navigate, runId, stock, strategyName, symbol],
  );

  const openPaperDesk = useCallback(() => {
    const params = new URLSearchParams();
    if (symbol) params.set("symbol", symbol);
    navigate(`/paper${params.toString() ? `?${params.toString()}` : ""}`, {
      state: {
        symbol,
        strategyName,
        runId: runId || null,
        returnTo: `${location.pathname}${location.search || ""}`,
      },
    });
  }, [location.pathname, location.search, navigate, runId, strategyName, symbol]);

  return (
    <div className="st-stock-trade-actions" data-testid="stock-trade-actions" role="group" aria-label="Trading actions">
      <button
        type="button"
        className="ds-btn ds-btn--buy ds-btn--sm"
        data-testid="stock-details-buy"
        onClick={() => openPaperOrder("BUY")}
        aria-label={`Place paper buy for ${symbol}`}
      >
        BUY
      </button>
      <button
        type="button"
        className="ds-btn ds-btn--sell ds-btn--sm"
        data-testid="stock-details-sell"
        onClick={() => openPaperOrder("SELL")}
        aria-label={`Place paper sell for ${symbol}`}
      >
        SELL / Trade
      </button>
      <button
        type="button"
        className="ds-btn ds-btn--secondary ds-btn--sm"
        data-testid="stock-details-paper-trade"
        onClick={openPaperDesk}
        aria-label={`Open paper desk for ${symbol}`}
      >
        PaperTrade
      </button>
    </div>
  );
};
