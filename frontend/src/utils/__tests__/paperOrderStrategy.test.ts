import { describe, expect, it } from "vitest";
import {
  extractStrategyFromNotes,
  formatStrategyNote,
  mergeStrategyNote,
} from "../paperOrderStrategy";

describe("paper order strategy notes", () => {
  it("formats strategy and run tags", () => {
    expect(formatStrategyNote("LTM Momentum 252 [SCAN]", "IND-20260904-001")).toBe(
      "Strategy: LTM Momentum 252 [SCAN] · Run: IND-20260904-001",
    );
    expect(formatStrategyNote("  ", null)).toBe("");
  });

  it("merges the strategy tag without duplicating it", () => {
    const first = mergeStrategyNote("", "RSI Scanner", "IND-1");
    expect(first).toBe("Strategy: RSI Scanner · Run: IND-1");
    expect(mergeStrategyNote(first, "RSI Scanner", "IND-1")).toBe(first);
    expect(mergeStrategyNote("Manual note", "RSI Scanner")).toBe(
      "Manual note · Strategy: RSI Scanner",
    );
  });

  it("extracts the originating strategy from stored notes", () => {
    expect(extractStrategyFromNotes("Strategy: LTM Momentum 252 [SCAN] · Run: IND-1")).toBe(
      "LTM Momentum 252 [SCAN]",
    );
    expect(extractStrategyFromNotes("Imported from RSI Scanner | signal=BUY")).toBe("RSI Scanner");
    expect(extractStrategyFromNotes("Imported from system recommendation | signal=BUY")).toBeNull();
    expect(extractStrategyFromNotes("plain notes")).toBeNull();
  });
});
