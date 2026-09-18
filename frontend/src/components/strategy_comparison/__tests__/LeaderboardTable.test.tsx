import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ComparisonPayload } from "../../../api_strategy_comparison";
import { ComparisonLeaderboard } from "../LeaderboardTable";

const comparison = {
  slots: [
    {
      slot_id: "s0",
      strategy_name: "Scan Strategy",
      source: "strategy_tester",
      metrics: {
        win_rate: 40,
        total_return_pct: 1.5,
        total_trades: 2,
        profit_factor: null,
        average_trade: 1.5,
        average_trade_unit: "pct",
        cagr: null,
        max_drawdown_pct: null,
        max_drawdown: null,
        calmar_ratio: null,
        avg_cash: null,
        avg_exposure_pct: null,
        best_trade: { symbol: "RELIANCE", return_pct: 12 },
        worst_trade: { symbol: "TCS", return_pct: -6 },
      },
      config: {},
      equity_curve: [],
    },
    {
      slot_id: "s1",
      strategy_name: "LEAN Strategy",
      source: "lean",
      metrics: {
        win_rate: 55.25,
        total_return_pct: 12.4,
        total_trades: 18,
        profit_factor: 1.4,
        average_trade: 0.82,
        average_trade_unit: "pct",
        cagr: 8.1,
        max_drawdown_pct: 10.5,
        max_drawdown: null,
        calmar_ratio: 0.7714,
        avg_cash: 80000,
        avg_exposure_pct: 22.5,
        best_trade: { symbol: "INFY", return_pct: 18.2 },
        worst_trade: { symbol: "HDFCBANK", return_pct: -9.1 },
      },
      config: {},
      equity_curve: [],
    },
  ],
  radar: {
    axes: [],
    series: [
      { slot_id: "s0", name: "Scan Strategy", values: { win_rate: 40, total_return_pct: 20 }, raw: {} },
      { slot_id: "s1", name: "LEAN Strategy", values: { win_rate: 70, total_return_pct: 90 }, raw: {} },
    ],
    note: "",
  },
} as unknown as ComparisonPayload;

describe("ComparisonLeaderboard table", () => {
  it("renders ranked rows from real comparison metrics", () => {
    render(<ComparisonLeaderboard comparison={comparison} highlight={false} />);

    const table = screen.getByTestId("sc-leaderboard");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("LEAN Strategy");
    expect(screen.getByTestId("sc-lb-row-s1").querySelector(".sc-lb-rank")?.textContent).toBe("1");
    expect(screen.getByTestId("sc-lb-row-s0").querySelector(".sc-lb-rank")?.textContent).toBe("2");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("A");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("55.25%");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("1.40");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("8.10%");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("12.40%");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("10.50%");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("0.77");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("₹80,000");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("22.5%");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("INFY +18.20%");
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("HDFCBANK -9.10%");
    expect(screen.getByTestId("sc-lb-row-s0").textContent).toMatch(/—/);
  });

  it("highlights stronger metric cells without renaming values", () => {
    const { container } = render(<ComparisonLeaderboard comparison={comparison} highlight />);
    expect(container.querySelectorAll(".sc-cell--hi").length).toBeGreaterThan(0);
    expect(screen.getByTestId("sc-lb-row-s1").textContent).toContain("12.40%");
    expect(screen.queryByText(/best strategy/i)).toBeNull();
  });
});
