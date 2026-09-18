import { describe, expect, it } from "vitest";

import { formatAttributionPeriod, periodNoun, periodWindowStart } from "../attributionPeriod";
import { resolveAttributionView } from "../attributionBoards";

describe("attributionPeriod", () => {
  it("uses calendar windows from the evaluation date", () => {
    expect(periodWindowStart("2026-08-17", "1D")).toBe("2026-08-17");
    expect(periodWindowStart("2026-08-17", "1W")).toBe("2026-08-11");
    expect(periodWindowStart("2026-08-17", "1M")).toBe("2026-07-17");
    expect(periodWindowStart("2026-08-17", "1Y")).toBe("2025-08-17");
    expect(periodWindowStart("2026-08-17", "3Y")).toBe("2023-08-17");
    expect(periodWindowStart("2026-08-17", "5Y")).toBe("2021-08-17");
    expect(periodWindowStart("2026-08-17", "7Y")).toBe("2019-08-17");
    expect(periodWindowStart("2026-08-17", "8Y")).toBe("2018-08-17");
    expect(periodWindowStart("2026-08-17", "18Y")).toBe("2008-08-17");
  });

  it("labels short and long windows in completed-session language", () => {
    expect(periodNoun("1D")).toBe("1-day");
    expect(formatAttributionPeriod("2026-08-17", "2026-08-17", "1D")).toBe(
      "Period 2026-08-17 → 2026-08-17 · last 1 day of completed sessions",
    );
    expect(formatAttributionPeriod("2023-08-17", "2026-08-17", "3Y")).toBe(
      "Period 2023-08-17 → 2026-08-17 · last 3 years of completed sessions",
    );
  });
});

describe("resolveAttributionView", () => {
  const payload = {
    recommendations_final: true,
    evaluation_date: "2026-08-17",
    summary: { total: 4 },
    recommendations: [
      { symbol: "WIN-EQ", signal: "BUY" },
      { symbol: "OLD-EQ", signal: "REJECT" },
      { symbol: "LOSE-EQ", signal: "WATCH" },
      { symbol: "MISS-EQ", signal: "REJECT" },
    ],
    blotter: [
      { symbol: "WIN-EQ", entry_date: "2026-08-17", exit_date: "2026-08-17", pnl_pct: 0.05 },
      { symbol: "OLD-EQ", entry_date: "2020-01-10", exit_date: "2020-06-10", pnl_pct: 2.0 },
      { symbol: "LOSE-EQ", entry_date: "2026-08-10", exit_date: "2026-08-16", pnl_pct: -0.1 },
    ],
  };

  it("keeps 3Y as the default long window and omits never-selected names", () => {
    const view = resolveAttributionView(payload, "3Y");
    expect(view?.windowStart).toBe("2023-08-17");
    expect(view?.top5.map((r) => r.symbol)).toEqual(["WIN-EQ"]);
    expect(view?.least5.map((r) => r.symbol)).toEqual(["LOSE-EQ", "WIN-EQ"]);
    expect(view?.average?.valid_backtests).toBe(2);
    expect(view?.average?.unavailable).toBe(2);
    expect(view?.average?.average_return).toBeCloseTo(-0.025, 8);
  });

  it("narrows to 1D without fabricating missing names as 0%", () => {
    const view = resolveAttributionView(payload, "1D");
    expect(view?.windowStart).toBe("2026-08-17");
    expect(view?.top5.map((r) => r.symbol)).toEqual(["WIN-EQ"]);
    expect(view?.least5.map((r) => r.symbol)).toEqual(["WIN-EQ"]);
    expect(view?.average?.valid_backtests).toBe(1);
    expect(view?.average?.average_return).toBeCloseTo(0.05, 8);
  });

  it("includes the 18Y book when the trade is old enough", () => {
    const view = resolveAttributionView(payload, "18Y");
    expect(view?.windowStart).toBe("2008-08-17");
    expect(view?.top5[0]?.symbol).toBe("OLD-EQ");
    expect(view?.average?.valid_backtests).toBe(3);
  });

  it("does not treat end-of-sample liquidation as a 1D trade", () => {
    const eodPayload = {
      ...payload,
      blotter: [
        {
          symbol: "HELD-EQ",
          entry_date: "2025-09-10",
          exit_date: "2026-08-17",
          pnl_pct: 0.055,
          reason: "eod_liquidation",
        },
        { symbol: "WIN-EQ", entry_date: "2026-08-17", exit_date: "2026-08-17", pnl_pct: 0.05 },
      ],
      recommendations: [
        { symbol: "HELD-EQ", signal: "REJECT" },
        { symbol: "WIN-EQ", signal: "BUY" },
      ],
    };
    const day = resolveAttributionView(eodPayload, "1D");
    expect(day?.top5.map((r) => r.symbol)).toEqual(["WIN-EQ"]);
    expect(day?.average?.valid_backtests).toBe(1);
    const year = resolveAttributionView(eodPayload, "1Y");
    expect(year?.top5.map((r) => r.symbol).sort()).toEqual(["HELD-EQ", "WIN-EQ"]);
  });
});
