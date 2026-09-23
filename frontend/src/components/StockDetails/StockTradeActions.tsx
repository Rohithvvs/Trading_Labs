import React, { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { StrategyResultRow, StrategyRunStatus } from "../../api_strategy_tester";
import type { SymbolDetail } from "../../types";
import { isIndicatorScanId, resolveTradePlanDetails } from "../../utils/indicatorScanDetail";
import { navigateToPaperOrder } from "../../utils/paperOrderNavigation";

type StockTradeActionsProps = {
  symbol: string;
  strategyName: string;
  runId?: string | null;
  stock?: StrategyResultRow | null;
  symbolDetail?: SymbolDetail | null;
  runStatus?: StrategyRunStatus | null;
};

export const StockTradeActions: React.FC<StockTradeActionsProps> = ({
  symbol,
  strategyName,
  runId,
  stock,
  symbolDetail,
  runStatus,
}) => {
  const navigate = useNavigate();
  const location = useLocation();

  const openPaperOrder = useCallback(
    (side: "BUY" | "SELL") => {
      const plan = resolveTradePlanDetails({
        stock,
        symbolDetail,
        runStatus,
        runId,
        side,
      });

      const entry = plan.displayEntryPrice;
      const stopLoss = plan.stopLoss;
      const target = plan.target;

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
          suggested_stop: stopLoss,
          suggested_targets: target != null ? [target] : [],
          recommendation_meta: {
            signal: stock?.signal || side,
            strategy_name: strategyName,
            strategy_id: runId || "",
            source: isIndicatorScanId(runId) ? "indicator_scanner" : "strategy_tester",
            stop_source: "strategy",
            target_source: "strategy",
          },
        },
      });
    },
    [location.pathname, location.search, navigate, runId, runStatus, stock, strategyName, symbol, symbolDetail],
  );

  const openPaperDesk = useCallback(() => {
    const params = new URLSearchParams();
    if (symbol) params.set("symbol", symbol);
    const plan = resolveTradePlanDetails({
      stock,
      symbolDetail,
      runStatus,
      runId,
      side: "BUY",
    });
    const entry = plan.displayEntryPrice;
    const stopLoss = plan.stopLoss;
    const target = plan.target;

    navigate(`/paper${params.toString() ? `?${params.toString()}` : ""}`, {
      state: {
        symbol,
        strategyName,
        runId: runId || null,
        returnTo: `${location.pathname}${location.search || ""}`,
        prefill: {
          symbol,
          suggested_entry: entry,
          suggested_stop: stopLoss,
          suggested_targets: target != null ? [target] : [],
        },
      },
    });
  }, [location.pathname, location.search, navigate, runId, runStatus, stock, strategyName, symbol, symbolDetail]);

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
