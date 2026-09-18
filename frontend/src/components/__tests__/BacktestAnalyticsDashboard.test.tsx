import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BacktestAnalyticsDashboard } from "../BacktestAnalyticsDashboard";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  ComposedChart: ({ children }: any) => <div>{children}</div>,
  PieChart: ({ children }: any) => <div>{children}</div>,
  Pie: () => <div />,
  ReferenceLine: () => <div />,
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
  it("exposes from/to date inputs alongside 1Y 3Y 5Y All in the toolbar", () => {
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
    // Open date dropdown
    const dateBtn = screen.getByTitle("Change backtest date range");
    fireEvent.click(dateBtn);

    expect(screen.getByRole("button", { name: "1Y" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "3Y" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "8Y" })).toBeTruthy();
    expect(screen.getByLabelText("Backtest start date")).toBeTruthy();
    expect(screen.getByLabelText("Backtest end date")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Backtest start date"), { target: { value: "2023-03-01" } });
    expect(onCustom).toHaveBeenCalledWith("2023-03-01", "2025-06-30");
  });

  it("populates Key stats and TradingView toolbar when a valid dashboard exists", () => {
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          period_start: "2023-08-14",
          period_end: "2026-08-14",
          total_return: 5.36,
          net_pnl: 5360,
          cagr: 4.63,
          max_drawdown: -13.51,
          max_drawdown_inr: -13510,
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
    expect(screen.getByText("Key stats")).toBeTruthy();
    expect(screen.getByText("Total PnL")).toBeTruthy();
    expect(screen.getByText("Max drawdown")).toBeTruthy();
    expect(screen.getByText("Profitable trades")).toBeTruthy();
    expect(screen.getAllByText("Profit factor").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+5.36%").length).toBeGreaterThan(0);
    expect(screen.getByText("1.400")).toBeTruthy();
    expect(screen.queryByTestId("backtest-unavailable")).toBeNull();
  });

  it("does not render the 5 removed legacy sections (Trades Equity Curve, Signal Track, old Distribution, Returns Distribution, Detailed Trade Log)", () => {
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
          trades: [
            { entry_date: "2025-09-01", exit_date: "2025-09-10", type: "LONG", entry_price: 100, exit_price: 90, pnl_percent: -10, open: false },
            { entry_date: "2025-10-01", exit_date: "2025-10-15", type: "LONG", entry_price: 100, exit_price: 95, pnl_percent: -5, open: false },
          ],
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

    // 1. Trades Equity Curve & Controls
    expect(screen.queryByText("Trades Equity Curve")).toBeNull();
    expect(screen.queryByText("Cumulative strategy portfolio equity growth over time")).toBeNull();
    expect(screen.queryByText("Strategy: +0.96%")).toBeNull();
    expect(screen.queryByText("NIFTY 500 Buy & Hold")).toBeNull();

    // 2. Signal Execution Track
    expect(screen.queryByText("Signal Execution Track")).toBeNull();

    // 3. Old standalone Distribution
    expect(screen.queryByTestId("trades-distribution")).toBeNull();

    // 4. Old standalone Returns Distribution section
    expect(screen.queryByText("Frequency distribution of trade returns across performance buckets")).toBeNull();

    // 5. Old Detailed Trade Log
    expect(screen.queryByText("Detailed Trade Log")).toBeNull();
    expect(document.getElementById("bt-trade-log-section")).toBeNull();
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
    expect(dashes.length).toBeGreaterThan(1);
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

  it("renders professional loading state when loading is true", () => {
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

  it("opens configuration modal upon clicking info/config icon button", () => {
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

  it("renders exact final page structure: TradingView Overview -> Performance Analysis -> Trades Analysis", () => {
    const trades = [
      { entry_date: "2024-01-10", exit_date: "2024-02-10", type: "LONG", entry_price: 100, exit_price: 120, pnl_percent: 20, net_pnl: 2000, holding_days: 31, open: false },
      { entry_date: "2024-03-01", exit_date: "2024-03-15", type: "LONG", entry_price: 120, exit_price: 110, pnl_percent: -8.33, net_pnl: -1000, holding_days: 14, open: false },
    ];
    render(
      <BacktestAnalyticsDashboard
        model={{
          window: "3Y",
          trades,
          trade_count: 2,
          initial_capital: 100000,
          total_return: 10,
          net_pnl: 1000,
          max_drawdown: -5,
          ledger: {
            total_trades: 2,
            winning_trades: 1,
            losing_trades: 1,
            breakeven_trades: 0,
            win_rate: 50.0,
            expected_payoff_inr: 500.0,
            expected_payoff: 5.835,
            largest_profit_inr: 2000.0,
            largest_loss_inr: -1000.0,
            average_profit: 20.0,
            average_loss: -8.33,
            outlier_pnl: 0,
            outlier_trades: 0,
          },
        }}
        range="3Y"
        onRangeChange={() => undefined}
      />,
    );

    // Verify presence of all three major components
    expect(screen.getByTestId("tv-backtest-overview")).toBeTruthy();
    expect(screen.getByTestId("performance-analysis-section")).toBeTruthy();
    expect(screen.getByText("Performance analysis")).toBeTruthy();
    expect(screen.getByTestId("trades-analysis-section")).toBeTruthy();
    expect(screen.getByText("Trades analysis")).toBeTruthy();

    // Verify DOM structure order: TradingView Overview -> Performance Analysis -> Trades Analysis
    const tvSection = screen.getByTestId("tv-backtest-overview");
    const paSection = document.getElementById("bt-performance-analysis-section");
    const taSection = document.getElementById("bt-trades-analysis-section");
    expect(tvSection).toBeTruthy();
    expect(paSection).toBeTruthy();
    expect(taSection).toBeTruthy();

    // tvSection precedes paSection
    expect(tvSection.compareDocumentPosition(paSection!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // paSection precedes taSection
    expect(paSection!.compareDocumentPosition(taSection!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Verify Performance Analysis tabs remain intact
    const periodicalTab = screen.getByRole("tab", { name: "Periodical" });
    fireEvent.click(periodicalTab);
    expect(screen.getByTestId("performance-periodical-tab")).toBeTruthy();

    // Verify Trades Analysis tabs remain intact (including new Distribution tab)
    const distributionTab = screen.getByRole("tab", { name: "Distribution" });
    fireEvent.click(distributionTab);
    expect(screen.getByTestId("distribution-tab-content")).toBeTruthy();

    const streaksTab = screen.getByRole("tab", { name: "Streaks" });
    fireEvent.click(streaksTab);
    expect(screen.getByTestId("streaks-tab-content")).toBeTruthy();

    const detailsTab = screen.getByRole("tab", { name: "Trades analysis details" });
    fireEvent.click(detailsTab);
    expect(screen.getByTestId("trades-analysis-details-tab-content")).toBeTruthy();
  });
});


