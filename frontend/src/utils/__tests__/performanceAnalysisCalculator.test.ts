import { describe, expect, it } from "vitest";
import {
  calculateBenchmarking,
  calculateBreakdown,
  calculateCorrelation,
  calculateGrowthDecline,
  calculateMarginUsage,
  calculatePeriodical,
  computePerformanceAnalysis,
} from "../performanceAnalysisCalculator";

describe("performanceAnalysisCalculator", () => {
  const sampleTrades = [
    { entry_date: "2024-01-01", exit_date: "2024-01-10", type: "LONG", pnl_percent: 5.0, net_pnl: 500, reason: "Breakout", open: false },
    { entry_date: "2024-01-15", exit_date: "2024-01-20", type: "SHORT", pnl_percent: -2.0, net_pnl: -200, reason: "Pullback", open: false },
    { entry_date: "2024-02-01", exit_date: "2024-02-10", type: "LONG", pnl_percent: 3.0, net_pnl: 300, reason: "Breakout", open: false },
  ];

  const sampleEquityCurve = [
    { date: "2024-01-01", label: "2024-01-01", equity: 100000 },
    { date: "2024-01-10", label: "2024-01-10", equity: 100500 },
    { date: "2024-01-20", label: "2024-01-20", equity: 100300 },
    { date: "2024-02-10", label: "2024-02-10", equity: 100600 },
  ];

  const sampleBenchmarkCurve = [
    { date: "2024-01-01", close: 20000, equity: 100000 },
    { date: "2024-01-10", close: 20200, equity: 101000 },
    { date: "2024-01-20", close: 20100, equity: 100500 },
    { date: "2024-02-10", close: 20400, equity: 102000 },
  ];

  describe("calculateBreakdown", () => {
    it("computes gross profit, gross loss, profit factor, and groupings", () => {
      const res = calculateBreakdown(sampleTrades, 100000);
      expect(res.metrics.grossProfitInr).toBe(800);
      expect(res.metrics.grossLossInr).toBe(200);
      expect(res.metrics.profitFactor).toBe(4.0);
      expect(res.metrics.netPnlInr).toBe(600);

      // By signals
      expect(res.bySignals.length).toBeGreaterThan(1);
      expect(res.bySignals[0].name).toBe("All signals");
      expect(res.bySignals[0].netPnl).toBe(600);

      // By side
      expect(res.bySide.length).toBe(2);
      const longRow = res.bySide.find((s) => s.side === "Long");
      const shortRow = res.bySide.find((s) => s.side === "Short");
      expect(longRow?.netPnl).toBe(800);
      expect(shortRow?.netPnl).toBe(-200);
    });

    it("handles zero loss safely with infinite profit factor", () => {
      const winTrades = [
        { entry_date: "2024-01-01", pnl_percent: 5.0, net_pnl: 500, open: false },
      ];
      const res = calculateBreakdown(winTrades, 100000);
      expect(res.metrics.profitFactorInfinite).toBe(true);
    });
  });

  describe("calculatePeriodical", () => {
    it("aggregates weekly, quarterly, and yearly metrics", () => {
      const res = calculatePeriodical(sampleEquityCurve, sampleTrades, 100000, 0.6, 3.5, 1.2);
      expect(res.metrics.totalReturn).toBe(0.6);
      expect(res.metrics.cagr).toBe(3.5);
      expect(res.metrics.sharpeRatio).toBe(1.2);
      expect(res.weekly.length).toBeGreaterThan(0);
      expect(res.quarterly.length).toBeGreaterThan(0);
      expect(res.yearly.length).toBeGreaterThan(0);
    });
  });

  describe("calculateBenchmarking", () => {
    it("computes strategy return, buy & hold return, outperformance, and correlation", () => {
      const res = calculateBenchmarking(sampleEquityCurve, sampleBenchmarkCurve, sampleTrades, 100000, 0.6);
      expect(res.metrics.strategyReturn).toBe(0.6);
      expect(res.metrics.buyAndHoldReturn).toBe(2.0); // (20400-20000)/20000 = 2%
      expect(res.metrics.outperformance).toBeCloseTo(0.6 - 2.0, 2);
      expect(res.weekly.length).toBeGreaterThan(0);
    });
  });

  describe("calculateCorrelation", () => {
    it("calculates Pearson correlation accurately", () => {
      const x = [1, 2, 3, 4, 5];
      const y = [2, 4, 6, 8, 10];
      expect(calculateCorrelation(x, y)).toBe(1);
    });

    it("returns null for insufficient data points", () => {
      expect(calculateCorrelation([1], [2])).toBeNull();
    });
  });

  describe("calculateMarginUsage", () => {
    it("calculates margin metrics and series", () => {
      const res = calculateMarginUsage(sampleEquityCurve, sampleTrades, 100000);
      expect(res.metrics.marginCalls).toBe(0);
      expect(res.metrics.totalLiquidatedVolume).toBe(0);
      expect(res.series.length).toBe(sampleEquityCurve.length);
    });
  });

  describe("calculateGrowthDecline", () => {
    it("computes run-up, drawdown duration, and comparisons", () => {
      const res = calculateGrowthDecline(sampleEquityCurve, 100000);
      expect(res.alternating.length).toBeGreaterThan(0);
      expect(res.comparison.runUp.maximumPct).toBeGreaterThanOrEqual(0);
      expect(res.comparison.drawdown.maximumPct).toBeGreaterThanOrEqual(0);
    });
  });

  describe("computePerformanceAnalysis master function", () => {
    it("assembles complete model for full backtest dashboard", () => {
      const model = {
        trades: sampleTrades,
        equity_curve: sampleEquityCurve,
        benchmark_curve: sampleBenchmarkCurve,
        total_return: 0.6,
        cagr: 3.5,
        sharpe_ratio: 1.2,
        initial_capital: 100000,
      };

      const result = computePerformanceAnalysis({ model, initialCapital: 100000 });
      expect(result.breakdown.metrics.grossProfitInr).toBe(800);
      expect(result.periodical.metrics.totalReturn).toBe(0.6);
      expect(result.benchmarking.metrics.buyAndHoldReturn).toBe(2.0);
      expect(result.marginUsage.metrics.marginCalls).toBe(0);
      expect(result.growthDecline.alternating.length).toBeGreaterThan(0);
    });

    it("handles zero-trade and empty model gracefully without crashing", () => {
      const result = computePerformanceAnalysis({ model: null, initialCapital: 100000 });
      expect(result.breakdown.metrics.grossProfitInr).toBe(0);
      expect(result.periodical.metrics.totalReturn).toBe(0);
      expect(result.benchmarking.metrics.strategyReturn).toBe(0);
      expect(result.marginUsage.metrics.marginCalls).toBe(0);
      expect(result.growthDecline.alternating.length).toBe(0);
    });
  });
});
