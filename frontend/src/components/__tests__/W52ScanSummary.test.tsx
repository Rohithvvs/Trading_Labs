import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { W52ScanSummary } from "../W52ScanSummary";

describe("W52ScanSummary", () => {
  it("labels a live overlay as the TradingView 1D bar", () => {
    render(
      <W52ScanSummary
        payload={{
          recommendations_final: true,
          evaluation_date: "2026-08-21",
          evaluation_bar: "live_session",
          book_status: "ACTIVE",
          summary: { total: 755, buy: 5, hold: 5, watch: 0, reject: 745, screener_matches: 5 },
        }}
      />,
    );
    expect(screen.getByText(/live 1D bar, TradingView Pine/)).toBeTruthy();
    expect(screen.getByText(/same three legs as the TradingView Pine Screener/)).toBeTruthy();
  });
});
