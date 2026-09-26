import { describe, expect, it } from "vitest";
import { isIndicatorScanContext, isIndicatorScanId, mapIndicatorResultToStock, resolveTradePlanDetails } from "../indicatorScanDetail";

describe("indicatorScanDetail", () => {
  it("treats IND- public ids as indicator scans", () => {
    expect(isIndicatorScanId("IND-20260904-001")).toBe(true);
    expect(isIndicatorScanId("STR-20260903-001")).toBe(false);
  });

  it("detects indicator-scan context from stock source or IND- run id", () => {
    expect(isIndicatorScanContext({ source: "indicator_scanner" }, "STR-1")).toBe(true);
    expect(isIndicatorScanContext(null, "IND-20260904-001")).toBe(true);
    expect(isIndicatorScanContext({ source: "strategy_tester" }, "STR-1")).toBe(false);
  });

  it("maps LTM scan rows to MATCH with the indicator's own entry conditions, not SMA/RSI", () => {
    const stock = mapIndicatorResultToStock({
      symbol: "RATEGAIN",
      display_name: "Rategain Travel Technologies Ltd.",
      status: "ok",
      matched: true,
      as_of: "2026-09-04",
      outputs: {
        "LTM Eligible Signal": 1,
        "Momentum 252": 0.76,
        Close: 869.75,
        "Close t-252": 495.05,
      },
      filter_results: [{ name: "Momentum 252 > 0.5", passed: true }],
      indicator_name: "LTM Momentum 252 [SCAN]",
    });
    expect(stock.signal).toBe("MATCH");
    expect(stock.source).toBe("indicator_scanner");
    expect(stock.entry_price).toBe(495.05);
    expect(stock.exit_price).toBe(869.75);
    expect(stock.return_pct).toBeCloseTo(76);
    expect(stock.filter_results?.map((item) => item.name)).toEqual(["Momentum 252 > 0.5"]);
    expect(stock.failed_filters).toEqual([]);
  });

  it("does not fall back to the aggregate signal filter when filter_results are missing", () => {
    const stock = mapIndicatorResultToStock(
      {
        symbol: "RATEGAIN",
        display_name: "Rategain Travel Technologies Ltd.",
        status: "ok",
        matched: true,
        as_of: "2026-09-07",
        outputs: { "LTM Eligible Signal": 1, "Momentum 252": 0.76 },
        ohlcv: { close: 869.75 },
      },
      {
        id: "run-1",
        scan_id: "IND-20260907-004",
        indicator_name: "LTM Momentum 252 [SCAN]",
        universe: "nse-755",
        universe_size: 750,
        timeframe: "1D",
        status: "completed",
        progress_pct: 100,
        processed_count: 750,
        total_count: 750,
        filters: [{ field: "LTM Eligible Signal", operator: "=", value: 1 }],
        entry_conditions: [{ name: "Momentum 252 > 0.5" }],
      },
    );
    expect(stock.filter_results?.map((item) => item.name)).toEqual(["Momentum 252 > 0.5"]);
    expect(stock.filter_results?.some((item) => item.name === "LTM Eligible Signal = 1")).toBe(false);
  });

  it("maps 13 Trend Pullback [SCAN] with Mom 252, deriving closeT252 and populating indicators", () => {
    const stock = mapIndicatorResultToStock({
      symbol: "TCS",
      display_name: "Tata Consultancy Services Ltd.",
      status: "ok",
      matched: true,
      as_of: "2026-09-21",
      outputs: {
        "SMA 50": 3153.02,
        "SMA 200": 2568.52,
        "Mom 252": 0.25,
        Close: 3265.10,
        "EMA 20": 3220.45,
        "EMA 50": 3140.10,
        "Avg Volume": 1250000,
        RSI: 43.6,
      },
      ohlcv: { close: 3265.10, volume: 838700 },
      indicator_name: "13 Trend Pullback [SCAN]",
    });

    expect(stock.signal).toBe("MATCH");
    expect(stock.return_pct).toBeCloseTo(25.0);
    // Derived closeT252: 3265.10 / (1 + 0.25) = 2612.08
    expect(stock.entry_price).toBeCloseTo(2612.08);
    expect(stock.exit_price).toBe(3265.10);
    expect(stock.sma_50).toBe(3153.02);
    expect(stock.sma_200).toBe(2568.52);
    expect(stock.avg_volume).toBe(1250000);
    expect(stock.indicators?.ema_20).toBe(3220.45);
    expect(stock.indicators?.ema_50).toBe(3140.10);
  });

  it("resolves trade plan details with consistent entry, stopLoss, and target levels for indicator scans", () => {
    const stock = mapIndicatorResultToStock({
      symbol: "TCS",
      display_name: "Tata Consultancy Services Ltd.",
      status: "ok",
      matched: true,
      as_of: "2026-09-21",
      outputs: {
        "SMA 50": 3153.02,
        "SMA 200": 2568.52,
        "Mom 252": 0.25,
        Close: 3265.10,
        RSI: 43.6,
      },
      ohlcv: { close: 3265.10 },
      indicator_name: "13 Trend Pullback [SCAN]",
    });

    const plan = resolveTradePlanDetails({
      stock,
      runId: "IND-20260921-031",
      side: "BUY",
    });

    expect(plan.displayEntryPrice).toBe(3265.10);
    // For LONG: stop loss must be below entry price (using SMA 50 = 3153.02)
    expect(plan.stopLoss).toBe(3153.02);
    expect(plan.stopLoss!).toBeLessThan(plan.displayEntryPrice!);

    // Target must be 1:2 R:R above entry price: 3265.10 + 2 * (3265.10 - 3153.02) = 3489.26
    expect(plan.target).toBe(3489.26);
    expect(plan.target!).toBeGreaterThan(plan.displayEntryPrice!);

    // Risk and reward calculations
    expect(plan.riskAmount).toBeCloseTo(112.08);
    expect(plan.rewardAmount).toBeCloseTo(224.16);
    expect(plan.riskReward).toBe(2.0);
    expect(plan.rr).toBe(2.0);
    expect(plan.position).toBe("LONG");
  });

  it("maps AETHER stock setup with entry, stop loss, target, and 1:2 RR", () => {
    const stock = mapIndicatorResultToStock({
      symbol: "AETHER",
      display_name: "Aether Industries Ltd.",
      status: "ok",
      matched: true,
      as_of: "2026-09-25",
      outputs: {
        Close: 1767.00,
        "SMA 50": 1197.63,
        "SMA 150": 1050.00,
        "SMA 200": 980.00,
        "Mom 252": 1.4008,
      },
      ohlcv: { close: 1767.00 },
      indicator_name: "Top 5: Minervini Stage-2 VCP [SCAN]",
    });

    expect(stock.entry).toBe(1767.00);
    expect(stock.stop_loss).toBe(1197.63);
    expect(stock.target).toBe(2905.74);
    expect(stock.rr).toBe(2.0);
    expect(stock.risk_reward).toBe(2.0);
    expect(stock.return_pct).toBeCloseTo(140.08);
  });
});
