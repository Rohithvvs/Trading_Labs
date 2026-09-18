import { describe, expect, it } from "vitest";

import { classifySignalFromScore } from "../signalClassification";
import {
  buildLtmCandidateRows,
  buildPaperTradingPrefill,
  buildW52CandidateRows,
  preferredPaperEntry,
} from "../scannerCandidates";

describe("LTM scanner rows", () => {
  it("does not treat 252-session momentum as a 0–100 Score or reclassify WATCH as BUY", () => {
    const rows = buildLtmCandidateRows({
      recommendations_final: true,
      clock_status: "MID_CYCLE",
      evaluation_date: "2026-08-15",
      recommendations: [
        {
          symbol: "CUPID-EQ",
          signal: "WATCH",
          selected: true,
          rank: 1,
          momentum_252: 0.7118,
          entry: 290.15,
          stop_loss: null,
          target: null,
          technicals: { close_t: 290.15, momentum_252: 0.7118 },
        },
      ],
    });

    expect(rows).toHaveLength(1);
    const row = rows[0];
    expect(row.symbol).toBe("CUPID-EQ");
    expect(row.signal).toBe("WATCH");
    expect(row.score).toBeNull();
    expect(row.scoreKind).toBe("momentum_252");
    expect(row.scoreLabel).toBe("Momentum 252");
    expect(row.momentumValue).toBe(71.2);
    expect(row.momentum).toBe("71.2%");
    expect(row.entryLow).toBe(290.15);
    expect(row.stopLoss).toBeNull();
    expect(row.target1).toBeNull();
    expect(classifySignalFromScore(row.momentumValue ?? 0)).toBe("BUY");
    expect(row.signal).not.toBe(classifySignalFromScore(row.momentumValue ?? 0));
  });

  it("keeps a real +711.8% 252-session return labeled as momentum, not a 0–100 Score", () => {
    const rows = buildLtmCandidateRows({
      recommendations_final: true,
      clock_status: "MID_CYCLE",
      recommendations: [
        {
          symbol: "CUPID-EQ",
          signal: "WATCH",
          selected: true,
          momentum_252: 7.118232044198894,
          technicals: { close_t: 293.88, momentum_252: 7.118232044198894 },
        },
      ],
    });
    const row = rows[0];
    expect(row.signal).toBe("WATCH");
    expect(row.score).toBeNull();
    expect(row.scoreLabel).toBe("Momentum 252");
    expect(row.momentumValue).toBe(711.8);
    expect(row.momentum).toBe("711.8%");
    expect(row.entryLow).toBe(293.88);
    expect(row.stopLoss).toBeNull();
    expect(row.target1).toBeNull();
    const prefill = buildPaperTradingPrefill(row, "BUY");
    expect(prefill.suggested_entry).toBe(293.88);
    expect(prefill.suggested_stop).toBeLessThan(293.88);
    expect(prefill.suggested_targets[0]).toBeGreaterThan(293.88);
    expect(preferredPaperEntry(prefill, 999)).toBe(293.88);
  });

  it("does not clone the shared book blotter or equity curve onto every row", () => {
    const blotter = [{ symbol: "AAA-EQ", pnl_pct: 0.1 }];
    const bookCurve = Array.from({ length: 400 }, (_, i) => ({ date: `d${i}`, equity: 100 + i }));
    const rows = buildLtmCandidateRows({
      recommendations_final: true,
      blotter,
      equity_curve: bookCurve,
      index_curve: bookCurve,
      book_metrics: { initial_capital: 100000 },
      recommendations: [
        {
          symbol: "AAA-EQ",
          signal: "WATCH",
          selected: true,
          momentum_252: 0.5,
          technicals: { close_t: 10 },
          backtest_1y: { trades: [{ pnl_pct: 0.1 }, { pnl_pct: -0.05 }] },
        },
        {
          symbol: "BBB-EQ",
          signal: "REJECT",
          first_failure: "ranked_outside_top_10",
          momentum_252: 0.1,
          technicals: { close_t: 8 },
        },
      ],
    });
    expect(rows).toHaveLength(2);
    expect(rows[0].ltm?.blotter).toBeUndefined();
    expect(rows[0].ltm?.index_curve).toBeUndefined();
    expect(rows[0].ltm?.book_metrics).toBeUndefined();
    expect(rows[0].ltm?.equity_curve?.length).toBeLessThanOrEqual(32);
    expect(rows[0].ltm?.equity_curve).not.toBe(bookCurve);
    expect(rows[1].ltm?.equity_curve).toEqual([]);
  });

  it("does not invent a trade plan for REJECT names", () => {
    const rows = buildLtmCandidateRows({
      recommendations_final: true,
      recommendations: [
        {
          symbol: "XYZ-EQ",
          signal: "REJECT",
          first_failure: "ranked_outside_top_10",
          momentum_252: 0.12,
          technicals: { close_t: 50 },
        },
      ],
    });
    expect(rows[0].entryLow).toBeNull();
    expect(rows[0].stopLoss).toBeNull();
    expect(rows[0].target1).toBeNull();
  });
});

