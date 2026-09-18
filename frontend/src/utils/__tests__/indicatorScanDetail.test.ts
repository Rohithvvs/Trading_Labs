import { describe, expect, it } from "vitest";
import { isIndicatorScanContext, isIndicatorScanId, mapIndicatorResultToStock } from "../indicatorScanDetail";

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
});
