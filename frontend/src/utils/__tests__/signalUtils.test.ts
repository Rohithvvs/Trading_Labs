import { describe, it, expect } from "vitest";
import { simplifySignal, getSignalTone, getSignalDescription } from "../signalUtils";

describe("signalUtils", () => {
  describe("simplifySignal", () => {
    it("simplifies bullish entry signals to BUY", () => {
      expect(simplifySignal("BUY")).toBe("BUY");
      expect(simplifySignal("buy")).toBe("BUY");
      expect(simplifySignal("STRONG_BUY")).toBe("BUY");
      expect(simplifySignal("STRONG BUY")).toBe("BUY");
      expect(simplifySignal("WEAK_BUY")).toBe("BUY");
      expect(simplifySignal("BULLISH")).toBe("BUY");
      expect(simplifySignal("LONG")).toBe("BUY");
      expect(simplifySignal("MATCH")).toBe("BUY");
    });

    it("simplifies monitor/hold signals to WATCH", () => {
      expect(simplifySignal("WATCH")).toBe("WATCH");
      expect(simplifySignal("watch")).toBe("WATCH");
      expect(simplifySignal("MONITOR")).toBe("WATCH");
      expect(simplifySignal("HOLD")).toBe("WATCH");
      expect(simplifySignal("NEUTRAL")).toBe("WATCH");
      expect(simplifySignal("SIDEWAYS")).toBe("WATCH");
      expect(simplifySignal("WAIT")).toBe("WATCH");
    });

    it("simplifies discard/fail signals to REJECT", () => {
      expect(simplifySignal("REJECT")).toBe("REJECT");
      expect(simplifySignal("reject")).toBe("REJECT");
      expect(simplifySignal("DISCARD")).toBe("REJECT");
      expect(simplifySignal("AVOID")).toBe("REJECT");
      expect(simplifySignal("BLOCKED")).toBe("REJECT");
      expect(simplifySignal("FAIL")).toBe("REJECT");
      expect(simplifySignal("FAILED")).toBe("REJECT");
    });

    it("preserves explicit SELL/SHORT signals", () => {
      expect(simplifySignal("SELL")).toBe("SELL");
      expect(simplifySignal("SHORT")).toBe("SELL");
    });

    it("handles empty or null values gracefully", () => {
      expect(simplifySignal(null)).toBe("—");
      expect(simplifySignal(undefined)).toBe("—");
      expect(simplifySignal("")).toBe("—");
      expect(simplifySignal("—")).toBe("—");
      expect(simplifySignal("UNKNOWN")).toBe("—");
    });
  });

  describe("getSignalTone", () => {
    it("returns appropriate tones", () => {
      expect(getSignalTone("BUY")).toBe("buy");
      expect(getSignalTone("STRONG_BUY")).toBe("buy");
      expect(getSignalTone("WATCH")).toBe("watch");
      expect(getSignalTone("HOLD")).toBe("watch");
      expect(getSignalTone("REJECT")).toBe("sell");
      expect(getSignalTone("DISCARD")).toBe("sell");
      expect(getSignalTone("SELL")).toBe("sell");
      expect(getSignalTone("")).toBe("neutral");
    });
  });

  describe("getSignalDescription", () => {
    it("returns descriptive trader guidance for each signal", () => {
      expect(getSignalDescription("BUY")).toContain("Passed all screening criteria");
      expect(getSignalDescription("WATCH")).toContain("Setup is forming");
      expect(getSignalDescription("REJECT")).toContain("Failed core trend");
    });
  });
});
