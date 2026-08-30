import React from "react";
import type { CandlePoint, StrategyResultRow, StrategyRunStatus } from "../../api_strategy_tester";
import type { SymbolDetail } from "../../types";
import { TechnicalsTab } from "./TechnicalsTab";
import { TradePlanTab } from "./TradePlanTab";
import type { FilterEvalItem } from "./types";

export interface OverviewTabProps {
  stock: StrategyResultRow | null;
  resolvedRunId: string;
  filterResults: FilterEvalItem[];
  runStatus?: StrategyRunStatus | null;
  symbolDetail?: SymbolDetail | null;
  strategyName?: string;
  candles?: CandlePoint[];
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
  stock,
  resolvedRunId,
  filterResults,
  runStatus = null,
  symbolDetail = null,
  strategyName = "52-Week High Breakout",
  candles = [],
  isLoading = false,
  error = null,
  onRetry,
}) => {
  return (
    <div className="st-stock-detail-stack" style={{ display: "flex", flexDirection: "column", gap: 20 }} data-testid="overview-tab-content">
      {/* 1. Trade Plan */}
      <div className="st-overview-section">
        <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
          <h2 style={{ fontSize: "1rem", fontWeight: 700, color: "#f8fafc", margin: 0, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Trade Plan
          </h2>
        </div>
        <TradePlanTab
          stock={stock}
          runStatus={runStatus}
          symbolDetail={symbolDetail}
          filterResults={filterResults}
          strategyName={strategyName}
          runId={resolvedRunId}
          isLoading={isLoading}
          error={error}
          onRetry={onRetry}
        />
      </div>

      {/* 2. Technicals */}
      <div className="st-overview-section">
        <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
          <h2 style={{ fontSize: "1rem", fontWeight: 700, color: "#f8fafc", margin: 0, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Technicals
          </h2>
        </div>
        <TechnicalsTab
          stock={stock}
          symbolDetail={symbolDetail}
          candles={candles}
          isLoading={isLoading}
          error={error}
          onRetry={onRetry}
        />
      </div>
    </div>
  );
};

