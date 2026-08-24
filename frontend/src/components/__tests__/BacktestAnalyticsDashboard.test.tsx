import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BacktestAnalyticsDashboard } from "../BacktestAnalyticsDashboard";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  ComposedChart: ({ children }: any) => <div>{children}</div>,
  Line: () => <div />,
  Area: () => <div />,
  Bar: () => <div />,
  Cell: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
}));

describe("BacktestAnalyticsDashboard", () => {
  it("exposes from/to date inputs alongside 1Y 3Y 5Y All", () => {
    const onCustom = vi.fn();
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "CUSTOM",
          period_start: "2024-01-15",
          period_end: "2025-06-30",
          total_return: 1,
          trade_count: 2,
        }}
        range="CUSTOM"
        startDate="2024-01-15"
        endDate="2025-06-30"
        onRangeChange={() => undefined}
        onCustomRange={onCustom}
      />,
    );
    expect(screen.getByRole("button", { name: "1Y" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "3Y" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "8Y" })).toBeTruthy();
    expect(screen.getByLabelText("Backtest start date")).toBeTruthy();
    expect(screen.getByLabelText("Backtest end date")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Backtest start date"), { target: { value: "2023-03-01" } });
    expect(onCustom).toHaveBeenCalledWith("2023-03-01", "2025-06-30");
  });

  it("populates metric cards and header configuration when a valid dashboard exists", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          period_start: "2023-08-14",
          period_end: "2026-08-14",
          total_return: 5.36,
          cagr: 4.63,
          max_drawdown: -13.51,
          win_rate: 40,
          trade_count: 3,
          sharpe_ratio: 0.8,
          profit_factor: 1.4,
          initial_capital: 100000,
          ending_capital: 105360,
        }}
        range="3Y"
        symbol="GLAXO-EQ"
        strategyName="52-Week High Breakout"
        timeframe="1D"
        onRangeChange={() => undefined}
      />,
    );
    expect(screen.getAllByText("+5.36%").length).toBeGreaterThan(0);
    expect(screen.getByText("+4.63%")).toBeTruthy();
    expect(screen.getAllByText("40.0%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1.40").length).toBeGreaterThan(0);
    expect(screen.getByText("GLAXO-EQ")).toBeTruthy();
    expect(screen.getByText("52-Week High Breakout")).toBeTruthy();
    expect(screen.getByText("1D")).toBeTruthy();
    expect(screen.queryByTestId("backtest-unavailable")).toBeNull();
  });

  it("uses stored strategy tester profit and loss counts instead of assuming from the trade list", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "ALL",
          trade_count: 1,
          trades: [{ entry_date: "2025-01-01", exit_date: "2025-02-01", pnl_percent: 10, open: false }],
          strategy_tester: {
            total_pnl: 701.4,
            max_drawdown: -12.5,
            total_trades: 6,
            profitable_trades: 3,
            losing_trades: 3,
            breakeven: 0,
            profit_factor: 1.25,
            gross_profit: 1200,
            gross_loss: -960,
            commission: 0,
            expected_payoff: 1.1,
            largest_profit: 27.25,
            largest_loss: -19.59,
            average_winning_trade: 13.84,
            average_losing_trade: -10.41,
            outlier_pnl: 0,
          },
        }}
        range="ALL"
        symbol="IIFL-EQ"
        onRangeChange={() => undefined}
      />,
    );
    expect(screen.getAllByText("3 / 6 = 50.00%").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("0 / 6 = 0.00%").length).toBeGreaterThanOrEqual(1);
  });

  it("renders TradingView Strategy Tester rupee fields from the ledger", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "1Y",
          period_start: "2025-08-21",
          period_end: "2026-08-21",
          total_return: -1.24,
          max_drawdown: -2.32,
          max_drawdown_inr: -2320,
          trade_count: 2,
          profit_factor: 0.981,
          ledger: {
            total_trades: 2,
            winning_trades: 0,
            losing_trades: 2,
            breakeven_trades: 0,
            win_rate: 0,
            net_pnl: -44.3,
            gross_profit: 0,
            gross_loss: -44.3,
            commission: 0,
            expected_payoff_inr: -22.15,
            expected_payoff: -6.17,
            largest_profit_inr: null,
            largest_loss_inr: -44.3,
            average_profit: null,
            average_loss: -6.17,
            outlier_pnl: 0,
            outlier_trades: 0,
            source: "closed_trade_ledger",
          },
        }}
        range="1Y"
        onRangeChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("strategy-tester-report")).toBeTruthy();
    expect(screen.getAllByText("Total P&L").length).toBeGreaterThan(0);
    expect(screen.getByText("Profitable trades")).toBeTruthy();
    expect(screen.getByText("Gross Profit")).toBeTruthy();
    expect(screen.getByText("Gross Loss")).toBeTruthy();
    expect(screen.getByText("Outlier P&L")).toBeTruthy();
    expect(screen.getAllByText("0 / 2 = 0.00%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2 / 2 = 100.00%").length).toBeGreaterThanOrEqual(1);
  });

  it("Trades Distribution uses the closed-trade ledger, not a second 860-trade dataset", () => {
    const junk = Array.from({ length: 860 }, (_, i) => ({
      entry_date: "2019-01-01",
      exit_date: "2019-01-02",
      pnl_percent: i % 2 === 0 ? 1 : -1,
      open: false,
    }));
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "8Y",
          period_start: "2018-08-21",
          period_end: "2026-08-21",
          trade_count: 860,
          trades: junk,
          trade_distribution: {
            total_trades: 6,
            winners: 3,
            losers: 3,
            breakevens: 0,
            open_trades: 1,
            source: "closed_trade_ledger",
          },
          ledger: {
            total_trades: 6,
            winning_trades: 3,
            losing_trades: 3,
            breakeven_trades: 0,
            source: "closed_trade_ledger",
          },
        }}
        range="8Y"
        onRangeChange={() => undefined}
      />,
    );
    const dist = screen.getByTestId("trades-distribution");
    expect(dist.textContent).toContain("6");
    expect(dist.textContent).toContain("3 trades");
    expect(dist.textContent).not.toContain("860");
    expect(screen.getAllByText("3 / 6 = 50.00%").length).toBeGreaterThanOrEqual(2);
  });

  it("prefers canonical ledger win/loss counts over client recomputation", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          period_start: "2023-08-21",
          period_end: "2026-08-21",
          trade_count: 3,
          trades: [
            { entry_date: "2026-01-01", exit_date: "2026-01-10", pnl_percent: 1.2, open: false, outcome: "winner" },
            { entry_date: "2025-01-01", exit_date: "2025-01-10", pnl_percent: -0.8, open: false, outcome: "loser" },
            { entry_date: "2024-01-01", exit_date: "2024-01-10", pnl_percent: 0, open: false, outcome: "breakeven" },
          ],
          ledger: {
            total_trades: 3,
            winning_trades: 1,
            losing_trades: 1,
            breakeven_trades: 1,
            win_rate: 33.3333,
            expected_payoff: 0.13,
            expected_payoff_inr: 1.38,
            source: "closed_trade_ledger",
          },
        }}
        range="3Y"
        onRangeChange={() => undefined}
      />,
    );
    expect(screen.getByText("Canonical closed-trade ledger: 3 closed")).toBeTruthy();
    expect(screen.getAllByText("Break-even").length).toBeGreaterThan(0);
  });

  it("displays '--' instead of 0 when metrics are unavailable", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          period_start: "2023-08-14",
          period_end: "2026-08-14",
          total_return: null,
          cagr: null,
          max_drawdown: null,
          win_rate: null,
          trade_count: null,
          sharpe_ratio: null,
          profit_factor: null,
        }}
        range="3Y"
        onRangeChange={() => undefined}
      />,
    );
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBeGreaterThan(3);
  });

  it("explains insufficient history for a requested multi-year window", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          never_selected_in_window: false,
          trade_count: 0,
          unavailable_reason: "insufficient_history",
          coverage: {
            requested_start: "2023-08-18",
            requested_end: "2026-08-18",
            actual_start: "2026-08-18",
            actual_end: "2026-08-18",
            candle_count: 1,
          },
        }}
        range="3Y"
        onRangeChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("backtest-unavailable").textContent).toMatch(/Insufficient historical data/);
    expect(screen.getByTestId("backtest-unavailable").textContent).toMatch(/2023-08-18/);
  });

  it("shows an explicit unavailable reason instead of silent placeholders only", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{ never_selected_in_window: true, trade_count: 0 }}
        range="3Y"
        onRangeChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("backtest-unavailable").textContent).toMatch(/Reason:/);
  });

  it("provides Drawdown and Benchmark view toggles in the main chart", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          period_start: "2023-08-14",
          period_end: "2026-08-14",
          total_return: 5.36,
          cagr: 4.63,
          max_drawdown: -13.51,
          win_rate: 40,
          trade_count: 3,
          equity_curve: [
            { date: "2023-08-14", label: "2023-08-14", equity: 100000 },
            { date: "2024-08-14", label: "2024-08-14", equity: 105360 },
          ],
          drawdown_curve: [
            { date: "2023-08-14", label: "2023-08-14", drawdown: 0 },
            { date: "2024-08-14", label: "2024-08-14", drawdown: -5.2 },
          ],
          benchmark_curve: [
            { date: "2023-08-14", label: "2023-08-14", close: 20000 },
            { date: "2024-08-14", label: "2024-08-14", close: 22000 },
          ],
        }}
        range="3Y"
        onRangeChange={() => undefined}
      />,
    );

    const ddBtn = screen.getByRole("button", { name: "Drawdown" });
    expect(ddBtn).toBeTruthy();

    fireEvent.click(ddBtn);
    expect(screen.getByRole("heading", { level: 3, name: "Drawdown" })).toBeTruthy();

    const benchBtn = screen.getByRole("button", { name: "Benchmark" });
    fireEvent.click(benchBtn);
    expect(screen.getByRole("heading", { level: 3, name: "Benchmark (NIFTY 500)" })).toBeTruthy();
  });

  it("renders monthly returns heatmap with missing months as '--'", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          monthly_returns: [
            { month: "2025-01", return: 0.025 },
            { month: "2025-03", return: -0.012 },
          ],
        }}
        range="3Y"
        onRangeChange={() => undefined}
      />,
    );
    expect(screen.getByText("+2.5%")).toBeTruthy();
    expect(screen.getByText("-1.2%")).toBeTruthy();
    // February 2025 is missing, should be rendered as --
    expect(screen.getAllByText("--").length).toBeGreaterThan(0);
  });

  it("filters and sorts trade log table", () => {
    const trades = [
      { entry_date: "2024-01-10", exit_date: "2024-02-10", type: "LONG", entry_price: 100, exit_price: 120, pnl_percent: 20, holding_days: 31, reason: "target" },
      { entry_date: "2024-03-01", exit_date: "2024-03-15", type: "LONG", entry_price: 120, exit_price: 110, pnl_percent: -8.33, holding_days: 14, reason: "stop_loss" },
    ];
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          trades,
          trade_count: 2,
        }}
        range="3Y"
        onRangeChange={() => undefined}
      />,
    );

    expect(screen.getByText("Detailed Trade Log")).toBeTruthy();
    expect(screen.getByText("target")).toBeTruthy();
    expect(screen.getByText("stop_loss")).toBeTruthy();

    // Filter to Winners only
    const winnersBtn = screen.getByRole("button", { name: /Winners \(1\)/ });
    fireEvent.click(winnersBtn);
    expect(screen.getByText("target")).toBeTruthy();
    expect(screen.queryByText("stop_loss")).toBeNull();

    // Filter to Losers only
    const losersBtn = screen.getByRole("button", { name: /Losers \(1\)/ });
    fireEvent.click(losersBtn);
    expect(screen.queryByText("target")).toBeNull();
    expect(screen.getByText("stop_loss")).toBeTruthy();
  });

  it("renders professional loading state with 'Running 3-year backtest...'", () => {
    render(
      <BacktestAnalyticsDashboard
        model={null}
        range="3Y"
        loading={true}
        onRangeChange={() => undefined}
      />,
    );
    expect(screen.getByTestId("backtest-loading-state")).toBeTruthy();
    expect(screen.getAllByText(/Running 3 years backtest/i).length).toBeGreaterThan(0);
  });

  it("opens configuration modal upon clicking info icon button", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          symbol: "BOSCHLTD-EQ",
          strategy_name: "52-Week High Breakout",
          initial_capital: 100000,
          coverage: { candle_count: 750, coverage_ratio: 0.99 },
        }}
        range="3Y"
        symbol="BOSCHLTD-EQ"
        onRangeChange={() => undefined}
      />,
    );

    const infoBtn = screen.getByLabelText("Backtest configuration details");
    fireEvent.click(infoBtn);

    expect(screen.getByRole("heading", { level: 3, name: "Backtest Configuration" })).toBeTruthy();
    expect(screen.getAllByText("BOSCHLTD-EQ").length).toBeGreaterThan(0);
    expect(screen.getByText("750 bars")).toBeTruthy();

    // Close modal
    const closeBtn = screen.getByLabelText("Close configuration modal");
    fireEvent.click(closeBtn);
    expect(screen.queryByText("Backtest Configuration")).toBeNull();
  });
});
