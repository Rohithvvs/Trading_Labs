import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IndicatorLeanBacktestView } from "../IndicatorLeanBacktestView";
import type { IndicatorBacktestJob, LeanBacktestResult } from "../../../api_indicator_scanner";

describe("IndicatorLeanBacktestView", () => {
  const mockResult: LeanBacktestResult = {
    jobId: "LEAN-JOB-999",
    strategyId: "17_long_term_mom",
    strategyName: "LTM Momentum 252 [SCAN]",
    engine: "LEAN",
    status: "COMPLETED",
    startDate: "2020-01-01",
    endDate: "2026-09-08",
    symbols: ["ALL_755"],
    summary: {
      initialCapital: 100000,
      finalEquity: 350000,
      netProfit: 250000,
      netProfitPct: 250.0,
      cagr: 0.235,
      sharpeRatio: 1.62,
      sortinoRatio: 2.38,
      maximumDrawdown: 22000,
      maximumDrawdownPct: 0.145,
      calmarRatio: 1.62,
      totalTrades: 30,
      winningTrades: 22,
      losingTrades: 8,
      winRate: 0.733,
      profitFactor: 2.85,
      averageTrade: 8333.33,
      averageWinningTrade: 14000.0,
      averageLosingTrade: -7250.0,
      expectancy: 1.5,
      totalCommission: 600,
      totalSlippage: 600,
      executionModel: "LEAN NextBarOpen",
      dataSource: "Trading Labs NSE Data",
      dataCoverageRatio: 1.0,
      tradingDaysCount: 1512,
    },
    trades: [
      {
        tradeId: 1,
        symbol: "TCS",
        direction: "LONG",
        entryDate: "2021-01-10",
        entryPrice: 3100.0,
        exitDate: "2022-01-15",
        exitPrice: 3850.0,
        quantity: 30,
        grossPnL: 22500.0,
        commission: 25.0,
        slippage: 25.0,
        netPnL: 22450.0,
        returnPct: 0.2419,
        holdingPeriod: 252,
        entryReason: "LTM Top Rank",
        exitReason: "Annual Rebalance",
        isOpen: false,
      },
      {
        tradeId: 2,
        symbol: "WIPRO",
        direction: "LONG",
        entryDate: "2021-01-10",
        entryPrice: 450.0,
        exitDate: "2022-01-15",
        exitPrice: 410.0,
        quantity: 200,
        grossPnL: -8000.0,
        commission: 20.0,
        slippage: 20.0,
        netPnL: -8040.0,
        returnPct: -0.0889,
        holdingPeriod: 252,
        entryReason: "LTM Top Rank",
        exitReason: "Annual Rebalance",
        isOpen: false,
      },
    ],
    equityCurve: [
      { date: "2020-01-01", equity: 100000, cash: 100000, investedCapital: 0, drawdown: 0, drawdownPct: 0 },
      { date: "2023-01-01", equity: 220000, cash: 220000, investedCapital: 0, drawdown: 0, drawdownPct: 0 },
      { date: "2026-09-08", equity: 350000, cash: 350000, investedCapital: 0, drawdown: 0, drawdownPct: 0 },
    ],
    positions: [],
    runtimeMetrics: {},
  };

  const mockRunningJob: IndicatorBacktestJob = {
    jobId: "LEAN-JOB-RUNNING",
    strategyId: "17_long_term_mom",
    strategyName: "LTM Momentum 252 [SCAN]",
    status: "RUNNING",
    progressPct: 45,
    stage: "Simulating trades (session 680 of 1512)",
    createdAt: "2026-09-08T12:00:00Z",
    request: {},
  };

  const mockFailedJob: IndicatorBacktestJob = {
    jobId: "LEAN-JOB-FAILED",
    strategyId: "17_long_term_mom",
    strategyName: "LTM Momentum 252 [SCAN]",
    status: "FAILED",
    progressPct: 10,
    stage: "Failed",
    error: "Insufficient price history for benchmark NIFTY500",
    createdAt: "2026-09-08T12:00:00Z",
    request: {},
  };

  it("renders running progress banner when backtest is active", () => {
    const onCancel = vi.fn();
    render(
      <IndicatorLeanBacktestView
        job={mockRunningJob}
        result={null}
        loading={false}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByTestId("lean-running-card")).toBeDefined();
    expect(screen.getByText("45%")).toBeDefined();
    expect(screen.getByText(/Simulating trades/)).toBeDefined();

    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("renders error card when backtest fails", () => {
    render(
      <IndicatorLeanBacktestView
        job={mockFailedJob}
        result={null}
        loading={false}
      />,
    );

    expect(screen.getByTestId("lean-error-card")).toBeDefined();
    expect(screen.getByText(/Insufficient price history/)).toBeDefined();
  });

  it("renders completed KPIs, chart, and trades table", () => {
    render(
      <IndicatorLeanBacktestView
        job={null}
        result={mockResult}
        loading={false}
      />,
    );

    expect(screen.getByTestId("lean-kpi-grid")).toBeDefined();
    expect(screen.getByTestId("lean-equity-chart")).toBeDefined();
    expect(screen.getByTestId("lean-trades-table")).toBeDefined();

    expect(screen.getByText("23.50%")).toBeDefined(); // CAGR
    expect(screen.getByText("1.62")).toBeDefined(); // Sharpe
    expect(screen.getByText("73.3%")).toBeDefined(); // Win Rate
    expect(screen.getByText("TCS")).toBeDefined();
    expect(screen.getByText("WIPRO")).toBeDefined();
  });

  it("filters trades by outcome (Winners vs Losers)", () => {
    render(
      <IndicatorLeanBacktestView
        job={null}
        result={mockResult}
        loading={false}
      />,
    );

    // Default: All 2 trades visible
    expect(screen.getByText("TCS")).toBeDefined();
    expect(screen.getByText("WIPRO")).toBeDefined();

    // Click "Wins" tab
    fireEvent.click(screen.getByText(/Wins/));
    expect(screen.getByText("TCS")).toBeDefined();
    expect(screen.queryByText("WIPRO")).toBeNull();

    // Click "Losses" tab
    fireEvent.click(screen.getByText(/Losses/));
    expect(screen.queryByText("TCS")).toBeNull();
    expect(screen.getByText("WIPRO")).toBeDefined();
  });

  it("filters trades by symbol search query", () => {
    render(
      <IndicatorLeanBacktestView
        job={null}
        result={mockResult}
        loading={false}
      />,
    );

    const searchInput = screen.getByPlaceholderText("Filter by symbol...");
    fireEvent.change(searchInput, { target: { value: "TCS" } });

    expect(screen.getByText("TCS")).toBeDefined();
    expect(screen.queryByText("WIPRO")).toBeNull();
  });
});
