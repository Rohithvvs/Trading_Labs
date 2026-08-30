import { describe, expect, it } from "vitest";
import { absorbOutputs, absorbScreenFilters, describeAbsorbedFilter } from "../indicatorAbsorb";

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
});
