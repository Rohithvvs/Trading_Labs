import { describe, expect, it } from "vitest";

import {
  hasDisplayableStrategyResults,
  isCurrentScanCompleted,
  isCurrentScanFailed,
  isStrategyRunActive,
  mapStrategyStage,
} from "../strategyScan";

describe("strategyScan lifecycle", () => {
  it("treats queued/evaluating/backtesting/publishing as in-flight", () => {
    expect(isStrategyRunActive({ run_status: "queued" })).toBe(true);
    expect(isStrategyRunActive({ status: "evaluating" })).toBe(true);
    expect(isStrategyRunActive({ run_status: "backtesting" })).toBe(true);
    expect(isStrategyRunActive({ run_status: "publishing" })).toBe(true);
    expect(isStrategyRunActive({ run_status: "completed" })).toBe(false);
    expect(isStrategyRunActive({ run_status: "failed" })).toBe(false);
    expect(isStrategyRunActive(null)).toBe(false);
  });

  it("does not treat a previous completed row as the new scan finishing", () => {
    const previous = { run_status: "completed", scan_id: "old-scan", recommendations_final: true };
    expect(isCurrentScanCompleted(previous, "new-scan")).toBe(false);
    expect(isCurrentScanCompleted(previous, "old-scan")).toBe(true);
    expect(isCurrentScanCompleted({ run_status: "queued", scan_id: "new-scan" }, "new-scan")).toBe(false);
    expect(isCurrentScanCompleted({ run_status: "completed", scan_id: "new-scan" }, "new-scan")).toBe(true);
    const click = Date.parse("2026-08-16T12:00:00.000Z");
    expect(
      isCurrentScanCompleted(
        { run_status: "completed", scan_id: "old-scan", completed_at: "2026-08-16T10:00:00.000Z" },
        null,
        click,
      ),
    ).toBe(false);
  });

  it("maps backend stages to the progress copy", () => {
    expect(mapStrategyStage("evaluating")).toBe("Scanning universe...");
    expect(mapStrategyStage("backtesting")).toBe("Running portfolio backtest...");
    expect(mapStrategyStage("publishing")).toBe("Publishing results...");
    expect(mapStrategyStage("queued")).toBe("Starting scan...");
  });

  it("hides last-completed recommendations while a new scan is in flight", () => {
    const last = {
      completed_at: "2026-08-16T10:00:00Z",
      recommendations: [{ symbol: "OLD" }],
      recommendations_final: false,
      run_status: "evaluating",
    };
    expect(hasDisplayableStrategyResults(last, { inFlight: true })).toBe(false);
    expect(hasDisplayableStrategyResults({ ...last, recommendations_final: true, run_status: "completed" }, { inFlight: false })).toBe(
      true,
    );
  });

  it("treats failed/cancelled as terminal for the current scan_id only", () => {
    expect(isCurrentScanFailed({ run_status: "failed", scan_id: "a" }, "a")).toBe(true);
    expect(isCurrentScanFailed({ run_status: "cancelled", scan_id: "a" }, "a")).toBe(true);
    expect(isCurrentScanFailed({ run_status: "failed", scan_id: "old" }, "new")).toBe(false);
  });
});
