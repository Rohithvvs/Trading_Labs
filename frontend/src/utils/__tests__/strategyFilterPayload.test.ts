import { describe, expect, it } from "vitest";
import { buildStrategyPayload, mapRawFilterToModalFilter, parseFilterField, toApiFilter } from "../strategyFilterPayload";
import type { ModalBuilderFilter } from "../pineParser";

const defaults: ModalBuilderFilter[] = [
  { id: "f1", field: "CLOSE", operator: ">", rightKind: "indicator", literal: "", indicator: "SMA", indicatorPeriod: "50", low: "", high: "" },
  { id: "f2", field: "SMA", period: "50", operator: ">", rightKind: "indicator", literal: "", indicator: "SMA", indicatorPeriod: "200", low: "", high: "" },
  { id: "f3", field: "RSI", period: "14", operator: ">", rightKind: "literal", literal: "55", indicator: "SMA", indicatorPeriod: "20", low: "", high: "" },
  { id: "f4", field: "VOLUME", operator: ">", rightKind: "indicator", literal: "", indicator: "AVG_VOLUME", indicatorPeriod: "20", low: "", high: "" },
];

describe("toApiFilter", () => {
  it("sends RSI > 55 as a numeric literal even when indicator defaults to SMA", () => {
    const leaf = toApiFilter(defaults[2]);
    expect(leaf.field).toBe("RSI_14");
    expect(leaf.left).toEqual({ indicator: "RSI", period: 14 });
    expect(leaf.value).toBe(55);
  });

  it("sends Close > SMA 50 as a structured indicator comparison", () => {
    const leaf = toApiFilter(defaults[0]);
    expect(leaf.field).toBe("CLOSE");
    expect(leaf.value).toEqual({ indicator: "SMA", period: 50 });
  });

  it("keeps Pine input.int 252/20 periods on the API payload (not HIGH with no period)", () => {
    const high = toApiFilter({
      id: "h",
      field: "CLOSE",
      operator: ">=",
      rightKind: "indicator",
      literal: "",
      indicator: "HIGH",
      indicatorPeriod: "252",
      low: "",
      high: "",
      label: "CLOSE >= HIGH 252",
    });
    expect(high.value).toEqual({ indicator: "HIGH", period: 252 });

    const vol = toApiFilter({
      id: "v",
      field: "VOLUME",
      operator: ">",
      rightKind: "indicator",
      literal: "",
      indicator: "AVG_VOLUME",
      indicatorPeriod: "20",
      low: "",
      high: "",
    });
    expect(vol.value).toEqual({ indicator: "AVG_VOLUME", period: 20 });
  });

  it("maps pine 52-week breakout leaves including the NIFTY 500 gate", () => {
    const bench = toApiFilter({
      id: "b",
      field: "BENCHMARK_CLOSE",
      operator: ">",
      rightKind: "indicator",
      literal: "",
      indicator: "SMA",
      indicatorPeriod: "50",
      low: "",
      high: "",
      isBenchmark: true,
      label: "NIFTY 500 Close > NIFTY 500 SMA 50",
    });
    expect(bench.field).toBe("BENCHMARK_CLOSE");
    expect(bench.value).toEqual({ indicator: "SMA", period: 50 });

    const brk = toApiFilter({
      id: "h",
      field: "CLOSE",
      operator: ">=",
      rightKind: "indicator",
      literal: "",
      indicator: "HIGH",
      indicatorPeriod: "252",
      low: "",
      high: "",
    });
    expect(brk.value).toEqual({ indicator: "HIGH", period: 252 });
  });

  it("rejects incomplete literal filters instead of sending an empty value", () => {
    expect(() =>
      toApiFilter({
        id: "x",
        field: "CLOSE",
        operator: ">",
        rightKind: "literal",
        literal: "",
        indicator: "",
        indicatorPeriod: "",
        low: "",
        high: "",
      }),
    ).toThrow(/missing a comparison value/i);
  });
});

