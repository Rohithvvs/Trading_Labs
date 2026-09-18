import { describe, expect, it } from "vitest";
import {
  absorbFromParsedDefinition,
  absorbOutputs,
  absorbScreenFilters,
  defaultColumnFilter,
  describeAbsorbedFilter,
  insertScreenerSignalPlot,
  isAggregateSignalFilter,
  isTvStyleSignalEqualsOneOnPricePlot,
  looksLikeAggregateSignal,
  normalizePineScreenerFilters,
  preferredScreenerColumn,
} from "../indicatorAbsorb";

describe("indicatorAbsorb", () => {
  it("absorbs plot titles as screener columns and Signal = 1 as the screen rule", () => {
    const columns = absorbOutputs([
      { name: "52W Breakout Signal", kind: "plot" },
      { name: "Close", kind: "plot" },
      { name: "Prior 252 High", kind: "plot" },
      { name: "52W Breakout", kind: "plotshape" },
      { name: "52W Breakout Scan", kind: "alertcondition" },
    ]);
    expect(columns.map((c) => c.name)).toEqual([
      "52W Breakout Signal",
      "Close",
      "Prior 252 High",
      "52W Breakout",
      "52W Breakout Scan",
    ]);
    expect(absorbScreenFilters(columns)).toEqual([{ field: "52W Breakout Signal", operator: "=", value: 1 }]);
    expect(describeAbsorbedFilter({ field: "52W Breakout Signal", operator: "=", value: 1 })).toBe(
      "52W Breakout Signal = 1",
    );
  });

  it("uses the selected strategy's entry conditions instead of the aggregate signal", () => {
    const absorbed = absorbFromParsedDefinition({
      outputs: [
        { name: "LTM Eligible Signal", kind: "plot" },
        { name: "Momentum 252", kind: "plot" },
      ],
      entry_conditions: [
        { id: "c1", name: "Close > SMA 50" },
        { id: "c2", name: "SMA 50 > SMA 200" },
        { id: "c3", name: "RSI 14 > 55" },
        { id: "c4", name: "Volume > Average Volume 20" },
        { name: "LTM Eligible Signal = 1" },
      ],
    });
    expect(absorbed.entryConditions).toEqual([
      "Close > SMA 50",
      "SMA 50 > SMA 200",
      "RSI 14 > 55",
      "Volume > Average Volume 20",
    ]);
    expect(absorbed.filters).toEqual([]);
  });

  it("does not treat Momentum Signal = 1 as the collapsed aggregate plot", () => {
    expect(looksLikeAggregateSignal("Momentum Signal")).toBe(false);
    expect(looksLikeAggregateSignal("Momentum Signal = 1")).toBe(false);
    expect(isAggregateSignalFilter({ field: "Momentum Signal", operator: "=", value: 1 })).toBe(false);
    expect(isAggregateSignalFilter({ field: "Momentum Pulse", operator: "is_true" })).toBe(false);
    expect(looksLikeAggregateSignal("LTM Eligible Signal = 1")).toBe(true);
    expect(looksLikeAggregateSignal("52W Breakout Signal")).toBe(true);
  });

  it("does not treat EMA 20 as Signal = 1 when the user clicks a price plot", () => {
    expect(defaultColumnFilter({ name: "EMA 20", kind: "plot" })).toEqual({
      field: "EMA 20",
      operator: "=",
    });
    expect(defaultColumnFilter({ name: "Momentum Signal", kind: "plotshape" })).toEqual({
      field: "Momentum Signal",
      operator: "is_true",
    });
    expect(defaultColumnFilter({ name: "52W Breakout Signal", kind: "plot" })).toEqual({
      field: "52W Breakout Signal",
      operator: "=",
      value: 1,
    });
  });

  it("prefers the plotshape signal column over the first price plot", () => {
    const columns = [
      { name: "EMA 20", kind: "plot" },
      { name: "Momentum Signal", kind: "plotshape" },
      { name: "Momentum Pulse", kind: "alertcondition" },
    ];
    expect(preferredScreenerColumn(columns)?.name).toBe("Momentum Signal");
    expect(
      isTvStyleSignalEqualsOneOnPricePlot({ field: "EMA 20", operator: ">=", value: 1 }, columns),
    ).toBe(true);
    expect(
      normalizePineScreenerFilters([{ field: "EMA 20", operator: ">=", value: 1 }], columns),
    ).toEqual([{ field: "EMA 20", operator: "=", value: 1 }]);
    expect(
      isTvStyleSignalEqualsOneOnPricePlot({ field: "Momentum Signal", operator: "is_true" }, columns),
    ).toBe(false);
  });

  it("inserts a 0/1 Signal plot so TradingView Pine Screener can filter Signal = 1", () => {
    const source = `//@version=6
indicator("Momentum Pulse Finder", overlay=true)
ema20 = ta.ema(close, 20)
rsiValue = ta.rsi(close, 14)
buySignal = close > ema20 and ta.crossover(rsiValue, 50)
plot(ema20, title="EMA 20")
plotshape(buySignal, title="Momentum Signal")
`;
    const next = insertScreenerSignalPlot(source);
    expect(next).toContain('plot(buySignal ? 1 : 0, "Signal")');
    expect(next.indexOf('plot(buySignal ? 1 : 0, "Signal")')).toBeLessThan(next.indexOf("plot(ema20"));
    expect(insertScreenerSignalPlot(next)).toBe(next);
  });
});
