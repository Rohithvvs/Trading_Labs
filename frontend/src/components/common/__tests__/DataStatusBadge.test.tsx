import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { DataStatusBadge, detectDataStatusKind } from "../DataStatusBadge";

describe("DataStatusBadge", () => {
  describe("detectDataStatusKind", () => {
    it("detects mock data source", () => {
      expect(detectDataStatusKind({ source: "TEST_MOCK" })).toBe("mock");
      expect(detectDataStatusKind({ source: "SYNTHETIC" })).toBe("mock");
      expect(detectDataStatusKind({ isMock: true })).toBe("mock");
      expect(detectDataStatusKind({ warning: "Mock data in use" })).toBe("mock");
    });

    it("detects cached data source", () => {
      expect(detectDataStatusKind({ source: "DB_CACHE" })).toBe("cached");
      expect(detectDataStatusKind({ isCached: true })).toBe("cached");
    });

    it("detects fallback data source", () => {
      expect(detectDataStatusKind({ source: "CANDLE_FALLBACK" })).toBe("fallback");
      expect(detectDataStatusKind({ isFallback: true })).toBe("fallback");
    });

    it("detects delayed data", () => {
      expect(detectDataStatusKind({ isDelayed: true })).toBe("delayed");
      expect(detectDataStatusKind({ warning: "Quotes delayed by 15 minutes" })).toBe("delayed");
    });

    it("detects unavailable data", () => {
      expect(detectDataStatusKind({ source: "NO_DATA" })).toBe("unavailable");
      expect(detectDataStatusKind({ isUnavailable: true })).toBe("unavailable");
    });

    it("detects live data", () => {
      expect(detectDataStatusKind({ source: "FYERS_QUOTE" })).toBe("live");
      expect(detectDataStatusKind({ source: "LIVE" })).toBe("live");
    });
  });

  describe("rendering", () => {
    it("renders mock data badge", () => {
      render(<DataStatusBadge kind="mock" />);
      const badge = screen.getByTestId("data-status-mock");
      expect(badge).toBeTruthy();
      expect(badge.textContent).toContain("MOCK DATA");
    });

    it("renders fallback data badge", () => {
      render(<DataStatusBadge kind="fallback" />);
      const badge = screen.getByTestId("data-status-fallback");
      expect(badge).toBeTruthy();
      expect(badge.textContent).toContain("FALLBACK DATA");
    });

    it("renders delayed data badge", () => {
      render(<DataStatusBadge kind="delayed" />);
      const badge = screen.getByTestId("data-status-delayed");
      expect(badge).toBeTruthy();
      expect(badge.textContent).toContain("DELAYED");
    });

    it("renders unavailable data badge", () => {
      render(<DataStatusBadge kind="unavailable" />);
      const badge = screen.getByTestId("data-status-unavailable");
      expect(badge).toBeTruthy();
      expect(badge.textContent).toContain("DATA UNAVAILABLE");
    });

    it("hides live badge by default when hideWhenLive is true", () => {
      const { container } = render(<DataStatusBadge kind="live" hideWhenLive={true} />);
      expect(container.firstChild).toBeNull();
    });

    it("renders live badge when hideWhenLive is false", () => {
      render(<DataStatusBadge kind="live" hideWhenLive={false} />);
      const badge = screen.getByTestId("data-status-live");
      expect(badge).toBeTruthy();
      expect(badge.textContent).toContain("LIVE DATA");
    });
  });
});
