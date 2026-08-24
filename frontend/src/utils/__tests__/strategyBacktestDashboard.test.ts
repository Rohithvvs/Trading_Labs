import { describe, expect, it } from "vitest";

import type { CandidateRow } from "../../types";
import { hydrateStrategyBacktest, isSymbolWindowReplay } from "../strategyBacktestDashboard";

function w52Row(symbol: string): CandidateRow {
  return {
    rank: 1,
    symbol,
    signal: "BUY",
    score: null,
    scoreKind: "momentum_60",
    scoreLabel: "Momentum 60",
    momentumValue: 12,
    strategyId: "09_52w_breakout",
    confidence: null,
    entryLow: 100,
    entryHigh: 100,
    stopLoss: 90,
    target1: 120,
    target2: null,
    riskReward: 2,
    trend: "ACTIVE",
    momentum: "12.0%",
    volume: "n/a",
    newsSentiment: "n/a",
    lastUpdated: "2026-08-14",
    tradeReadiness: "Review manually",
    recommendationSummary: "52-Week High Breakout selection",
    w52: {
      technicals: {},
      backtest_1y: { net_return: 0, trade_count: 1 },
      initial_capital: 100000,
    },
  };
}

describe("strategyBacktestDashboard", () => {
  it("rejects the shared scan-book dashboard", () => {
    const bookDash = {
      symbol: "BOSCHLTD-EQ",
      window: "3Y",
      replay_kind: "scan_blotter",
      total_return: 0,
      trade_count: 1,
      equity_curve: [
        { date: "2025-06-27", equity: 100000 },
        { date: "2026-08-18", equity: 100195 },
      ],
    };
    expect(isSymbolWindowReplay(bookDash, "BOSCHLTD-EQ", "3Y")).toBe(false);
    expect(hydrateStrategyBacktest(w52Row("BOSCHLTD-EQ"), "3Y", { dashboard: bookDash })).toBeNull();
  });

  it("rejects a replay stamped for a different symbol", () => {
    const dash = {
      symbol: "ACE-EQ",
      window: "3Y",
      replay_kind: "symbol_window",
      trade_count: 4,
      equity_curve: [
        { date: "2023-08-18", equity: 100000 },
        { date: "2026-08-18", equity: 105000 },
      ],
    };
    expect(hydrateStrategyBacktest(w52Row("BOSCHLTD-EQ"), "3Y", { dashboard: dash })).toBeNull();
  });

  it("accepts independent symbol-window replays", () => {
    const bosch = hydrateStrategyBacktest(w52Row("BOSCHLTD-EQ"), "3Y", {
      dashboard: {
        symbol: "BOSCHLTD-EQ",
        window: "3Y",
        replay_kind: "symbol_window",
        total_return: 4.5,
        data_hash: "aaa",
        equity_curve: [
          { date: "2023-08-18", equity: 100000 },
          { date: "2026-08-18", equity: 104500 },
        ],
      },
    });
    const ace = hydrateStrategyBacktest(w52Row("ACE-EQ"), "3Y", {
      dashboard: {
        symbol: "ACE-EQ",
        window: "3Y",
        replay_kind: "symbol_window",
        total_return: 1.2,
        data_hash: "bbb",
        equity_curve: [
          { date: "2023-08-18", equity: 100000 },
          { date: "2026-08-18", equity: 101200 },
        ],
      },
    });
    expect(bosch?.symbol).toBe("BOSCHLTD-EQ");
    expect(ace?.symbol).toBe("ACE-EQ");
    expect(bosch?.data_hash).not.toBe(ace?.data_hash);
    expect(bosch?.total_return).not.toBe(ace?.total_return);
    expect(bosch?.equity_curve?.at(-1)?.equity).not.toBe(100195);
  });

  it("does not invent a 3Y result from the scan blotter when the API is missing", () => {
    expect(hydrateStrategyBacktest(w52Row("ACE-EQ"), "3Y", null)).toBeNull();
  });
});
