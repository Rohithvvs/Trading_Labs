import { describe, expect, it } from "vitest";

import { resolveUniverseAverage, windowStartIso } from "../universeAverage";

describe("resolveUniverseAverage", () => {
  it("uses 2023-08-14 → 2026-08-14 for a 3Y window", () => {
    expect(windowStartIso("2026-08-14", 3)).toBe("2023-08-14");
  });

  it("averages all names with blotter trades and does not treat missing as 0", () => {
    const { average } = resolveUniverseAverage({
      evaluation_date: "2026-08-14",
      summary: { total: 755 },
      recommendations: [{ symbol: "WIN" }, { symbol: "SKIP" }, { symbol: "MISS" }],
      blotter: [
        { symbol: "WIN", entry_date: "2024-01-10", exit_date: "2024-06-10", pnl_pct: 0.2 },
        { symbol: "WIN", entry_date: "2025-09-01", exit_date: "2025-12-01", pnl_pct: 0.1 },
      ],
    });
    expect(average?.window_start).toBe("2023-08-14");
    expect(average?.window_end).toBe("2026-08-14");
    expect(average?.universe_size).toBe(3);
    expect(average?.valid_backtests).toBe(1);
    expect(average?.unavailable).toBe(2);
    expect(average?.average_return).toBeCloseTo(0.32, 8);
  });
});
