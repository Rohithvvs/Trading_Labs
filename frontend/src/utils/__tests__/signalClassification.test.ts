import { describe, expect, it } from "vitest";

import {
  BUY_SCORE_THRESHOLD,
  WATCH_SCORE_THRESHOLD,
  classifySignalFromScore,
} from "../signalClassification";

describe("composite score classification", () => {
  it("uses 68 / 55 and does not treat non-finite scores as BUY", () => {
    expect(BUY_SCORE_THRESHOLD).toBe(68);
    expect(WATCH_SCORE_THRESHOLD).toBe(55);
    expect(classifySignalFromScore(100)).toBe("BUY");
    expect(classifySignalFromScore(68)).toBe("BUY");
    expect(classifySignalFromScore(67.99)).toBe("WATCH");
    expect(classifySignalFromScore(55)).toBe("WATCH");
    expect(classifySignalFromScore(54.99)).toBe("REJECT");
    expect(classifySignalFromScore(Number.NaN)).toBe("REJECT");
    expect(classifySignalFromScore(Number.POSITIVE_INFINITY)).toBe("REJECT");
  });
});
