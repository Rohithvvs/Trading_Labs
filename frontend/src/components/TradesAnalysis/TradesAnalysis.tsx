import React, { useMemo, useState } from "react";
import type { BacktestDashboardModel } from "../BacktestAnalyticsDashboard";
import { computeTradesAnalysis } from "../../utils/tradeAnalysisCalculator";
import { DistributionTab } from "./DistributionTab";
import { StreaksTab } from "./StreaksTab";
import { TradesAnalysisDetailsTab } from "./TradesAnalysisDetailsTab";

export type TradesAnalysisTab = "distribution" | "streaks" | "details";

export interface TradesAnalysisProps {
  model: BacktestDashboardModel | null;
  loading?: boolean;
  initialCapital?: number;
}

export function TradesAnalysis({
  model,
  loading = false,
  initialCapital = 100000,
}: TradesAnalysisProps) {
  const [activeTab, setActiveTab] = useState<TradesAnalysisTab>("distribution");

  const analysis = useMemo(() => {
    return computeTradesAnalysis({
      trades: model?.trades || [],
      ledger: model?.ledger || null,
      strategyTester: model?.strategy_tester || null,
      initialCapital: model?.initial_capital ?? initialCapital,
      totalReturn: model?.total_return ?? null,
    });
  }, [model, initialCapital]);

  // Loading State
  if (loading) {
    return (
      <section className="bt-chart-panel bt-ta-panel" data-testid="trades-analysis-loading">
        <div className="bt-ta-header">
          <h3 className="bt-ta-title">Trades analysis</h3>
        </div>
        <div className="bt-ta-loading-wrap">
          <div className="bt-spinner" aria-label="Loading trades analysis" />
          <p className="muted-copy" style={{ marginTop: "12px" }}>
            Computing trades distribution and streak statistics...
          </p>
        </div>
      </section>
    );
  }

  const hasTrades = analysis.tradesDistribution.totalTrades > 0;

  return (
    <section
      className="bt-chart-panel bt-ta-panel"
      id="bt-trades-analysis-section"
      data-testid="trades-analysis-section"
    >
      {/* Main Header with Title & Tab Navigation */}
      <div className="bt-ta-header">
        <h3 className="bt-ta-title">Trades analysis</h3>

        {/* Tab Pills */}
        <div className="bt-ta-tabs" role="tablist" aria-label="Trades analysis views">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "distribution"}
            className={`bt-ta-tab-pill ${activeTab === "distribution" ? "is-active" : ""}`}
            onClick={() => setActiveTab("distribution")}
          >
            Distribution
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "streaks"}
            className={`bt-ta-tab-pill ${activeTab === "streaks" ? "is-active" : ""}`}
            onClick={() => setActiveTab("streaks")}
          >
            Streaks
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "details"}
            className={`bt-ta-tab-pill ${activeTab === "details" ? "is-active" : ""}`}
            onClick={() => setActiveTab("details")}
          >
            Trades analysis details
          </button>
        </div>
      </div>

      {/* Tab Content or Clean Empty State */}
      {!hasTrades ? (
        <div className="bt-ta-empty-state" data-testid="trades-analysis-empty-state">
          <div className="bt-ta-empty-icon">📊</div>
          <h4 className="bt-ta-empty-title">No trade analysis available</h4>
          <p className="bt-ta-empty-desc">
            Run a backtest with completed trades to view trade statistics.
          </p>
        </div>
      ) : (
        <div className="bt-ta-content">
          {activeTab === "distribution" && <DistributionTab model={analysis} />}
          {activeTab === "streaks" && <StreaksTab model={analysis} />}
          {activeTab === "details" && <TradesAnalysisDetailsTab model={analysis} />}
        </div>
      )}
    </section>
  );
}