describe("parseFilterField", () => {
  it("extracts numeric period suffix when present", () => {
    expect(parseFilterField("SMA_50")).toEqual({ field: "SMA", period: "50" });
    expect(parseFilterField("RSI_14")).toEqual({ field: "RSI", period: "14" });
    expect(parseFilterField("AVG_VOLUME_20")).toEqual({ field: "AVG_VOLUME", period: "20" });
    expect(parseFilterField("BB_UPPER_20")).toEqual({ field: "BB_UPPER", period: "20" });
  });

  it("preserves multi-word indicator names with underscores and no period", () => {
    expect(parseFilterField("REL_VOLUME")).toEqual({ field: "REL_VOLUME", period: undefined });
    expect(parseFilterField("AVG_VOLUME")).toEqual({ field: "AVG_VOLUME", period: undefined });
    expect(parseFilterField("PREV_CLOSE")).toEqual({ field: "PREV_CLOSE", period: undefined });
    expect(parseFilterField("PREV_HIGH")).toEqual({ field: "PREV_HIGH", period: undefined });
    expect(parseFilterField("DAILY_RETURN")).toEqual({ field: "DAILY_RETURN", period: undefined });
    expect(parseFilterField("GAP_PCT")).toEqual({ field: "GAP_PCT", period: undefined });
    expect(parseFilterField("BENCHMARK_CLOSE")).toEqual({ field: "BENCHMARK_CLOSE", period: undefined });
    expect(parseFilterField("BB_UPPER")).toEqual({ field: "BB_UPPER", period: undefined });
  });
});

describe("mapRawFilterToModalFilter", () => {
  it("correctly maps Breakout preset filters without corrupting REL_VOLUME", () => {
    const rawBreakoutFilters = [
      { id: "close_high20", field: "close", operator: ">", value: { indicator: "HIGH", period: 20 } },
      { id: "vol_1_5", field: "REL_VOLUME", operator: ">", value: 1.5, label: "Volume > 1.5 × Average Volume" },
      { id: "rsi_band", field: "RSI", operator: "between", low: 50, high: 70 },
      { id: "close_ema50", field: "close", operator: ">", value: { indicator: "EMA", period: 50 } },
    ];
    const mapped = rawBreakoutFilters.map((f, i) => mapRawFilterToModalFilter(f, i));

    expect(mapped[1].field).toBe("REL_VOLUME");
    expect(mapped[1].period).toBeUndefined();
    expect(mapped[1].literal).toBe("1.5");
    expect(mapped[1].rightKind).toBe("literal");
    expect(mapped[1].label).toBe("Volume > 1.5 × Average Volume");

    expect(mapped[2].field).toBe("RSI");
    expect(mapped[2].operator).toBe("between");
    expect(mapped[2].low).toBe("50");
    expect(mapped[2].high).toBe("70");

    // Converting mapped back to API payload produces valid backend shapes
    const apiFilter = toApiFilter(mapped[1]);
    expect(apiFilter.field).toBe("REL_VOLUME");
    expect(apiFilter.value).toBe(1.5);
  });
});

describe("buildStrategyPayload", () => {
  it("uses snake_case API fields the backend validates", () => {
    const payload = buildStrategyPayload({
      name: "Momentum Strategy",
      description: "desc",
      universe: "ALL_755",
      timeframe: "1 Day",
      side: "LONG",
      startDate: "2024-01-01",
      endDate: "2026-08-26",
      initialCapital: 1_000_000,
      filters: defaults,
      logic: "ALL",
      source: { type: "builder" },
    });
    expect(payload.timeframe).toBe("1D");
    expect(payload.start_date).toBe("2024-01-01");
    expect(payload.initial_capital).toBe(1_000_000);
    expect(payload.filters).toHaveLength(4);
    expect(payload.signal_rules?.buy_requires_all).toBe(true);
    expect(payload.filters?.[2].value).toBe(55);
  });
});
