import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  TradingViewBacktestOverview,
  TvToolbar,
  TvKeyStats,
  TvPerformanceChart,
  TvListOfTrades,
} from "../TradingViewBacktest";
import type { DashboardTrade } from "../BacktestAnalyticsDashboard";

// Mock Recharts for test environment
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  ComposedChart: ({ children }: any) => <div data-testid="composed-chart">{children}</div>,
  Area: () => <div data-testid="chart-area" />,
  Line: () => <div data-testid="chart-line" />,
  Bar: () => <div data-testid="chart-bar" />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  ReferenceLine: () => <div />,
}));

describe("TradingView Backtest Overview Components", () => {
  const sampleTrades: DashboardTrade[] = [
    {
      trade_id: "T1",
      type: "LONG",
      entry_date: "2026-08-21",
      exit_date: "2026-08-24",
      entry_price: 2175.0,
      exit_price: 2290.0,
      pnl_percent: 5.29,
      net_pnl: 115.0,
      holding_days: 3,
      reason: "target",
      open: false,
    },
    {
      trade_id: "T2",
      type: "LONG",
      entry_date: "2026-08-19",
      exit_date: "2026-08-20",
      entry_price: 1929.2,
      exit_price: 1990.0,
      pnl_percent: 3.15,
      net_pnl: 60.8,
      holding_days: 1,
      reason: "target",
      open: false,
    },
    {
      trade_id: "T3",
      type: "SHORT",
      entry_date: "2026-08-11",
      exit_date: "2026-08-12",
      entry_price: 1848.1,
      exit_price: 1844.4,
      pnl_percent: -0.2,
      net_pnl: -3.7,
      holding_days: 1,
      reason: "stop_loss",
      open: false,
    },
  ];

  describe("TvToolbar", () => {
    it("renders view toggle, date range, capital, detailization, and script execution", () => {
      const onViewModeChange = vi.fn();
      render(
        <TvToolbar
          viewMode="chart"
          onViewModeChange={onViewModeChange}
          startDate="2020-06-23"
          endDate="2026-08-24"
          initialCapital={100000}
          detailization="default"
          onDetailizationChange={() => undefined}
          scriptStatus="completed"
          tradeCount={3}
        />,
      );

      expect(screen.getByTestId("tv-toolbar")).toBeTruthy();
      expect(screen.getByTestId("tv-view-chart-btn")).toBeTruthy();
      expect(screen.getByTestId("tv-view-table-btn")).toBeTruthy();

      // Click table view button
      fireEvent.click(screen.getByTestId("tv-view-table-btn"));
      expect(onViewModeChange).toHaveBeenCalledWith("table");

      // Verify date range text and badges
      expect(screen.getByText(/Jun 23, 2020 — Aug 24, 2026/)).toBeTruthy();
      expect(screen.getByText("DEEP")).toBeTruthy();
      expect(screen.getByText(/1,00,000/)).toBeTruthy();
      expect(screen.getByText("Default detailization")).toBeTruthy();
      expect(screen.getByText("Script execution")).toBeTruthy();
    });
  });

  describe("TvKeyStats", () => {
    it("renders all 4 primary metrics with proper formatting", () => {
      render(
        <TvKeyStats
          stats={{
            totalPnlInr: 1278.2,
            totalPnlPct: 0.13,
            maxDrawdownInr: 627.4,
            maxDrawdownPct: 0.06,
            winRatePct: 45.77,
            winCount: 1352,
            totalTrades: 2954,
            profitFactor: 1.186,
            profitFactorInfinite: false,
          }}
          currency="INR"
        />,
      );

      expect(screen.getByText("Key stats")).toBeTruthy();
      expect(screen.getByText("Total PnL")).toBeTruthy();
      expect(screen.getByText("+1,278.20")).toBeTruthy();
      expect(screen.getByText("+0.13%")).toBeTruthy();

      expect(screen.getByText("Max drawdown")).toBeTruthy();
      expect(screen.getByText("627.40")).toBeTruthy();
      expect(screen.getByText("0.06%")).toBeTruthy();

      expect(screen.getByText("Profitable trades")).toBeTruthy();
      expect(screen.getByText("45.77%")).toBeTruthy();
      expect(screen.getByText("1352/2954")).toBeTruthy();

      expect(screen.getByText("Profit factor")).toBeTruthy();
      expect(screen.getByText("1.186")).toBeTruthy();
    });

    it("handles infinite profit factor safely", () => {
      render(
        <TvKeyStats
          stats={{
            totalPnlInr: 5000,
            totalPnlPct: 5.0,
            maxDrawdownInr: 0,
            maxDrawdownPct: 0,
            winRatePct: 100,
            winCount: 5,
            totalTrades: 5,
            profitFactor: null,
            profitFactorInfinite: true,
          }}
        />,
      );
      expect(screen.getByText("∞")).toBeTruthy();
    });
  });

  describe("TvPerformanceChart", () => {
    it("renders layer controls, header actions, and chart container", () => {
      const points = [
        {
          date: "2024-01-01",
          label: "2024-01-01",
          cumulativePnl: 0,
          cumulativePnlPct: 0,
          buyAndHoldPnl: 0,
          buyAndHoldPct: 0,
          drawdownInr: 0,
          drawdownPct: 0,
          runUpInr: 0,
          runUpPct: 0,
          isWinningInterval: true,
        },
        {
          date: "2026-08-24",
          label: "2026-08-24",
          cumulativePnl: 1278.2,
          cumulativePnlPct: 1.28,
          buyAndHoldPnl: 500,
          buyAndHoldPct: 0.5,
          drawdownInr: 100,
          drawdownPct: 0.1,
          runUpInr: 1278.2,
          runUpPct: 1.28,
          isWinningInterval: true,
        },
      ];

      render(
        <TvPerformanceChart
          points={points}
          currency="INR"
        />,
      );

      expect(screen.getByTestId("tv-performance-section")).toBeTruthy();
      expect(screen.getByText("Performance")).toBeTruthy();
      expect(screen.getByText("Cumulative PnL")).toBeTruthy();
      expect(screen.getByText("Buy and hold")).toBeTruthy();
      expect(screen.getByText("Trades excursions")).toBeTruthy();
      expect(screen.getByText("Run-ups and drawdowns")).toBeTruthy();

      // Toggle Buy and Hold layer
      const buyHoldBtn = screen.getByRole("button", { name: /Buy and hold/i });
      fireEvent.click(buyHoldBtn);
      expect(screen.getByTestId("composed-chart")).toBeTruthy();
    });
  });

  describe("TvListOfTrades", () => {
    it("renders 2-subrow trades table with sorting, filters, pagination, and columns", () => {
      render(
        <TvListOfTrades
          trades={sampleTrades}
          initialCapital={100000}
          currency="INR"
          symbol="RELIANCE"
        />,
      );

      expect(screen.getByTestId("tv-list-of-trades")).toBeTruthy();
      expect(screen.getByText("List of trades")).toBeTruthy();

      // Verify table headers
      expect(screen.getByText(/Trade number/)).toBeTruthy();
      expect(screen.getByText("Type")).toBeTruthy();
      expect(screen.getByText(/Date and time/)).toBeTruthy();
      expect(screen.getByText("Price")).toBeTruthy();
      expect(screen.getByText("Size")).toBeTruthy();
      expect(screen.getByText(/Net PnL/)).toBeTruthy();
      expect(screen.getByText(/Return/)).toBeTruthy();

      // Verify trade items exist in table
      const tradeNums = Array.from(document.querySelectorAll(".tv-trade-num")).map((el) => el.textContent);
      expect(tradeNums).toContain("3");
      expect(tradeNums).toContain("2");
      expect(tradeNums).toContain("1");

      // Verify Exit & Entry subrows exist
      expect(screen.getAllByText("Exit").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Entry").length).toBeGreaterThanOrEqual(1);

      // Verify prices and returns
      expect(screen.getByText("2,290.0")).toBeTruthy();
      expect(screen.getByText("+115.00")).toBeTruthy();
      expect(screen.getByText("+5.29%")).toBeTruthy();

      // Filter to Winners
      const winFilterBtn = screen.getByRole("button", { name: /Winners \(2\)/ });
      fireEvent.click(winFilterBtn);
      expect(screen.getByText("+115.00")).toBeTruthy();
      expect(screen.queryByText("-3.70")).toBeNull();

      // Filter to Losers
      const lossFilterBtn = screen.getByRole("button", { name: /Losers \(1\)/ });
      fireEvent.click(lossFilterBtn);
      expect(screen.getByText("-3.70")).toBeTruthy();
      expect(screen.queryByText("+115.00")).toBeNull();
    });
  });

  describe("TradingViewBacktestOverview Integration", () => {
    it("switches smoothly between Chart view and Table view without reloading", () => {
      const model = {
        window: "3Y",
        period_start: "2023-08-24",
        period_end: "2026-08-24",
        total_return: 13.72,
        initial_capital: 100000,
        ending_capital: 113716.09,
        net_pnl: 13716.09,
        max_drawdown: 3.66,
        max_drawdown_inr: 3826.34,
        win_rate: 66.67,
        trade_count: 3,
        profit_factor: 6.82,
        trades: sampleTrades,
        equity_curve: [
          { date: "2023-08-24", label: "2023-08-24", equity: 100000 },
          { date: "2026-08-24", label: "2026-08-24", equity: 113716.09 },
        ],
      };

      render(
        <TradingViewBacktestOverview
          model={model}
          range="3Y"
          onRangeChange={() => undefined}
          symbol="TCS"
          strategyName="52-Week High Breakout"
        />,
      );

      // Default view is Chart view
      expect(screen.getByTestId("tv-chart-view-stack")).toBeTruthy();
      expect(screen.getByText("Key stats")).toBeTruthy();
      expect(screen.getByText("Performance")).toBeTruthy();

      // Click Table view
      fireEvent.click(screen.getByTestId("tv-view-table-btn"));
      expect(screen.queryByTestId("tv-chart-view-stack")).toBeNull();
      expect(screen.getByTestId("tv-table-view-stack")).toBeTruthy();
      expect(screen.getByText("List of trades")).toBeTruthy();

      // Click Chart view back
      fireEvent.click(screen.getByTestId("tv-view-chart-btn"));
      expect(screen.getByTestId("tv-chart-view-stack")).toBeTruthy();
      expect(screen.queryByTestId("tv-table-view-stack")).toBeNull();
    });
  });
});
