import { describe, expect, it } from "vitest";

import { completePaperLevels, levelsFromEntry, roundToTick } from "../paperOrderLevels";

describe("paper order levels from limit price", () => {
  it("uses the 2% stop / 1:2 target convention for a BUY limit", () => {
    const levels = levelsFromEntry(293.88, "BUY");
    expect(levels.stopLoss).toBe(roundToTick(293.88 * 0.98));
    expect(levels.stopLoss).toBe(288);
    expect(levels.target).toBe(roundToTick(293.88 + (293.88 - 288) * 2));
    expect(levels.target).toBeGreaterThan(293.88);
    expect(levels.stopLoss).toBeLessThan(293.88);
  });

  it("inverts the range for SELL", () => {
    const levels = levelsFromEntry(200, "SELL");
    expect(levels.stopLoss).toBe(204);
    expect(levels.target).toBe(192);
  });

  it("keeps a strategy stop and only fills the missing target at 1:2", () => {
    const levels = completePaperLevels({ entry: 100, side: "BUY", stop: 94, target: null });
    expect(levels.stopLoss).toBe(94);
    expect(levels.derivedStop).toBe(false);
    expect(levels.target).toBe(112);
    expect(levels.derivedTarget).toBe(true);
  });

  it("does not invent levels without an entry", () => {
    const levels = completePaperLevels({ entry: null, side: "BUY" });
    expect(levels.stopLoss).toBeNull();
    expect(levels.target).toBeNull();
  });
});
