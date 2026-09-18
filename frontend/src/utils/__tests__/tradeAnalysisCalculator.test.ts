import { describe, expect, it } from "vitest";
import {
  calculateOutliers,
  calculateStreaks,
  classifyTradeOutcome,
  computeTradesAnalysis,
  generateReturnsHistogramBins,
} from "../tradeAnalysisCalculator";

describe("tradeAnalysisCalculator", () => {
  describe("classifyTradeOutcome", () => {
    it("classifies explicit outcome if provided", () => {
      expect(classifyTradeOutcome({ outcome: "winner" })).toBe("winner");
      expect(classifyTradeOutcome({ outcome: "loser" })).toBe("loser");
      expect(classifyTradeOutcome({ outcome: "breakeven" })).toBe("breakeven");
    });

    it("classifies based on net_pnl", () => {
      expect(classifyTradeOutcome({ net_pnl: 150 })).toBe("winner");
      expect(classifyTradeOutcome({ net_pnl: -50 })).toBe("loser");
      expect(classifyTradeOutcome({ net_pnl: 0 })).toBe("breakeven");
    });

    it("classifies based on pnl_percent", () => {
      expect(classifyTradeOutcome({ pnl_percent: 2.5 })).toBe("winner");
      expect(classifyTradeOutcome({ pnl_percent: -1.8 })).toBe("loser");
      expect(classifyTradeOutcome({ pnl_percent: 0 })).toBe("breakeven");
    });

    it("classifies based on entry and exit price", () => {
      expect(classifyTradeOutcome({ entry_price: 100, exit_price: 110 })).toBe("winner");
      expect(classifyTradeOutcome({ entry_price: 100, exit_price: 90 })).toBe("loser");
      expect(classifyTradeOutcome({ entry_price: 100, exit_price: 100 })).toBe("breakeven");
    });
  });

  describe("calculateOutliers", () => {
    it("returns 0 outliers for small datasets", () => {
      expect(calculateOutliers([10], [1])).toEqual({
        outlierPnlInr: 0,
        outlierPnlPct: 0,
        outlierCount: 0,
      });
    });

    it("detects values beyond 3 standard deviations", () => {
      // 100 normal trades around 10 INR, and 1 massive outlier of 1000 INR
      const normalPnls = Array.from({ length: 100 }, () => 10);
      const normalPcts = Array.from({ length: 100 }, () => 0.01);
      const pnls = [...normalPnls, 1000];
      const pcts = [...normalPcts, 1.0];

      const res = calculateOutliers(pnls, pcts);
      expect(res.outlierCount).toBe(1);
      expect(res.outlierPnlInr).toBe(1000);
      expect(res.outlierPnlPct).toBe(1.0);
    });
  });

  describe("generateReturnsHistogramBins", () => {
    it("handles zero returns gracefully with default bins", () => {
      const res = generateReturnsHistogramBins([]);
      expect(res.bins.length).toBeGreaterThan(0);
      expect(res.minReturn).toBe(0);
      expect(res.maxReturn).toBe(0);
      expect(res.bins.every((b) => b.count === 0)).toBe(true);
    });

    it("groups returns into positive and negative buckets", () => {
      const rets = [-4.5, -2.1, -1.2, 0.5, 1.8, 2.2, 5.9];
      const res = generateReturnsHistogramBins(rets);
      const totalCount = res.bins.reduce((sum, b) => sum + b.count, 0);
      expect(totalCount).toBe(rets.length);
      expect(res.minReturn).toBe(-4.5);
      expect(res.maxReturn).toBe(5.9);
    });
  });

  describe("calculateStreaks", () => {
    it("correctly calculates win, loss, and breakeven streaks", () => {
      const trades = [
        { entry_date: "2024-01-01", pnl_percent: 2.0, net_pnl: 200, outcome: "winner" },
        { entry_date: "2024-01-02", pnl_percent: 3.0, net_pnl: 300, outcome: "winner" },
        { entry_date: "2024-01-03", pnl_percent: -1.0, net_pnl: -100, outcome: "loser" },
        { entry_date: "2024-01-04", pnl_percent: -2.0, net_pnl: -200, outcome: "loser" },
        { entry_date: "2024-01-05", pnl_percent: -0.5, net_pnl: -50, outcome: "loser" },
        { entry_date: "2024-01-06", pnl_percent: 0, net_pnl: 0, outcome: "breakeven" },
        { entry_date: "2024-01-07", pnl_percent: 4.0, net_pnl: 400, outcome: "winner" },
      ];

      const streaks = calculateStreaks(trades, 100000);
      expect(streaks.maxWinStreak).toBe(2);
      expect(streaks.currentWinStreak).toBe(1);
      expect(streaks.maxLossStreak).toBe(3);
      expect(streaks.currentLossStreak).toBe(0);
      expect(streaks.maxBreakevenStreak).toBe(1);
      expect(streaks.winStreakCount).toBe(2);
      expect(streaks.lossStreakCount).toBe(1);
      expect(streaks.maxConsecutiveProfitInr).toBe(500);
      expect(streaks.maxConsecutiveLossInr).toBe(-350);
    });
  });

  describe("Dataset Scenarios (A through F)", () => {
    it("Dataset A: Winning + losing + breakeven trades", () => {
      const trades = [
        { entry_date: "2024-01-01", pnl_percent: 5.0, net_pnl: 500, holding_days: 10, open: false },
        { entry_date: "2024-01-02", pnl_percent: -2.5, net_pnl: -250, holding_days: 5, open: false },
        { entry_date: "2024-01-03", pnl_percent: 0.0, net_pnl: 0, holding_days: 3, open: false },
        { entry_date: "2024-01-04", pnl_percent: 3.5, net_pnl: 350, holding_days: 8, open: false },
      ];

      const res = computeTradesAnalysis({ trades, initialCapital: 10000 });
      expect(res.tradesDistribution.totalTrades).toBe(4);
      expect(res.tradesDistribution.winCount).toBe(2);
      expect(res.tradesDistribution.lossCount).toBe(1);
      expect(res.tradesDistribution.breakEvenCount).toBe(1);
      expect(res.tradesDistribution.winPct).toBe(50);
      expect(res.tradesDistribution.lossPct).toBe(25);
      expect(res.tradesDistribution.breakEvenPct).toBe(25);

      expect(res.topMetrics.largestProfitInr).toBe(500);
      expect(res.topMetrics.largestLossInr).toBe(-250);
      expect(res.topMetrics.largestProfitPct).toBe(5.0);
      expect(res.topMetrics.largestLossPct).toBe(-2.5);
      expect(res.details.profitFactor).toBeCloseTo((500 + 350) / 250, 2);
    });

    it("Dataset B: Only winning trades", () => {
      const trades = [
        { entry_date: "2024-01-01", pnl_percent: 4.0, net_pnl: 400, open: false },
        { entry_date: "2024-01-02", pnl_percent: 6.0, net_pnl: 600, open: false },
      ];

      const res = computeTradesAnalysis({ trades, initialCapital: 10000 });
      expect(res.tradesDistribution.totalTrades).toBe(2);
      expect(res.tradesDistribution.winCount).toBe(2);
      expect(res.tradesDistribution.lossCount).toBe(0);
      expect(res.tradesDistribution.winPct).toBe(100);
      expect(res.tradesDistribution.lossPct).toBe(0);
      expect(res.details.profitFactorInfinite).toBe(true);
      expect(res.topMetrics.largestLossInr).toBeNull();
    });

    it("Dataset C: Only losing trades", () => {
      const trades = [
        { entry_date: "2024-01-01", pnl_percent: -3.0, net_pnl: -300, open: false },
        { entry_date: "2024-01-02", pnl_percent: -5.0, net_pnl: -500, open: false },
      ];

      const res = computeTradesAnalysis({ trades, initialCapital: 10000 });
      expect(res.tradesDistribution.totalTrades).toBe(2);
      expect(res.tradesDistribution.winCount).toBe(0);
      expect(res.tradesDistribution.lossCount).toBe(2);
      expect(res.tradesDistribution.winPct).toBe(0);
      expect(res.tradesDistribution.lossPct).toBe(100);
      expect(res.topMetrics.largestProfitInr).toBeNull();
      expect(res.topMetrics.largestLossInr).toBe(-500);
    });

    it("Dataset D: Only breakeven trades", () => {
      const trades = [
        { entry_date: "2024-01-01", pnl_percent: 0, net_pnl: 0, open: false },
        { entry_date: "2024-01-02", pnl_percent: 0, net_pnl: 0, open: false },
      ];

      const res = computeTradesAnalysis({ trades, initialCapital: 10000 });
      expect(res.tradesDistribution.totalTrades).toBe(2);
      expect(res.tradesDistribution.breakEvenCount).toBe(2);
      expect(res.tradesDistribution.breakEvenPct).toBe(100);
      expect(res.details.netProfitInr).toBe(0);
    });

    it("Dataset E: Zero trades", () => {
      const res = computeTradesAnalysis({ trades: [], initialCapital: 100000 });
      expect(res.tradesDistribution.totalTrades).toBe(0);
      expect(res.tradesDistribution.winCount).toBe(0);
      expect(res.tradesDistribution.lossCount).toBe(0);
      expect(res.returnsDistribution.bins.length).toBeGreaterThan(0);
      expect(res.topMetrics.expectedPayoffInr).toBeNull();
      expect(res.topMetrics.largestProfitInr).toBeNull();
      expect(res.topMetrics.largestLossInr).toBeNull();
    });

    it("Dataset F: Large trade dataset (500 trades)", () => {
      const largeTrades = Array.from({ length: 500 }, (_, i) => ({
        entry_date: `2024-01-${String((i % 28) + 1).padStart(2, "0")}`,
        pnl_percent: (i % 3 === 0 ? 1 : i % 3 === 1 ? -1 : 0) * ((i % 10) + 1),
        net_pnl: (i % 3 === 0 ? 1 : i % 3 === 1 ? -1 : 0) * ((i % 10) + 1) * 100,
        holding_days: (i % 15) + 1,
        open: false,
      }));

      const startTime = performance.now();
      const res = computeTradesAnalysis({ trades: largeTrades, initialCapital: 100000 });
      const elapsed = performance.now() - startTime;

      expect(res.tradesDistribution.totalTrades).toBe(500);
      expect(res.returnsDistribution.bins.length).toBeGreaterThan(0);
      expect(elapsed).toBeLessThan(1000); // Fast under 1000ms even under test runner load
    });
  });
});