describe("52W scanner rows", () => {
  it("maps book entry and trailing stop without inventing a target", () => {
    const rows = buildW52CandidateRows({
      recommendations_final: true,
      book_status: "ACTIVE",
      recommendations: [
        {
          symbol: "AAA-EQ",
          signal: "WATCH",
          mom60: 0.154,
          entry: 100,
          stop_loss: 94,
          target: null,
          technicals: { tsl: 94, close_t: 100, mom60: 0.154 },
        },
      ],
    });
    const row = rows[0];
    expect(row.signal).toBe("WATCH");
    expect(row.score).toBeNull();
    expect(row.scoreKind).toBe("momentum_60");
    expect(row.momentumValue).toBe(15.4);
    expect(row.entryLow).toBe(100);
    expect(row.stopLoss).toBe(94);
    expect(row.target1).toBeNull();
    expect(row.strategyId).toBe("09_52w_breakout");
  });

  it("lists current gate passers (WATCH) before book HOLD", () => {
    const rows = buildW52CandidateRows({
      recommendations_final: true,
      recommendations: [
        { symbol: "ACE-EQ", signal: "HOLD", mom60: 0.3, entry: 1184 },
        { symbol: "CHENNPETRO-EQ", signal: "WATCH", mom60: 0.2, entry: 1487, first_failure: "no_free_slot" },
        { symbol: "GLAXO-EQ", signal: "BUY", mom60: 0.4, entry: 3015 },
      ],
    });
    expect(rows.map((r) => r.symbol)).toEqual(["GLAXO-EQ", "CHENNPETRO-EQ", "ACE-EQ"]);
  });

  it("hides universe REJECT rows from Favorites and keeps TradingView-style gate passers", () => {
    const rows = buildW52CandidateRows({
      recommendations_final: true,
      recommendations: [
        { symbol: "BALRAMCHIN", signal: "BUY", mom60: 0.38, entry: 767.1, screener_pass: true, rank: 1 },
        { symbol: "EPL", signal: "WATCH", mom60: 0.25, entry: 270.1, screener_pass: true, rank: 2 },
        { symbol: "WELCORP", signal: "REJECT", first_failure: "sold_today", screener_pass: true, mom60: 0.61, close: 2005.2 },
        { symbol: "360ONE", signal: "REJECT", first_failure: "close_below_prior_high", screener_pass: false, mom60: 0.11 },
        { symbol: "3MINDIA", signal: "REJECT", first_failure: "close_below_prior_high", screener_pass: false, mom60: 0.02 },
      ],
    });
    expect(rows.map((r) => r.symbol)).toEqual(["BALRAMCHIN", "EPL", "WELCORP"]);
    expect(rows.find((r) => r.symbol === "360ONE")).toBeUndefined();
  });

  it("puts every evaluated name on Scan results with BUY when the strategy matches and REJECT otherwise", () => {
    const rows = buildW52CandidateRows(
      {
        recommendations_final: true,
        recommendations: [
          { symbol: "BALRAMCHIN", signal: "BUY", mom60: 0.38, entry: 767.1, screener_pass: true, rank: 1 },
          { symbol: "EPL", signal: "WATCH", mom60: 0.25, entry: 270.1, screener_pass: true, rank: 2 },
          { symbol: "ACE-EQ", signal: "HOLD", mom60: 0.3, entry: 1184, buy_signal: false },
          { symbol: "WELCORP", signal: "REJECT", first_failure: "sold_today", screener_pass: true, mom60: 0.61, close: 2005.2 },
          { symbol: "360ONE", signal: "REJECT", first_failure: "close_below_prior_high", screener_pass: false, mom60: 0.11 },
          { symbol: "3MINDIA", signal: "REJECT", first_failure: "close_below_prior_high", screener_pass: false, mom60: 0.02 },
        ],
      },
      { includeUniverseRejects: true },
    );
    expect(rows.map((r) => r.symbol)).toEqual([
      "BALRAMCHIN",
      "EPL",
      "ACE-EQ",
      "360ONE",
      "3MINDIA",
      "WELCORP",
    ]);
    expect(rows.find((r) => r.symbol === "BALRAMCHIN")?.signal).toBe("BUY");
    expect(rows.find((r) => r.symbol === "360ONE")?.signal).toBe("REJECT");
    expect(rows.find((r) => r.symbol === "3MINDIA")?.signal).toBe("REJECT");
    expect(rows.find((r) => r.symbol === "360ONE")?.entryLow).toBeNull();
  });

  it("keeps last completed Scan results while a new run is still in flight", () => {
    const rows = buildW52CandidateRows(
      {
        recommendations_final: false,
        completed_at: "2026-08-21T10:00:00Z",
        run_status: "evaluating",
        recommendations: [
          { symbol: "GLAXO-EQ", signal: "BUY", mom60: 0.4, entry: 3015, screener_pass: true },
          { symbol: "360ONE", signal: "REJECT", first_failure: "close_below_prior_high", screener_pass: false },
        ],
      },
      { includeUniverseRejects: true },
    );
    expect(rows.map((r) => r.symbol)).toEqual(["GLAXO-EQ", "360ONE"]);
    expect(rows[0].signal).toBe("BUY");
    expect(rows[1].signal).toBe("REJECT");
  });

  it("keeps Trade Plan and Backtest on the same registered strategy ID", () => {
    const [row] = buildW52CandidateRows({
      recommendations_final: true,
      strategy_id: "09_52w_breakout",
      recommendations: [{ symbol: "CCC-EQ", signal: "BUY", entry: 10, stop_loss: 9, mom60: 0.1 }],
    });
    expect(row.strategyId).toBe("09_52w_breakout");
    expect(row.w52).toBeTruthy();
    const prefill = buildPaperTradingPrefill(row, "BUY");
    expect(prefill.recommendation_meta.strategy_id).toBe("09_52w_breakout");
  });
});

