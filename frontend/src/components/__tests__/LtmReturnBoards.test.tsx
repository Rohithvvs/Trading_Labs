import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LtmReturnBoards } from "../LtmReturnBoards";
import { LTM_STRATEGY_ID } from "../../utils/strategyIdentity";

const payload = {
  recommendations_final: true,
  strategy_id: LTM_STRATEGY_ID,
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
    strategy_id: LTM_STRATEGY_ID,
    window: "3Y",
    window_start: "2023-08-14",
    window_end: "2026-08-14",
    universe_size: 755,
    valid_backtests: 30,
    unavailable: 725,
    average_return: 0.013,
  },
  data_coverage: {
    requested_start: "2023-08-14",
    requested_end: "2026-08-14",
    ohlcv_start: "2025-06-18",
    ohlcv_end: "2026-08-14",
    complete_3y: false,
  },
};

describe("LtmReturnBoards", () => {
  it("shows the same 3Y universe average card as 52W", () => {
    render(<LtmReturnBoards payload={payload} />);
    expect(screen.getByText("Long-Term Buy & Hold Momentum — Average Return")).toBeTruthy();
    expect(screen.getByText("Average 3-year backtest return across all 755 universe stocks")).toBeTruthy();
    expect(screen.getAllByText("Period 2023-08-14 → 2026-08-14 · last 3 years of completed sessions").length).toBeGreaterThan(0);
    expect(screen.getByTestId("ltm-average-return-value").textContent).toBe("+1.3%");
    expect(screen.getByText("725")).toBeTruthy();
    expect(screen.getByText("2023-08-14 → 2026-08-14")).toBeTruthy();
    expect(screen.getByText(/Stock OHLCV available 2025-06-18 → 2026-08-14/)).toBeTruthy();
  });

  it("recomputes top 5 from the blotter when the period is shorter than 3Y", () => {
    render(
      <LtmReturnBoards
        payload={{
          recommendations_final: true,
          strategy_id: LTM_STRATEGY_ID,
          evaluation_date: "2026-08-14",
          summary: { total: 2 },
          recommendations: [
            { symbol: "NEW-EQ", signal: "BUY" },
            { symbol: "OLD-EQ", signal: "REJECT" },
          ],
          blotter: [
            { symbol: "NEW-EQ", entry_date: "2026-08-14", exit_date: "2026-08-14", pnl_pct: 0.08 },
            { symbol: "OLD-EQ", entry_date: "2020-01-10", exit_date: "2020-06-10", pnl_pct: 1.5 },
          ],
        }}
      />,
    );
    fireEvent.click(screen.getAllByRole("tab", { name: "18Y" })[0]);
    expect(screen.getAllByText("OLD").length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("tab", { name: "1D" })[0]);
    expect(screen.getAllByText("NEW").length).toBeGreaterThan(0);
    expect(screen.queryByText("OLD")).toBeNull();
    expect(screen.getByTestId("ltm-average-return-value").textContent).toBe("+8.0%");
  });

  it("computes the 755-stock 3Y average from the blotter when universe_average is missing", () => {
    render(
      <LtmReturnBoards
        payload={{
          recommendations_final: true,
          strategy_id: LTM_STRATEGY_ID,
          evaluation_date: "2026-08-14",
          summary: { total: 755 },
          recommendations: Array.from({ length: 755 }, (_, i) => ({ symbol: `S${i}` })),
          top5_positive: payload.top5_positive,
          least5: payload.least5,
          blotter: [
            { symbol: "S0", entry_date: "2024-01-10", exit_date: "2024-06-10", pnl_pct: 0.1 },
            { symbol: "S1", entry_date: "2025-01-10", exit_date: "2025-06-10", pnl_pct: 0.2 },
          ],
          equity_curve: [
            { date: "2025-06-18", equity: 100000 },
            { date: "2026-08-14", equity: 110000 },
          ],
        }}
      />,
    );
    expect(screen.getByText("Long-Term Buy & Hold Momentum — Average Return")).toBeTruthy();
    expect(screen.getByTestId("ltm-average-return-value").textContent).toBe("+15.0%");
    expect(screen.getByText("755")).toBeTruthy();
    expect(screen.getByText("753")).toBeTruthy();
  });

  it("does not render a 0% average when the backend left the value unavailable", () => {
    render(
      <LtmReturnBoards
        payload={{
          ...payload,
          universe_average: { ...payload.universe_average, average_return: null, valid_backtests: 0, unavailable: 755 },
        }}
      />,
    );
    expect(screen.getByTestId("ltm-average-return-value").textContent).toBe("Unavailable");
    expect(screen.queryByText("0.0%")).toBeNull();
  });
});
