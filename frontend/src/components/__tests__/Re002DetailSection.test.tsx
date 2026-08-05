import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Re002DetailSection } from "../Re002DetailSection";

vi.mock("../../api", () => ({
  fetchRe002SymbolLatest: vi.fn().mockRejectedValue(new Error("no data")),
}));

describe("Re002DetailSection", () => {
  it("renders empty state", async () => {
    render(<Re002DetailSection decision={null} symbol={null} />);
    expect(screen.getByTestId("re002-detail-empty")).toBeTruthy();
    expect(screen.getByText(/Lab · Experimental · RE-002/i)).toBeTruthy();
  });

  it("renders decision state and strategy", () => {
    render(
      <Re002DetailSection
        decision={{
          recommendation_state: "BUY",
          confidence_score: 0.82,
          strategy_name: "Relative Strength Leadership",
          market_regime: "Bull",
          production_action: "WATCH",
          engine_id: "RE-002",
          engine_version: "1.0",
          explanation: "Strong RS leader",
        }}
      />,
    );
    expect(screen.getByTestId("re002-detail")).toBeTruthy();
    expect(screen.getByText(/Relative Strength Leadership/)).toBeTruthy();
    expect(screen.getByText(/BUY/)).toBeTruthy();
  });
});
