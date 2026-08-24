import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { W52ReturnBoards } from "../W52ReturnBoards";
import { W52_STRATEGY_ID } from "../../utils/strategyIdentity";

const payload = {
  recommendations_final: true,
  strategy_id: W52_STRATEGY_ID,
  attribution_window: "3Y",
  attribution_window_start: "2023-08-14",
  attribution_window_end: "2026-08-14",
  top5_positive: [
    {
      rank: 1,
      symbol: "AAA-EQ",
      signal: "BUY",
      return: 0.2,
      trades: 2,
      win_rate: 1,
      max_dd: -0.05,
      profit_factor: 2,
      window_start: "2023-08-14",
      window_end: "2026-08-14",
    },
  ],
  least5: [
    {
      rank: 1,
      symbol: "ZZZ-EQ",
      signal: "REJECT",
      return: -0.1,
      trades: 1,
      win_rate: 0,
      max_dd: -0.1,
      profit_factor: 0,
      window_start: "2023-08-14",
      window_end: "2026-08-14",
    },
  ],
  universe_average: {
    strategy_id: W52_STRATEGY_ID,
    window: "3Y",
    window_start: "2023-08-14",
    window_end: "2026-08-14",
    universe_size: 755,
    valid_backtests: 40,
    unavailable: 715,
    average_return: 0.123,
  },
};

describe("W52ReturnBoards", () => {
  it("uses the same 3Y window for top 5, least 5, and average", () => {
    render(<W52ReturnBoards payload={payload} />);
    const periods = screen.getAllByText("Period 2023-08-14 → 2026-08-14 · last 3 years of completed sessions");
    expect(periods.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("52-Week High Breakout — Average Return")).toBeTruthy();
    expect(screen.getByTestId("w52-average-return-value").textContent).toBe("+12.3%");
    expect(screen.getByText("755")).toBeTruthy();
    expect(screen.getByText("40")).toBeTruthy();
  });

  it("recomputes boards from blotter entry dates when the period changes", () => {
    render(
      <W52ReturnBoards
        payload={{
          recommendations_final: true,
          strategy_id: W52_STRATEGY_ID,
          evaluation_date: "2026-08-20",
          summary: { total: 3 },
          recommendations: [
            { symbol: "EMIL-EQ", signal: "REJECT" },
            { symbol: "TODAY-EQ", signal: "BUY" },
            { symbol: "OLD-EQ", signal: "REJECT" },
          ],
          blotter: [
            { symbol: "EMIL-EQ", entry_date: "2026-01-10", exit_date: "2026-08-20", pnl_pct: 0.055, reason: "eod_liquidation" },
            { symbol: "TODAY-EQ", entry_date: "2026-08-20", exit_date: "2026-08-20", pnl_pct: 0.017 },
            { symbol: "OLD-EQ", entry_date: "2020-03-01", exit_date: "2020-06-01", pnl_pct: 1.2 },
          ],
        }}
      />,
    );
    fireEvent.click(screen.getAllByRole("tab", { name: "1D" })[0]);
    expect(screen.getAllByText("TODAY").length).toBeGreaterThan(0);
    expect(screen.queryByText("EMIL")).toBeNull();
    expect(screen.queryByText("OLD")).toBeNull();
    fireEvent.click(screen.getAllByRole("tab", { name: "1Y" })[0]);
    expect(screen.getAllByText("EMIL").length).toBeGreaterThan(0);
    expect(screen.getAllByText("TODAY").length).toBeGreaterThan(0);
    expect(screen.queryByText("OLD")).toBeNull();
    fireEvent.click(screen.getAllByRole("tab", { name: "18Y" })[0]);
    expect(screen.getAllByText("OLD").length).toBeGreaterThan(0);
  });

  it("switches all three sections together when a period tab is clicked", () => {
    render(<W52ReturnBoards payload={payload} />);
    fireEvent.click(screen.getAllByRole("tab", { name: "1Y" })[0]);
    expect(screen.getAllByText("Period 2025-08-14 → 2026-08-14 · last 1 year of completed sessions").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText(/Average 1-year backtest return/)).toBeTruthy();
    fireEvent.click(screen.getAllByRole("tab", { name: "18Y" })[0]);
    expect(screen.getAllByText("Period 2008-08-14 → 2026-08-14 · last 18 years of completed sessions").length).toBeGreaterThanOrEqual(3);
  });

  it("does not render a 0% average when the backend left the value unavailable", () => {
    render(
      <W52ReturnBoards
        payload={{
          ...payload,
          universe_average: { ...payload.universe_average, average_return: null, valid_backtests: 0, unavailable: 755 },
        }}
      />,
    );
    expect(screen.getByTestId("w52-average-return-value").textContent).toBe("Unavailable");
    expect(screen.queryByText("0.0%")).toBeNull();
  });
});
