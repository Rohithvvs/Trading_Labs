import React, { useMemo, useState } from "react";
import type { BacktestDashboardModel } from "../BacktestAnalyticsDashboard";
import { computePerformanceAnalysis } from "../../utils/performanceAnalysisCalculator";
import { BreakdownTab } from "./BreakdownTab";
import { PeriodicalTab } from "./PeriodicalTab";
import { BenchmarkingTab } from "./BenchmarkingTab";
import { MarginUsageTab } from "./MarginUsageTab";
import { GrowthDeclineTab } from "./GrowthDeclineTab";

export type PerformanceAnalysisTab =
  | "breakdown"
  | "periodical"
  | "benchmarking"
  | "margin_usage"
  | "growth_decline";

export interface PerformanceAnalysisProps {
  model: BacktestDashboardModel | null;
  loading?: boolean;
  initialCapital?: number;
}

export function PerformanceAnalysis({
  model,
  loading = false,
  initialCapital = 100000,
}: PerformanceAnalysisProps) {
  const [activeTab, setActiveTab] = useState<PerformanceAnalysisTab>("breakdown");

  const analysis = useMemo(() => {
    return computePerformanceAnalysis({
      model,
      initialCapital: model?.initial_capital ?? initialCapital,
    });
  }, [model, initialCapital]);

  // Loading State
  if (loading) {
    return (
      <section className="bt-chart-panel bt-pa-panel" data-testid="performance-analysis-loading">
        <div className="bt-pa-header">
          <h3 className="bt-pa-title">Performance analysis</h3>
        </div>
        <div className="bt-pa-loading-wrap">
          <div className="bt-spinner" aria-label="Loading performance analysis" />
          <p className="muted-copy" style={{ marginTop: "12px" }}>
            Computing performance breakdown, periodical returns, and drawdown periods...
          </p>
        </div>
      </section>
    );
  }

  const hasData =
    (model?.trades && model.trades.length > 0) ||
    (model?.equity_curve && model.equity_curve.length > 0) ||
    model?.total_return != null;

  return (
    <section
      className="bt-chart-panel bt-pa-panel"
      id="bt-performance-analysis-section"
      data-testid="performance-analysis-section"
    >
      {/* Header with Title & 5 Tabs */}
      <div className="bt-pa-header">
        <h3 className="bt-pa-title">Performance analysis</h3>

        <div className="bt-pa-tabs" role="tablist" aria-label="Performance analysis views">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "breakdown"}
            className={`bt-pa-tab-pill ${activeTab === "breakdown" ? "is-active" : ""}`}
            onClick={() => setActiveTab("breakdown")}
          >
            Breakdown
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "periodical"}
            className={`bt-pa-tab-pill ${activeTab === "periodical" ? "is-active" : ""}`}
            onClick={() => setActiveTab("periodical")}
          >
            Periodical
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "benchmarking"}
            className={`bt-pa-tab-pill ${activeTab === "benchmarking" ? "is-active" : ""}`}
            onClick={() => setActiveTab("benchmarking")}
          >
            Benchmarking
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "margin_usage"}
            className={`bt-pa-tab-pill ${activeTab === "margin_usage" ? "is-active" : ""}`}
            onClick={() => setActiveTab("margin_usage")}
          >
            Margin usage
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "growth_decline"}
            className={`bt-pa-tab-pill ${activeTab === "growth_decline" ? "is-active" : ""}`}
            onClick={() => setActiveTab("growth_decline")}
          >
            Growth and decline
          </button>
        </div>
      </div>

      {/* Tab Content or Empty State */}
      {!hasData ? (
        <div className="bt-pa-empty-state" data-testid="performance-analysis-empty-state">
          <div className="bt-pa-empty-icon">📈</div>
          <h4 className="bt-pa-empty-title">No performance analysis available</h4>
          <p className="bt-pa-empty-desc">
            Run a backtest to view performance analytics.
          </p>
        </div>
      ) : (
        <div className="bt-pa-content">
          {activeTab === "breakdown" && <BreakdownTab model={analysis} />}
          {activeTab === "periodical" && <PeriodicalTab model={analysis} />}
          {activeTab === "benchmarking" && <BenchmarkingTab model={analysis} />}
          {activeTab === "margin_usage" && <MarginUsageTab model={analysis} />}
          {activeTab === "growth_decline" && <GrowthDeclineTab model={analysis} />}
        </div>
      )}
    </section>
  );
}
