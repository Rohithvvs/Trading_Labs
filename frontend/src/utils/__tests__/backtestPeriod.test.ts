import { describe, expect, it } from "vitest";

import {
  formatCompletedSessionPeriod,
  inferCompletedYears,
  periodLabelFromPayload,
  yearsFromWindow,
} from "../backtestPeriod";

describe("backtestPeriod", () => {
  it("resolves the requested 3Y completed-session window", () => {
    expect(inferCompletedYears("2023-08-14", "2026-08-14")).toBe(3);
    expect(yearsFromWindow("3Y", "2023-08-14", "2026-08-14")).toBe(3);
    expect(formatCompletedSessionPeriod("2023-08-14", "2026-08-14", 3)).toBe(
      "Period 2023-08-14 → 2026-08-14 · last 3 years of completed sessions",
    );
  });

  it("keeps a 1Y window labeled as 1 year", () => {
    expect(formatCompletedSessionPeriod("2025-08-14", "2026-08-14")).toBe(
      "Period 2025-08-14 → 2026-08-14 · last 1 year of completed sessions",
    );
  });

  it("prefers payload attribution window over inferred 1Y leftovers", () => {
    const label = periodLabelFromPayload({
      attribution_window: "3Y",
      attribution_window_start: "2023-08-14",
      attribution_window_end: "2026-08-14",
      top5_positive: [{ window_start: "2023-08-14", window_end: "2026-08-14" }],
    });
    expect(label).toBe("Period 2023-08-14 → 2026-08-14 · last 3 years of completed sessions");
  });
});