describe("paper trade prefill", () => {
  it("prefills LTM entry and leaves SL/target unavailable", () => {
    const [row] = buildLtmCandidateRows({
      recommendations_final: true,
      recommendations: [
        {
          symbol: "CUPID-EQ",
          signal: "WATCH",
          selected: true,
          momentum_252: 0.7118,
          entry: 290.15,
          technicals: { close_t: 290.15 },
        },
      ],
    });
    const prefill = buildPaperTradingPrefill(row, "BUY");
    expect(prefill.suggested_entry).toBe(290.15);
    expect(prefill.suggested_stop).toBeLessThan(290.15);
    expect(prefill.suggested_targets[0]).toBeGreaterThan(290.15);
    expect(preferredPaperEntry(prefill, 293.88)).toBe(290.15);
    expect(prefill.recommendation_meta.signal).toBe("WATCH");
    expect(prefill.recommendation_meta.stop_source).toBe("limit_price");
    expect(prefill.recommendation_meta.target_source).toBe("limit_price");
  });

  it("prefills 52W stop from the strategy and completes target at 1:2", () => {
    const [row] = buildW52CandidateRows({
      recommendations_final: true,
      recommendations: [
        {
          symbol: "BBB-EQ",
          signal: "BUY",
          entry: 200,
          stop_loss: 188,
          mom60: 0.2,
        },
      ],
    });
    const prefill = buildPaperTradingPrefill(row, "BUY");
    expect(prefill.suggested_entry).toBe(200);
    expect(prefill.suggested_stop).toBe(188);
    expect(prefill.suggested_targets[0]).toBe(224);
    expect(prefill.recommendation_meta.stop_source).toBe("strategy");
    expect(prefill.recommendation_meta.target_source).toBe("limit_price");
  });

  it("keeps direct paper-trade access empty when no recommendation exists", () => {
    const prefill = buildPaperTradingPrefill(
      {
        rank: null,
        symbol: "INFY",
        signal: "WATCH",
        score: null,
        confidence: null,
        entryLow: null,
        entryHigh: null,
        stopLoss: null,
        target1: null,
        target2: null,
        riskReward: null,
        trend: "—",
        momentum: "unavailable",
        volume: "n/a",
        newsSentiment: "n/a",
        lastUpdated: null,
        tradeReadiness: "Review manually",
        recommendationSummary: "",
      },
      "BUY",
    );
    expect(prefill.suggested_entry).toBeNull();
    expect(prefill.suggested_stop).toBeNull();
    expect(prefill.suggested_targets).toEqual([]);
    expect(preferredPaperEntry(prefill, null)).toBeNull();
  });
});
