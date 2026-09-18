import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BacktestPerformanceTable } from "../BacktestPerformanceTable";
import { formatScanTime } from "../StatusCards";

describe("BacktestPerformanceTable", () => {
  it("formats returns, missing values, and infinite PF", () => {
    render(
      <BacktestPerformanceTable
        title="Top 5 positive backtest returns"
        rows={[
          {
            rank: 1,
            symbol: "AAA",
            signal: "REJECT",
            return: 1.197, // +119.7% as a decimal book return
            trades: 2,
            win_rate: 1,
            max_dd: 0,
            profit_factor: null,
            profit_factor_infinite: true,
          },
          {
            rank: 2,
            symbol: "BBB",
            signal: "BUY",
            return: null,
            trades: null,
            win_rate: null,
            max_dd: null,
            profit_factor: null,
          },
        ]}
        variant="top"
      />,
    );
    expect(screen.getByText("+119.7%")).toBeTruthy();
    expect(screen.getByText("∞")).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText("AAA")).toBeTruthy();
  });

  it("displays the canonical ticker rather than the stored -EQ identity", () => {
    render(
      <BacktestPerformanceTable
        title="Top 5 positive backtest returns"
        rows={[
          {
            rank: 1,
            symbol: "AARTIDRUGS-EQ",
            signal: "BUY",
            return: 0.1,
            trades: 1,
            win_rate: 1,
            max_dd: 0,
            profit_factor: 2,
          },
        ]}
        variant="top"
      />,
    );
    expect(screen.getByText("AARTIDRUGS")).toBeTruthy();
    expect(screen.queryByText("AARTIDRUGS-EQ")).toBeNull();
  });

  it("renders negative returns for least-5", () => {
    render(
      <BacktestPerformanceTable
        title="Least 5 backtest returns"
        rows={[
          {
            rank: 1,
            symbol: "ZZZ",
            signal: "WATCH",
            return: -0.266,
            trades: 3,
            win_rate: 0.33,
            max_dd: -0.4,
            profit_factor: 0.5,
          },
        ]}
        variant="least"
      />,
    );
    expect(screen.getByText("-26.6%")).toBeTruthy();
  });
});

describe("formatScanTime", () => {
  it("does not hardcode a date and formats a real ISO timestamp", () => {
    const out = formatScanTime("2026-08-16T08:25:00.000Z");
    expect(out).toBeTruthy();
    expect(out).not.toContain("06 Aug 2026");
    expect(out).toMatch(/2026/);
  });

  it("returns null for invalid input", () => {
    expect(formatScanTime(null)).toBeNull();
    expect(formatScanTime("not-a-date")).toBeNull();
  });
});
