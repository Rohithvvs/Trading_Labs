import { describe, expect, it } from "vitest";
import { buildLeaderboard, gradeFromScore, LEADERBOARD_COLUMNS, scoreFromRadar } from "../leaderboardModel";
import type { ComparisonPayload } from "../../../api_strategy_comparison";

describe("comparisonLeaderboard", () => {
  it("maps scores to grades", () => {
    expect(gradeFromScore(80)).toBe("A");
    expect(gradeFromScore(65)).toBe("B");
    expect(gradeFromScore(50)).toBe("C");
    expect(gradeFromScore(35)).toBe("D");
    expect(gradeFromScore(10)).toBe("F");
    expect(gradeFromScore(null)).toBeNull();
  });

  it("averages radar display-scale values for a slot", () => {
    const score = scoreFromRadar("s0", {
      axes: [],
      series: [{ slot_id: "s0", name: "A", values: { win_rate: 50, total_return_pct: 30 }, raw: {} }],
      note: "",
    });
    expect(score).toBe(40);
  });

  it("ranks by score then total return using real slot metrics", () => {
    const comparison = {
      slots: [
        {
          slot_id: "s0",
          strategy_name: "Alpha",
          source: "strategy_tester",
          metrics: { win_rate: 40, total_return_pct: 1.5, total_trades: 2, profit_factor: null, average_trade: 1.5, average_trade_unit: "pct", cagr: null, max_drawdown_pct: null, max_drawdown: null, calmar_ratio: null, avg_cash: null, avg_exposure_pct: null, best_trade: { symbol: "AAA", return_pct: 10 }, worst_trade: { symbol: "BBB", return_pct: -4 } },
          config: {},
          equity_curve: [],
        },
        {
          slot_id: "s1",
          strategy_name: "Beta",
          source: "lean",
          metrics: { win_rate: 55, total_return_pct: 8, total_trades: 12, profit_factor: 1.4, average_trade: 0.8, average_trade_unit: "pct", cagr: 6, max_drawdown_pct: 12, max_drawdown: null, calmar_ratio: 0.5, avg_cash: 80000, avg_exposure_pct: 22, best_trade: { symbol: "CCC", return_pct: 18 }, worst_trade: { symbol: "DDD", return_pct: -9 } },
          config: {},
          equity_curve: [],
        },
      ],
      radar: {
        axes: [],
        series: [
          { slot_id: "s0", name: "Alpha", values: { win_rate: 40, total_return_pct: 20 }, raw: {} },
          { slot_id: "s1", name: "Beta", values: { win_rate: 55, total_return_pct: 80 }, raw: {} },
        ],
        note: "",
      },
    } as unknown as ComparisonPayload;

    const rows = buildLeaderboard(comparison);
    expect(rows[0].slot.strategy_name).toBe("Beta");
    expect(rows[0].rank).toBe(1);
    expect(rows[0].grade).toBe("B");
    expect(rows[1].slot.strategy_name).toBe("Alpha");
    expect(rows[1].rank).toBe(2);
    expect(rows[0].calmar).toBe(0.5);
    expect(rows[0].avgCash).toBe(80000);
  });

  it("keeps the documented comparison columns and ranks 4 strategies from real metrics", () => {
    expect([...LEADERBOARD_COLUMNS]).toEqual([
      "Rank",
      "Strategy",
      "Score",
      "Grade",
      "Trades",
      "Win Rate",
      "PF",
      "Avg Trade",
      "CAGR",
      "Total Return",
      "Max DD",
      "Calmar",
      "Avg Cash",
      "Avg Exposure",
      "Best Trade",
      "Worst Trade",
    ]);

    const comparison = {
      slots: [
        {
          slot_id: "s0",
          strategy_name: "A",
          source: "strategy_tester",
          metrics: { total_return_pct: 2, win_rate: 40, total_trades: 3, average_trade: 1, average_trade_unit: "pct", profit_factor: null, cagr: null, max_drawdown_pct: null, calmar_ratio: null, avg_cash: null, avg_exposure_pct: null, best_trade: { symbol: "AAA", return_pct: 4 }, worst_trade: { symbol: "BBB", return_pct: -2 } },
          config: {},
          equity_curve: [],
        },
        {
          slot_id: "s1",
          strategy_name: "B",
          source: "lean",
          metrics: { total_return_pct: 9, win_rate: 58, total_trades: 20, average_trade: 0.9, average_trade_unit: "pct", profit_factor: 1.6, cagr: 11, max_drawdown_pct: 8, calmar_ratio: 1.375, avg_cash: 72000, avg_exposure_pct: 28, best_trade: { symbol: "CCC", return_pct: 12 }, worst_trade: { symbol: "DDD", return_pct: -5 } },
          config: {},
          equity_curve: [],
        },
        {
          slot_id: "s2",
          strategy_name: "C",
          source: "lean",
          metrics: { total_return_pct: 5, win_rate: 51, total_trades: 14, average_trade: 0.4, average_trade_unit: "pct", profit_factor: 1.1, cagr: 6, max_drawdown_pct: 10, calmar_ratio: 0.6, avg_cash: 81000, avg_exposure_pct: 18, best_trade: { symbol: "EEE", return_pct: 7 }, worst_trade: { symbol: "FFF", return_pct: -6 } },
          config: {},
          equity_curve: [],
        },
        {
          slot_id: "s3",
          strategy_name: "D",
          source: "strategy_tester",
          metrics: { total_return_pct: 1, win_rate: 33, total_trades: 2, average_trade: 0.2, average_trade_unit: "pct", profit_factor: null, cagr: null, max_drawdown_pct: null, calmar_ratio: null, avg_cash: null, avg_exposure_pct: null, best_trade: { symbol: "GGG", return_pct: 3 }, worst_trade: { symbol: "HHH", return_pct: -1 } },
          config: {},
          equity_curve: [],
        },
      ],
      radar: {
        axes: [],
        series: [
          { slot_id: "s0", name: "A", values: { win_rate: 40, total_return_pct: 20 }, raw: {} },
          { slot_id: "s1", name: "B", values: { win_rate: 70, total_return_pct: 90 }, raw: {} },
          { slot_id: "s2", name: "C", values: { win_rate: 55, total_return_pct: 50 }, raw: {} },
          { slot_id: "s3", name: "D", values: { win_rate: 20, total_return_pct: 10 }, raw: {} },
        ],
        note: "",
      },
    } as unknown as ComparisonPayload;

    const rows = buildLeaderboard(comparison);
    expect(rows.map((row) => row.slot.strategy_name)).toEqual(["B", "C", "A", "D"]);
    expect(rows.map((row) => row.rank)).toEqual([1, 2, 3, 4]);
    expect(rows[0].grade).toBe("A");
    expect(rows[3].cagr).toBeNull();
    expect(rows[3].avgCash).toBeNull();
    expect(rows[0].bestTrade).toContain("CCC");
  });
});
